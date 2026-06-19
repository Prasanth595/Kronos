"""Experiment ① — entry skip-gate for the STOM gap-up ``ts_imb`` RULE.

**RULE strategy, NOT reinforcement learning.**  This module asks the money
question left open by ``docs/stom_rl_resume_handoff_2026-06-01.md``:

    Can causal entry microstructure identify trades that should be SKIPPED,
    improving the existing fixed-entry ``ts_imb`` rule after 23bp costs and
    marketable fills?

The target is realized, cost-adjusted net return from
``marketable_fill.simulate_rule_from_entry``.  SL labels are intentionally not
used for the trading decision: SL predictability is only a risk proxy and can
fall into the documented drift trap (SL-heavy slices may still have positive
net).  The gate therefore skips a train-selected bottom predicted-net fraction
and books a paired baseline-relative increment:

* baseline: take every ``ts_imb`` trade -> realized ``net``;
* policy: take non-skipped trades -> realized ``net``; skipped trades -> ``0``;
* incremental: ``policy - baseline`` -> ``-net`` for skipped trades, ``0`` else.

Pure stats functions are I/O-free and unit-tested.  DB extraction is isolated in
``extract_skip_samples``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from stom_rl.exit_baselines import deflated_sharpe_ratio, per_trade_sharpe
from stom_rl.marketable_fill import simulate_rule_from_entry
from stom_rl.microstructure_features import FEATURE_NAMES, causal_feature_vector
from stom_rl.predictability_probe import _COLS, _sec_of
from stom_rl.timing_gate import DEFAULT_EXTERNAL_SHARPE_VARIANCE, DEFAULT_TRIAL_LEDGER

DEFAULT_BOUNDARIES: Tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9)
DEFAULT_SKIP_FRACTIONS: Tuple[float, ...] = (0.10, 0.20, 0.30, 0.40)
DEFAULT_PRIMARY_BOUNDARY: float = 0.7


def _as_float_array(values: Sequence[float], *, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains non-finite values")
    return arr


def _validate_inputs(
    X: np.ndarray,
    net: np.ndarray,
    dates: np.ndarray,
    group_ids: np.ndarray,
) -> None:
    if X.ndim != 2:
        raise ValueError("X must be a 2D feature matrix")
    n = len(net)
    if len(X) != n or len(dates) != n or len(group_ids) != n:
        raise ValueError("X, net, dates, and group_ids must have the same length")


def _validate_skip_fractions(skip_fractions: Sequence[float]) -> Tuple[float, ...]:
    vals = tuple(float(v) for v in skip_fractions)
    if not vals:
        raise ValueError("skip_fractions must be non-empty")
    if any(v <= 0.0 or v >= 1.0 for v in vals):
        raise ValueError("each skip fraction must be in (0, 1)")
    return vals


def bottom_fraction_mask(scores: Sequence[float], skip_fraction: float) -> np.ndarray:
    """Boolean mask for the bottom predicted-net fraction.

    Uses stable rank selection instead of a threshold comparison so ties cannot
    accidentally skip the whole dataset.  At least one row is skipped for a
    non-empty input and a valid positive fraction.
    """

    pred = _as_float_array(scores, name="scores")
    if not 0.0 < float(skip_fraction) < 1.0:
        raise ValueError("skip_fraction must be in (0, 1)")
    mask = np.zeros(len(pred), dtype=bool)
    if len(pred) == 0:
        return mask
    k = min(len(pred), max(1, int(np.ceil(len(pred) * float(skip_fraction)))))
    order = np.argsort(pred, kind="mergesort")
    mask[order[:k]] = True
    return mask


def score_skip_policy(
    net: Sequence[float],
    skip_mask: Sequence[bool],
    group_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Score a skip mask against the take-all baseline.

    ``net`` is realized cost-adjusted return (%) if the trade is taken.  A skipped
    trade earns ``0``.  Therefore the baseline-relative increment is ``-net`` for
    skipped rows and ``0`` for taken rows.
    """

    net_arr = _as_float_array(net, name="net")
    skip = np.asarray(skip_mask, dtype=bool)
    if len(skip) != len(net_arr):
        raise ValueError("skip_mask and net must have the same length")

    policy = np.where(skip, 0.0, net_arr)
    inc = policy - net_arr
    skipped = net_arr[skip]
    taken = net_arr[~skip]

    out: Dict[str, Any] = {
        "n": int(len(net_arr)),
        "n_skipped": int(skip.sum()),
        "skip_fraction_realized": float(skip.mean()) if len(skip) else 0.0,
        "baseline_total_net_pct": float(net_arr.sum()) if len(net_arr) else 0.0,
        "policy_total_net_pct": float(policy.sum()) if len(policy) else 0.0,
        "incremental_total_pct": float(inc.sum()) if len(inc) else 0.0,
        "baseline_mean_net_pct": float(net_arr.mean()) if len(net_arr) else None,
        "policy_mean_net_pct": float(policy.mean()) if len(policy) else None,
        "incremental_mean_pct": float(inc.mean()) if len(inc) else None,
        "skipped_net_mean_pct": float(skipped.mean()) if len(skipped) else None,
        "taken_net_mean_pct": float(taken.mean()) if len(taken) else None,
        "drift_trap_ok": bool(len(skipped) > 0 and float(skipped.mean()) < 0.0),
        "increments": inc,
    }

    if group_ids is not None:
        groups = np.asarray([str(g) for g in group_ids])
        if len(groups) != len(net_arr):
            raise ValueError("group_ids and net must have the same length")
        group_incs = []
        for g in np.unique(groups):
            rows = groups == g
            group_incs.append(float(inc[rows].mean()))
        out["group_incremental"] = np.asarray(group_incs, dtype=float)
    return out


