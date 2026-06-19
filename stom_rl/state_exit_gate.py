"""Experiment ④ — 30s state-conditioned early-exit gate for STOM ``ts_imb``.

RULE / supervised risk-control gate, NOT reinforcement learning.

Question: if a gap-up ``ts_imb`` rule trade is still open at 30 seconds, can
causal path state identify cases where selling marketable now beats continuing
the fixed TP5/SL1/09:25 baseline?  The target is paired money delta after
marketable fills and 23bp costs; SL labels are diagnostics only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from stom_rl.exit_baselines import deflated_sharpe_ratio, per_trade_sharpe
from stom_rl.marketable_fill import (
    DEFAULT_TIME_EXIT_SEC,
    EXIT_SL,
    EXIT_TIME,
    EXIT_TP,
    marketable_entry_price,
    marketable_exit_price,
)
from stom_rl.microstructure_features import FEATURE_NAMES, causal_feature_vector
from stom_rl.predictability_probe import _COLS, _sec_of
from stom_rl.timing_gate import DEFAULT_EXTERNAL_SHARPE_VARIANCE

DEFAULT_BOUNDARIES: Tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9)
DEFAULT_EXIT_FRACTIONS: Tuple[float, ...] = (0.10, 0.20, 0.30, 0.40)
DEFAULT_PRIMARY_BOUNDARY = 0.7
DEFAULT_CHECKPOINT_SEC = 30
PRIMARY_MODEL_FAMILY = "gbm"
MODEL_FAMILIES: Tuple[str, ...] = ("ridge", "gbm")


def _as_float_array(values: Sequence[float], *, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values")
    return arr


def _validate_exit_fractions(exit_fractions: Sequence[float]) -> Tuple[float, ...]:
    vals = tuple(float(v) for v in exit_fractions)
    if not vals:
        raise ValueError("exit_fractions must be non-empty")
    if any(v <= 0.0 or v >= 1.0 for v in vals):
        raise ValueError("each exit fraction must be in (0, 1)")
    return vals


def top_fraction_mask(scores: Sequence[float], fraction: float) -> np.ndarray:
    """Boolean mask for the top predicted-delta fraction."""

    pred = _as_float_array(scores, name="scores")
    if not 0.0 < float(fraction) < 1.0:
        raise ValueError("fraction must be in (0, 1)")
    mask = np.zeros(len(pred), dtype=bool)
    if len(pred) == 0:
        return mask
    k = min(len(pred), max(1, int(np.ceil(len(pred) * float(fraction)))))
    mask[np.argsort(-pred, kind="mergesort")[:k]] = True
    return mask


def eligible_top_fraction_mask(
    pred_eligible: Sequence[float],
    eligible_mask: Sequence[bool],
    exit_fraction: float,
) -> np.ndarray:
    """Map top-fraction predictions for eligible rows back to all original rows."""

    eligible = np.asarray(eligible_mask, dtype=bool)
    pred = _as_float_array(pred_eligible, name="pred_eligible")
    pos = np.flatnonzero(eligible)
    if len(pred) != len(pos):
        raise ValueError("pred_eligible length must equal eligible row count")
    out = np.zeros(len(eligible), dtype=bool)
    out[pos[top_fraction_mask(pred, exit_fraction)]] = True
    return out


def score_exit_policy(
    baseline_net: Sequence[float],
    early_exit_net: Sequence[float],
    eligible_mask: Sequence[bool],
    exit_mask: Sequence[bool],
    group_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Score early-exit decisions against the continue-baseline policy.

    Primary mean is over all original trades. Ineligible trades and continued
    eligible trades both receive incremental zero.
    """

    base = _as_float_array(baseline_net, name="baseline_net")
    early = _as_float_array(early_exit_net, name="early_exit_net")
    eligible = np.asarray(eligible_mask, dtype=bool)
    exits = np.asarray(exit_mask, dtype=bool) & eligible
    if not (len(base) == len(early) == len(eligible) == len(exits)):
        raise ValueError("baseline, early_exit, eligible, and exit_mask lengths must match")

    policy = np.where(exits, early, base)
    inc = policy - base
    delta = early - base
    exited_delta = delta[exits]
    eligible_inc = inc[eligible]
    out: Dict[str, Any] = {
        "n_original_trades": int(len(base)),
        "n_checkpoint_eligible_trades": int(eligible.sum()),
        "n_policy_exits": int(exits.sum()),
        "exit_fraction_realized": float(exits.sum() / max(1, eligible.sum())) if len(base) else 0.0,
        "baseline_total_net_pct": float(base.sum()) if len(base) else 0.0,
        "policy_total_net_pct": float(policy.sum()) if len(policy) else 0.0,
        "incremental_total_pct": float(inc.sum()) if len(inc) else 0.0,
        "baseline_mean_net_pct": float(base.mean()) if len(base) else None,
        "policy_mean_net_pct": float(policy.mean()) if len(policy) else None,
        "incremental_mean_pct_per_original_trade": float(inc.mean()) if len(inc) else None,
        "eligible_incremental_mean_pct": float(eligible_inc.mean()) if len(eligible_inc) else None,
        "exited_delta_mean_pct": float(exited_delta.mean()) if len(exited_delta) else None,
        "exited_baseline_mean_net_pct": float(base[exits].mean()) if exits.any() else None,
        "exited_early_exit_mean_net_pct": float(early[exits].mean()) if exits.any() else None,
        "increments": inc,
    }
    if group_ids is not None:
        groups = np.asarray([str(g) for g in group_ids])
        if len(groups) != len(base):
            raise ValueError("group_ids and baseline_net must have the same length")
        out["group_incremental"] = np.asarray(
            [float(inc[groups == g].mean()) for g in np.unique(groups)],
            dtype=float,
        )
    return out


