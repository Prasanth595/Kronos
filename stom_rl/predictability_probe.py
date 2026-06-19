"""Within-window predictability gate P0+P1 (the cheap deep-RL go/no-go).

**RULE strategy, NOT reinforcement learning.**  This is the decisive, CPU-only
gate from ``docs/stom_rl_deeprl_opening20min_design_2026-05-29.md``: before any
deep RL, test whether the causal per-second microstructure state predicts a
cost-relevant short-horizon forward return OUT-OF-SAMPLE at all.  If it cannot
beat a naive baseline OOS (rank-IC CI excludes 0) and translate to a net-of-cost
Deflated-Sharpe > 0.95, then every downstream RL formulation is dead and we STOP.

* **P0 — MinTRL admissibility** (Bailey & López de Prado 2012): is the smallest
  edge worth deploying even statistically distinguishable at our sample size?
* **P1 — supervised predictability probe**: Ridge + gradient-boosting on the
  causal feature vector, purged walk-forward by session DATE, Spearman rank-IC
  with session-block bootstrap CI, plus a one-trade-per-session threshold policy
  scored net of 23 bp → Deflated Sharpe.

The pure stats (``min_track_record_length``, ``run_probe`` on arrays) have no I/O
and are unit-tested; the DB extraction is separated into ``extract_samples``.
"""

from __future__ import annotations

from statistics import NormalDist, variance
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from stom_rl.exit_baselines import deflated_sharpe_ratio, per_trade_sharpe
from stom_rl.microstructure_features import FEATURE_NAMES, causal_feature_vector

DEFAULT_COST_PCT: float = 0.23  # 23 bp round trip, in percent
SD_DIFF_PCT: float = 1.2  # assumed per-trade dispersion of the incremental edge (doc §7)


# ---------------------------------------------------------------------------
# P0 — Minimum Track Record Length (admissibility).
# ---------------------------------------------------------------------------
def min_track_record_length(
    sharpe: float,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    benchmark_sharpe: float = 0.0,
    prob: float = 0.95,
) -> float:
    """Observations needed for PSR(benchmark) > prob (Bailey-López de Prado 2012).

    ``MinTRL = 1 + (1 - skew*SR + (kurt-1)/4*SR^2) * (Z_prob / (SR - SR_bench))^2``
    with per-observation Sharpe ``SR`` and non-excess ``kurtosis`` (normal = 3).
    Returns ``inf`` when ``SR <= benchmark`` (never distinguishable).
    """

    if sharpe <= benchmark_sharpe:
        return float("inf")
    z = NormalDist().inv_cdf(prob)
    num = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe ** 2
    return 1.0 + num * (z / (sharpe - benchmark_sharpe)) ** 2


def _spearman_ic(pred: np.ndarray, actual: np.ndarray) -> float:
    """Spearman rank correlation; 0.0 if degenerate (no variance / <2 points)."""

    if len(pred) < 2:
        return 0.0
    from scipy.stats import spearmanr

    rho, _ = spearmanr(pred, actual)
    return 0.0 if (rho is None or not np.isfinite(rho)) else float(rho)


def _policy_nets(
    pred: np.ndarray, y: np.ndarray, groups: np.ndarray, secs: np.ndarray, cost_pct: float
) -> np.ndarray:
    """One-trade-per-session net returns: enter at the first decision second with
    predicted forward return > cost, book the realized forward return minus cost.

    One non-overlapping trade per (symbol,session) so the resulting per-trade
    series is a clean Sharpe input (no within-session overlap inflation)."""

    nets: List[float] = []
    for g in np.unique(groups):
        rows = np.where(groups == g)[0]
        order = rows[np.argsort(secs[rows])]
        qual = [r for r in order if pred[r] > cost_pct]
        if qual:
            nets.append(float(y[qual[0]] - cost_pct))
    return np.array(nets, dtype=float)


