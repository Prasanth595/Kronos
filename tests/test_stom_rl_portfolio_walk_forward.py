import numpy as np
import pandas as pd

from stom_rl.portfolio_env import PortfolioEnv, PortfolioEnvConfig
from stom_rl.portfolio_walk_forward import (
    COST_AWARE_MIN_HOLD_STEPS,
    PortfolioWalkForwardConfig,
    _fit_cost_aware_policy,
    build_expanding_window_folds,
    run_portfolio_walk_forward,
    shuffle_candidate_signal,
)


def _holdout_candidates(n_steps: int = 12) -> pd.DataFrame:
    """Tiny in-memory candidate frame with many distinct timestamps.

    Two symbols, ``n_steps`` one-second bars each, carrying the Page 9 T+1 fill
    contract (``price`` = close at T, ``fill_price`` = next-bar close, last bar
    unfillable).  Enough distinct timestamps for a real train/test split with no
    DB dependency.
    """

    base = pd.Timestamp("2025-07-09 09:00:00")
    rows = []
    for symbol, start in (("A", 100.0), ("B", 50.0)):
        series = [start + step for step in range(n_steps)]
        for t, price in enumerate(series):
            fill = series[t + 1] if t + 1 < len(series) else float("nan")
            rows.append(
                {
                    "timestamp": (base + pd.Timedelta(seconds=t)).isoformat(),
                    "symbol": symbol,
                    "condition_id": "holdout_fixture",
                    "passed": True,
                    "rank_score": float((100 - t) if symbol == "A" else (50 - t)),
                    "price": float(price),
                    "fill_price": fill,
                    "fillable": not np.isnan(fill),
                    "feature_momentum": float(t),
                }
            )
    return pd.DataFrame(rows)


def _config(tmp_path, **overrides) -> PortfolioWalkForwardConfig:
    params = dict(output_dir=str(tmp_path), n_folds=3, max_steps_per_fold=8, write_artifacts=False)
    params.update(overrides)
    return PortfolioWalkForwardConfig(**params)


def test_eval_segment_is_disjoint_and_strictly_later_than_train():
    """Every fold's TEST timestamps are disjoint from AND strictly later than TRAIN."""

    frame = _holdout_candidates()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    folds = build_expanding_window_folds(frame, n_folds=3)

    assert len(folds) >= 2
    for fold in folds:
        train_ts = set(pd.Timestamp(ts) for ts in fold.train_frame["timestamp"].unique())
        test_ts = set(pd.Timestamp(ts) for ts in fold.test_frame["timestamp"].unique())
        assert train_ts and test_ts
        # Disjoint: no shared timestamp between train and test (no in-sample eval).
        assert not (train_ts & test_ts)
        # Strictly later: the earliest test bar comes after the latest train bar.
        assert min(test_ts) > max(train_ts)
        # Expanding window: train of fold N contains train of fold N-1.
    for earlier, later in zip(folds, folds[1:]):
        earlier_train = set(pd.Timestamp(ts) for ts in earlier.train_frame["timestamp"].unique())
        later_train = set(pd.Timestamp(ts) for ts in later.train_frame["timestamp"].unique())
        assert earlier_train < later_train


def test_fold_split_is_deterministic(tmp_path):
    """Same input + seed -> identical fold rows (split + eval determinism)."""

    config = _config(tmp_path)
    first = run_portfolio_walk_forward(config)
    second = run_portfolio_walk_forward(config)
    assert first["fold_periods"] == second["fold_periods"]
    assert first["folds"] == second["folds"]


def test_baseline_metrics_are_populated(tmp_path):
    """The fold report carries the 5 baselines + costed metrics on the TEST segment."""

    payload = run_portfolio_walk_forward(_config(tmp_path))

    assert payload["summary"]["smoke_success"] is True
    assert payload["summary"]["cost_bps"] == 25.0
    policies = {row["policy"] for row in payload["folds"]}
    assert policies == {
        "no_trade",
        "equal_weight_candidate",
        "buy_and_hold",
        "rule_baseline",
        "rl_baseline",
        "cost_aware",
    }
    # Each fold period exposes explicit train/test ranges.
    for period in payload["fold_periods"]:
        assert period["train_end"] < period["test_start"]
        assert period["test_candidate_count"] > 0
    # Costed metrics are present on every row, with cost_bps kept explicit.
    for row in payload["folds"]:
        for key in ("return_pct", "max_drawdown_pct", "turnover", "trade_count", "total_cost", "cost_bps"):
            assert key in row
        assert row["cost_bps"] == 25.0
        assert row["total_cost"] >= 0.0
        assert row["turnover"] >= 0.0