def select_exit_fraction(
    pred_eligible: Sequence[float],
    baseline_net: Sequence[float],
    early_exit_net: Sequence[float],
    eligible_mask: Sequence[bool],
    exit_fractions: Sequence[float] = DEFAULT_EXIT_FRACTIONS,
) -> Dict[str, Any]:
    """Select one exit fraction using train data only."""

    rows: List[Dict[str, Any]] = []
    for frac in _validate_exit_fractions(exit_fractions):
        exits = eligible_top_fraction_mask(pred_eligible, eligible_mask, frac)
        scored = score_exit_policy(baseline_net, early_exit_net, eligible_mask, exits)
        rows.append({
            "exit_fraction": float(frac),
            "train_incremental_mean_pct_per_original_trade": scored["incremental_mean_pct_per_original_trade"],
            "train_exited_delta_mean_pct": scored["exited_delta_mean_pct"],
            "train_n_policy_exits": scored["n_policy_exits"],
        })
    best = max(
        rows,
        key=lambda r: (
            float(r["train_incremental_mean_pct_per_original_trade"]),
            -float(r["exit_fraction"]),
        ),
    )
    return {"selected_exit_fraction": float(best["exit_fraction"]), "train_scores": rows}


def _split_by_date(dates: np.ndarray, boundary: float) -> Tuple[np.ndarray, np.ndarray]:
    uniq = np.array(sorted(set(dates.tolist())))
    if len(uniq) < 3:
        return np.zeros(len(dates), dtype=bool), np.zeros(len(dates), dtype=bool)
    cut = uniq[max(0, min(len(uniq) - 1, int(round(len(uniq) * boundary)) - 1))]
    return dates < cut, dates > cut


def _models(rng_seed: int):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge

    return {
        "ridge": Ridge(alpha=10.0),
        "gbm": HistGradientBoostingRegressor(
            max_depth=3,
            max_iter=200,
            learning_rate=0.05,
            l2_regularization=1.0,
            random_state=rng_seed,
        ),
    }


