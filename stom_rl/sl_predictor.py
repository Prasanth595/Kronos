"""Experiment ③ — SL-vs-non-SL precursor classifier (cheap de-risker gate).

**RULE strategy, NOT reinforcement learning.**  This is the MEASUREMENT-FIRST gate
from ``docs/stom_data_layer_assessment_2026-05-30.md`` §4: can causal entry-bar +
early-path microstructure predict whether a ts_imb trade EVENTUALLY exits on the
stop-loss (rule TP5/SL1/09:25)?  If SL-predictability is at chance (AUC ~ 0.5,
symbol-robust), it cheaply KILLS the more expensive experiments ① (skip-gate) and
④ (state-conditioned exit) BEFORE they are built.  It is not a money test; it is a
"is there anything to condition on" test.

Two pre-registered snapshots, two AUCs:

* ``entry``  — features from the entry bar + first few seconds (ALL instances).
  Relevant to ① (decide at entry whether to skip).  No survival conditioning.
* ``path30`` — features from the first ``path_window_sec`` seconds, restricted to
  instances STILL OPEN at that time (not yet TP/SL).  Relevant to ④ (decide while
  holding: "I'm still in at 30s, will this end in SL?").  Conditioning on
  open-at-30s is correct for ④, not a leak (the SL/TP check truncates features at
  any in-window resolution, so features never use post-exit path).

Pre-registered verdict (recorded BEFORE results): a snapshot is PREDICTABLE only if
its purged walk-forward test AUC has a session-bootstrap 95% CI **lower bound > 0.5**
(statistically above chance) AND point AUC >= 0.55 (practically meaningful) AND the
symbol-disjoint AUC >= 0.53 (robust to per-ticker memorisation).  Otherwise AT-CHANCE.
GO for ①④ requires at least one snapshot PREDICTABLE; else STOP.

Pure stats (``run_sl_gate`` on arrays) have no I/O and are unit-tested; the DB
extraction (``extract_sl_samples``) is separated.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from stom_rl.microstructure_features import FEATURE_NAMES, causal_feature_vector

# Pre-registered thresholds (locked before results).
AUC_ABOVE_CHANCE: float = 0.5    # CI lower bound must exceed this
AUC_MEANINGFUL: float = 0.55     # point AUC must reach this to be "practically useful"
AUC_ROBUST: float = 0.53         # symbol-disjoint AUC must reach this
RULE_TP_PCT: float = 5.0
RULE_SL_PCT: float = 1.0


def _auc(scores: np.ndarray, labels: np.ndarray) -> Optional[float]:
    """ROC AUC; None when the label vector is single-class (AUC undefined)."""

    labels = np.asarray(labels)
    if labels.min() == labels.max():
        return None
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(labels, scores))


def rule_exit_reason(
    prices: Sequence[float],
    secs: Sequence[float],
    *,
    tp_pct: float = RULE_TP_PCT,
    sl_pct: float = RULE_SL_PCT,
) -> Tuple[str, int]:
    """Rule exit reason + bar index over a per-second 현재가 path (entry = index 0).

    Scans forward: the FIRST bar whose return from entry reaches ``+tp_pct`` is a
    take-profit (``"tp"``); the first reaching ``-sl_pct`` is a stop-loss
    (``"sl"``); if both are crossed on the same scan step SL wins (conservative);
    otherwise the final bar is a time exit (``"time"``).  Returns ``(reason, idx)``.
    """

    if not prices:
        raise ValueError("prices must be non-empty")
    entry = float(prices[0])
    if entry <= 0:
        raise ValueError("entry price must be positive")
    for i in range(1, len(prices)):
        ret = (float(prices[i]) / entry - 1.0) * 100.0
        if ret <= -sl_pct:
            return "sl", i
        if ret >= tp_pct:
            return "tp", i
    return "time", len(prices) - 1


def _walk_forward_auc(
    X: np.ndarray,
    y: np.ndarray,
    dates: np.ndarray,
    groups: np.ndarray,
    *,
    boundary: float,
    n_bootstrap: int,
    rng: np.random.Generator,
) -> Dict[str, Any]:
    """Train on earlier sessions, test on later; AUC + session-bootstrap CI.

    Logistic regression (linear-first) and gradient boosting.  CI resamples test
    GROUPS (symbols) with replacement so the interval respects per-ticker
    clustering.  Returns per-model AUC, CI, and bootstrap detail.
    """

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    uniq = np.array(sorted(set(dates.tolist())))
    cut = uniq[max(0, min(len(uniq) - 1, int(round(len(uniq) * boundary)) - 1))]
    tr = dates < cut
    te = dates > cut
    out: Dict[str, Any] = {"n_train": int(tr.sum()), "n_test": int(te.sum()), "models": {}}
    if tr.sum() < 50 or te.sum() < 50 or y[tr].min() == y[tr].max() or y[te].min() == y[te].max():
        out["degenerate"] = True
        return out

    scaler = StandardScaler().fit(X[tr])
    Xtr, Xte = scaler.transform(X[tr]), scaler.transform(X[te])
    test_groups = groups[te]
    uniq_tg = np.array(sorted(set(test_groups.tolist())))
    g_rows = {g: np.where(test_groups == g)[0] for g in uniq_tg}

    models = {
        "logit": LogisticRegression(max_iter=1000, C=1.0),
        "gbm": HistGradientBoostingClassifier(
            max_depth=3, max_iter=200, learning_rate=0.05, l2_regularization=1.0,
            random_state=0,
        ),
    }
    for name, model in models.items():
        model.fit(Xtr, y[tr])
        score = model.predict_proba(Xte)[:, 1]
        auc = _auc(score, y[te])
        boot: List[float] = []
        if auc is not None:
            for _ in range(n_bootstrap):
                pick = rng.choice(uniq_tg, size=len(uniq_tg), replace=True)
                idx = np.concatenate([g_rows[g] for g in pick])
                a = _auc(score[idx], y[te][idx])
                if a is not None:
                    boot.append(a)
        lo, hi = (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))) if boot else (None, None)
        out["models"][name] = {
            "auc": auc,
            "auc_ci95": [lo, hi],
            "ci_excludes_chance": bool(lo is not None and lo > AUC_ABOVE_CHANCE),
        }
    return out


def _symbol_disjoint_auc(
    X: np.ndarray, y: np.ndarray, dates: np.ndarray, groups: np.ndarray, *, boundary: float,
) -> Dict[str, Optional[float]]:
    """AUC on unseen tickers (train 70% symbols earlier, test 30% symbols later)."""

    import zlib

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    uniq = np.array(sorted(set(dates.tolist())))
    cut = uniq[max(0, min(len(uniq) - 1, int(round(len(uniq) * boundary)) - 1))]
    symbols = np.array([str(g).split("_", 1)[0] for g in groups])
    pool = np.array([zlib.crc32(s.encode()) % 10 for s in symbols])
    tr = (dates < cut) & (pool < 7)
    te = (dates > cut) & (pool >= 7)
    res: Dict[str, Optional[float]] = {}
    if tr.sum() < 50 or te.sum() < 50 or y[tr].min() == y[tr].max() or y[te].min() == y[te].max():
        return res
    scaler = StandardScaler().fit(X[tr])
    Xtr, Xte = scaler.transform(X[tr]), scaler.transform(X[te])
    for name, model in (
        ("logit", LogisticRegression(max_iter=1000, C=1.0)),
        ("gbm", HistGradientBoostingClassifier(
            max_depth=3, max_iter=200, learning_rate=0.05, l2_regularization=1.0, random_state=0)),
    ):
        model.fit(Xtr, y[tr])
        res[name] = _auc(model.predict_proba(Xte)[:, 1], y[te])
    return res


def run_sl_gate(
    X: np.ndarray,
    y: np.ndarray,
    dates: Sequence[str],
    group_ids: Sequence[str],
    *,
    boundary: float = 0.7,
    n_bootstrap: int = 1000,
    rng_seed: int = 0,
) -> Dict[str, Any]:
    """Purged walk-forward SL-predictability gate for ONE snapshot.

    ``y`` is the binary eventual-SL label.  Trains logit + GBM on earlier sessions,
    tests on later; reports AUC + session-bootstrap CI and a symbol-disjoint AUC.
    ``predictable`` is True iff some model clears all three pre-registered bars
    (CI lower > 0.5, AUC >= 0.55, symbol-disjoint AUC >= 0.53).
    """

    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=int)
    dates = np.asarray([str(d) for d in dates])
    groups = np.asarray([str(g) for g in group_ids])
    rng = np.random.default_rng(rng_seed)

    wf = _walk_forward_auc(X, y, dates, groups, boundary=boundary, n_bootstrap=n_bootstrap, rng=rng)
    sd = _symbol_disjoint_auc(X, y, dates, groups, boundary=boundary)

    predictable = False
    for name, m in wf.get("models", {}).items():
        auc = m.get("auc")
        ci_ok = m.get("ci_excludes_chance", False)
        meaningful = auc is not None and auc >= AUC_MEANINGFUL
        robust = sd.get(name) is not None and sd[name] >= AUC_ROBUST
        m["meaningful"] = bool(meaningful)
        m["symbol_disjoint_auc"] = sd.get(name)
        m["robust"] = bool(robust)
        m["predictable"] = bool(ci_ok and meaningful and robust)
        predictable = predictable or m["predictable"]

    base_rate = float(y.mean()) if len(y) else None
    return {
        "n_samples": int(len(y)),
        "n_groups": int(len(set(groups.tolist()))),
        "base_rate_sl": base_rate,
        "boundary": boundary,
        "thresholds": {
            "auc_above_chance": AUC_ABOVE_CHANCE,
            "auc_meaningful": AUC_MEANINGFUL,
            "auc_robust": AUC_ROBUST,
        },
        "walk_forward": wf,
        "symbol_disjoint_auc": sd,
        "predictable": predictable,
        "verdict": "PREDICTABLE" if predictable else "AT-CHANCE",
    }


# ---------------------------------------------------------------------------
# DB extraction: ts_imb instances -> (entry snapshot, path30 snapshot) datasets.
# ---------------------------------------------------------------------------
_COLS = {
    "px": "현재가", "cr": "등락율", "strength": "체결강도",
    "buy_val": "초당매수금액", "sell_val": "초당매도금액",
    "buy_qty": "초당매수수량", "sell_qty": "초당매도수량",
    "bid_tot": "매수총잔량", "ask_tot": "매도총잔량",
    "bid1": "매수호가1", "ask1": "매도호가1", "bidq1": "매수잔량1", "askq1": "매도잔량1",
}


def _sec_of(ts: int) -> int:
    s = str(int(ts))
    return int(s[8:10]) * 3600 + int(s[10:12]) * 60 + int(s[12:14]) - 9 * 3600


def _row_dict(r: Sequence[Any]) -> Dict[str, Any]:
    return {
        "sec": _sec_of(r[0]), "price": float(r[1]), "cr": r[2], "ts": r[3],
        "buy_val": r[4], "sell_val": r[5], "buy_qty": r[6], "sell_qty": r[7],
        "bid_tot": r[8], "ask_tot": r[9], "bid1": r[10], "ask1": r[11],
        "bidq1": r[12], "askq1": r[13],
    }


def extract_sl_samples(
    db_path: str,
    *,
    max_symbols: int = 0,
    entry_window_sec: int = 5,
    path_window_sec: int = 30,
    strength_thr: float = 100.0,
    imbalance_thr: float = 0.5,
    entry_cr_thr: float = 2.0,
) -> Dict[str, Any]:
    """Emit two causal datasets (entry, path30) with eventual-SL labels.

    ts_imb gate identical to the predictability probe (등락율>=2 AND 체결강도>=100 AND
    매수총잔량 imbalance>=0.5 at the first valid-price bar).  Path pulled over
    [09:00, 09:25] (rule TP5/SL1/09:25 window).  For each instance:

    * label = rule exit reason == "sl" (:func:`rule_exit_reason`);
    * ``entry`` features = causal vector over rows within ``entry_window_sec``
      (truncated at exit if it resolves that fast);
    * ``path30`` features = causal vector over rows within ``path_window_sec``,
      ONLY if the trade is still open at ``path_window_sec`` (else excluded),
      truncated at any in-window resolution so no post-exit path is used.
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

    entry_X: List[List[float]] = []
    entry_y: List[int] = []
    entry_d: List[str] = []
    entry_g: List[str] = []
    path_X: List[List[float]] = []
    path_y: List[int] = []
    path_d: List[str] = []
    path_g: List[str] = []
    n_instances = 0
    n_sl = 0
    n_open_at_path = 0
    try:
        tables = list_stock_tables(conn, max_tables=max_symbols if max_symbols > 0 else None)
        for table in tables:
            cols = set(get_table_columns(conn, table))
            if not all(c in cols for c in sel[1:]):
                continue
            qt = table.replace('"', '""')
            q_sel = ", ".join('"' + c.replace('"', '""') + '"' for c in sel)
            cr_c, st_c = _COLS["cr"], _COLS["strength"]
            bt_c, at_c, px_c = _COLS["bid_tot"], _COLS["ask_tot"], _COLS["px"]
            date_q = 'SELECT DISTINCT substr(CAST("index" AS TEXT),1,8) FROM "%s"' % qt
            sessions = [str(r[0]) for r in conn.execute(date_q).fetchall()
                        if r[0] is not None and len(str(r[0])) == 8 and str(r[0]).isdigit()]
            prefilter_q = (
                'SELECT "%s","%s","%s","%s" FROM "%s" WHERE "index">=? AND "index"<=? '
                'AND "%s">0 ORDER BY "index" LIMIT 1' % (cr_c, st_c, bt_c, at_c, qt, px_c)
            )
            for sess in sorted(sessions):
                lo, hi = int(sess + "090000"), int(sess + "092500")
                pre = conn.execute(prefilter_q, (lo, hi)).fetchall()
                if not pre:
                    continue
                pcr, pts, pbt, pat = pre[0]
                if pcr is None or float(pcr) < entry_cr_thr or pts is None or float(pts) < strength_thr:
                    continue
                psum = (float(pbt) if pbt is not None else 0.0) + (float(pat) if pat is not None else 0.0)
                if psum <= 0 or (float(pbt) if pbt is not None else 0.0) / psum < imbalance_thr:
                    continue
                raw = conn.execute(
                    'SELECT %s FROM "%s" WHERE "index">=? AND "index"<=? ORDER BY "index"' % (q_sel, qt),
                    (lo, hi),
                ).fetchall()
                rows: List[Dict[str, Any]] = []
                for r in raw:
                    px = r[1]
                    if px is None or float(px) <= 0:
                        continue
                    if len(str(int(r[0]))) != 14:
                        continue
                    rows.append(_row_dict(r))
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
                prices = [rr["price"] for rr in rows]
                secs = [rr["sec"] for rr in rows]
                reason, exit_idx = rule_exit_reason(prices, secs)
                label = 1 if reason == "sl" else 0
                n_sl += label
                gid = "%s_%s" % (table, sess)

                # entry snapshot: rows within entry_window_sec, capped at exit.
                e_cap = exit_idx
                e_last = 0
                for j in range(len(rows)):
                    if rows[j]["sec"] <= entry_window_sec and j <= e_cap:
                        e_last = j
                    else:
                        break
                fv_e = causal_feature_vector(rows[: e_last + 1])
                entry_X.append([fv_e[k] for k in FEATURE_NAMES])
                entry_y.append(label)
                entry_d.append(sess)
                entry_g.append(gid)

                # path30 snapshot: only if still open at path_window_sec.
                if exit_idx >= 1 and secs[exit_idx] > path_window_sec:
                    n_open_at_path += 1
                    p_last = 0
                    for j in range(len(rows)):
                        if rows[j]["sec"] <= path_window_sec:
                            p_last = j
                        else:
                            break
                    fv_p = causal_feature_vector(rows[: p_last + 1])
                    path_X.append([fv_p[k] for k in FEATURE_NAMES])
                    path_y.append(label)
                    path_d.append(sess)
                    path_g.append(gid)
    finally:
        conn.close()

    def _pack(Xl, yl, dl, gl):
        return {
            "X": np.array(Xl, dtype=float) if Xl else np.zeros((0, len(FEATURE_NAMES))),
            "y": np.array(yl, dtype=int),
            "dates": dl, "group_ids": gl,
        }

    return {
        "entry": _pack(entry_X, entry_y, entry_d, entry_g),
        "path30": _pack(path_X, path_y, path_d, path_g),
        "n_instances": n_instances,
        "n_sl": n_sl,
        "n_open_at_path": n_open_at_path,
        "sl_rate": (n_sl / n_instances) if n_instances else None,
        "feature_names": FEATURE_NAMES,
        "entry_window_sec": entry_window_sec,
        "path_window_sec": path_window_sec,
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
    p = argparse.ArgumentParser(description="Experiment 3: SL-predictability precursor gate (RULE NOT RL).")
    p.add_argument("--db", default=str(root / "_database" / "stock_tick_back.db"))
    p.add_argument("--max-symbols", type=int, default=0)
    p.add_argument("--entry-window-sec", type=int, default=5)
    p.add_argument("--path-window-sec", type=int, default=30)
    p.add_argument("--json-out", default=str(root / ".omx" / "artifacts" / "sl_predictor" / "summary.json"))
    args = p.parse_args(argv)

    print("=== experiment 3: SL-vs-non-SL precursor gate (RULE strategy, NOT RL) ===")
    data = extract_sl_samples(
        args.db, max_symbols=args.max_symbols,
        entry_window_sec=args.entry_window_sec, path_window_sec=args.path_window_sec,
    )
    print("instances(ts_imb)=%d  SL=%d (rate=%.1f%%)  open_at_%ds=%d  features=%d"
          % (data["n_instances"], data["n_sl"], 100.0 * (data["sl_rate"] or 0.0),
             args.path_window_sec, data["n_open_at_path"], len(data["feature_names"])))

    out: Dict[str, Any] = {
        "n_instances": data["n_instances"], "n_sl": data["n_sl"], "sl_rate": data["sl_rate"],
        "n_open_at_path": data["n_open_at_path"],
        "entry_window_sec": args.entry_window_sec, "path_window_sec": args.path_window_sec,
        "snapshots": {},
    }
    any_predictable = False
    for snap in ("entry", "path30"):
        d = data[snap]
        if len(d["y"]) < 200:
            print("-- %s: too few samples (%d) — skip" % (snap, len(d["y"])))
            continue
        res = run_sl_gate(d["X"], d["y"], d["dates"], d["group_ids"])
        out["snapshots"][snap] = res
        any_predictable = any_predictable or res["predictable"]
        print("-- %s snapshot: n=%d base_rate_SL=%.1f%% --"
              % (snap, res["n_samples"], 100.0 * (res["base_rate_sl"] or 0.0)))
        for name, m in res["walk_forward"].get("models", {}).items():
            ci = m.get("auc_ci95", [None, None])
            print("   %-5s AUC=%s CI95=[%s,%s] sd_auc=%s -> %s"
                  % (name,
                     ("%.3f" % m["auc"]) if m.get("auc") is not None else "n/a",
                     ("%.3f" % ci[0]) if ci[0] is not None else "n/a",
                     ("%.3f" % ci[1]) if ci[1] is not None else "n/a",
                     ("%.3f" % m["symbol_disjoint_auc"]) if m.get("symbol_disjoint_auc") is not None else "n/a",
                     "PREDICTABLE" if m.get("predictable") else "chance"))
        print("   verdict: %s" % res["verdict"])

    final = "GO (build experiments 1/4)" if any_predictable else "STOP — SL at chance, skip experiments 1 and 4"
    out["final_verdict"] = "GO" if any_predictable else "STOP"
    print("\nFINAL: %s" % final)
    print("(pre-registered: PREDICTABLE needs AUC CI lower>0.5 AND AUC>=0.55 AND symbol-disjoint AUC>=0.53)")

    outp = Path(args.json_out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print("wrote -> %s" % outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