def select_skip_fraction(
    pred: Sequence[float],
    net: Sequence[float],
    skip_fractions: Sequence[float] = DEFAULT_SKIP_FRACTIONS,
) -> Dict[str, Any]:
    """Select ONE skip fraction using train data only.

    The selected fraction maximizes train-set incremental mean.  Ties prefer the
    smaller skip fraction to reduce turnover/selection degrees of freedom.
    """

    pred_arr = _as_float_array(pred, name="pred")
    net_arr = _as_float_array(net, name="net")
    if len(pred_arr) != len(net_arr):
        raise ValueError("pred and net must have the same length")
    fractions = _validate_skip_fractions(skip_fractions)

    rows: List[Dict[str, Any]] = []
    for frac in fractions:
        mask = bottom_fraction_mask(pred_arr, frac)
        scored = score_skip_policy(net_arr, mask)
        rows.append({
            "skip_fraction": float(frac),
            "train_incremental_mean_pct": scored["incremental_mean_pct"],
            "train_skipped_net_mean_pct": scored["skipped_net_mean_pct"],
            "train_n_skipped": scored["n_skipped"],
        })
    best = max(
        rows,
        key=lambda r: (
            float(r["train_incremental_mean_pct"]),
            -float(r["skip_fraction"]),
        ),
    )
    return {
        "selected_skip_fraction": float(best["skip_fraction"]),
        "train_scores": rows,
    }


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


def _fit_predict(X: np.ndarray, y: np.ndarray, train: np.ndarray, test: np.ndarray, *, rng_seed: int):
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(X[train])
    Xtr, Xte = scaler.transform(X[train]), scaler.transform(X[test])
    preds: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for name, model in _models(rng_seed).items():
        model.fit(Xtr, y[train])
        preds[name] = (model.predict(Xtr), model.predict(Xte))
    return preds


def _bootstrap_ci(values: np.ndarray, *, n_bootstrap: int, rng: np.random.Generator) -> Tuple[Optional[float], Optional[float]]:
    if len(values) < 2 or n_bootstrap <= 0:
        return None, None
    boot = rng.choice(values, size=(int(n_bootstrap), len(values)), replace=True).mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return float(lo), float(hi)