def _fit_predict_eligible(
    X: np.ndarray,
    y_delta: np.ndarray,
    train_eligible: np.ndarray,
    test_eligible: np.ndarray,
    *,
    rng_seed: int,
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(X[train_eligible])
    Xtr = scaler.transform(X[train_eligible])
    Xte = scaler.transform(X[test_eligible])
    preds: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for name, model in _models(rng_seed).items():
        model.fit(Xtr, y_delta[train_eligible])
        preds[name] = (model.predict(Xtr), model.predict(Xte))
    return preds


def _bootstrap_ci(values: np.ndarray, *, n_bootstrap: int, rng: np.random.Generator) -> Tuple[Optional[float], Optional[float]]:
    if len(values) < 2 or n_bootstrap <= 0:
        return None, None
    boot = rng.choice(values, size=(int(n_bootstrap), len(values)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return float(lo), float(hi)


def _evaluate_model_boundary(
    pred_train_eligible: np.ndarray,
    pred_test_eligible: np.ndarray,
    baseline_train: np.ndarray,
    early_train: np.ndarray,
    eligible_train: np.ndarray,
    baseline_test: np.ndarray,
    early_test: np.ndarray,
    eligible_test: np.ndarray,
    test_groups: np.ndarray,
    *,
    exit_fractions: Sequence[float],
    n_bootstrap: int,
    rng: np.random.Generator,
    external_sharpe_variance: float,
    n_trials: int,
    min_checkpoint_eligible_test: int,
    min_policy_exits: int,
) -> Dict[str, Any]:
    selected = select_exit_fraction(pred_train_eligible, baseline_train, early_train, eligible_train, exit_fractions)
    frac = selected["selected_exit_fraction"]
    exits = eligible_top_fraction_mask(pred_test_eligible, eligible_test, frac)
    scored = score_exit_policy(baseline_test, early_test, eligible_test, exits, test_groups)
    group_inc = np.asarray(scored.get("group_incremental", []), dtype=float)
    lo, hi = _bootstrap_ci(group_inc, n_bootstrap=n_bootstrap, rng=rng)
    sr = per_trade_sharpe(group_inc.tolist()) if len(group_inc) >= 2 else None
    dsr = (
        deflated_sharpe_ratio(
            sr,
            n_trials=n_trials,
            sharpe_variance=external_sharpe_variance,
            n_samples=len(group_inc),
        )
        if sr is not None
        else None
    )
    ci_go = bool(lo is not None and lo > 0.0)
    dsr_go = bool(dsr is not None and dsr >= 0.95)
    delta_go = bool(scored["exited_delta_mean_pct"] is not None and scored["exited_delta_mean_pct"] > 0.0)
    policy_go = bool(
        scored["policy_mean_net_pct"] is not None
        and scored["baseline_mean_net_pct"] is not None
        and scored["policy_mean_net_pct"] > scored["baseline_mean_net_pct"]
    )
    min_eligible_go = bool(scored["n_checkpoint_eligible_trades"] >= int(min_checkpoint_eligible_test))
    min_exits_go = bool(scored["n_policy_exits"] >= int(min_policy_exits))
    return {
        "selected_exit_fraction": float(frac),
        "train_exit_fraction_scores": selected["train_scores"],
        "n_original_test_trades": scored["n_original_trades"],
        "n_checkpoint_eligible_test_trades": scored["n_checkpoint_eligible_trades"],
        "n_policy_exits": scored["n_policy_exits"],
        "exit_fraction_realized": scored["exit_fraction_realized"],
        "baseline_mean_net_pct": scored["baseline_mean_net_pct"],
        "policy_mean_net_pct": scored["policy_mean_net_pct"],
        "incremental_mean_pct_per_original_trade": float(group_inc.mean()) if len(group_inc) else None,
        "eligible_incremental_mean_pct": scored["eligible_incremental_mean_pct"],
        "incremental_ci95": [lo, hi],
        "ci_excludes_zero": ci_go,
        "incremental_sharpe": sr,
        "incremental_dsr": dsr,
        "dsr_gt_0_95": dsr_go,
        "exited_delta_mean_pct": scored["exited_delta_mean_pct"],
        "exited_baseline_mean_net_pct": scored["exited_baseline_mean_net_pct"],
        "exited_early_exit_mean_net_pct": scored["exited_early_exit_mean_net_pct"],
        "components": {
            "ci_excludes_zero": ci_go,
            "dsr_gt_0_95": dsr_go,
            "exited_delta_mean_gt_0": delta_go,
            "policy_mean_gt_baseline": policy_go,
            "min_checkpoint_eligible_test_trades": min_eligible_go,
            "min_policy_exits": min_exits_go,
        },
        "go": False,
    }


def run_state_exit_gate(
    X: np.ndarray,
    baseline_net: Sequence[float],
    early_exit_net: Sequence[float],
    eligible: Sequence[bool],
    dates: Sequence[str],
    group_ids: Sequence[str],
    *,
    boundaries: Sequence[float] = DEFAULT_BOUNDARIES,
    primary_boundary: float = DEFAULT_PRIMARY_BOUNDARY,
    exit_fractions: Sequence[float] = DEFAULT_EXIT_FRACTIONS,
    primary_model_family: str = PRIMARY_MODEL_FAMILY,
    n_bootstrap: int = 1000,
    rng_seed: int = 0,
    external_sharpe_variance: float = DEFAULT_EXTERNAL_SHARPE_VARIANCE,
    n_trials: Optional[int] = None,
    min_train_eligible: int = 50,
    min_test_eligible: int = 50,
    min_checkpoint_eligible_test: int = 500,
    min_policy_exits: int = 50,
) -> Dict[str, Any]:
    """Walk-forward 30s early-exit gate over paired marketable net deltas."""

    X_arr = np.asarray(X, dtype=float)
    base = _as_float_array(baseline_net, name="baseline_net")
    early = _as_float_array(early_exit_net, name="early_exit_net")
    eligible_arr = np.asarray(eligible, dtype=bool)
    dates_arr = np.asarray([str(d) for d in dates])
    groups_arr = np.asarray([str(g) for g in group_ids])
    if X_arr.ndim != 2 or not (len(X_arr) == len(base) == len(early) == len(eligible_arr) == len(dates_arr) == len(groups_arr)):
        raise ValueError("X, nets, eligible, dates, and group_ids must have matching lengths")
    if primary_model_family not in MODEL_FAMILIES:
        raise ValueError("primary_model_family must be one of %r" % (MODEL_FAMILIES,))

    fractions = _validate_exit_fractions(exit_fractions)
    boundaries_t = tuple(float(b) for b in boundaries)
    trial_count = int(n_trials) if n_trials is not None else len(fractions) * len(boundaries_t) * 1
    rng = np.random.default_rng(rng_seed)
    y_delta = early - base
    per_boundary: Dict[str, Dict[float, Optional[float]]] = {m: {} for m in MODEL_FAMILIES}
    primary_results: Dict[str, Dict[str, Any]] = {}

    for frac in boundaries_t:
        train, test = _split_by_date(dates_arr, frac)
        train_eligible = train & eligible_arr
        test_eligible = test & eligible_arr
        if train_eligible.sum() < min_train_eligible or test_eligible.sum() < min_test_eligible:
            for name in per_boundary:
                per_boundary[name][float(frac)] = None
            continue
        preds = _fit_predict_eligible(X_arr, y_delta, train_eligible, test_eligible, rng_seed=rng_seed)
        for name, (pred_train, pred_test) in preds.items():
            eval_res = _evaluate_model_boundary(
                pred_train,
                pred_test,
                base[train],
                early[train],
                eligible_arr[train],
                base[test],
                early[test],
                eligible_arr[test],
                groups_arr[test],
                exit_fractions=fractions,
                n_bootstrap=n_bootstrap,
                rng=rng,
                external_sharpe_variance=external_sharpe_variance,
                n_trials=trial_count,
                min_checkpoint_eligible_test=min_checkpoint_eligible_test,
                min_policy_exits=min_policy_exits,
            )
            per_boundary[name][float(frac)] = eval_res["incremental_mean_pct_per_original_trade"]
            if abs(frac - primary_boundary) < 1e-9:
                primary_results[name] = eval_res

    primary_train, primary_test = _split_by_date(dates_arr, primary_boundary)
    result: Dict[str, Any] = {
        "verdict": "NO-GO",
        "n_original_trades": int(len(base)),
        "n_checkpoint_eligible_trades": int(eligible_arr.sum()),
        "n_original_test_trades": int(primary_test.sum()),
        "n_checkpoint_eligible_test_trades": int((primary_test & eligible_arr).sum()),
        "n_policy_exits": 0,
        "n_groups": int(len(set(groups_arr.tolist()))),
        "n_dates": int(len(set(dates_arr.tolist()))),
        "primary_boundary": float(primary_boundary),
        "boundaries": [float(b) for b in boundaries_t],
        "exit_fractions": [float(v) for v in fractions],
        "primary_model_family": primary_model_family,
        "n_trials": trial_count,
        "external_sharpe_variance": float(external_sharpe_variance),
        "per_boundary_incremental_mean": per_boundary,
        "models": {},
        "negative_controls": [],
    }

    for name in MODEL_FAMILIES:
        m = dict(primary_results.get(name, {}))
        if not m:
            continue
        positive_count = sum(1 for v in per_boundary.get(name, {}).values() if v is not None and float(v) > 0.0)
        components = dict(m["components"])
        components["positive_boundaries_ge_3"] = positive_count >= 3
        can_go = bool(
            components["ci_excludes_zero"]
            and components["dsr_gt_0_95"]
            and components["exited_delta_mean_gt_0"]
            and components["policy_mean_gt_baseline"]
            and components["positive_boundaries_ge_3"]
            and components["min_checkpoint_eligible_test_trades"]
            and components["min_policy_exits"]
        )
        m["positive_boundary_count"] = int(positive_count)
        m["components"] = components
        m["go"] = bool(can_go and name == primary_model_family)
        if name != primary_model_family:
            m["diagnostic_only"] = True
        result["models"][name] = m

    if primary_model_family not in result["models"]:
        result["verdict"] = "INCONCLUSIVE"
        result["inconclusive_reason"] = "primary_boundary_not_evaluable"
    else:
        pm = result["models"][primary_model_family]
        result["n_policy_exits"] = int(pm.get("n_policy_exits", 0))
        comps = pm.get("components", {})
        if not comps.get("min_checkpoint_eligible_test_trades", True) or not comps.get("min_policy_exits", True):
            result["verdict"] = "INCONCLUSIVE"
            result["inconclusive_reason"] = "primary_min_count_not_met"
        elif pm.get("go"):
            result["verdict"] = "GO"
        else:
            result["verdict"] = "NO-GO"
    return result


def run_shuffled_feature_controls(
    X: np.ndarray,
    baseline_net: Sequence[float],
    early_exit_net: Sequence[float],
    eligible: Sequence[bool],
    dates: Sequence[str],
    group_ids: Sequence[str],
    *,
    n_shuffles: int = 5,
    rng_seed: int = 1000,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Run deterministic shuffled-feature negative controls."""

    X_arr = np.asarray(X, dtype=float)
    controls: List[Dict[str, Any]] = []
    for i in range(int(n_shuffles)):
        seed = int(rng_seed) + i
        order = np.random.default_rng(seed).permutation(len(X_arr))
        ctrl = run_state_exit_gate(X_arr[order], baseline_net, early_exit_net, eligible, dates, group_ids, rng_seed=seed, **kwargs)
        controls.append({
            "shuffle_index": i,
            "rng_seed": seed,
            "verdict": ctrl.get("verdict"),
            "primary_model": ctrl.get("models", {}).get(ctrl.get("primary_model_family", PRIMARY_MODEL_FAMILY), {}),
        })
    return controls


def apply_negative_control_gate(result: Dict[str, Any], controls: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach shuffled controls and enforce them as a hard GO blocker."""

    out = dict(result)
    negs = list(controls)
    out["negative_controls"] = negs
    passed = bool(negs) and all(str(c.get("verdict", "")).upper() == "NO-GO" for c in negs)
    out["negative_control_passed"] = passed
    if out.get("verdict") == "GO" and not passed:
        out["verdict_before_negative_control"] = "GO"
        out["verdict"] = "NO-GO"
        out["negative_control_blocked_go"] = True
        out["go_block_reason"] = "negative_controls_not_all_no_go"
    else:
        out["negative_control_blocked_go"] = False
    return out


def _baseline_exit(
    prices: Sequence[float],
    bids: Sequence[Optional[float]],
    asks: Sequence[Optional[float]],
    secs: Sequence[int],
    *,
    entry_idx: int,
    tp_pct: float,
    sl_pct: float,
    time_exit_sec: int,
    cost_bps: float,
    slippage_bps: float,
) -> Tuple[float, str, int]:
    entry_fill = marketable_entry_price(bids[entry_idx], asks[entry_idx], prices[entry_idx], slippage_bps=slippage_bps)
    tp_level = entry_fill * (1.0 + tp_pct / 100.0)
    sl_level = entry_fill * (1.0 - sl_pct / 100.0)
    exit_idx, reason = len(prices) - 1, EXIT_TIME
    for j in range(entry_idx + 1, len(prices)):
        if int(secs[j]) >= time_exit_sec:
            exit_idx, reason = j, EXIT_TIME
            break
        p = float(prices[j])
        if p <= sl_level:
            exit_idx, reason = j, EXIT_SL
            break
        if p >= tp_level:
            exit_idx, reason = j, EXIT_TP
            break
    exit_fill = marketable_exit_price(bids[exit_idx], asks[exit_idx], prices[exit_idx], slippage_bps=slippage_bps)
    return (exit_fill / entry_fill - 1.0) * 100.0 - cost_bps / 100.0, reason, exit_idx


def _checkpoint_index(secs: Sequence[int], checkpoint_sec: int) -> int:
    idx = 0
    for j, sec in enumerate(secs):
        if int(sec) <= int(checkpoint_sec):
            idx = j
        else:
            break
    return idx


def checkpoint_features_from_rows(rows: Sequence[Dict[str, Any]], checkpoint_sec: int = DEFAULT_CHECKPOINT_SEC) -> Dict[str, float]:
    """Causal feature vector using only rows at or before ``checkpoint_sec``."""

    if not rows:
        raise ValueError("rows must be non-empty")
    idx = _checkpoint_index([int(r["sec"]) for r in rows], checkpoint_sec)
    return causal_feature_vector(rows[: idx + 1])


def simulate_checkpoint_exit_pair(
    prices: Sequence[float],
    bids: Sequence[Optional[float]],
    asks: Sequence[Optional[float]],
    secs: Sequence[int],
    *,
    checkpoint_sec: int = DEFAULT_CHECKPOINT_SEC,
    entry_idx: int = 0,
    tp_pct: float = 5.0,
    sl_pct: float = 1.0,
    time_exit_sec: int = DEFAULT_TIME_EXIT_SEC,
    cost_bps: float = 23.0,
    slippage_bps: float = 0.0,
) -> Dict[str, Any]:
    """Return paired baseline-vs-checkpoint early-exit nets."""

    baseline_net, reason, exit_idx = _baseline_exit(
        prices,
        bids,
        asks,
        secs,
        entry_idx=entry_idx,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        time_exit_sec=time_exit_sec,
        cost_bps=cost_bps,
        slippage_bps=slippage_bps,
    )
    cp_idx = _checkpoint_index(secs, checkpoint_sec)
    eligible = bool(exit_idx > cp_idx)
    if eligible:
        entry_fill = marketable_entry_price(bids[entry_idx], asks[entry_idx], prices[entry_idx], slippage_bps=slippage_bps)
        exit_fill = marketable_exit_price(bids[cp_idx], asks[cp_idx], prices[cp_idx], slippage_bps=slippage_bps)
        early_net = (exit_fill / entry_fill - 1.0) * 100.0 - cost_bps / 100.0
    else:
        early_net = baseline_net
    return {
        "baseline_continue_net_pct": float(baseline_net),
        "early_exit_now_net_pct": float(early_net),
        "delta_exit_now_pct": float(early_net - baseline_net),
        "eligible": eligible,
        "baseline_exit_reason": reason,
        "baseline_exit_idx": int(exit_idx),
        "baseline_exit_sec": int(secs[exit_idx]),
        "checkpoint_idx": int(cp_idx),
        "checkpoint_sec_observed": int(secs[cp_idx]),
    }


def extract_state_exit_samples(
    db_path: str,
    *,
    max_symbols: int = 0,
    checkpoint_sec: int = DEFAULT_CHECKPOINT_SEC,
    tp_pct: float = 5.0,
    sl_pct: float = 1.0,
    cost_bps: float = 23.0,
    slippage_bps: float = 0.0,
    strength_thr: float = 100.0,
    imbalance_thr: float = 0.5,
    entry_cr_thr: float = 2.0,
) -> Dict[str, Any]:
    """Extract one state-exit sample per ``ts_imb`` rule instance."""

    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from finetune_csv.stom_tick_dataset import connect_readonly, get_table_columns, list_stock_tables

    conn = connect_readonly(db_path)
    sel = ["index"] + [_COLS[k] for k in (
        "px", "cr", "strength", "buy_val", "sell_val", "buy_qty", "sell_qty",
        "bid_tot", "ask_tot", "bid1", "ask1", "bidq1", "askq1")]
    feats: List[List[float]] = []
    baseline_nets: List[float] = []
    early_nets: List[float] = []
    eligible: List[bool] = []
    dates: List[str] = []
    groups: List[str] = []
    exit_reasons: List[str] = []
    n_instances = n_eligible = 0
    try:
        tables = list_stock_tables(conn, max_tables=max_symbols if max_symbols > 0 else None)
        for table in tables:
            cols = set(get_table_columns(conn, table))
            if not all(c in cols for c in sel[1:]):
                continue
            qt = table.replace('"', '""')
            q_sel = ", ".join('"' + c.replace('"', '""') + '"' for c in sel)
            raw = conn.execute(
                'SELECT %s FROM "%s" WHERE "%s">0 ORDER BY "index"' % (q_sel, qt, _COLS["px"])
            ).fetchall()
            by_session: Dict[str, List[Dict[str, Any]]] = {}
            for r in raw:
                idx_s = str(int(r[0])) if r[0] is not None else ""
                if len(idx_s) != 14:
                    continue
                sec = _sec_of(r[0])
                if sec < 0 or sec > 1800 or r[1] is None or float(r[1]) <= 0:
                    continue
                by_session.setdefault(idx_s[:8], []).append({
                    "sec": sec, "price": float(r[1]), "cr": r[2], "ts": r[3],
                    "buy_val": r[4], "sell_val": r[5], "buy_qty": r[6], "sell_qty": r[7],
                    "bid_tot": r[8], "ask_tot": r[9], "bid1": r[10], "ask1": r[11],
                    "bidq1": r[12], "askq1": r[13],
                })
            for sess in sorted(by_session):
                rows = by_session[sess]
                if len(rows) < 120:
                    continue
                e = rows[0]
                imb = None
                if e["bid_tot"] is not None and e["ask_tot"] is not None:
                    s = float(e["bid_tot"]) + float(e["ask_tot"])
                    imb = (float(e["bid_tot"]) / s) if s > 0 else None
                if (e["cr"] is None or float(e["cr"]) < entry_cr_thr
                        or e["ts"] is None or float(e["ts"]) < strength_thr
                        or imb is None or imb < imbalance_thr):
                    continue
                prices = [rr["price"] for rr in rows]
                bids = [rr["bid1"] for rr in rows]
                asks = [rr["ask1"] for rr in rows]
                secs_arr = [rr["sec"] for rr in rows]
                paired = simulate_checkpoint_exit_pair(
                    prices, bids, asks, secs_arr,
                    checkpoint_sec=checkpoint_sec,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    cost_bps=cost_bps,
                    slippage_bps=slippage_bps,
                )
                fv = checkpoint_features_from_rows(rows, checkpoint_sec=checkpoint_sec)
                feats.append([fv[k] for k in FEATURE_NAMES])
                baseline_nets.append(float(paired["baseline_continue_net_pct"]))
                early_nets.append(float(paired["early_exit_now_net_pct"]))
                eligible.append(bool(paired["eligible"]))
                dates.append(sess)
                groups.append("%s_%s" % (table, sess))
                exit_reasons.append(str(paired["baseline_exit_reason"]))
                n_instances += 1
                n_eligible += int(bool(paired["eligible"]))
    finally:
        conn.close()

    base_arr = np.array(baseline_nets, dtype=float)
    early_arr = np.array(early_nets, dtype=float)
    elig_arr = np.array(eligible, dtype=bool)
    return {
        "X": np.array(feats, dtype=float) if feats else np.zeros((0, len(FEATURE_NAMES))),
        "baseline_net": base_arr,
        "early_exit_net": early_arr,
        "eligible": elig_arr,
        "dates": dates,
        "group_ids": groups,
        "exit_reasons": exit_reasons,
        "n_instances": n_instances,
        "n_checkpoint_eligible": n_eligible,
        "checkpoint_eligible_rate": (n_eligible / n_instances) if n_instances else None,
        "n_closed_before_checkpoint": n_instances - n_eligible,
        "mean_baseline_net_pct": float(base_arr.mean()) if len(base_arr) else None,
        "mean_early_exit_net_pct_eligible": float(early_arr[elig_arr].mean()) if elig_arr.any() else None,
        "mean_delta_exit_now_pct_eligible": float((early_arr[elig_arr] - base_arr[elig_arr]).mean()) if elig_arr.any() else None,
        "feature_names": FEATURE_NAMES,
        "checkpoint_sec": int(checkpoint_sec),
        "cost_bps": cost_bps,
        "slippage_bps": slippage_bps,
    }


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, np.bool_):
        return bool(obj)
    return float(obj)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json
    import sys
    from pathlib import Path

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description="STOM ④ state-conditioned early-exit gate (RULE/SUPERVISED, NOT RL).")
    p.add_argument("--db-path", "--db", default=str(root / "_database" / "stock_tick_back.db"))
    p.add_argument("--max-symbols", type=int, default=0)
    p.add_argument("--output-dir", default=str(root / ".omx" / "artifacts" / "state_exit"))
    p.add_argument("--n-bootstrap", type=int, default=1000)
    p.add_argument("--rng-seed", type=int, default=0)
    p.add_argument("--n-negative-shuffles", type=int, default=5)
    p.add_argument("--slippage-bps", type=float, default=0.0)
    p.add_argument("--no-write", action="store_true")
    args = p.parse_args(argv)

    print("=== STOM ④ state-conditioned early-exit gate (RULE/SUPERVISED NOT RL) ===")
    d = extract_state_exit_samples(args.db_path, max_symbols=args.max_symbols, slippage_bps=args.slippage_bps)
    print(
        "instances=%d eligible=%d eligible_rate=%s baseline_mean=%s eligible_delta_mean=%s"
        % (
            d["n_instances"],
            d["n_checkpoint_eligible"],
            ("%.3f" % d["checkpoint_eligible_rate"]) if d["checkpoint_eligible_rate"] is not None else "n/a",
            ("%.4f%%" % d["mean_baseline_net_pct"]) if d["mean_baseline_net_pct"] is not None else "n/a",
            ("%.4f%%" % d["mean_delta_exit_now_pct_eligible"]) if d["mean_delta_exit_now_pct_eligible"] is not None else "n/a",
        )
    )

    if len(d["baseline_net"]) < 200:
        res = {
            "verdict": "INCONCLUSIVE",
            "reason": "too_few_samples_for_preregistered_gate",
            "n_original_trades": int(len(d["baseline_net"])),
            "extract": {k: v for k, v in d.items() if k not in {"X", "baseline_net", "early_exit_net", "eligible", "dates", "group_ids", "exit_reasons"}},
        }
    else:
        res = run_state_exit_gate(d["X"], d["baseline_net"], d["early_exit_net"], d["eligible"], d["dates"], d["group_ids"], n_bootstrap=args.n_bootstrap, rng_seed=args.rng_seed)
        controls = run_shuffled_feature_controls(
            d["X"], d["baseline_net"], d["early_exit_net"], d["eligible"], d["dates"], d["group_ids"],
            n_shuffles=args.n_negative_shuffles,
            n_bootstrap=max(100, min(args.n_bootstrap, 300)),
            rng_seed=args.rng_seed + 1000,
        )
        res = apply_negative_control_gate(res, controls)
        res["extract"] = {k: v for k, v in d.items() if k not in {"X", "baseline_net", "early_exit_net", "eligible", "dates", "group_ids", "exit_reasons"}}

    print("-- primary boundary %s --" % res.get("primary_boundary", "n/a"))
    for name, m in res.get("models", {}).items():
        ci = m.get("incremental_ci95") or [None, None]
        print(
            "   %-5s inc=%s CI95=[%s,%s] DSR=%s delta=%s exits=%s pos_bounds=%s -> %s%s"
            % (
                name,
                ("%.4f%%" % m["incremental_mean_pct_per_original_trade"]) if m.get("incremental_mean_pct_per_original_trade") is not None else "n/a",
                ("%.4f" % ci[0]) if ci[0] is not None else "n/a",
                ("%.4f" % ci[1]) if ci[1] is not None else "n/a",
                ("%.3f" % m["incremental_dsr"]) if m.get("incremental_dsr") is not None else "n/a",
                ("%.4f%%" % m["exited_delta_mean_pct"]) if m.get("exited_delta_mean_pct") is not None else "n/a",
                m.get("n_policy_exits"),
                m.get("positive_boundary_count"),
                "GO" if m.get("go") else "no",
                " diagnostic" if m.get("diagnostic_only") else "",
            )
        )
    print("negative controls: %s" % [c.get("verdict") for c in res.get("negative_controls", [])])
    print("VERDICT: %s" % res["verdict"])

    if not args.no_write:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        outp = out_dir / "summary.json"
        outp.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        print("wrote -> %s" % outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
