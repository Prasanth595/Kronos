"""Portfolio walk-forward validation with an expanding-window train/test holdout.

Page 11 upgrades the smoke runner into a real *out-of-sample* validation:

* Timestamps are split into contiguous, time-ordered **segments**.
* Fold ``N`` *trains/fits* on the expanding window of segments ``0..N`` and is
  *evaluated* on the **strictly later, disjoint** segment ``N+1``.
* The deterministic stand-in policy has nothing to fit, but the split mechanics
  and the eval-on-held-out-later-segment are real, so a trained policy can slot
  into ``_fit_policy`` later without touching the holdout machinery.

The fold report carries each fold's train range, test range, and the five
baselines + policy metrics (return, MDD, turnover, trade count, cost) computed
on the **test** segment, with ``cost_bps`` kept explicit.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .portfolio_env import ACTION_HOLD, PortfolioEnv, PortfolioEnvConfig, synthetic_candidates
from .symbol_norm import read_candidates_csv


DEFAULT_PORTFOLIO_WALK_FORWARD_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_portfolio_walk_forward"
# "rl_baseline" is the deterministic RL stand-in (no trained model yet).
# "cost_aware" is the Page 17 cost-aware policy: parameters (rank_score
# threshold + min-hold) are *fit on the TRAIN segment* and frozen for the
# disjoint, strictly-later TEST eval (see ``_fit_cost_aware_policy``).
DEFAULT_BASELINES = (
    "no_trade",
    "equal_weight_candidate",
    "buy_and_hold",
    "rule_baseline",
    "rl_baseline",
    "cost_aware",
)

# P0-2 — trained/learned baseline keys.  These are NOT in DEFAULT_BASELINES (the
# deterministic stand-ins) because they require an out-of-band fit/model handoff
# that ``_fit_policy`` performs via ``TRAINED_POLICY_FACTORIES`` (below).  Keeping
# them in a separate set keeps the diff small AND lets ``_parse_baselines`` accept
# them WITHOUT relaxing the strict DEFAULT_BASELINES membership check that guards
# typos.  ``supervised_ranker`` (§7a) is a built-in factory; ``trained_ppo`` is
# registered at runtime by the trainer once a model is loaded.
TRAINED_BASELINES = (
    "trained_ppo",
    "supervised_ranker",
)

# Model-handoff seam (P0-2(b)): a module-level registry the runner consults in
# ``_fit_policy`` BEFORE the ``del train_frame, config, fold_index`` line, so a
# trained model (or a TRAIN-fit ranker) can be handed to the holdout machinery
# without changing ``_fit_policy``'s signature.  Each factory receives the TRAIN
# segment + config + fold_index and returns a ``PolicyFn`` evaluated on the
# disjoint, strictly-later TEST segment.
TrainedPolicyFactory = Callable[..., "PolicyFn"]
TRAINED_POLICY_FACTORIES: Dict[str, "TrainedPolicyFactory"] = {}


def register_trained_policy_factory(key: str, factory: "TrainedPolicyFactory") -> None:
    """Register a trained-policy factory under ``key`` for the ``_fit_policy`` seam.

    The factory is called as ``factory(train_frame=..., config=..., fold_index=...)``
    and must return a ``PolicyFn``.  ``trained_ppo`` (SB3 model handoff) and any
    ad-hoc trained baseline register here; ``supervised_ranker`` is built in.
    """

    if not isinstance(key, str) or not key:
        raise ValueError("trained policy factory key must be a non-empty string")
    TRAINED_POLICY_FACTORIES[key] = factory


def unregister_trained_policy_factory(key: str) -> None:
    """Remove a registered trained-policy factory (no error if absent)."""

    TRAINED_POLICY_FACTORIES.pop(key, None)

# Bounded TRAIN tuning grid for the cost-aware policy (no open-ended search).
# ``score_quantile``: only buy a candidate whose rank_score is at/above this
# quantile of the TRAIN rank_score distribution (higher ⇒ more selective).
# ``min_hold_steps``: suppress churn by forbidding a sell for N steps post-buy.
COST_AWARE_SCORE_QUANTILES: Tuple[float, ...] = (0.0, 0.5, 0.75, 0.9)
COST_AWARE_MIN_HOLD_STEPS: Tuple[int, ...] = (1, 2, 4, 8)
# Turnover-penalty λ used *only* while scoring TRAIN candidates so the tuner
# prefers low-churn params; the held-out TEST eval reports the unshaped costed
# return (no λ) so the comparison table stays honest vs the other baselines.
COST_AWARE_TRAIN_LAMBDA: float = 1.0


@dataclass(frozen=True)
class PortfolioWalkForwardConfig:
    candidate_path: Optional[str] = None
    output_dir: str = str(DEFAULT_PORTFOLIO_WALK_FORWARD_OUTPUT_DIR)
    n_folds: int = 2
    baselines: Tuple[str, ...] = DEFAULT_BASELINES
    top_k_candidates: int = 3
    max_positions: int = 2
    max_steps_per_fold: int = 24
    seed: int = 100
    initial_cash: float = 1_000_000.0
    cost_bps: float = 25.0
    slippage_bps: float = 0.0
    # Turnover-cost penalty λ threaded into the env reward (Page 17).  Default
    # ``0.0`` ⇒ legacy NAV-change reward.  The cost-aware tuner overrides this
    # to ``COST_AWARE_TRAIN_LAMBDA`` *for TRAIN scoring only*; the held-out TEST
    # eval always runs with λ unchanged from this config (kept 0 for honesty).
    turnover_penalty_lambda: float = 0.0
    write_artifacts: bool = True
    # Mandatory shuffle/permutation sanity check (plan §7).  When ``shuffle_signal``
    # is True the loaded candidate frame has its ``rank_score`` + ``feature_*``
    # columns permuted within each timestamp (selection signal destroyed, fills
    # untouched) before folds are built — used to prove a real edge vanishes under
    # shuffle.  ``shuffle_seed`` makes the permutation deterministic/auditable.
    shuffle_signal: bool = False
    shuffle_seed: int = 0


@dataclass(frozen=True)
class FoldSplit:
    """One expanding-window fold: train on ``0..N``, evaluate on ``N+1``."""

    fold_index: int
    train_frame: pd.DataFrame
    test_frame: pd.DataFrame
    train_start: str
    train_end: str
    test_start: str
    test_end: str


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_candidates(path: Optional[str]) -> pd.DataFrame:
    if path:
        frame = read_candidates_csv(path)
    else:
        frame = synthetic_candidates()
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    return frame.dropna(subset=["timestamp"]).sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def shuffle_candidate_signal(frame: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Destroy the per-timestamp *selection* signal while keeping accounting identical.

    Mandatory shuffle/permutation sanity check (plan §7, V8/V8b).  Within EACH
    timestamp group, the values of ``rank_score`` AND every ``feature_*`` column
    are permuted across that timestamp's rows.  Crucially this OVERWRITES the
    ``rank_score`` values (not merely the row order): :meth:`PortfolioEnv._current_candidates`
    re-sorts by ``rank_score`` before ``head(top_k)``, so reordering rows alone is
    a no-op — only overwriting the score values changes which candidates the env
    selects.  ``price`` / ``fill_price`` / ``symbol`` / ``timestamp`` / ``fillable``
    are left untouched so the realised fills and cost accounting are byte-for-byte
    identical to the real run; ONLY the selection signal is scrambled.

    Each column is permuted *independently* per timestamp (its own draw from the
    shared deterministic ``numpy`` generator), so no row retains its original
    feature/score vector — the joint signal is fully destroyed.  Singleton
    timestamps (one row) are unchanged by construction (a permutation of one
    element is the identity); the shuffle therefore only perturbs timestamps with
    >=2 candidates, which is exactly where selection happens.

    Returns a NEW frame (input is not mutated).
    """

    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
    signal_cols = [c for c in work.columns if str(c).startswith("feature_")]
    if "rank_score" in work.columns:
        signal_cols.insert(0, "rank_score")
    if not signal_cols:
        return work.reset_index(drop=True)

    rng = np.random.default_rng(int(seed))
    # Permute within each timestamp group, in a deterministic timestamp order so a
    # fixed seed yields a reproducible shuffle (audit + V8b unit test).
    for _ts, idx in sorted(
        work.groupby("timestamp").groups.items(), key=lambda kv: kv[0]
    ):
        positions = list(idx)
        if len(positions) < 2:
            continue
        for col in signal_cols:
            values = work.loc[positions, col].to_numpy()
            work.loc[positions, col] = values[rng.permutation(len(positions))]
    return work.reset_index(drop=True)


