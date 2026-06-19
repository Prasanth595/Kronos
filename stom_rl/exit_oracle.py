"""Oracle-exit ceiling test for the 시초 갭상승 strategy (Page R1).

**RULE strategy, NOT reinforcement learning.**  This module does NOT learn or
trade; it MEASURES whether a smarter exit could even exist, to decide — before
any RL/optimal-stopping work — whether such work is worth attempting.

The question (gate before RL)
-----------------------------
The rule exits via a fixed TP5 / SL1 / 09:25 time-exit.  Could a *smarter* exit
do materially better?  We compute, per trade::

    regret = oracle_exit_net  -  rule_exit_net

where ``oracle_exit_net`` is the **perfect-foresight best exit**: sell at the
HIGHEST price actually reached on the forward path (a price that occurred, so it
is achievable in principle).  Perfect foresight is an UPPER BOUND on ANY causal
exit policy — including the best possible RL policy — so:

* **small regret**  → the fixed rule already captures the achievable exit value;
  an RL exit policy has almost no ceiling → **DO NOT build it.**
* **large regret**  → there is headroom a causal policy *might* recover a
  fraction of → an RL / optimal-stopping exit is worth attempting (still gated
  by honest OOS evaluation: Deflated Sharpe, PBO/CSCV, multi-seed).

Cost-invariance (a robustness feature)
--------------------------------------
Both the oracle and the rule pay ONE round-trip cost, so cost CANCELS in the
regret (``regret = oracle_gross - rule_gross``).  The ceiling verdict is
therefore robust to the exact cost assumption (23 vs 25 bp); cost only shifts the
*level* of ``rule_net`` / ``oracle_net``, not the headroom between them.

Fill realism (why the default is ``realized``)
----------------------------------------------
Both legs use **realized** fills (a price that actually occurred) by default, so
``regret >= 0`` always and measures pure exit-*timing* headroom.  The rule's
``idealized`` fill books the exact TP/SL *level* — an optimistic fiction that can
exceed the realized oracle on a gap-through stop (yielding a spurious NEGATIVE
regret), so it is deliberately NOT the default for this ceiling test.

The core functions are PURE (no I/O); the CLI reuses ``collect_gap_up_instances``
from :mod:`stom_rl.gap_up_backtest` for the same bounded DB reads.
"""

from __future__ import annotations

from statistics import mean, median
from typing import Any, Dict, List, Optional, Sequence

from stom_rl.gap_up_backtest import (
    EXIT_SL,
    EXIT_TIME,
    EXIT_TP,
    GapUpInstance,
    simulate_trade,
)

# Primary cell (verified upstream): TP5 / SL1, ts_imb filter, 23 bp real cost.
DEFAULT_TP_PCT: float = 5.0
DEFAULT_SL_PCT: float = 1.0
DEFAULT_COST_BPS: float = 23.0


def _percentile(values: Sequence[float], q: float) -> Optional[float]:
    """Nearest-rank percentile (q in [0, 1]); None for an empty sequence."""

    if not values:
        return None
    if not (0.0 <= q <= 1.0):
        raise ValueError("q must be in [0, 1]")
    ordered = sorted(values)
    idx = int(round(q * (len(ordered) - 1)))
    idx = max(0, min(len(ordered) - 1, idx))
    return ordered[idx]


def oracle_exit_net_pct(
    prices: Sequence[float],
    *,
    cost_bps: float = DEFAULT_COST_BPS,
) -> float:
    """Perfect-foresight best-exit net return (%) for an already-entered trade.

    The position is entered at ``prices[0]``; the oracle sells at the HIGHEST
    price on the forward path (``prices[1:]``).  When there is no forward bar the
    only achievable exit is the entry price itself.  The booked price is the
    actual maximum (a realized fill, the most generous assumption), making this a
    strict UPPER BOUND on any causal exit policy.  One round-trip ``cost_bps`` is
    subtracted, matching :func:`stom_rl.gap_up_backtest.simulate_trade`.
    """

    if not prices:
        raise ValueError("prices must contain at least the entry bar")
    entry = float(prices[0])
    if entry <= 0:
        raise ValueError("entry price must be positive")
    if cost_bps < 0:
        raise ValueError("cost_bps must be >= 0")
    forward = prices[1:]
    best_price = max(float(p) for p in forward) if forward else entry
    gross = (best_price / entry - 1.0) * 100.0
    return gross - float(cost_bps) / 100.0