def _evaluate_model_boundary(
    pred_train: np.ndarray,
    pred_test: np.ndarray,
    net_train: np.ndarray,
    net_test: np.ndarray,
    test_groups: np.ndarray,
    *,
    skip_fractions: Sequence[float],
    n_bootstrap: int,
    rng: np.random.Generator,
    external_sharpe_variance: float,
    n_trials: int,
) -> Dict[str, Any]:
    selected = select_skip_fraction(pred_train, net_train, skip_fractions)
    frac = selected["selected_skip_fraction"]
    skip = bottom_fraction_mask(pred_test, frac)
    scored = score_skip_policy(net_test, skip, test_groups)
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
    drift_ok = bool(scored["drift_trap_ok"])
    return {
        "selected_skip_fraction": float(frac),
        "train_skip_fraction_scores": selected["train_scores"],
        "n_test_trades": int(len(net_test)),
        "n_sessions": int(len(group_inc)),
        "n_skipped": scored["n_skipped"],
        "skip_fraction_realized": scored["skip_fraction_realized"],
        "baseline_mean_net_pct": scored["baseline_mean_net_pct"],
        "policy_mean_net_pct": scored["policy_mean_net_pct"],
        "incremental_mean_pct": float(group_inc.mean()) if len(group_inc) else None,
        "incremental_ci95": [lo, hi],
        "ci_excludes_zero": ci_go,
        "incremental_sharpe": sr,
        "incremental_dsr": dsr,
        "dsr_gt_0_95": dsr_go,
        "skipped_net_mean_pct": scored["skipped_net_mean_pct"],
        "taken_net_mean_pct": scored["taken_net_mean_pct"],
        "drift_trap_ok": drift_ok,
        "go_components": {
            "ci_excludes_zero": ci_go,
            "dsr_gt_0_95": dsr_go,
            "skipped_net_mean_lt_0": drift_ok,
        },
        "go": False,  # filled after boundary-positive count is known
    }


def run_skip_gate(
    X: np.ndarray,
    net: Sequence[float],
    dates: Sequence[str],
    group_ids: Sequence[str],
    *,
    boundaries: Sequence[float] = DEFAULT_BOUNDARIES,
    primary_boundary: float = DEFAULT_PRIMARY_BOUNDARY,
    skip_fractions: Sequence[float] = DEFAULT_SKIP_FRACTIONS,
    n_bootstrap: int = 1000,
    rng_seed: int = 0,
    external_sharpe_variance: float = DEFAULT_EXTERNAL_SHARPE_VARIANCE,
    n_trials: int = DEFAULT_TRIAL_LEDGER,
    min_train: int = 50,
    min_test: int = 50,
) -> Dict[str, Any]:
    """Purged walk-forward entry skip-gate over realized marketable net.

    Trains on earlier sessions and tests on later sessions.  For each model and
    boundary, the skip fraction is selected on the train split only.  GO at the
    primary boundary requires:

    * incremental bootstrap CI lower bound > 0;
    * DSR >= 0.95;
    * skipped test slice has negative realized net (drift-trap guard);
    * at least 3 of 5 boundary means are positive for the same model.
    """

    X_arr = np.asarray(X, dtype=float)
    net_arr = _as_float_array(net, name="net")
    dates_arr = np.asarray([str(d) for d in dates])
    groups_arr = np.asarray([str(g) for g in group_ids])
    _validate_inputs(X_arr, net_arr, dates_arr, groups_arr)
    fractions = _validate_skip_fractions(skip_fractions)
    rng = np.random.default_rng(rng_seed)

    boundaries_t = tuple(float(b) for b in boundaries)
    uniq_dates = np.array(sorted(set(dates_arr.tolist())))
    per_boundary: Dict[str, Dict[float, Optional[float]]] = {"ridge": {}, "gbm": {}}
    primary: Dict[str, Dict[str, Any]] = {}

    for frac in boundaries_t:
        train, test = _split_by_date(dates_arr, frac)
        if train.sum() < min_train or test.sum() < min_test:
            for name in per_boundary:
                per_boundary[name][float(frac)] = None
            continue
        preds = _fit_predict(X_arr, net_arr, train, test, rng_seed=rng_seed)
        for name, (pred_train, pred_test) in preds.items():
            eval_res = _evaluate_model_boundary(
                pred_train,
                pred_test,
                net_arr[train],
                net_arr[test],
                groups_arr[test],
                skip_fractions=fractions,
                n_bootstrap=n_bootstrap,
                rng=rng,
                external_sharpe_variance=external_sharpe_variance,
                n_trials=n_trials,
            )
            per_boundary[name][float(frac)] = eval_res["incremental_mean_pct"]
            if abs(frac - primary_boundary) < 1e-9:
                primary[name] = eval_res

    results: Dict[str, Any] = {
        "n_samples": int(len(net_arr)),
        "n_groups": int(len(set(groups_arr.tolist()))),
        "n_dates": int(len(uniq_dates)),
        "n_trials": int(n_trials),
        "external_sharpe_variance": float(external_sharpe_variance),
        "primary_boundary": float(primary_boundary),
        "boundaries": [float(b) for b in boundaries_t],
        "skip_fractions": [float(v) for v in fractions],
        "per_boundary_incremental_mean": per_boundary,
        "models": {},
        "symbol_disjoint": {},
    }

    best_go = False
    for name in ("ridge", "gbm"):
        m = dict(primary.get(name, {}))
        if not m:
            continue
        positive_count = sum(
            1 for v in per_boundary.get(name, {}).values() if v is not None and float(v) > 0.0
        )
        boundary_ok = positive_count >= 3
        components = dict(m["go_components"])
        components["positive_boundaries_ge_3"] = boundary_ok
        go = bool(
            components["ci_excludes_zero"]
            and components["dsr_gt_0_95"]
            and components["skipped_net_mean_lt_0"]
            and components["positive_boundaries_ge_3"]
        )
        m["positive_boundary_count"] = int(positive_count)
        m["go_components"] = components
        m["go"] = go
        results["models"][name] = m
        best_go = best_go or go

    results["symbol_disjoint"] = _symbol_disjoint_diagnostic(
        X_arr,
        net_arr,
        dates_arr,
        groups_arr,
        primary_boundary=primary_boundary,
        skip_fractions=fractions,
        rng_seed=rng_seed,
        min_train=min_train,
        min_test=min_test,
    )
    results["verdict"] = "GO" if best_go else "NO-GO"
    return results


