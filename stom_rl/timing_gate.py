"""P1b — baseline-relative, de-idealized entry-timing gate (the decisive deep-RL test).

**RULE strategy, NOT reinforcement learning.**

P1 found a real ranking signal but scored it with idealized fills and NOT
baseline-relative, so its apparent "GO" conflated the model's selection skill with
the gap-up momentum drift the RULE already harvests.  P1b closes both gaps:

* **De-idealized fills**: every entry/exit is MARKETABLE (buy at the ask, sell at
  the bid) via :mod:`stom_rl.marketable_fill`, so the spread is paid twice and the
  60-second idealization is gone.  The label for a decision second ``t`` is the
  de-idealized net of ENTERING at ``t`` and holding to the RULE's exit (TP5/SL1/
  09:25).
* **Baseline-relative**: the model's chosen entry is compared PAIRED, per session,
  against the RULE's fixed 09:00 entry (same de-idealized exit).  The incremental
  series ``model_net - rule_net`` is what must be positive — so beating the
  unconditional drift the rule already captures is NOT rewarded.

GO requires the incremental mean's session-block bootstrap CI to exclude 0 AND a
Deflated Sharpe > 0.95 computed with a CONSERVATIVE external Sharpe dispersion
(not the too-small within-probe one that inflated P1).  Else STOP — the model's
timing adds nothing over the rule and deep RL is not worth building.

Pure stats (``run_timing_gate`` on arrays) have no I/O; DB extraction is isolated.
"""

from __future__ import annotations

from statistics import NormalDist
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from stom_rl.exit_baselines import deflated_sharpe_ratio, per_trade_sharpe
from stom_rl.marketable_fill import simulate_rule_from_entry
from stom_rl.microstructure_features import FEATURE_NAMES, causal_feature_vector
from stom_rl.predictability_probe import _COLS, _sec_of

# Conservative EXTERNAL per-trade Sharpe dispersion for DSR (NOT the within-probe
# cross-config variance, which is too small and inflated P1's DSR).  SD ~0.08 of a
# per-trade Sharpe across the broad strategy search the lab has run.
DEFAULT_EXTERNAL_SHARPE_VARIANCE: float = 0.08 ** 2
# Lab trial ledger: many strategies/configs tried across the whole lab (1s/1min/
# session selection, exit grid, this probe family). Conservative count for DSR.
DEFAULT_TRIAL_LEDGER: int = 40