def _segment_timestamps(timestamps: Sequence[pd.Timestamp], n_segments: int) -> List[List[pd.Timestamp]]:
    """Split sorted unique timestamps into contiguous, time-ordered segments.

    The split is deterministic: ``np.array_split`` over the sorted timestamps
    yields the same boundaries for the same input.  Empty buckets are dropped.
    """

    if not timestamps:
        raise ValueError("No timestamps available for portfolio walk-forward")
    n_segments = min(max(1, int(n_segments)), len(timestamps))
    buckets = np.array_split(np.asarray(timestamps, dtype=object), n_segments)
    segments: List[List[pd.Timestamp]] = []
    for bucket in buckets:
        block = [pd.Timestamp(ts) for ts in bucket]
        if block:
            segments.append(block)
    return segments


def build_expanding_window_folds(frame: pd.DataFrame, n_folds: int) -> List[FoldSplit]:
    """Build expanding-window folds with a disjoint, strictly-later test segment.

    ``n_folds`` is the number of *evaluated* folds.  To produce ``n_folds`` test
    segments we need ``n_folds + 1`` time segments: fold ``N`` trains on segments
    ``0..N`` and evaluates on segment ``N+1``.  When there are too few distinct
    timestamps to honour the request, the fold count is reduced (and a fold needs
    at least two segments to exist at all).
    """

    timestamps = sorted(pd.Timestamp(ts) for ts in frame["timestamp"].dropna().unique())
    if not timestamps:
        raise ValueError("No timestamps available for portfolio walk-forward")

    requested = max(1, int(n_folds))
    n_segments = min(requested + 1, len(timestamps))
    segments = _segment_timestamps(timestamps, n_segments)
    if len(segments) < 2:
        raise ValueError(
            "Walk-forward holdout requires at least two time segments "
            f"(got {len(segments)} from {len(timestamps)} distinct timestamps); "
            "supply more candidate timestamps for a meaningful train/test split."
        )

    folds: List[FoldSplit] = []
    for fold_index in range(len(segments) - 1):
        train_ts = [ts for seg in segments[: fold_index + 1] for ts in seg]
        test_ts = segments[fold_index + 1]
        train_frame = frame[frame["timestamp"].isin(train_ts)].copy()
        test_frame = frame[frame["timestamp"].isin(test_ts)].copy()
        folds.append(
            FoldSplit(
                fold_index=fold_index,
                train_frame=train_frame,
                test_frame=test_frame,
                train_start=train_ts[0].isoformat(),
                train_end=train_ts[-1].isoformat(),
                test_start=test_ts[0].isoformat(),
                test_end=test_ts[-1].isoformat(),
            )
        )
    return folds