def _symbol_disjoint_diagnostic(
    X: np.ndarray,
    net: np.ndarray,
    dates: np.ndarray,
    groups: np.ndarray,
    *,
    primary_boundary: float,
    skip_fractions: Sequence[float],
    rng_seed: int,
    min_train: int,
    min_test: int,
) -> Dict[str, Any]:
    import zlib

    uniq_dates = np.array(sorted(set(dates.tolist())))
    if len(uniq_dates) < 3:
        return {"degenerate": True}
    cut = uniq_dates[max(0, min(len(uniq_dates) - 1, int(round(len(uniq_dates) * primary_boundary)) - 1))]
    symbols = np.array([str(g).split("_", 1)[0] for g in groups])
    pool = np.array([zlib.crc32(str(s).encode()) % 10 for s in symbols])
    train = (dates < cut) & (pool < 7)
    test = (dates > cut) & (pool >= 7)
    out: Dict[str, Any] = {
        "n_train": int(train.sum()),
        "n_test": int(test.sum()),
        "models": {},
    }
    if train.sum() < min_train or test.sum() < min_test:
        out["degenerate"] = True
        return out
    preds = _fit_predict(X, net, train, test, rng_seed=rng_seed)
    for name, (pred_train, pred_test) in preds.items():
        selected = select_skip_fraction(pred_train, net[train], skip_fractions)
        skip = bottom_fraction_mask(pred_test, selected["selected_skip_fraction"])
        scored = score_skip_policy(net[test], skip, groups[test])
        out["models"][name] = {
            "selected_skip_fraction": selected["selected_skip_fraction"],
            "incremental_mean_pct": scored["incremental_mean_pct"],
            "skipped_net_mean_pct": scored["skipped_net_mean_pct"],
            "drift_trap_ok": scored["drift_trap_ok"],
            "n_skipped": scored["n_skipped"],
        }
    return out


