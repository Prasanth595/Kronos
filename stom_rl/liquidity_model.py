"""Liquidity feasibility & slippage model for the 시초 갭상승 strategy (Page C).

**RULE strategy, NOT reinforcement learning.**

Page A sized positions (f=10%, accounts 1천만/5천만/1억 -> 100만/500만/1000만 per
entry) with a flat ``max_participation`` placeholder.  Page C grounds that in the
REAL entry-bar ``초당거래대금`` (per-second traded value, ``entry_sec_amount``):

1. **Liquidity feasibility** — for a given order size, what fraction of one
   second's traded value does it represent (``participation_rate``)?  A trade is
   feasible only if the order is a small enough fraction of available flow.  This
   is answered from REAL data (the entry_sec_amount distribution of ts_imb
   trades), so it is the hard, data-grounded part of Page C.
2. **Slippage** — a transparent square-root market-impact model
   (``slippage_bps = impact_coef * sqrt(participation)``).  WITHOUT L2 queue data
   this coefficient is an ASSUMPTION, not a calibration, so it is reported as a
   sensitivity (several coefficients) and against the strategy's breakeven
   cushion, never as a single "true" slippage.

Unit (VERIFIED): the DB column ``초당거래대금`` (-> ``entry_sec_amount``) is stored
in **백만원 (millions of won)**, NOT raw won.  Confirmed against the same row's
raw-won fields: ``초당거래대금 ~= (초당매수금액 + 초당매도금액) / 1e6`` (e.g. a second
with 5.8M won of flow stores 6; 41.8M stores 42).  So the loader converts to won
via ``x 1,000,000`` before any participation math.  (A median of 622 means
~6.22억원/sec of flow, not 622 won — the latter would be physically impossible.)

Honest limits (carried from the project guardrails): ``entry_sec_amount`` is one
second's value at/near the open as a liquidity PROXY; there is no L2 queue-position
/ partial-fill data, so true fill dynamics are out of reach.  The feasibility
fractions are real; the slippage magnitudes are model assumptions.  Caveat: the
first session bar's value may be cumulative-since-09:00 rather than a clean
1-second slice, which would INFLATE the denominator and make participation /
slippage look more favorable than reality — treat the feasibility headroom as an
optimistic bound near the entry bar.

All core functions are PURE (no I/O); the CLI reads the gitignored
``instances.json`` artifact (which carries ``entry_sec_amount`` + ``pass_ts_imb``).
"""

from __future__ import annotations

import math
from statistics import mean, median
from typing import Any, Dict, List, Optional, Sequence

# Defaults (verified upstream).  gross_expectancy is the full-universe ts_imb OOS
# zero-cost expectancy (= breakeven_OOS/100 = 98 bp -> +0.98%/trade); base cost 23 bp.
DEFAULT_BASE_COST_BPS: float = 23.0
DEFAULT_GROSS_EXPECTANCY_PCT: float = 0.98
DEFAULT_IMPACT_COEF_BPS: float = 10.0  # ASSUMPTION (no L2 calibration)


def participation_rate(order_won: float, entry_sec_amount: float) -> float:
    """Order size as a multiple of one second's traded value (>= 0).

    ``order_won / entry_sec_amount``.  1.0 means the order equals one full second
    of traded value at the entry bar; 0.1 means a tenth of it.
    """

    if order_won < 0:
        raise ValueError("order_won must be >= 0")
    if entry_sec_amount <= 0:
        raise ValueError("entry_sec_amount must be > 0")
    return float(order_won) / float(entry_sec_amount)


def is_liquidity_feasible(
    order_won: float,
    entry_sec_amount: float,
    *,
    max_participation: float,
) -> bool:
    """True when the order is within ``max_participation`` of one second's flow."""

    if max_participation <= 0:
        raise ValueError("max_participation must be > 0")
    return participation_rate(order_won, entry_sec_amount) <= max_participation


def sqrt_impact_slippage_bps(
    participation: float,
    *,
    impact_coef_bps: float = DEFAULT_IMPACT_COEF_BPS,
) -> float:
    """Square-root market-impact slippage (bps) = ``coef * sqrt(participation)``.

    The square-root law is the standard impact shape (Almgren et al.); the
    coefficient is an UNCALIBRATED assumption here (no L2 data) and should be swept
    as a sensitivity, not trusted as a point estimate.
    """

    if participation < 0:
        raise ValueError("participation must be >= 0")
    if impact_coef_bps < 0:
        raise ValueError("impact_coef_bps must be >= 0")
    return impact_coef_bps * math.sqrt(participation)