def _make_env(candidates: pd.DataFrame, config: PortfolioWalkForwardConfig, fold_index: int) -> PortfolioEnv:
    return PortfolioEnv(
        PortfolioEnvConfig(
            top_k_candidates=config.top_k_candidates,
            max_positions=config.max_positions,
            initial_cash=config.initial_cash,
            cost_bps=config.cost_bps,
            slippage_bps=config.slippage_bps,
            turnover_penalty_lambda=config.turnover_penalty_lambda,
            seed=config.seed + fold_index,
        ),
        candidates=candidates,
    )


# A policy maps (env, info) -> discrete action.  The deterministic stand-in is
# closed over the policy name; a trained model would expose the same signature.
PolicyFn = Callable[[PortfolioEnv, Mapping[str, Any]], int]


def _action_for_policy(policy: str, env: PortfolioEnv, info: Mapping[str, Any]) -> int:
    mask = list(info["action_mask"])
    sell_offset = 1 + env.config.top_k_candidates
    if policy == "no_trade":
        return ACTION_HOLD
    if policy == "buy_and_hold":
        for action in range(1, sell_offset):
            if mask[action]:
                return action
        return ACTION_HOLD
    if policy in {"rule_baseline", "rl_baseline"} and int(info["current_step"]) % 4 == 3:
        for action in range(sell_offset, len(mask)):
            if mask[action]:
                return action
    for action in range(1, sell_offset):
        if mask[action]:
            return action
    for action in range(sell_offset, len(mask)):
        if policy in {"rule_baseline", "rl_baseline"} and mask[action]:
            return action
    return ACTION_HOLD