def rule_exit_net_pct(
    prices: Sequence[float],
    *,
    tp_pct: float = DEFAULT_TP_PCT,
    sl_pct: float = DEFAULT_SL_PCT,
    cost_bps: float = DEFAULT_COST_BPS,
    fill_mode: str = "realized",
) -> float:
    """Net return (%) of the fixed TP/SL/time rule (delegates to simulate_trade).

    Defaults to ``realized`` fills so it pairs apples-to-apples with the realized
    oracle in :func:`exit_regret_pct` (see the module docstring's "Fill realism").
    """

    return simulate_trade(
        prices,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        cost_bps=cost_bps,
        fill_mode=fill_mode,
    ).net_return_pct


def exit_regret_pct(
    prices: Sequence[float],
    *,
    tp_pct: float = DEFAULT_TP_PCT,
    sl_pct: float = DEFAULT_SL_PCT,
    cost_bps: float = DEFAULT_COST_BPS,
    fill_mode: str = "realized",
) -> float:
    """Per-trade exit regret = oracle_net - rule_net.

    Under the default ``realized`` fills this is ``>= 0`` by construction: the
    oracle books the maximum forward price, and the realized rule books some
    forward price ``<= max``.  A large value means the fixed rule left exit value
    on the table (e.g. stopped out before a recovery, or sold at the first TP
    cross before a higher print); near-zero means the rule already exited
    near-optimally.  Passing ``fill_mode="idealized"`` can yield a spurious
    NEGATIVE regret (the SL/TP-level fiction beats the realized oracle) — see the
    module docstring.
    """

    oracle = oracle_exit_net_pct(prices, cost_bps=cost_bps)
    rule = rule_exit_net_pct(
        prices,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        cost_bps=cost_bps,
        fill_mode=fill_mode,
    )
    return oracle - rule


def summarize_exit_regret(
    instances: Sequence[GapUpInstance],
    *,
    tp_pct: float = DEFAULT_TP_PCT,
    sl_pct: float = DEFAULT_SL_PCT,
    cost_bps: float = DEFAULT_COST_BPS,
    fill_mode: str = "realized",
    optimal_eps: float = 1e-9,
) -> Dict[str, Any]:
    """Aggregate the oracle-vs-rule exit regret over a set of instances.

    Returns rule/oracle mean net, the regret distribution (mean/median/p90/max),
    the capture ratio (rule_mean / oracle_mean when the oracle mean is positive),
    the fraction of trades the rule already exits optimally (regret <= eps), and a
    per-rule-exit-reason regret breakdown (tp / sl / time) so the headroom can be
    attributed (e.g. large regret on SL exits == stops cut winners that recover).
    """

    n = len(instances)
    if n == 0:
        return {
            "n": 0,
            "rule_mean_net_pct": None,
            "oracle_mean_net_pct": None,
            "regret_mean_pct": None,
            "regret_median_pct": None,
            "regret_p90_pct": None,
            "regret_max_pct": None,
            "capture_ratio": None,
            "frac_rule_optimal": None,
            "by_exit_reason": {},
        }

    rule_nets: List[float] = []
    oracle_nets: List[float] = []
    regrets: List[float] = []
    reasons: List[str] = []
    for inst in instances:
        tr = simulate_trade(
            inst.prices,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            cost_bps=cost_bps,
            seconds=inst.seconds,
            fill_mode=fill_mode,
        )
        oracle = oracle_exit_net_pct(inst.prices, cost_bps=cost_bps)
        rule_nets.append(tr.net_return_pct)
        oracle_nets.append(oracle)
        regrets.append(oracle - tr.net_return_pct)
        reasons.append(tr.exit_reason)

    rule_mean = mean(rule_nets)
    oracle_mean = mean(oracle_nets)
    capture = (rule_mean / oracle_mean) if oracle_mean > 0 else None
    frac_optimal = sum(1 for r in regrets if r <= optimal_eps) / n

    by_reason: Dict[str, Dict[str, Any]] = {}
    for reason in (EXIT_TP, EXIT_SL, EXIT_TIME):
        idxs = [i for i, rr in enumerate(reasons) if rr == reason]
        if not idxs:
            by_reason[reason] = {"n": 0, "share": 0.0, "regret_mean_pct": None}
            continue
        reason_regrets = [regrets[i] for i in idxs]
        by_reason[reason] = {
            "n": len(idxs),
            "share": len(idxs) / n,
            "regret_mean_pct": mean(reason_regrets),
        }

    return {
        "n": n,
        "rule_mean_net_pct": rule_mean,
        "oracle_mean_net_pct": oracle_mean,
        "regret_mean_pct": mean(regrets),
        "regret_median_pct": median(regrets),
        "regret_p90_pct": _percentile(regrets, 0.90),
        "regret_max_pct": max(regrets),
        "capture_ratio": capture,
        "frac_rule_optimal": frac_optimal,
        "by_exit_reason": by_reason,
    }


