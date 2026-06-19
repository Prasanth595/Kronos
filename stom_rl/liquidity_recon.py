"""Clean per-second traded-value reconstruction for the 시초 갭상승 strategy.

**RULE strategy, NOT reinforcement learning.**  This is experiment ② of the
data-layer assessment (``docs/stom_data_layer_assessment_2026-05-30.md``): remove
the *optimistic bias* in :mod:`stom_rl.liquidity_model` and re-derive capacity.

The bias (now MEASURED, not just suspected).  The backtest's entry bar is the
FIRST recorded row of the session window (``gap_up_backtest.py`` — entry =
``rows[0]`` at/after 09:00:00).  That row is the **opening single-price call
auction**, so its ``초당거래대금`` (per-second traded value) is **cumulative
since 09:00**, not a clean 1-second slice.  Verified on real data: at the entry
bar ``초당거래대금 * 1e6 / (초당매수금액 + 초당매도금액)`` is a **median ~72x** (mean
thousands, max >300,000x), whereas at continuous-trading bars the same ratio is
~1.0.  Using that inflated denominator understates participation -> understates
slippage -> OVERSTATES deployable capacity.

The fix.  ``초당매수금액 + 초당매도금액`` is the *clean incremental* per-second flow
(it is ~equal to ``초당거래대금 * 1e6`` at every continuous bar, and is small/zero
at the auction bar because the auction's matched value only lands in the
cumulative ``당일거래대금`` / ``초당거래대금``).  So a clean entry-liquidity proxy is
the median of ``초당매수금액 + 초당매도금액`` over the first continuous-trading
seconds after entry (the auction bar excluded).  A cross-check reconstruction
differences the cumulative ``당일거래대금`` between consecutive bars.

Honest limits (unchanged): still a triggered-subset DB; no L2 queue / partial-fill
data; the square-root impact coefficient remains an ASSUMPTION (swept, not
calibrated).  This experiment can only make an already-passing gate *more honest*
— the expected outcome is a LOWER deployable capacity, never new alpha.

Core functions are PURE (no I/O).  The DB extractor + CLI are separate.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Reuse the verified participation / slippage primitives so the only thing that
# changes versus Page C is the *denominator* (clean vs contaminated).
from .liquidity_model import (
    DEFAULT_BASE_COST_BPS,
    DEFAULT_GROSS_EXPECTANCY_PCT,
    DEFAULT_IMPACT_COEF_BPS,
    participation_rate,
    slippage_adjusted_expectancy_pct,
    sqrt_impact_slippage_bps,
)

# Number of post-entry seconds over which the clean liquidity baseline is taken.
DEFAULT_CLEAN_WINDOW_SECONDS: int = 60
# Minimum continuous-trading bars required for a usable clean proxy.
DEFAULT_MIN_CLEAN_BARS: int = 5


def clean_per_second_values(
    buy_amounts: Sequence[Optional[float]],
    sell_amounts: Sequence[Optional[float]],
) -> List[float]:
    """Clean incremental per-second traded value = ``초당매수금액 + 초당매도금액`` (won).

    ``None`` entries are treated as ``0``.  These per-second buy/sell amounts are
    the un-accumulated flow (unlike the auction-contaminated ``초당거래대금`` at the
    entry bar), so they are the right liquidity signal.
    """

    if len(buy_amounts) != len(sell_amounts):
        raise ValueError("buy_amounts and sell_amounts must be the same length")
    out: List[float] = []
    for b, s in zip(buy_amounts, sell_amounts):
        bv = float(b) if b is not None else 0.0
        sv = float(s) if s is not None else 0.0
        out.append(bv + sv)
    return out


def entry_liquidity_proxy(
    per_second_values: Sequence[float],
    *,
    window_bars: int = DEFAULT_CLEAN_WINDOW_SECONDS,
    skip_first: bool = True,
    min_bars: int = DEFAULT_MIN_CLEAN_BARS,
) -> Optional[float]:
    """Clean entry-liquidity baseline = median of positive flow in an early window.

    Takes ``per_second_values`` (already clean, e.g. from
    :func:`clean_per_second_values`), drops the first bar when ``skip_first`` (the
    auction bar carries no clean continuous flow), keeps only the first
    ``window_bars`` bars, and returns the **median of strictly-positive** values.
    Returns ``None`` when fewer than ``min_bars`` positive bars exist (too thin to
    estimate a baseline honestly).
    """

    if window_bars <= 0:
        raise ValueError("window_bars must be positive")
    if min_bars <= 0:
        raise ValueError("min_bars must be positive")
    start = 1 if skip_first else 0
    window = list(per_second_values[start : start + window_bars])
    positive = [v for v in window if v > 0.0]
    if len(positive) < min_bars:
        return None
    return float(median(positive))


def reconstruct_from_cumulative(
    cumulative_value_won: Sequence[Optional[float]],
) -> List[float]:
    """Cross-check: per-second flow = positive first-difference of cumulative value.

    ``당일거래대금`` (daily cumulative traded value) differenced between consecutive
    bars gives the per-bar increment.  Negative/None diffs (resets, gaps) are
    clamped to ``0``.  The first bar has no predecessor -> dropped, which also
    discards the auction print that contaminates index 0.
    """

    out: List[float] = []
    prev: Optional[float] = None
    for raw in cumulative_value_won:
        cur = float(raw) if raw is not None else None
        if prev is not None and cur is not None:
            diff = cur - prev
            out.append(diff if diff > 0.0 else 0.0)
        if cur is not None:
            prev = cur
    return out


def summarize_capacity(
    clean_entry_values_won: Sequence[float],
    *,
    accounts_won: Sequence[float],
    per_trade_fraction: float = 0.10,
    base_cost_bps: float = DEFAULT_BASE_COST_BPS,
    gross_expectancy_pct: float = DEFAULT_GROSS_EXPECTANCY_PCT,
    impact_coefs_bps: Sequence[float] = (5.0, 10.0, 20.0),
    feasible_participation: float = 1.0,
    strict_participation: float = 0.1,
) -> Dict[str, Any]:
    """Per-account capacity using the CLEAN entry-liquidity denominators.

    For each account, ``order_won = per_trade_fraction * account``; participation
    is ``order_won / clean_entry_value`` per instance.  Reports median/mean
    participation, feasible/strict fractions, a slippage coefficient sweep at the
    median participation, and the slippage-adjusted expectancy.  Also derives the
    breakeven account size where the *median* participation reaches 1x.
    """

    usable = [float(v) for v in clean_entry_values_won if v is not None and float(v) > 0]
    dropped = len(clean_entry_values_won) - len(usable)
    median_clean = median(usable) if usable else None

    by_account: List[Dict[str, Any]] = []
    for acct in accounts_won:
        order = float(per_trade_fraction) * float(acct)
        if not usable:
            by_account.append({"account_won": float(acct), "order_won": order, "n": 0})
            continue
        parts = [participation_rate(order, v) for v in usable]
        n = len(parts)
        med_part = median(parts)
        coef_sweep = []
        for c in impact_coefs_bps:
            slip = sqrt_impact_slippage_bps(med_part, impact_coef_bps=c)
            coef_sweep.append(
                {
                    "impact_coef_bps": float(c),
                    "median_slippage_bps": slip,
                    "slippage_adj_expectancy_pct": slippage_adjusted_expectancy_pct(
                        gross_expectancy_pct, base_cost_bps, slip
                    ),
                }
            )
        by_account.append(
            {
                "account_won": float(acct),
                "order_won": order,
                "n": n,
                "median_participation": med_part,
                "mean_participation": sum(parts) / n,
                "frac_feasible_le_1x": sum(1 for p in parts if p <= feasible_participation) / n,
                "frac_strict_le_0.1x": sum(1 for p in parts if p <= strict_participation) / n,
                "coef_sweep": coef_sweep,
            }
        )

    # Account whose *median* order hits 1x of the median clean per-second value.
    breakeven_1x_account = (
        median_clean / float(per_trade_fraction) if median_clean else None
    )
    return {
        "n_usable": len(usable),
        "n_dropped": dropped,
        "median_clean_entry_value_won": median_clean,
        "p10_clean_entry_value_won": (
            sorted(usable)[int(0.1 * len(usable))] if usable else None
        ),
        "breakeven_1x_account_won_median": breakeven_1x_account,
        "by_account": by_account,
    }


# ---------------------------------------------------------------------------
# DB extractor (separate from the pure core).
# ---------------------------------------------------------------------------
def _seconds_since_open(ts: int, *, open_hhmmss: int = 90000) -> int:
    """Seconds of an index timestamp (YYYYMMDDHHMMSS) past 09:00:00."""

    hhmmss = int(ts) % 1_000_000
    h = hhmmss // 10_000
    m = (hhmmss // 100) % 100
    s = hhmmss % 100
    oh = open_hhmmss // 10_000
    om = (open_hhmmss // 100) % 100
    os_ = open_hhmmss % 100
    return (h * 3600 + m * 60 + s) - (oh * 3600 + om * 60 + os_)


def extract_clean_entry_values(
    instances_path: str,
    db_path: str,
    *,
    only_ts_imb: bool = True,
    window_bars: int = DEFAULT_CLEAN_WINDOW_SECONDS,
    session_start: str = "090000",
    time_exit: str = "093000",
    limit: int = 0,
) -> Dict[str, Any]:
    """Re-query the DB per (symbol, session) and reconstruct clean entry liquidity.

    Returns, per instance, both the OLD contaminated denominator
    (``초당거래대금`` at the entry bar, x1e6) and the NEW clean proxy (median of
    ``초당매수금액 + 초당매도금액`` over the first ``window_bars`` continuous seconds),
    plus the inflation ratio.  Read-only DB access.
    """

    import json
    import sqlite3
    from pathlib import Path

    rows = json.loads(Path(instances_path).read_text(encoding="utf-8"))
    if only_ts_imb:
        rows = [r for r in rows if r.get("pass_ts_imb")]
    if limit and limit > 0:
        rows = rows[: int(limit)]

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    clean_values: List[float] = []
    old_values: List[float] = []
    inflation_ratios: List[float] = []
    per_instance: List[Dict[str, Any]] = []
    n_no_clean = 0
    try:
        for r in rows:
            sym = str(r["symbol"])
            sess = str(r["session"])
            start_full = int(sess + session_start)
            end_full = int(sess + time_exit)
            q = (
                f'SELECT "index","초당매수금액","초당매도금액","초당거래대금","당일거래대금" '
                f'FROM "{sym}" WHERE "index" >= ? AND "index" <= ? ORDER BY "index"'
            )
            try:
                data = conn.execute(q, (start_full, end_full)).fetchall()
            except sqlite3.OperationalError:
                continue
            if not data:
                continue
            buy = [d[1] for d in data]
            sell = [d[2] for d in data]
            entry_sec_amt = data[0][3]  # 초당거래대금 at entry bar (백만원, contaminated)
            old_denom = float(entry_sec_amt) * 1_000_000.0 if entry_sec_amt else None
            psv = clean_per_second_values(buy, sell)
            clean = entry_liquidity_proxy(psv, window_bars=window_bars, skip_first=True)
            if clean is None:
                n_no_clean += 1
            else:
                clean_values.append(clean)
                if old_denom and old_denom > 0:
                    old_values.append(old_denom)
                    inflation_ratios.append(old_denom / clean)
            per_instance.append(
                {
                    "symbol": sym,
                    "session": sess,
                    "old_entry_sec_amount_won": old_denom,
                    "clean_entry_value_won": clean,
                    "inflation_ratio": (old_denom / clean) if (clean and old_denom) else None,
                }
            )
    finally:
        conn.close()

    infl_sorted = sorted(inflation_ratios)
    summary = {
        "n_instances": len(rows),
        "n_with_clean": len(clean_values),
        "n_no_clean": n_no_clean,
        "inflation_ratio_median": median(inflation_ratios) if inflation_ratios else None,
        "inflation_ratio_mean": (sum(inflation_ratios) / len(inflation_ratios)) if inflation_ratios else None,
        "inflation_ratio_p90": infl_sorted[int(0.9 * len(infl_sorted))] if infl_sorted else None,
        "median_old_denom_won": median(old_values) if old_values else None,
        "median_clean_denom_won": median(clean_values) if clean_values else None,
    }
    return {"summary": summary, "clean_values_won": clean_values, "per_instance": per_instance}


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
    parser = argparse.ArgumentParser(
        description="Clean per-second liquidity reconstruction (RULE NOT RL) - experiment 2."
    )
    parser.add_argument(
        "--instances",
        default=str(root / ".omx" / "artifacts" / "gap_up_full" / "instances.json"),
    )
    parser.add_argument(
        "--db", default=str(root / "_database" / "stock_tick_back.db")
    )
    parser.add_argument("--window-bars", type=int, default=DEFAULT_CLEAN_WINDOW_SECONDS)
    parser.add_argument("--per-trade-fraction", type=float, default=0.10)
    parser.add_argument(
        "--accounts-won", default="10000000,50000000,100000000,500000000,1000000000"
    )
    parser.add_argument("--impact-coefs-bps", default="5,10,20")
    parser.add_argument("--base-cost-bps", type=float, default=DEFAULT_BASE_COST_BPS)
    parser.add_argument("--gross-expectancy-pct", type=float, default=DEFAULT_GROSS_EXPECTANCY_PCT)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--json-out",
        default=str(root / ".omx" / "artifacts" / "liquidity_recon" / "summary.json"),
    )
    args = parser.parse_args(argv)

    accounts = [float(x) for x in args.accounts_won.split(",") if x.strip()]
    coefs = [float(x) for x in args.impact_coefs_bps.split(",") if x.strip()]

    print("=== clean per-second liquidity reconstruction (RULE NOT RL) — experiment 2 ===")
    print(f"instances={args.instances}")
    print("removing the auction-cumulative bias in entry-bar 초당거래대금; "
          "clean denom = median(초당매수금액+초당매도금액) over first "
          f"{args.window_bars} continuous seconds")

    ext = extract_clean_entry_values(
        args.instances, args.db, only_ts_imb=True, window_bars=args.window_bars, limit=args.limit
    )
    s = ext["summary"]
    print(
        f"\nts_imb instances={s['n_instances']}  with_clean={s['n_with_clean']}  "
        f"no_clean(thin)={s['n_no_clean']}"
    )
    print(
        f"INFLATION of old entry-bar denom vs clean: "
        f"median={s['inflation_ratio_median']:.1f}x  mean={s['inflation_ratio_mean']:.1f}x  "
        f"p90={s['inflation_ratio_p90']:.1f}x"
    )
    print(
        f"median denom: OLD(contaminated)={s['median_old_denom_won']:,.0f}원  "
        f"CLEAN={s['median_clean_denom_won']:,.0f}원"
    )

    cap = summarize_capacity(
        ext["clean_values_won"],
        accounts_won=accounts,
        per_trade_fraction=args.per_trade_fraction,
        base_cost_bps=args.base_cost_bps,
        gross_expectancy_pct=args.gross_expectancy_pct,
        impact_coefs_bps=coefs,
    )
    print(
        f"\nclean median per-second value={cap['median_clean_entry_value_won']:,.0f}원  "
        f"p10={cap['p10_clean_entry_value_won']:,.0f}원"
    )
    be = cap["breakeven_1x_account_won_median"]
    print(f"account where MEDIAN order hits 1x clean flow (f={args.per_trade_fraction:g}): "
          f"{be:,.0f}원" if be else "n/a")
    print("\n-- per-account capacity (CLEAN denominator) --")
    for e in cap["by_account"]:
        if e.get("n", 0) == 0:
            print(f"  account {e['account_won']:,.0f} -> no data")
            continue
        sweep = "  ".join(
            f"coef{c['impact_coef_bps']:g}->slip{c['median_slippage_bps']:.1f}bp/"
            f"exp{c['slippage_adj_expectancy_pct']:+.3f}%"
            for c in e["coef_sweep"]
        )
        print(
            f"  account {e['account_won']:,.0f}  order {e['order_won']:,.0f}  "
            f"med_part={e['median_participation']:.3f}x  "
            f"feasible(<=1x)={e['frac_feasible_le_1x']:.0%}  "
            f"strict(<=0.1x)={e['frac_strict_le_0.1x']:.0%}"
        )
        print(f"      {sweep}")

    out = {"reconstruction": s, "capacity": cap, "config": {
        "window_bars": args.window_bars, "per_trade_fraction": args.per_trade_fraction,
        "accounts_won": accounts, "impact_coefs_bps": coefs,
        "base_cost_bps": args.base_cost_bps, "gross_expectancy_pct": args.gross_expectancy_pct,
    }}
    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