class _CostAwarePolicy:
    """Selective, low-churn policy with TRAIN-fit, frozen parameters.

    The policy only buys a candidate whose ``rank_score`` is at/above a fitted
    ``score_threshold`` (an absolute score derived from a TRAIN-segment quantile)
    and refuses to sell a holding until it has been held ``min_hold_steps`` bars,
    directly attacking the turnover-cost loss Page 14 identified.  Both params
    are *fit on the TRAIN segment only* (:func:`_fit_cost_aware_policy`) and
    frozen here, so applying the callable to the disjoint, strictly-later TEST
    segment introduces no leakage.  The callable is stateful across a single
    episode (it tracks per-symbol entry steps); it is re-instantiated per eval.
    """

    def __init__(self, score_threshold: float, min_hold_steps: int) -> None:
        self.score_threshold = float(score_threshold)
        self.min_hold_steps = int(min_hold_steps)
        self._entry_step: Dict[str, int] = {}

    def __call__(self, env: PortfolioEnv, info: Mapping[str, Any]) -> int:
        mask = list(info["action_mask"])
        step = int(info["current_step"])
        sell_offset = 1 + env.config.top_k_candidates
        candidates = env._current_candidates()  # noqa: SLF001 - read-only view of current bar
        held = set(env.account.positions)
        # Forget entry steps for symbols no longer held (closed elsewhere).
        for symbol in list(self._entry_step):
            if symbol not in held:
                self._entry_step.pop(symbol, None)

        # 1) Sell only holdings that have satisfied the min-hold (anti-churn).
        holdings = sorted(held)
        for slot in range(min(len(holdings), env.config.max_positions)):
            action = sell_offset + slot
            if not mask[action]:
                continue
            symbol = holdings[slot]
            entered = self._entry_step.get(symbol, step)
            if step - entered >= self.min_hold_steps:
                self._entry_step.pop(symbol, None)
                return action

        # 2) Buy the best fillable candidate whose rank_score clears the
        #    fitted threshold (selective entry suppresses low-conviction churn).
        for slot in range(1, sell_offset):
            if not mask[slot]:
                continue
            cand_idx = slot - 1
            if cand_idx >= len(candidates):
                continue
            row = candidates.iloc[cand_idx]
            if float(row["rank_score"]) >= self.score_threshold:
                self._entry_step[str(row["symbol"])] = step
                return slot
        return ACTION_HOLD


def _score_quantile_threshold(train_frame: pd.DataFrame, quantile: float) -> float:
    scores = pd.to_numeric(train_frame.get("rank_score"), errors="coerce").dropna()
    if scores.empty:
        return float("-inf")  # no scores ⇒ threshold never blocks
    return float(scores.quantile(float(quantile)))


def _score_train_params(
    *,
    score_threshold: float,
    min_hold_steps: int,
    train_frame: pd.DataFrame,
    config: PortfolioWalkForwardConfig,
    fold_index: int,
) -> float:
    """Cost-adjusted TRAIN return for one (threshold, min_hold) candidate.

    Runs the cost-aware policy on the TRAIN segment with a turnover-penalty λ so
    the tuner prefers params that trade only when worth the cost.  Returns the
    final-NAV return percent (higher is better); used purely to *rank* params.
    """

    train_config = replace(
        config,
        turnover_penalty_lambda=COST_AWARE_TRAIN_LAMBDA,
        write_artifacts=False,
    )
    env = _make_env(train_frame, train_config, fold_index)
    _, info = env.reset(seed=config.seed + fold_index)
    policy = _CostAwarePolicy(score_threshold, min_hold_steps)
    terminated = False
    truncated = False
    steps = 0
    while not (terminated or truncated):
        if config.max_steps_per_fold and steps >= int(config.max_steps_per_fold):
            break
        action = policy(env, info)
        _, _, terminated, truncated, info = env.step(action)
        steps += 1
    final_nav = float(info["nav"])
    return (final_nav / float(config.initial_cash) - 1.0) * 100.0