def test_walk_forward_writes_fold_report_artifacts(tmp_path):
    payload = run_portfolio_walk_forward(_config(tmp_path, write_artifacts=True))
    assert (tmp_path / "portfolio_walk_forward_report.json").is_file()
    assert (tmp_path / "portfolio_walk_forward_folds.csv").is_file()
    assert payload["summary"]["holdout"] == "expanding_window_train_le_N_eval_N_plus_1"


def _policy_returns(payload, policy):
    return [row["return_pct"] for row in payload["folds"] if row["policy"] == policy]


def test_leakage_canary_future_column_does_not_change_holdout_eval(tmp_path):
    """Backward-only canary: a forward-looking *column* must not alter results.

    We inject a column whose values are the *next bar's* price (``future_close``)
    plus a perfect ``future_return`` — exactly the kind of forward-looking signal
    a leaky pipeline would consume.  The split geometry is untouched (same
    timestamps), so any change in held-out metrics would be a pure leak.  The
    correct backward-only env ignores unknown future columns, so the fold report
    is byte-identical with and without the injected future signal.
    """

    frame = _holdout_candidates(n_steps=12)
    clean_csv = tmp_path / "clean_cols.csv"
    frame.to_csv(clean_csv, index=False, encoding="utf-8-sig")

    leaky = frame.copy()
    # Perfect foresight columns: the realised next-bar move, only knowable later.
    leaky["future_close"] = leaky["fill_price"].fillna(leaky["price"])
    leaky["future_return"] = (leaky["future_close"] - leaky["price"]) / leaky["price"]
    leaky_csv = tmp_path / "leaky_cols.csv"
    leaky.to_csv(leaky_csv, index=False, encoding="utf-8-sig")

    clean_payload = run_portfolio_walk_forward(_config(tmp_path, candidate_path=str(clean_csv)))
    leaky_payload = run_portfolio_walk_forward(_config(tmp_path, candidate_path=str(leaky_csv)))

    # Identical timestamps -> identical splits; backward-only eval ignores the
    # future columns, so the held-out fold report is unchanged.  If a leak were
    # introduced (the env consuming future_return), these would diverge.
    assert clean_payload["fold_periods"] == leaky_payload["fold_periods"]
    assert clean_payload["folds"] == leaky_payload["folds"]


def test_leakage_canary_detects_forward_looking_corruption(tmp_path):
    """The canary has teeth: corrupting the TEST segment's prices shifts results.

    This proves the harness is sensitive to the data it evaluates on, so a real
    forward-looking leak (e.g. fills using a future price) would be *detected*
    as a performance change rather than silently passing.
    """

    frame = _holdout_candidates(n_steps=12)
    clean_csv = tmp_path / "clean.csv"
    frame.to_csv(clean_csv, index=False, encoding="utf-8-sig")
    clean = run_portfolio_walk_forward(_config(tmp_path, candidate_path=str(clean_csv)))

    corrupted = frame.copy()
    # Inject a forward-looking shock into fill prices (a leak would raise fills).
    corrupted["fill_price"] = corrupted["fill_price"] * 5.0
    corrupt_csv = tmp_path / "corrupt.csv"
    corrupted.to_csv(corrupt_csv, index=False, encoding="utf-8-sig")
    corrupt = run_portfolio_walk_forward(_config(tmp_path, candidate_path=str(corrupt_csv)))

    clean_returns = _policy_returns(clean, "rl_baseline")
    corrupt_returns = _policy_returns(corrupt, "rl_baseline")
    # Performance changes (collapses/inflates) under forward-looking corruption.
    assert clean_returns != corrupt_returns