def run_timing_gate(
    X: np.ndarray,
    y: np.ndarray,                 # de-idealized net (%) of entering at this decision t
    dates: Sequence[str],
    group_ids: Sequence[str],
    secs: Sequence[float],
    baseline_net: Sequence[float],  # rule's fixed-09:00 de-idealized net (%), per sample's session
    *,
    boundaries: Sequence[float] = (0.5, 0.6, 0.7, 0.8, 0.9),
    primary_boundary: float = 0.7,
    n_bootstrap: int = 1000,
    rng_seed: int = 0,
    external_sharpe_variance: float = DEFAULT_EXTERNAL_SHARPE_VARIANCE,
    n_trials: int = DEFAULT_TRIAL_LEDGER,
) -> Dict[str, Any]:
    """Walk-forward, baseline-relative, de-idealized entry-timing gate.

    Per date boundary, train Ridge + gradient-boosting to predict the de-idealized
    entry-net ``y`` from causal features; on the test split, the model's policy
    picks, per session, the decision second with the highest PREDICTED entry-net and
    books that entry's REALIZED de-idealized net.  The incremental series is
    ``model_net - rule_baseline_net`` per session; GO needs its bootstrap CI > 0 and
    DSR > 0.95 (conservative external variance + lab trial ledger).
    """

    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    dates = np.asarray([str(d) for d in dates])
    group_ids = np.asarray([str(g) for g in group_ids])
    secs = np.asarray(secs, dtype=float)
    baseline_net = np.asarray(baseline_net, dtype=float)
    rng = np.random.default_rng(rng_seed)
    uniq_dates = np.array(sorted(set(dates.tolist())))

    def _split(frac):
        cut = uniq_dates[max(0, min(len(uniq_dates) - 1, int(round(len(uniq_dates) * frac)) - 1))]
        return dates < cut, dates > cut

    def _models():
        return {
            "ridge": Ridge(alpha=10.0),
            "gbm": HistGradientBoostingRegressor(
                max_depth=3, max_iter=200, learning_rate=0.05,
                l2_regularization=1.0, random_state=rng_seed),
        }

    def _incremental_per_session(pred, idx):
        """Per session in the test index set: model picks the max-predicted-entry
        decision second; incremental = its realized de-idealized net - rule baseline."""
        g = group_ids[idx]
        diffs = []
        for grp in np.unique(g):
            rows = idx[g == grp]
            best = rows[int(np.argmax(pred[g == grp]))]
            diffs.append(float(y[best] - baseline_net[best]))
        return np.array(diffs, dtype=float)

    per_boundary_inc = {"ridge": {}, "gbm": {}}
    primary = {}
    for frac in boundaries:
        train, test = _split(frac)
        if train.sum() < 50 or test.sum() < 50:
            for m in per_boundary_inc:
                per_boundary_inc[m][float(frac)] = None
            continue
        scaler = StandardScaler().fit(X[train])
        Xtr, Xte = scaler.transform(X[train]), scaler.transform(X[test])
        test_idx = np.where(test)[0]
        for name, model in _models().items():
            model.fit(Xtr, y[train])
            pred = model.predict(Xte)
            inc = _incremental_per_session(pred, test_idx)
            per_boundary_inc[name][float(frac)] = float(inc.mean()) if len(inc) else None
            if abs(frac - primary_boundary) < 1e-9:
                primary[name] = inc

    results: Dict[str, Any] = {
        "n_samples": int(len(y)),
        "n_groups": int(len(set(group_ids.tolist()))),
        "n_dates": int(len(uniq_dates)),
        "n_trials": n_trials,
        "external_sharpe_variance": external_sharpe_variance,
        "primary_boundary": primary_boundary,
        "per_boundary_incremental_mean": per_boundary_inc,
        "models": {},
    }

    best_go = False
    for name in ("ridge", "gbm"):
        inc = primary.get(name)
        if inc is None or len(inc) < 2:
            continue
        mean_inc = float(inc.mean())
        boot = rng.choice(inc, size=(n_bootstrap, len(inc)), replace=True).mean(axis=1)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        sr = per_trade_sharpe(inc.tolist())
        dsr = (
            deflated_sharpe_ratio(
                sr, n_trials=n_trials, sharpe_variance=external_sharpe_variance,
                n_samples=len(inc))
            if sr is not None else None
        )
        ci_go = lo > 0.0
        dsr_go = dsr is not None and dsr > 0.95
        go = bool(ci_go and dsr_go)
        best_go = best_go or go
        results["models"][name] = {
            "n_sessions": int(len(inc)),
            "incremental_mean_pct": mean_inc,
            "incremental_ci95": [float(lo), float(hi)],
            "ci_excludes_zero": bool(ci_go),
            "incremental_sharpe": sr,
            "incremental_dsr": dsr,
            "dsr_gt_0_95": bool(dsr_go),
            "go": go,
        }

    results["verdict"] = "GO" if best_go else "NO-GO"
    return results