def _fit_cost_aware_policy(
    train_frame: pd.DataFrame,
    config: PortfolioWalkForwardConfig,
    fold_index: int,
) -> PolicyFn:
    """Grid-search the cost-aware policy params on the TRAIN segment only.

    Iterates the bounded ``(score_quantile × min_hold)`` grid, scoring each on
    the TRAIN segment with a turnover penalty, and freezes the best-scoring
    params.  The returned callable applies those frozen params; the surrounding
    holdout machinery then evaluates it on the disjoint, strictly-later TEST
    segment with *no* further fitting (no leakage).  Ties break deterministically
    toward the more selective / longer-hold (lower-churn) configuration.
    """

    best_key: Optional[Tuple[float, int, int]] = None
    best_threshold = float("-inf")
    best_min_hold = COST_AWARE_MIN_HOLD_STEPS[0]
    for quantile in COST_AWARE_SCORE_QUANTILES:
        threshold = _score_quantile_threshold(train_frame, quantile)
        for min_hold in COST_AWARE_MIN_HOLD_STEPS:
            train_return = _score_train_params(
                score_threshold=threshold,
                min_hold_steps=min_hold,
                train_frame=train_frame,
                config=config,
                fold_index=fold_index,
            )
            # Maximise TRAIN cost-adjusted return; on ties prefer higher
            # quantile then longer hold (both reduce turnover) for determinism.
            key = (round(train_return, 10), float(quantile), int(min_hold))
            if best_key is None or key > best_key:
                best_key = key
                best_threshold = threshold
                best_min_hold = min_hold

    frozen = _CostAwarePolicy(best_threshold, best_min_hold)

    def _policy(env: PortfolioEnv, info: Mapping[str, Any]) -> int:
        return frozen(env, info)

    # Re-instantiate per eval episode so per-symbol entry-step state is fresh
    # (the holdout eval runs one episode; a fresh policy avoids stale state).
    _policy.frozen_params = {  # type: ignore[attr-defined]
        "score_threshold": float(best_threshold),
        "min_hold_steps": int(best_min_hold),
    }
    return _policy


def _causal_feature_columns(frame: pd.DataFrame) -> List[str]:
    """The same causal feature columns the env consumes: ``rank_score`` + ``feature_*``.

    Mirrors ``PortfolioEnv._infer_feature_columns`` so the supervised ranker is
    fit on the EXACT features the RL policy sees (no leaky strawman).
    """

    features = [str(c) for c in frame.columns if str(c).startswith("feature_")]
    if "rank_score" in frame.columns and "rank_score" not in features:
        features.insert(0, "rank_score")
    return features