# ---------------------------------------------------------------------------
# P1 — supervised predictability probe (pure: operates on arrays, no I/O).
# ---------------------------------------------------------------------------
def run_probe(
    X: np.ndarray,
    y: np.ndarray,
    dates: Sequence[str],
    group_ids: Sequence[str],
    secs: Sequence[float],
    *,
    boundaries: Sequence[float] = (0.5, 0.6, 0.7, 0.8, 0.9),
    primary_boundary: float = 0.7,
    cost_pct: float = DEFAULT_COST_PCT,
    n_bootstrap: int = 1000,
    rng_seed: int = 0,
) -> Dict[str, Any]:
    """Purged walk-forward predictability probe over the causal feature matrix.

    For each date boundary, train Ridge + gradient-boosting on earlier sessions
    and test on strictly later sessions (the boundary day is embargoed).  Reports,
    per model: OOS Spearman rank-IC at every boundary; at the primary boundary a
    session-block bootstrap 95% CI for the IC; and a one-trade-per-session
    threshold policy (enter at the first decision second with predicted forward
    return > cost) scored net of ``cost_pct`` → per-trade Sharpe → Deflated Sharpe
    (charging the full #models x #boundaries trial count).  ``verdict`` is GO only
    if some model has IC CI strictly > 0 AND net-of-cost DSR > 0.95.
    """

    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    dates = np.asarray([str(d) for d in dates])
    group_ids = np.asarray([str(g) for g in group_ids])
    secs = np.asarray(secs, dtype=float)
    rng = np.random.default_rng(rng_seed)

    uniq_dates = np.array(sorted(set(dates.tolist())))
    n_trials = 2 * len(boundaries)  # 2 model families x boundaries

    def _split(frac: float) -> Tuple[np.ndarray, np.ndarray]:
        cut = uniq_dates[max(0, min(len(uniq_dates) - 1, int(round(len(uniq_dates) * frac)) - 1))]
        train = dates < cut          # strictly earlier
        test = dates > cut           # strictly later (boundary day embargoed)
        return train, test

    def _models():
        return {
            "ridge": Ridge(alpha=10.0),
            "gbm": HistGradientBoostingRegressor(
                max_depth=3, max_iter=200, learning_rate=0.05,
                l2_regularization=1.0, random_state=rng_seed,
            ),
        }

    per_boundary_ic: Dict[str, Dict[float, Optional[float]]] = {"ridge": {}, "gbm": {}}
    # primary-boundary artifacts for CI + DSR
    primary_pred: Dict[str, np.ndarray] = {}
    primary_test_idx: Optional[np.ndarray] = None
    primary_y: Optional[np.ndarray] = None
    policy_sharpes: List[float] = []  # across all (model, boundary) configs -> DSR variance

    for frac in boundaries:
        train, test = _split(frac)
        if train.sum() < 50 or test.sum() < 50:
            for m in per_boundary_ic:
                per_boundary_ic[m][float(frac)] = None
            continue
        scaler = StandardScaler().fit(X[train])
        Xtr, Xte = scaler.transform(X[train]), scaler.transform(X[test])
        for name, model in _models().items():
            model.fit(Xtr, y[train])
            pred = model.predict(Xte)
            per_boundary_ic[name][float(frac)] = _spearman_ic(pred, y[test])
            nets_b = _policy_nets(pred, y[test], group_ids[test], secs[test], cost_pct)
            sr_b = per_trade_sharpe(nets_b.tolist()) if len(nets_b) >= 2 else None
            if sr_b is not None:
                policy_sharpes.append(sr_b)
            if abs(frac - primary_boundary) < 1e-9:
                primary_pred[name] = pred
        if abs(frac - primary_boundary) < 1e-9:
            primary_test_idx = np.where(test)[0]
            primary_y = y[test]

    # Data-derived cross-config Sharpe dispersion for DSR (mirrors exit_baselines),
    # floored; replaces a hardcoded variance so the deflation bar is principled.
    sharpe_var = max(variance(policy_sharpes), 1e-4) if len(policy_sharpes) >= 2 else 0.25

    results: Dict[str, Any] = {
        "n_samples": int(len(y)),
        "n_groups": int(len(set(group_ids.tolist()))),
        "n_dates": int(len(uniq_dates)),
        "n_trials": n_trials,
        "primary_boundary": primary_boundary,
        "cost_pct": cost_pct,
        "sharpe_variance": float(sharpe_var),
        "per_boundary_ic": per_boundary_ic,
        "models": {},
    }

    best_go = False
    if primary_test_idx is not None and primary_y is not None and len(primary_y) >= 2:
        test_groups = group_ids[primary_test_idx]
        test_secs = secs[primary_test_idx]
        uniq_test_groups = np.array(sorted(set(test_groups.tolist())))
        for name in ("ridge", "gbm"):
            pred = primary_pred.get(name)
            if pred is None:
                continue
            ic = _spearman_ic(pred, primary_y)
            # session-block bootstrap CI for IC (resample test GROUPS w/ replacement)
            g_to_rows = {g: np.where(test_groups == g)[0] for g in uniq_test_groups}
            boot = []
            for _ in range(n_bootstrap):
                pick = rng.choice(uniq_test_groups, size=len(uniq_test_groups), replace=True)
                rows = np.concatenate([g_to_rows[g] for g in pick])
                boot.append(_spearman_ic(pred[rows], primary_y[rows]))
            lo, hi = np.percentile(boot, [2.5, 97.5])
            # one-trade-per-session threshold policy, net of cost
            nets: List[float] = []
            for g in uniq_test_groups:
                rows = g_to_rows[g]
                order = rows[np.argsort(test_secs[rows])]
                qual = [r for r in order if pred[r] > cost_pct]
                if qual:
                    nets.append(float(primary_y[qual[0]] - cost_pct))
            nets_arr = np.array(nets) if nets else np.array([])
            sr = per_trade_sharpe(nets_arr.tolist()) if len(nets_arr) >= 2 else None
            dsr = (
                deflated_sharpe_ratio(
                    sr, n_trials=n_trials, sharpe_variance=sharpe_var,
                    n_samples=len(nets_arr),
                )
                if sr is not None else None
            )
            ic_go = lo > 0.0
            dsr_go = dsr is not None and dsr > 0.95
            go = bool(ic_go and dsr_go)
            best_go = best_go or go
            results["models"][name] = {
                "ic_primary": ic,
                "ic_ci95": [float(lo), float(hi)],
                "ic_ci_excludes_zero": bool(ic_go),
                "n_policy_trades": int(len(nets_arr)),
                "policy_mean_net_pct": float(nets_arr.mean()) if len(nets_arr) else None,
                "policy_sharpe": sr,
                "policy_dsr": dsr,
                "dsr_gt_0_95": bool(dsr_go),
                "go": go,
            }

    # Symbol-disjoint robustness IC (unseen tickers, date-purged) — design §3-P1
    # "purge by symbol": train on 70% of symbols' earlier sessions, test on the
    # held-out 30% of symbols' later sessions, so the date-only primary IC (an
    # upper bound) is checked against per-ticker memorization.
    import zlib

    symbols = np.array([g.split("_", 1)[0] for g in group_ids])
    cut_idx = max(0, min(len(uniq_dates) - 1, int(round(len(uniq_dates) * primary_boundary)) - 1))
    cut = uniq_dates[cut_idx]
    pool = np.array([zlib.crc32(s.encode()) % 10 for s in symbols])
    tr_sd = (dates < cut) & (pool < 7)
    te_sd = (dates > cut) & (pool >= 7)
    results["symbol_disjoint_ic"] = {}
    if tr_sd.sum() >= 50 and te_sd.sum() >= 50:
        sc = StandardScaler().fit(X[tr_sd])
        Xtr2, Xte2 = sc.transform(X[tr_sd]), sc.transform(X[te_sd])
        for name, model in _models().items():
            model.fit(Xtr2, y[tr_sd])
            results["symbol_disjoint_ic"][name] = _spearman_ic(model.predict(Xte2), y[te_sd])

    results["verdict"] = "GO" if best_go else "NO-GO"
    return results