# ---------------------------------------------------------------------------
# CLI: bounded DB read (reuses gap_up_backtest) -> ts_imb regret summary.
# ---------------------------------------------------------------------------
def _format_summary(s: Dict[str, Any]) -> str:
    if s["n"] == 0:
        return "n=0 (no instances)"

    def f(v: Optional[float]) -> str:
        return "n/a" if v is None else f"{v:+.3f}%"

    lines = [
        f"  N={s['n']}  rule_mean={f(s['rule_mean_net_pct'])}  "
        f"oracle_mean={f(s['oracle_mean_net_pct'])}",
        f"  regret: mean={f(s['regret_mean_pct'])}  "
        f"median={f(s['regret_median_pct'])}  "
        f"p90={f(s['regret_p90_pct'])}  max={f(s['regret_max_pct'])}",
        f"  capture_ratio="
        + ("n/a" if s["capture_ratio"] is None else f"{s['capture_ratio']:.1%}")
        + f"  frac_rule_optimal={s['frac_rule_optimal']:.1%}",
        "  regret by rule exit reason:",
    ]
    for reason in (EXIT_TP, EXIT_SL, EXIT_TIME):
        r = s["by_exit_reason"].get(reason, {})
        lines.append(
            f"    {reason:<4} n={r.get('n', 0):<5} share={r.get('share', 0.0):.0%} "
            f"regret_mean={f(r.get('regret_mean_pct'))}"
        )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json
    import sys
    from pathlib import Path

    # Windows consoles default to cp949 here and cannot encode em-dash/arrows;
    # force UTF-8 so the report (and Korean) prints regardless of console codepage.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    from stom_rl.gap_up_backtest import (
        ENTRY_FILTERS,
        GapUpBacktestConfig,
        collect_gap_up_instances,
        filter_instances,
    )

    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Oracle-exit ceiling test (RULE strategy, NOT RL) - Page R1."
    )
    parser.add_argument(
        "--db", default=str(project_root / "_database" / "stock_tick_back.db")
    )
    parser.add_argument("--max-symbols", type=int, default=120)
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    parser.add_argument("--tp-pct", type=float, default=DEFAULT_TP_PCT)
    parser.add_argument("--sl-pct", type=float, default=DEFAULT_SL_PCT)
    parser.add_argument(
        "--fill-mode",
        choices=["idealized", "realized", "sl_gap_stress"],
        default="realized",
    )
    parser.add_argument(
        "--filter",
        choices=list(ENTRY_FILTERS.keys()),
        default="ts_imb",
        help="Entry filter applied before the regret summary (default ts_imb).",
    )
    parser.add_argument(
        "--json-out",
        default=str(
            project_root / ".omx" / "artifacts" / "oracle_exit" / "summary.json"
        ),
        help="Where to write the regret summary JSON (gitignored).",
    )
    args = parser.parse_args(argv)

    config = GapUpBacktestConfig(
        db_path=args.db, max_symbols=args.max_symbols, cost_bps=args.cost_bps
    )
    instances = collect_gap_up_instances(config)

    print("=== oracle-exit ceiling test (RULE strategy, NOT RL) - Page R1 ===")
    print(
        f"db_max_symbols={args.max_symbols} tp={args.tp_pct:g}% sl={args.sl_pct:g}% "
        f"cost={args.cost_bps:g}bp fill={args.fill_mode}  (regret is cost-invariant)"
    )
    results: Dict[str, Any] = {}
    for fname in (args.filter,):
        kept = filter_instances(instances, ENTRY_FILTERS[fname])
        summary = summarize_exit_regret(
            kept,
            tp_pct=args.tp_pct,
            sl_pct=args.sl_pct,
            cost_bps=args.cost_bps,
            fill_mode=args.fill_mode,
        )
        results[fname] = summary
        print(f"-- filter={fname} --")
        print(_format_summary(summary))
    print(
        "\nread: small regret -> rule already near-optimal exit -> RL exit NOT "
        "worth building; large regret -> headroom -> RL/optimal-stopping gated by "
        "honest OOS eval may be attempted."
    )
    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "max_symbols": args.max_symbols,
                "tp_pct": args.tp_pct,
                "sl_pct": args.sl_pct,
                "cost_bps": args.cost_bps,
                "fill_mode": args.fill_mode,
                "n_instances_all": len(instances),
                "summaries": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote summary -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