def slippage_adjusted_expectancy_pct(
    gross_expectancy_pct: float,
    base_cost_bps: float,
    slippage_bps: float,
) -> float:
    """Net %/trade after subtracting (base cost + slippage), both in bps."""

    if base_cost_bps < 0 or slippage_bps < 0:
        raise ValueError("costs must be >= 0")
    return gross_expectancy_pct - (base_cost_bps + slippage_bps) / 100.0


def max_order_for_slippage_budget_won(
    entry_sec_amount: float,
    *,
    slippage_budget_bps: float,
    impact_coef_bps: float = DEFAULT_IMPACT_COEF_BPS,
) -> float:
    """Largest order keeping square-root slippage at/under a bps budget.

    Inverting ``budget = coef * sqrt(p)`` gives ``p_max = (budget/coef)^2`` and
    ``order_max = entry_sec_amount * p_max``.
    """

    if slippage_budget_bps < 0:
        raise ValueError("slippage_budget_bps must be >= 0")
    if impact_coef_bps <= 0:
        raise ValueError("impact_coef_bps must be > 0")
    if entry_sec_amount <= 0:
        raise ValueError("entry_sec_amount must be > 0")
    p_max = (slippage_budget_bps / impact_coef_bps) ** 2
    return float(entry_sec_amount) * p_max


def summarize_liquidity(
    entry_sec_amounts: Sequence[float],
    *,
    order_won: float,
    base_cost_bps: float = DEFAULT_BASE_COST_BPS,
    gross_expectancy_pct: float = DEFAULT_GROSS_EXPECTANCY_PCT,
    impact_coef_bps: float = DEFAULT_IMPACT_COEF_BPS,
    feasible_participation: float = 1.0,
    strict_participation: float = 0.1,
) -> Dict[str, Any]:
    """Per-trade liquidity feasibility + slippage over a set of entry_sec_amounts.

    For a fixed ``order_won`` (one account's per-entry notional), computes the
    participation distribution, the fraction of trades feasible (participation <=
    ``feasible_participation``) and strictly liquid (<= ``strict_participation``),
    the median slippage at that participation, and the median-participation
    slippage-adjusted expectancy.  Non-positive ``entry_sec_amount`` values are
    dropped (and counted) since they carry no usable liquidity signal.  Note:
    ``median_slippage_bps`` is the slippage AT the median participation
    (slip of median p), NOT the median of per-trade slippages; by sqrt concavity
    it is <= the latter.
    """

    usable = [float(a) for a in entry_sec_amounts if a is not None and float(a) > 0]
    dropped = len(entry_sec_amounts) - len(usable)
    if not usable:
        return {
            "n": 0,
            "n_dropped": dropped,
            "order_won": float(order_won),
            "median_participation": None,
            "mean_participation": None,
            "frac_feasible": None,
            "frac_strict": None,
            "median_slippage_bps": None,
            "slippage_adj_expectancy_pct_at_median": None,
        }
    parts = [participation_rate(order_won, a) for a in usable]
    n = len(parts)
    med_part = median(parts)
    med_slip = sqrt_impact_slippage_bps(med_part, impact_coef_bps=impact_coef_bps)
    return {
        "n": n,
        "n_dropped": dropped,
        "order_won": float(order_won),
        "median_participation": med_part,
        "mean_participation": mean(parts),
        "frac_feasible": sum(1 for p in parts if p <= feasible_participation) / n,
        "frac_strict": sum(1 for p in parts if p <= strict_participation) / n,
        "median_slippage_bps": med_slip,
        "slippage_adj_expectancy_pct_at_median": slippage_adjusted_expectancy_pct(
            gross_expectancy_pct, base_cost_bps, med_slip
        ),
    }