def test_cost_aware_policy_fits_on_train_and_freezes_params(tmp_path):
    """The cost-aware policy is genuinely FIT on TRAIN, then frozen for TEST.

    The fold report carries the frozen (rank_score threshold, min-hold) params
    on every cost_aware row, and the fitted min-hold is drawn from the bounded
    TRAIN tuning grid.  This proves a real fit happened on train (not a no-op)
    before the disjoint, strictly-later TEST eval.
    """

    payload = run_portfolio_walk_forward(_config(tmp_path))
    cost_rows = [row for row in payload["folds"] if row["policy"] == "cost_aware"]
    assert cost_rows, "cost_aware policy must appear in the fold report"
    for row in cost_rows:
        # Frozen params are present and concrete on every held-out fold.
        assert row["fitted_score_threshold"] != ""
        assert int(row["fitted_min_hold_steps"]) in COST_AWARE_MIN_HOLD_STEPS
        # Costed metrics are still reported (honest comparison vs baselines).
        assert row["cost_bps"] == 25.0
        assert row["total_cost"] >= 0.0


def test_cost_aware_fit_uses_only_train_segment_no_test_leakage(tmp_path):
    """Fitting only sees TRAIN: perturbing the TEST tail must not change the fit.

    We build two frames identical on the TRAIN portion but differing on the
    last (latest) timestamp — which falls in a fold's TEST segment.  Because
    ``_fit_cost_aware_policy`` is handed only the train_frame, the frozen params
    of the *earliest* fold (whose train excludes the perturbed tail) must be
    byte-identical.  Any change would mean the fitter peeked at TEST data.
    """

    frame = _holdout_candidates(n_steps=12)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    folds = build_expanding_window_folds(frame, n_folds=3)
    fold0 = folds[0]
    config = _config(tmp_path)

    # Perturb only rows strictly later than fold0's train (i.e. its TEST/future).
    train_max = max(pd.Timestamp(ts) for ts in fold0.train_frame["timestamp"].unique())
    perturbed = frame.copy()
    later = perturbed["timestamp"] > train_max
    assert later.any(), "fixture must have rows later than fold0 train"
    perturbed.loc[later, "rank_score"] = perturbed.loc[later, "rank_score"] + 1000.0
    perturbed.loc[later, "price"] = perturbed.loc[later, "price"] * 3.0

    perturbed_folds = build_expanding_window_folds(perturbed, n_folds=3)
    perturbed_fold0 = perturbed_folds[0]
    # fold0's TRAIN is untouched by a TEST-only perturbation.
    pd.testing.assert_frame_equal(
        fold0.train_frame.reset_index(drop=True),
        perturbed_fold0.train_frame.reset_index(drop=True),
    )

    fit_clean = _fit_cost_aware_policy(fold0.train_frame, config, fold0.fold_index)
    fit_perturbed = _fit_cost_aware_policy(perturbed_fold0.train_frame, config, perturbed_fold0.fold_index)
    # Same TRAIN ⇒ identical frozen params, regardless of the future TEST tail.
    assert fit_clean.frozen_params == fit_perturbed.frozen_params


def test_too_few_timestamps_raises(tmp_path):
    """A single distinct timestamp cannot form a holdout split (fails loudly)."""

    frame = _holdout_candidates(n_steps=1)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    try:
        build_expanding_window_folds(frame, n_folds=3)
    except ValueError as exc:
        assert "two time segments" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError for too few timestamps")


def _multi_candidate_frame(n_steps: int = 8) -> pd.DataFrame:
    """Candidate frame with THREE symbols per timestamp (so selection is real).

    Each timestamp has 3 competing candidates with distinct rank_scores and a
    feature column, so the env's top_k re-rank actually chooses between them —
    the precondition for the shuffle test to be able to change selection.
    """

    base = pd.Timestamp("2025-08-30 09:00:00")
    rows = []
    for sym_i, (symbol, start) in enumerate((("A", 100.0), ("B", 50.0), ("C", 75.0))):
        series = [start + step + sym_i for step in range(n_steps)]
        for t, price in enumerate(series):
            fill = series[t + 1] if t + 1 < len(series) else float("nan")
            rows.append(
                {
                    "timestamp": (base + pd.Timedelta(seconds=t)).isoformat(),
                    "symbol": symbol,
                    "condition_id": "shuffle_fixture",
                    "passed": True,
                    # Distinct, symbol-separated scores so the top_k pick is unambiguous.
                    "rank_score": float((sym_i + 1) * 10 + t),
                    "price": float(price),
                    "fill_price": fill,
                    "fillable": not np.isnan(fill),
                    "feature_momentum": float(sym_i * 100 + t),
                }
            )
    return pd.DataFrame(rows)