# ---------------------------------------------------------------------------
# DB extraction: ts_imb panels -> (features, de-idealized entry-net label, baseline).
# ---------------------------------------------------------------------------
def extract_timing_samples(
    db_path: str,
    *,
    max_symbols: int = 0,
    sample_every_sec: int = 10,
    entry_window_end_sec: int = 1080,  # last entry decision = 09:18
    tp_pct: float = 5.0,
    sl_pct: float = 1.0,
    cost_bps: float = 23.0,
    slippage_bps: float = 0.0,
    strength_thr: float = 100.0,
    imbalance_thr: float = 0.5,
    entry_cr_thr: float = 2.0,
) -> Dict[str, Any]:
    """Per ts_imb instance, emit decision-point features, the de-idealized net of
    entering at that second (held to the rule's exit), and the rule's fixed-09:00
    de-idealized net (baseline) for that session."""

    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from finetune_csv.stom_tick_dataset import connect_readonly, get_table_columns, list_stock_tables

    conn = connect_readonly(db_path)
    feats: List[List[float]] = []
    ys: List[float] = []
    base: List[float] = []
    dates: List[str] = []
    groups: List[str] = []
    secs_out: List[float] = []
    n_instances = 0
    sel = ["index"] + [_COLS[k] for k in (
        "px", "cr", "strength", "buy_val", "sell_val", "buy_qty", "sell_qty",
        "bid_tot", "ask_tot", "bid1", "ask1", "bidq1", "askq1")]
    try:
        tables = list_stock_tables(conn, max_tables=max_symbols if max_symbols > 0 else None)
        for table in tables:
            cols = set(get_table_columns(conn, table))
            if not all(c in cols for c in sel[1:]):
                continue
            qt = table.replace('"', '""')
            q_sel = ", ".join('"' + c.replace('"', '""') + '"' for c in sel)
            cr_c, st_c, bt_c, at_c, px_c = (
                _COLS["cr"], _COLS["strength"], _COLS["bid_tot"], _COLS["ask_tot"], _COLS["px"])
            pre_q = ('SELECT "%s","%s","%s","%s" FROM "%s" WHERE "index">=? AND "index"<=? '
                     'AND "%s">0 ORDER BY "index" LIMIT 1' % (cr_c, st_c, bt_c, at_c, qt, px_c))
            date_q = 'SELECT DISTINCT substr(CAST("index" AS TEXT),1,8) FROM "%s"' % qt
            sessions = [str(r[0]) for r in conn.execute(date_q).fetchall()
                        if r[0] is not None and len(str(r[0])) == 8 and str(r[0]).isdigit()]
            for sess in sorted(sessions):
                lo, hi = int(sess + "090000"), int(sess + "093000")
                pre = conn.execute(pre_q, (lo, hi)).fetchall()
                if not pre:
                    continue
                pcr, pts, pbt, pat = pre[0]
                if pcr is None or float(pcr) < entry_cr_thr or pts is None or float(pts) < strength_thr:
                    continue
                psum = (float(pbt) if pbt is not None else 0.0) + (float(pat) if pat is not None else 0.0)
                if psum <= 0 or (float(pbt) if pbt is not None else 0.0) / psum < imbalance_thr:
                    continue
                raw = conn.execute(
                    'SELECT %s FROM "%s" WHERE "index">=? AND "index"<=? ORDER BY "index"'
                    % (q_sel, qt), (lo, hi)).fetchall()
                rows: List[Dict[str, Any]] = []
                for r in raw:
                    px = r[1]
                    if px is None or float(px) <= 0 or len(str(int(r[0]))) != 14:
                        continue
                    rows.append({
                        "sec": _sec_of(r[0]), "price": float(px), "cr": r[2], "ts": r[3],
                        "buy_val": r[4], "sell_val": r[5], "buy_qty": r[6], "sell_qty": r[7],
                        "bid_tot": r[8], "ask_tot": r[9], "bid1": r[10], "ask1": r[11],
                        "bidq1": r[12], "askq1": r[13]})
                if len(rows) < 120:
                    continue
                e = rows[0]
                imb = None
                if e["bid_tot"] is not None and e["ask_tot"] is not None:
                    s = float(e["bid_tot"]) + float(e["ask_tot"])
                    imb = (float(e["bid_tot"]) / s) if s > 0 else None
                if (e["cr"] is None or float(e["cr"]) < entry_cr_thr or e["ts"] is None
                        or float(e["ts"]) < strength_thr or imb is None or imb < imbalance_thr):
                    continue
                n_instances += 1
                prices = [rr["price"] for rr in rows]
                bids = [rr["bid1"] for rr in rows]
                asks = [rr["ask1"] for rr in rows]
                secs_arr = [rr["sec"] for rr in rows]
                rule_net, _ = simulate_rule_from_entry(
                    prices, bids, asks, secs_arr, 0,
                    tp_pct=tp_pct, sl_pct=sl_pct, cost_bps=cost_bps, slippage_bps=slippage_bps)
                gid = "%s_%s" % (table, sess)
                ti = 0
                last_ti = -1
                for tsec in range(sample_every_sec, entry_window_end_sec + 1, sample_every_sec):
                    while ti + 1 < len(rows) and secs_arr[ti + 1] <= tsec:
                        ti += 1
                    if secs_arr[ti] > tsec or ti == last_ti:
                        continue
                    last_ti = ti
                    net_t, _ = simulate_rule_from_entry(
                        prices, bids, asks, secs_arr, ti,
                        tp_pct=tp_pct, sl_pct=sl_pct, cost_bps=cost_bps, slippage_bps=slippage_bps)
                    fv = causal_feature_vector(rows[:ti + 1])
                    feats.append([fv[k] for k in FEATURE_NAMES])
                    ys.append(net_t)
                    base.append(rule_net)
                    dates.append(sess)
                    groups.append(gid)
                    secs_out.append(float(tsec))
    finally:
        conn.close()
    return {
        "X": np.array(feats, dtype=float) if feats else np.zeros((0, len(FEATURE_NAMES))),
        "y": np.array(ys, dtype=float), "baseline_net": np.array(base, dtype=float),
        "dates": dates, "group_ids": groups, "secs": np.array(secs_out, dtype=float),
        "n_instances": n_instances,
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
    p = argparse.ArgumentParser(description="P1b baseline-relative de-idealized timing gate (RULE NOT RL).")
    p.add_argument("--db", default=str(root / "_database" / "stock_tick_back.db"))
    p.add_argument("--max-symbols", type=int, default=0)
    p.add_argument("--slippage-bps", type=float, default=0.0)
    p.add_argument("--json-out", default=str(root / ".omx" / "artifacts" / "timing_gate" / "summary.json"))
    args = p.parse_args(argv)

    print("=== P1b baseline-relative de-idealized entry-timing gate (RULE NOT RL) ===")
    d = extract_timing_samples(args.db, max_symbols=args.max_symbols, slippage_bps=args.slippage_bps)
    print("instances=%d samples=%d groups=%d  (marketable fills: buy@ask, sell@bid; +%.0fbp slip)"
          % (d["n_instances"], len(d["y"]), len(set(d["group_ids"])), args.slippage_bps))
    if len(d["y"]) < 200:
        print("too few samples — abort")
        return 0
    base = np.asarray(d["baseline_net"])
    print("rule fixed-09:00 de-idealized net: mean=%+.3f%%/trade (per-session baseline)"
          % (np.unique(np.array([(g, b) for g, b in zip(d["group_ids"], base)], dtype=object)[:, 1].astype(float)).mean()
             if len(base) else 0.0))
    res = run_timing_gate(d["X"], d["y"], d["dates"], d["group_ids"], d["secs"], d["baseline_net"])
    print("-- model timing vs rule (paired incremental, primary boundary %.1f) --" % res["primary_boundary"])
    for name, m in res.get("models", {}).items():
        print("   %-5s inc_mean=%+.4f%%/trade CI95=[%+.4f,%+.4f] excl0=%s | sharpe=%s DSR=%s -> %s"
              % (name, m["incremental_mean_pct"], m["incremental_ci95"][0], m["incremental_ci95"][1],
                 m["ci_excludes_zero"],
                 ("%.3f" % m["incremental_sharpe"]) if m["incremental_sharpe"] is not None else "n/a",
                 ("%.3f" % m["incremental_dsr"]) if m["incremental_dsr"] is not None else "n/a",
                 "GO" if m["go"] else "no"))
    print("   per-boundary incremental mean:",
          {k: {b: (round(v, 4) if v is not None else None) for b, v in dd.items()}
           for k, dd in res["per_boundary_incremental_mean"].items()})
    print("   DSR: external sharpe_variance=%.4f, n_trials=%d (conservative)"
          % (res["external_sharpe_variance"], res["n_trials"]))
    print("\nVERDICT: %s  (GO needs incremental-vs-rule CI>0 AND DSR>0.95; else STOP — RL not worth it)"
          % res["verdict"])
    outp = Path(args.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    res["n_instances"] = d["n_instances"]
    outp.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print("wrote -> %s" % outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