# ---------------------------------------------------------------------------
# CLI: read instances.json (ts_imb passers) -> per-account liquidity table.
# ---------------------------------------------------------------------------
def _load_entry_sec_amounts(
    instances_path: str,
    *,
    only_ts_imb: bool = True,
    unit_won: float = 1_000_000.0,
) -> List[float]:
    """Load entry_sec_amount (ts_imb passers), converted to WON via ``unit_won``.

    ``초당거래대금`` is stored in 백만원, so ``unit_won=1_000_000`` (default) converts
    to won.  None values are dropped; zeros are kept (and later treated as
    non-positive / dropped by :func:`summarize_liquidity`).
    """

    import json
    from pathlib import Path

    rows = json.loads(Path(instances_path).read_text(encoding="utf-8"))
    out: List[float] = []
    for r in rows:
        if only_ts_imb and not r.get("pass_ts_imb"):
            continue
        v = r.get("entry_sec_amount")
        if v is not None:
            out.append(float(v) * unit_won)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json
    import sys
    from pathlib import Path

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Liquidity feasibility & slippage (RULE NOT RL) - Page C."
    )
    parser.add_argument(
        "--instances",
        default=str(project_root / ".omx" / "artifacts" / "gap_up_full" / "instances.json"),
    )
    parser.add_argument("--base-cost-bps", type=float, default=DEFAULT_BASE_COST_BPS)
    parser.add_argument("--gross-expectancy-pct", type=float, default=DEFAULT_GROSS_EXPECTANCY_PCT)
    parser.add_argument(
        "--per-trade-fraction", type=float, default=0.10, help="f from Page A."
    )
    parser.add_argument(
        "--accounts-won",
        default="10000000,50000000,100000000",
        help="Comma-separated account sizes (won).",
    )
    parser.add_argument(
        "--impact-coefs-bps",
        default="5,10,20",
        help="Comma-separated square-root impact coefficients (bps) to sweep.",
    )
    parser.add_argument(
        "--sec-amount-unit-won",
        type=float,
        default=1_000_000.0,
        help="Unit of entry_sec_amount in won (초당거래대금 stored in 백만원 -> 1e6).",
    )
    parser.add_argument(
        "--json-out",
        default=str(project_root / ".omx" / "artifacts" / "liquidity" / "summary.json"),
    )
    args = parser.parse_args(argv)

    sec_amounts = _load_entry_sec_amounts(
        args.instances, only_ts_imb=True, unit_won=args.sec_amount_unit_won
    )
    accounts = [float(x) for x in args.accounts_won.split(",") if x.strip()]
    coefs = [float(x) for x in args.impact_coefs_bps.split(",") if x.strip()]

    print("=== liquidity feasibility & slippage (RULE strategy, NOT RL) - Page C ===")
    print(
        f"ts_imb instances with entry_sec_amount: {len(sec_amounts)}  "
        f"f={args.per_trade_fraction:g}  base_cost={args.base_cost_bps:g}bp  "
        f"gross_exp={args.gross_expectancy_pct:g}%"
    )
    print(
        f"  (초당거래대금 raw in 백만원; converted x{args.sec_amount_unit_won:,.0f} -> 원; "
        "slippage coef is an ASSUMPTION, no L2 calibration)"
    )

    results: Dict[str, Any] = {"n_ts_imb": len(sec_amounts), "by_account": []}
    for acct in accounts:
        order = args.per_trade_fraction * acct
        base = summarize_liquidity(
            sec_amounts,
            order_won=order,
            base_cost_bps=args.base_cost_bps,
            gross_expectancy_pct=args.gross_expectancy_pct,
            impact_coef_bps=DEFAULT_IMPACT_COEF_BPS,
        )
        coef_sweep = []
        for c in coefs:
            s = summarize_liquidity(
                sec_amounts,
                order_won=order,
                base_cost_bps=args.base_cost_bps,
                gross_expectancy_pct=args.gross_expectancy_pct,
                impact_coef_bps=c,
            )
            coef_sweep.append(
                {
                    "impact_coef_bps": c,
                    "median_slippage_bps": s["median_slippage_bps"],
                    "slippage_adj_expectancy_pct": s["slippage_adj_expectancy_pct_at_median"],
                }
            )
        entry = {
            "account_won": acct,
            "order_won": order,
            "median_participation": base["median_participation"],
            "frac_feasible_le_1x": base["frac_feasible"],
            "frac_strict_le_0.1x": base["frac_strict"],
            "coef_sweep": coef_sweep,
        }
        results["by_account"].append(entry)

        def f(v: Optional[float], spec: str = ".3f") -> str:
            return "n/a" if v is None else format(v, spec)

        print(f"-- account {acct:,.0f}원  order(f*acct)={order:,.0f}원 --")
        print(
            f"  median participation={f(base['median_participation'])}x  "
            f"feasible(<=1x)={f(base['frac_feasible'], '.0%')}  "
            f"strict(<=0.1x)={f(base['frac_strict'], '.0%')}"
        )
        for cs in coef_sweep:
            print(
                f"    impact_coef={cs['impact_coef_bps']:g}bp -> median_slip="
                f"{f(cs['median_slippage_bps'])}bp  "
                f"slip-adj exp={f(cs['slippage_adj_expectancy_pct'])}%"
            )

    print(
        "\nread: an account is liquidity-deployable when most trades are feasible "
        "(participation <= 1x) AND slip-adjusted expectancy stays positive across "
        "the coef sweep. Larger accounts push participation/slippage up."
    )

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote summary -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