def _env_topk_selection(frame: pd.DataFrame, top_k: int = 2) -> dict:
    """Per-timestamp env top_k selection (symbol order after the env re-rank)."""

    env = PortfolioEnv(
        PortfolioEnvConfig(top_k_candidates=top_k, max_positions=2, seed=100),
        candidates=frame,
    )
    selection = {}
    for ts in sorted(env.candidates["timestamp"].unique()):
        rows = env.candidates[env.candidates["timestamp"] == ts]
        ordered = rows.sort_values(["rank_score", "symbol"], ascending=[False, True]).head(top_k)
        selection[str(ts)] = list(ordered["symbol"])
    return selection


def test_shuffle_changes_candidate_selection_order(tmp_path):
    """V8b: the shuffle (rank_score overwrite) yields a DIFFERENT top_k selection.

    Proves the shuffle actually perturbs selection and is not silently cancelled
    by the env's re-rank (which sorts by rank_score before head(top_k)).  At one
    or more timestamps the shuffled frame must select a different symbol set.
    """

    frame = _multi_candidate_frame(n_steps=8)
    shuffled = shuffle_candidate_signal(frame, seed=7)

    real_sel = _env_topk_selection(frame, top_k=2)
    shuf_sel = _env_topk_selection(shuffled, top_k=2)
    assert real_sel.keys() == shuf_sel.keys()
    differing = [ts for ts in real_sel if real_sel[ts] != shuf_sel[ts]]
    assert differing, "shuffle must change the top_k selection at >=1 timestamp"


def test_shuffle_keeps_price_fill_symbol_untouched():
    """The shuffle scrambles ONLY signal columns; fills/accounting stay identical.

    price / fill_price / symbol / timestamp / fillable are byte-identical to the
    real frame (per row), so realised fills and cost accounting are unchanged —
    only rank_score + feature_* are permuted within each timestamp.
    """

    frame = _multi_candidate_frame(n_steps=8)
    shuffled = shuffle_candidate_signal(frame, seed=3)

    # Normalize the timestamp dtype (the shuffle parses to datetime) and align on
    # the stable (timestamp, symbol) key — each pair is unique in the fixture.
    a = frame.copy()
    a["timestamp"] = pd.to_datetime(a["timestamp"])
    key = ["timestamp", "symbol"]
    a = a.set_index(key).sort_index()
    b = shuffled.set_index(key).sort_index()
    for col in ("price", "fill_price", "fillable"):
        pd.testing.assert_series_equal(a[col], b[col], check_names=False)
    # The signal columns DO change for at least some rows (it really shuffled).
    assert not a["rank_score"].equals(b["rank_score"])


def test_shuffle_is_deterministic_for_a_fixed_seed():
    """Same seed -> identical shuffle (auditable, reproducible §7 sanity check)."""

    frame = _multi_candidate_frame(n_steps=8)
    first = shuffle_candidate_signal(frame, seed=42)
    second = shuffle_candidate_signal(frame, seed=42)
    pd.testing.assert_frame_equal(first, second)


def test_shuffle_signal_runs_end_to_end_through_walk_forward(tmp_path):
    """The --shuffle-signal path runs the full holdout and flags it in the summary."""

    frame = _multi_candidate_frame(n_steps=12)
    csv = tmp_path / "multi.csv"
    frame.to_csv(csv, index=False, encoding="utf-8-sig")

    payload = run_portfolio_walk_forward(
        _config(tmp_path, candidate_path=str(csv), shuffle_signal=True, shuffle_seed=11)
    )
    assert payload["summary"]["shuffle_signal"] is True
    assert payload["summary"]["shuffle_seed"] == 11
    assert payload["summary"]["smoke_success"] is True