# ---------------------------------------------------------------------------
# DB extraction (I/O): ts_imb instances -> causal samples (features + label).
# ---------------------------------------------------------------------------
_COLS = {
    "ts": "현재가", "px": "현재가", "cr": "등락율", "strength": "체결강도",
    "buy_val": "초당매수금액", "sell_val": "초당매도금액",
    "buy_qty": "초당매수수량", "sell_qty": "초당매도수량",
    "bid_tot": "매수총잔량", "ask_tot": "매도총잔량",
    "bid1": "매수호가1", "ask1": "매도호가1", "bidq1": "매수잔량1", "askq1": "매도잔량1",
}


def _sec_of(ts: int) -> int:
    s = str(int(ts))
    return int(s[8:10]) * 3600 + int(s[10:12]) * 60 + int(s[12:14]) - 9 * 3600


def extract_samples(
    db_path: str,
    *,
    max_symbols: int = 0,
    sample_every_sec: int = 10,
    horizon_sec: int = 60,
    window_end_sec: int = 1140,  # 09:19:00 (leave horizon to 09:20)
    strength_thr: float = 100.0,
    imbalance_thr: float = 0.5,
    entry_cr_thr: float = 2.0,
) -> Dict[str, Any]:
    """Read the DB and emit causal (features, forward-return label) samples.

    Only (symbol,session) instances passing the ts_imb ENTRY gate at the first bar
    (등락율>=2 AND 체결강도>=100 AND 매수총잔량 imbalance>=0.5) are used.  For each,
    decision seconds are sampled every ``sample_every_sec`` in [10, window_end_sec];
    features are the causal vector from rows<=t; the label is the forward
    ``horizon_sec`` return.  Returns arrays (X, y, dates, group_ids, secs).
    """

    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from finetune_csv.stom_tick_dataset import connect_readonly, get_table_columns, list_stock_tables

    conn = connect_readonly(db_path)
    feats_rows: List[List[float]] = []
    ys: List[float] = []
    dates: List[str] = []
    groups: List[str] = []
    secs_out: List[float] = []
    n_instances = 0
    try:
        tables = list_stock_tables(conn, max_tables=max_symbols if max_symbols > 0 else None)
        sel = ["index"] + [_COLS[k] for k in (
            "px", "cr", "strength", "buy_val", "sell_val", "buy_qty", "sell_qty",
            "bid_tot", "ask_tot", "bid1", "ask1", "bidq1", "askq1")]
        for table in tables:
            cols = set(get_table_columns(conn, table))
            if not all(c in cols for c in sel[1:]):
                continue
            q_sel = ", ".join('"' + c.replace('"', '""') + '"' for c in sel)
            date_q = 'SELECT DISTINCT substr(CAST("index" AS TEXT),1,8) FROM "%s"' % table.replace('"', '""')
            sessions = [str(r[0]) for r in conn.execute(date_q).fetchall()
                        if r[0] is not None and len(str(r[0])) == 8 and str(r[0]).isdigit()]
            qt = table.replace('"', '""')
            cr_c, st_c = _COLS["cr"], _COLS["strength"]
            bt_c, at_c, px_c = _COLS["bid_tot"], _COLS["ask_tot"], _COLS["px"]
            # First VALID-price bar so the prefilter gate is EXACTLY the in-loop
            # gate (entry = first row with price>0), not a data-dependent superset.
            prefilter_q = (
                'SELECT "%s","%s","%s","%s" FROM "%s" WHERE "index">=? AND "index"<=? '
                'AND "%s">0 ORDER BY "index" LIMIT 1' % (cr_c, st_c, bt_c, at_c, qt, px_c)
            )
            for sess in sorted(sessions):
                lo, hi = int(sess + "090000"), int(sess + "093000")
                # Cheap first-bar pre-filter: skip the full ~1000-bar pull unless the
                # entry bar already passes the ts_imb gate (the vast majority fail).
                pre = conn.execute(prefilter_q, (lo, hi)).fetchall()
                if not pre:
                    continue
                pcr, pts, pbt, pat = pre[0]
                if pcr is None or float(pcr) < entry_cr_thr or pts is None or float(pts) < strength_thr:
                    continue
                psum = (float(pbt) if pbt is not None else 0.0) + (float(pat) if pat is not None else 0.0)
                if psum <= 0 or (float(pbt) if pbt is not None else 0.0) / psum < imbalance_thr:
                    continue
                q = ('SELECT %s FROM "%s" WHERE "index">=? AND "index"<=? ORDER BY "index"'
                     % (q_sel, qt))
                raw = conn.execute(q, (lo, hi)).fetchall()
                if len(raw) < 120:
                    continue
                rows: List[Dict[str, Any]] = []
                for r in raw:
                    px = r[1]
                    if px is None or float(px) <= 0:
                        continue
                    if len(str(int(r[0]))) != 14:  # malformed index -> skip row, not abort
                        continue
                    rows.append({
                        "sec": _sec_of(r[0]), "price": float(px), "cr": r[2], "ts": r[3],
                        "buy_val": r[4], "sell_val": r[5], "buy_qty": r[6], "sell_qty": r[7],
                        "bid_tot": r[8], "ask_tot": r[9], "bid1": r[10], "ask1": r[11],
                        "bidq1": r[12], "askq1": r[13],
                    })
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
                n_instances += 1
                secs_arr = [rr["sec"] for rr in rows]
                gid = "%s_%s" % (table, sess)
                year = sess[:4]
                ti = 0
                last_pair = None
                for tsec in range(sample_every_sec, window_end_sec + 1, sample_every_sec):
                    while ti + 1 < len(rows) and secs_arr[ti + 1] <= tsec:
                        ti += 1
                    if secs_arr[ti] > tsec:
                        continue
                    fj = ti
                    target = tsec + horizon_sec
                    while fj + 1 < len(rows) and secs_arr[fj + 1] <= target:
                        fj += 1
                    if fj <= ti:
                        continue
                    if (ti, fj) == last_pair:  # sparse window -> skip duplicate (feature,label)
                        continue
                    last_pair = (ti, fj)
                    label = (rows[fj]["price"] / rows[ti]["price"] - 1.0) * 100.0
                    fv = causal_feature_vector(rows[:ti + 1])
                    feats_rows.append([fv[k] for k in FEATURE_NAMES])
                    ys.append(label)
                    dates.append(sess)
                    groups.append(gid)
                    secs_out.append(float(tsec))
    finally:
        conn.close()
    return {
        "X": np.array(feats_rows, dtype=float) if feats_rows else np.zeros((0, len(FEATURE_NAMES))),
        "y": np.array(ys, dtype=float),
        "dates": dates, "group_ids": groups, "secs": np.array(secs_out, dtype=float),
        "feature_names": FEATURE_NAMES, "n_instances": n_instances,
        "horizon_sec": horizon_sec,
    }


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
    p = argparse.ArgumentParser(description="P0+P1 predictability gate (RULE NOT RL).")
    p.add_argument("--db", default=str(root / "_database" / "stock_tick_back.db"))
    p.add_argument("--max-symbols", type=int, default=0)
    p.add_argument("--horizon-sec", type=int, default=60)
    p.add_argument("--sample-every-sec", type=int, default=10)
    p.add_argument("--json-out", default=str(root / ".omx" / "artifacts" / "predictability" / "summary.json"))
    args = p.parse_args(argv)

    print("=== P0+P1 within-window predictability gate (RULE strategy, NOT RL) ===")
    data = extract_samples(
        args.db, max_symbols=args.max_symbols,
        horizon_sec=args.horizon_sec, sample_every_sec=args.sample_every_sec,
    )
    print("instances(ts_imb)=%d  samples=%d  groups=%d  features=%d  horizon=%ds"
          % (data["n_instances"], len(data["y"]), len(set(data["group_ids"])),
             len(data["feature_names"]), data["horizon_sec"]))
    if len(data["y"]) < 200:
        print("too few samples — abort")
        return 0

    # P0: MinTRL admissibility for a few target incremental edges (sd_diff ~1.2%).
    print("-- P0 MinTRL admissibility (sd_diff~1.2%/trade, prob 0.95) --")
    for edge in (0.10, 0.20, 0.30):
        need = min_track_record_length(edge / SD_DIFF_PCT, prob=0.95)
        print("   target +%.2f%%/trade -> needs %.0f trades (have %d episodes)"
              % (edge, need, data["n_instances"]))

    res = run_probe(data["X"], data["y"], data["dates"], data["group_ids"], data["secs"],
                    cost_pct=DEFAULT_COST_PCT)
    print("-- P1 supervised probe (purged walk-forward, primary boundary %.1f) --" % res["primary_boundary"])
    for name, m in res.get("models", {}).items():
        print("   %-5s IC=%+.4f CI95=[%+.4f,%+.4f] excl0=%s | trades=%d net=%s sharpe=%s DSR=%s -> %s"
              % (name, m["ic_primary"], m["ic_ci95"][0], m["ic_ci95"][1], m["ic_ci_excludes_zero"],
                 m["n_policy_trades"],
                 ("%+.3f%%" % m["policy_mean_net_pct"]) if m["policy_mean_net_pct"] is not None else "n/a",
                 ("%.3f" % m["policy_sharpe"]) if m["policy_sharpe"] is not None else "n/a",
                 ("%.3f" % m["policy_dsr"]) if m["policy_dsr"] is not None else "n/a",
                 "GO" if m["go"] else "no"))
    print("   per-boundary IC:", {k: {b: (round(v, 4) if v is not None else None) for b, v in d.items()}
                                   for k, d in res["per_boundary_ic"].items()})
    if res.get("symbol_disjoint_ic"):
        print("   symbol-disjoint IC (unseen tickers):",
              {k: round(v, 4) for k, v in res["symbol_disjoint_ic"].items()})
    print("   DSR sharpe_variance (data-derived):", round(res.get("sharpe_variance", 0.0), 4))
    print("\nVERDICT: %s  (GO needs IC CI>0 AND net-of-cost DSR>0.95; else STOP — no deep RL)" % res["verdict"])

    outp = Path(args.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    res["n_instances"] = data["n_instances"]
    res["horizon_sec"] = data["horizon_sec"]
    outp.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print("wrote -> %s" % outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