def run_shuffled_feature_control(
    X: np.ndarray,
    net: Sequence[float],
    dates: Sequence[str],
    group_ids: Sequence[str],
    *,
    rng_seed: int = 999,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Negative control: destroy feature/target pairing by row-shuffling X."""

    X_arr = np.asarray(X, dtype=float)
    rng = np.random.default_rng(rng_seed)
    order = rng.permutation(len(X_arr))
    return run_skip_gate(X_arr[order], net, dates, group_ids, rng_seed=rng_seed, **kwargs)


def apply_negative_control_gate(result: Dict[str, Any], negative_control: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the feature-shuffle control and enforce it as a hard GO blocker.

    Pre-registration requires the negative control to be NO-GO.  Therefore a
    primary ``GO`` is downgraded when shuffled features also produce ``GO`` (or any
    non-``NO-GO`` verdict), because the apparent edge is not distinguishable from
    a destroyed feature/target pairing.
    """

    out = dict(result)
    neg_verdict = str(negative_control.get("verdict", "")).upper()
    out["negative_control"] = {
        "verdict": neg_verdict or None,
        "models": {
            name: {
                "incremental_mean_pct": m.get("incremental_mean_pct"),
                "go": m.get("go"),
                "skipped_net_mean_pct": m.get("skipped_net_mean_pct"),
            }
            for name, m in negative_control.get("models", {}).items()
        },
    }
    out["negative_control_passed"] = neg_verdict == "NO-GO"
    if out.get("verdict") == "GO" and neg_verdict != "NO-GO":
        out["verdict_before_negative_control"] = "GO"
        out["verdict"] = "NO-GO"
        out["negative_control_blocked_go"] = True
        out["go_block_reason"] = "negative_control_not_no_go"
    else:
        out["negative_control_blocked_go"] = False
    return out


# ---------------------------------------------------------------------------
# DB extraction: ts_imb instances -> entry features + marketable costed net.
# ---------------------------------------------------------------------------
def extract_skip_samples(
    db_path: str,
    *,
    max_symbols: int = 0,
    entry_window_sec: int = 5,
    tp_pct: float = 5.0,
    sl_pct: float = 1.0,
    cost_bps: float = 23.0,
    slippage_bps: float = 0.0,
    strength_thr: float = 100.0,
    imbalance_thr: float = 0.5,
    entry_cr_thr: float = 2.0,
) -> Dict[str, Any]:
    """Extract one entry skip-gate sample per ``ts_imb`` instance.

    The entry gate matches the existing gap-up rule: first valid bar must have
    ``등락율 >= 2``, ``체결강도 >= 100``, and total-depth bid imbalance >= 0.5.
    The feature vector uses only rows up to ``entry_window_sec``.  The label is
    marketable TP5/SL1/09:25 net after 23bp costs.
    """

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
    nets: List[float] = []
    dates: List[str] = []
    groups: List[str] = []
    exit_reasons: List[str] = []
    n_instances = 0
    n_negative_net = 0
    try:
        tables = list_stock_tables(conn, max_tables=max_symbols if max_symbols > 0 else None)
        for table in tables:
            cols = set(get_table_columns(conn, table))
            if not all(c in cols for c in sel[1:]):
                continue
            qt = table.replace('"', '""')
            q_sel = ", ".join('"' + c.replace('"', '""') + '"' for c in sel)
            px_c = _COLS["px"]
            # One ordered table scan is materially faster than issuing a separate
            # range query for every (symbol, session).  The DB is already bounded to
            # the opening 09:00-09:30 window; keep a defensive second filter anyway.
            raw = conn.execute(
                'SELECT %s FROM "%s" WHERE "%s">0 ORDER BY "index"' % (q_sel, qt, px_c)
            ).fetchall()
            by_session: Dict[str, List[Dict[str, Any]]] = {}
            for r in raw:
                idx_raw = r[0]
                idx_s = str(int(idx_raw)) if idx_raw is not None else ""
                if len(idx_s) != 14:
                    continue
                sec = _sec_of(idx_raw)
                if sec < 0 or sec > 1800:
                    continue
                px = r[1]
                if px is None or float(px) <= 0:
                    continue
                sess = idx_s[:8]
                by_session.setdefault(sess, []).append({
                    "sec": sec, "price": float(px), "cr": r[2], "ts": r[3],
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
                net, reason = simulate_rule_from_entry(
                    prices,
                    bids,
                    asks,
                    secs_arr,
                    0,
                    tp_pct=tp_pct,
                    sl_pct=sl_pct,
                    cost_bps=cost_bps,
                    slippage_bps=slippage_bps,
                )
                e_last = 0
                for j, row in enumerate(rows):
                    if row["sec"] <= entry_window_sec:
                        e_last = j
                    else:
                        break
                fv = causal_feature_vector(rows[: e_last + 1])
                feats.append([fv[k] for k in FEATURE_NAMES])
                nets.append(float(net))
                dates.append(sess)
                groups.append("%s_%s" % (table, sess))
                exit_reasons.append(reason)
                n_instances += 1
                n_negative_net += int(float(net) < 0.0)
    finally:
        conn.close()

    net_arr = np.array(nets, dtype=float)
    return {
        "X": np.array(feats, dtype=float) if feats else np.zeros((0, len(FEATURE_NAMES))),
        "net": net_arr,
        "dates": dates,
        "group_ids": groups,
        "exit_reasons": exit_reasons,
        "n_instances": n_instances,
        "n_negative_net": n_negative_net,
        "negative_net_rate": (n_negative_net / n_instances) if n_instances else None,
        "mean_net_pct": float(net_arr.mean()) if len(net_arr) else None,
        "feature_names": FEATURE_NAMES,
        "entry_window_sec": entry_window_sec,
        "cost_bps": cost_bps,
        "slippage_bps": slippage_bps,
    }


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
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
    p = argparse.ArgumentParser(description="STOM ① entry skip-gate (RULE NOT RL).")
    p.add_argument("--db-path", "--db", default=str(root / "_database" / "stock_tick_back.db"))
    p.add_argument("--max-symbols", type=int, default=0)
    p.add_argument("--output-dir", default=str(root / ".omx" / "artifacts" / "skip_gate"))
    p.add_argument("--n-bootstrap", type=int, default=1000)
    p.add_argument("--rng-seed", type=int, default=0)
    p.add_argument("--slippage-bps", type=float, default=0.0)
    p.add_argument("--no-write", action="store_true")
    args = p.parse_args(argv)

    print("=== STOM ① entry skip-gate (RULE NOT RL) ===")
    d = extract_skip_samples(
        args.db_path,
        max_symbols=args.max_symbols,
        slippage_bps=args.slippage_bps,
    )
    print(
        "instances=%d mean_net=%s negative_rate=%s"
        % (
            d["n_instances"],
            ("%.4f%%" % d["mean_net_pct"]) if d["mean_net_pct"] is not None else "n/a",
            ("%.3f" % d["negative_net_rate"]) if d["negative_net_rate"] is not None else "n/a",
        )
    )
    if len(d["net"]) < 200:
        res = {
            "verdict": "INCONCLUSIVE",
            "reason": "too_few_samples_for_preregistered_gate",
            "n_samples": int(len(d["net"])),
            "extract": {
                k: v for k, v in d.items()
                if k not in {"X", "net", "dates", "group_ids", "exit_reasons"}
            },
        }
        print("too few samples for the pre-registered gate; wrote INCONCLUSIVE summary")
        if not args.no_write:
            out_dir = Path(args.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            outp = out_dir / "summary.json"
            outp.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
            print("wrote -> %s" % outp)
        return 0

    res = run_skip_gate(
        d["X"],
        d["net"],
        d["dates"],
        d["group_ids"],
        n_bootstrap=args.n_bootstrap,
        rng_seed=args.rng_seed,
    )
    neg = run_shuffled_feature_control(
        d["X"],
        d["net"],
        d["dates"],
        d["group_ids"],
        n_bootstrap=max(100, min(args.n_bootstrap, 300)),
        rng_seed=args.rng_seed + 999,
    )
    res = apply_negative_control_gate(res, neg)
    res["extract"] = {
        k: v for k, v in d.items()
        if k not in {"X", "net", "dates", "group_ids", "exit_reasons"}
    }

    print("-- primary boundary %.1f --" % res["primary_boundary"])
    for name, m in res.get("models", {}).items():
        ci = m.get("incremental_ci95") or [None, None]
        print(
            "   %-5s inc=%s CI95=[%s,%s] DSR=%s skipped_net=%s pos_bounds=%s -> %s"
            % (
                name,
                ("%.4f%%" % m["incremental_mean_pct"]) if m.get("incremental_mean_pct") is not None else "n/a",
                ("%.4f" % ci[0]) if ci[0] is not None else "n/a",
                ("%.4f" % ci[1]) if ci[1] is not None else "n/a",
                ("%.3f" % m["incremental_dsr"]) if m.get("incremental_dsr") is not None else "n/a",
                ("%.4f%%" % m["skipped_net_mean_pct"]) if m.get("skipped_net_mean_pct") is not None else "n/a",
                m.get("positive_boundary_count"),
                "GO" if m.get("go") else "no",
            )
        )
    print("negative control verdict: %s" % res["negative_control"]["verdict"])
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