def _next_bar_return_labels(train_frame: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """Build (X, y) where y is the next-bar return of each candidate, TRAIN only.

    For each ``symbol`` the label is the realised next-bar move
    ``(price_{t+1} - price_t) / price_t`` within the TRAIN segment only (sorted by
    timestamp).  This is a TRAIN-segment quantity: it never reads the TEST tail
    because ``_fit_policy`` is handed only ``train_frame``.  The classifier target
    is ``y > 0`` (next bar up), so the ranker scores candidates by P(up).
    """

    feature_cols = _causal_feature_columns(train_frame)
    frame = train_frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "price"]).sort_values(["symbol", "timestamp"])
    frame["_next_price"] = frame.groupby("symbol")["price"].shift(-1)
    frame = frame.dropna(subset=["_next_price"])
    if frame.empty:
        return np.zeros((0, len(feature_cols)), dtype=np.float64), np.zeros((0,), dtype=np.int64)
    ret = (frame["_next_price"].to_numpy(dtype=np.float64) - frame["price"].to_numpy(dtype=np.float64))
    ret = ret / np.maximum(frame["price"].to_numpy(dtype=np.float64), 1e-12)
    features = frame[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    X = features.to_numpy(dtype=np.float64)
    y = (ret > 0.0).astype(np.int64)
    return X, y


class _SupervisedRankerPolicy:
    """TRAIN-fit supervised ranker that selects top_k candidates by P(next-up).

    A regularized logistic regression on the SAME causal features the env uses,
    fit on the TRAIN segment ONLY, predicting whether a candidate's next bar is
    up.  At eval it scores the current-bar candidates and buys the best fillable
    candidate whose predicted up-probability is highest (mirrors the env's top_k
    selection).  No TEST data ever reaches ``fit`` — the leakage guard test
    asserts this.  Falls back to the env's rank_score order if the model could
    not be fit (degenerate single-class TRAIN labels).
    """

    def __init__(self, feature_cols: Sequence[str], model: Optional[Any]) -> None:
        self.feature_cols = list(feature_cols)
        self.model = model

    def _score_rows(self, candidates: pd.DataFrame) -> np.ndarray:
        if candidates.empty:
            return np.zeros((0,), dtype=np.float64)
        feats = candidates.reindex(columns=self.feature_cols, fill_value=0.0)
        X = feats.apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
        if self.model is None or X.shape[0] == 0:
            # Fallback: rank by rank_score (already the candidate sort key).
            return pd.to_numeric(candidates.get("rank_score"), errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
        return self.model.predict_proba(X)[:, 1]

    def __call__(self, env: PortfolioEnv, info: Mapping[str, Any]) -> int:
        mask = list(info["action_mask"])
        sell_offset = 1 + env.config.top_k_candidates
        candidates = env._current_candidates()  # noqa: SLF001 - read-only current bar view
        scores = self._score_rows(candidates)
        # Rank buyable candidate slots by predicted P(up), descending.
        buy_slots = [slot for slot in range(1, sell_offset) if mask[slot] and (slot - 1) < len(scores)]
        buy_slots.sort(key=lambda slot: float(scores[slot - 1]), reverse=True)
        for slot in buy_slots:
            return slot
        # No buyable candidate: free a slot only if forced (hold otherwise — the
        # ranker is a long-only top_k selector, not a churn policy).
        return ACTION_HOLD


def _fit_supervised_ranker(
    *,
    train_frame: pd.DataFrame,
    config: PortfolioWalkForwardConfig,
    fold_index: int,
) -> PolicyFn:
    """Fit a logistic ranker on TRAIN causal features (P0-2 / §7a factory).

    Wired through the same ``_fit_policy`` plumbing as ``trained_ppo``; fit on the
    TRAIN segment only, evaluated on the identical disjoint holdout the RL policy
    uses.  ``fold_index``/``config`` are accepted for the uniform factory
    signature; the fit reads only ``train_frame``.
    """

    from sklearn.linear_model import LogisticRegression

    seed = int(config.seed) if config is not None else 0
    del fold_index, config  # uniform factory signature; ranker reads only TRAIN
    feature_cols = _causal_feature_columns(train_frame)
    X, y = _next_bar_return_labels(train_frame)
    model: Optional[Any] = None
    if X.shape[0] >= 2 and len(np.unique(y)) >= 2:
        model = LogisticRegression(C=1.0, max_iter=1000, random_state=seed)
        model.fit(X, y)
    frozen = _SupervisedRankerPolicy(feature_cols, model)

    def _policy(env: PortfolioEnv, info: Mapping[str, Any]) -> int:
        return frozen(env, info)

    _policy.frozen_params = {  # type: ignore[attr-defined]
        "ranker_fitted": bool(model is not None),
        "feature_count": len(feature_cols),
    }
    return _policy


# Built-in trained-baseline factory: supervised_ranker is always available.
register_trained_policy_factory(
    "supervised_ranker",
    lambda *, train_frame, config, fold_index: _fit_supervised_ranker(
        train_frame=train_frame, config=config, fold_index=fold_index
    ),
)


def _fit_policy(
    policy: str,
    train_frame: pd.DataFrame,
    config: PortfolioWalkForwardConfig,
    fold_index: int,
) -> PolicyFn:
    """Fit/prepare a policy on the TRAIN segment, returning a callable.

    The deterministic stand-in and the rule baselines have no learnable state,
    so fitting is a no-op that simply closes over the policy name.  The
    ``cost_aware`` policy *does* fit: its (rank_score threshold, min-hold) params
    are grid-searched on ``train_frame`` only and frozen, then evaluated on the
    disjoint, strictly-later TEST segment.

    P0-2: a trained/learned baseline (``trained_ppo``, ``supervised_ranker``, or
    any runtime-registered key) is handed off here via ``TRAINED_POLICY_FACTORIES``
    BEFORE the ``del`` below — so the factory still receives ``train_frame`` /
    ``config`` / ``fold_index``.  ``_fit_policy``'s signature is unchanged.
    """

    if policy == "cost_aware":
        return _fit_cost_aware_policy(train_frame, config, fold_index)

    # P0-2(b): trained/learned model handoff — MUST run before the del below.
    factory = TRAINED_POLICY_FACTORIES.get(policy)
    if factory is not None:
        return factory(train_frame=train_frame, config=config, fold_index=fold_index)

    del train_frame, config, fold_index  # train segment is the future seam

    def _policy(env: PortfolioEnv, info: Mapping[str, Any]) -> int:
        return _action_for_policy(policy, env, info)

    return _policy


def _max_drawdown_pct(nav_values: Sequence[float]) -> float:
    peak = float("-inf")
    max_dd = 0.0
    for value in nav_values:
        peak = max(peak, float(value))
        if peak > 0:
            max_dd = min(max_dd, (float(value) / peak) - 1.0)
    return max_dd * 100.0


def _evaluate_on_test(
    *,
    policy_fn: PolicyFn,
    test_candidates: pd.DataFrame,
    fold_index: int,
    policy: str,
    config: PortfolioWalkForwardConfig,
) -> Dict[str, Any]:
    """Run a (pre-fit) policy on the disjoint, later TEST segment and score it."""

    env = _make_env(test_candidates, config, fold_index)
    _, info = env.reset(seed=config.seed + fold_index)
    terminated = False
    truncated = False
    rewards: List[float] = []
    steps = 0
    while not (terminated or truncated):
        if config.max_steps_per_fold and steps >= int(config.max_steps_per_fold):
            break
        action = policy_fn(env, info)
        _, reward, terminated, truncated, info = env.step(action)
        rewards.append(float(reward))
        steps += 1

    nav_curve = [float(row["nav"]) for row in env.nav_log] or [float(config.initial_cash)]
    final_nav = float(info["nav"])
    turnover = float(sum(float(fill.get("gross_value", 0.0)) for fill in env.trade_log))
    total_cost = float(sum(float(fill.get("cost", 0.0)) for fill in env.trade_log))
    return {
        "fold_index": fold_index,
        "policy": policy,
        "steps": steps,
        "final_nav": final_nav,
        "return_pct": (final_nav / float(config.initial_cash) - 1.0) * 100.0,
        "max_drawdown_pct": _max_drawdown_pct(nav_curve),
        "turnover": turnover,
        "trade_count": int(info["trade_count"]),
        "total_cost": total_cost,
        "cost_bps": float(config.cost_bps),
        "invalid_action_count": int(info["invalid_action_count"]),
        "total_reward": float(sum(rewards)),
    }


def run_portfolio_walk_forward(config: PortfolioWalkForwardConfig) -> Dict[str, Any]:
    candidates = _load_candidates(config.candidate_path)
    if config.shuffle_signal:
        # Destroy the per-timestamp selection signal (rank_score + feature_*) while
        # keeping price/fill_price/symbol intact — the mandatory shuffle test (§7).
        candidates = shuffle_candidate_signal(candidates, seed=config.shuffle_seed)
    folds = build_expanding_window_folds(candidates, config.n_folds)
    rows: List[Dict[str, Any]] = []
    periods: List[Dict[str, Any]] = []
    for fold in folds:
        # Assert the holdout contract by construction at runtime: TEST is disjoint
        # from and strictly later than TRAIN.  This is a hard guard, not prose.
        train_ts = set(pd.Timestamp(ts) for ts in fold.train_frame["timestamp"].unique())
        test_ts = set(pd.Timestamp(ts) for ts in fold.test_frame["timestamp"].unique())
        if train_ts & test_ts:
            raise AssertionError(f"Fold {fold.fold_index}: train/test timestamps overlap")
        if test_ts and train_ts and min(test_ts) <= max(train_ts):
            raise AssertionError(f"Fold {fold.fold_index}: test segment is not strictly later than train")

        periods.append(
            {
                "fold_index": fold.fold_index,
                "train_start": fold.train_start,
                "train_end": fold.train_end,
                "test_start": fold.test_start,
                "test_end": fold.test_end,
                "train_candidate_count": int(len(fold.train_frame)),
                "test_candidate_count": int(len(fold.test_frame)),
            }
        )
        for policy in config.baselines:
            policy_fn = _fit_policy(policy, fold.train_frame, config, fold.fold_index)
            metrics = _evaluate_on_test(
                policy_fn=policy_fn,
                test_candidates=fold.test_frame,
                fold_index=fold.fold_index,
                policy=policy,
                config=config,
            )
            # Expose the TRAIN-fit params for the cost-aware policy so the fold
            # report shows exactly what was frozen before the held-out eval.
            # Trained/learned baselines (supervised_ranker, trained_ppo) carry a
            # differently-shaped ``frozen_params``; the cost-aware columns stay
            # blank for them (use ``.get`` so any factory shape is tolerated).
            fitted = getattr(policy_fn, "frozen_params", None) or {}
            rows.append(
                {
                    "train_start": fold.train_start,
                    "train_end": fold.train_end,
                    "test_start": fold.test_start,
                    "test_end": fold.test_end,
                    "fitted_score_threshold": (
                        float(fitted["score_threshold"]) if "score_threshold" in fitted else ""
                    ),
                    "fitted_min_hold_steps": (
                        int(fitted["min_hold_steps"]) if "min_hold_steps" in fitted else ""
                    ),
                    **metrics,
                }
            )
    ranking = sorted(rows, key=lambda row: float(row["return_pct"]), reverse=True)
    output_dir = Path(config.output_dir)
    payload: Dict[str, Any] = {
        "mode": "stom_rl_portfolio_walk_forward",
        "config": asdict(config),
        "summary": {
            "n_folds": len(folds),
            "baseline_count": len(config.baselines),
            "holdout": "expanding_window_train_le_N_eval_N_plus_1",
            "cost_bps": float(config.cost_bps),
            "shuffle_signal": bool(config.shuffle_signal),
            "shuffle_seed": int(config.shuffle_seed) if config.shuffle_signal else None,
            "smoke_success": bool(rows),
            "best_policy_by_return": ranking[0]["policy"] if ranking else None,
            "performance_success": bool(ranking and float(ranking[0]["return_pct"]) > 0.0),
            "performance_note": (
                "Engineering completion requires a real expanding-window holdout "
                "(eval on a disjoint, strictly-later test segment) plus generated "
                "fold artifacts; alpha superiority over baselines is tracked "
                "separately (Page 14)."
            ),
        },
        "fold_periods": periods,
        "folds": rows,
        "artifacts": {
            "output_dir": str(output_dir),
            "report_json": str(output_dir / "portfolio_walk_forward_report.json"),
            "folds_csv": str(output_dir / "portfolio_walk_forward_folds.csv"),
        },
    }
    if config.write_artifacts:
        _write_json(output_dir / "portfolio_walk_forward_report.json", payload)
        _write_csv(
            output_dir / "portfolio_walk_forward_folds.csv",
            rows,
            [
                "fold_index",
                "train_start",
                "train_end",
                "test_start",
                "test_end",
                "policy",
                "steps",
                "final_nav",
                "return_pct",
                "max_drawdown_pct",
                "turnover",
                "trade_count",
                "total_cost",
                "cost_bps",
                "invalid_action_count",
                "total_reward",
                "fitted_score_threshold",
                "fitted_min_hold_steps",
            ],
        )
    return payload


def _parse_baselines(raw: str) -> Tuple[str, ...]:
    baselines = tuple(part.strip() for part in raw.split(",") if part.strip())
    # P0-2(a): accept DEFAULT_BASELINES (deterministic stand-ins) PLUS the
    # trained/learned keys (TRAINED_BASELINES + any runtime-registered factory),
    # without relaxing the strict typo-guard for the deterministic set.
    allowed = set(DEFAULT_BASELINES) | set(TRAINED_BASELINES) | set(TRAINED_POLICY_FACTORIES)
    unknown = sorted(set(baselines) - allowed)
    if unknown:
        raise ValueError(f"Unknown portfolio baselines: {unknown}. Available: {sorted(allowed)}")
    return baselines


def _parse_args(argv: Optional[Sequence[str]] = None) -> PortfolioWalkForwardConfig:
    parser = argparse.ArgumentParser(description="Run portfolio walk-forward holdout validation.")
    parser.add_argument("--candidate-csv", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_PORTFOLIO_WALK_FORWARD_OUTPUT_DIR))
    parser.add_argument("--n-folds", type=int, default=2)
    parser.add_argument("--baselines", default=",".join(DEFAULT_BASELINES))
    parser.add_argument("--top-k-candidates", type=int, default=3)
    parser.add_argument("--max-positions", type=int, default=2)
    parser.add_argument("--max-steps-per-fold", type=int, default=24)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--cost-bps", type=float, default=25.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument(
        "--turnover-penalty-lambda",
        type=float,
        default=0.0,
        help="Additive turnover-cost penalty λ in the env reward (0 = legacy). "
        "The cost-aware policy overrides this for TRAIN tuning only; held-out "
        "TEST eval uses this value (keep 0 for an honest costed comparison).",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument(
        "--shuffle-signal",
        action="store_true",
        help="Mandatory shuffle test (§7): permute rank_score + feature_* within "
        "each timestamp (overwrite, not reorder) so the selection signal is "
        "destroyed while fills/cost stay identical. A real edge must vanish here.",
    )
    parser.add_argument("--shuffle-seed", type=int, default=0, help="Deterministic seed for the shuffle test.")
    args = parser.parse_args(argv)
    return PortfolioWalkForwardConfig(
        candidate_path=args.candidate_csv,
        output_dir=args.output_dir,
        n_folds=args.n_folds,
        baselines=_parse_baselines(args.baselines),
        top_k_candidates=args.top_k_candidates,
        max_positions=args.max_positions,
        max_steps_per_fold=args.max_steps_per_fold,
        seed=args.seed,
        initial_cash=args.initial_cash,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
        turnover_penalty_lambda=args.turnover_penalty_lambda,
        write_artifacts=not args.no_write,
        shuffle_signal=bool(args.shuffle_signal),
        shuffle_seed=int(args.shuffle_seed),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = run_portfolio_walk_forward(_parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
