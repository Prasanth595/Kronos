"""Frozen-policy paper-trading replay for the 시초 갭상승 strategy (Page D).

**RULE strategy, NOT reinforcement learning.**

There is no live market feed in this environment, so a TRUE forward/paper run is
impossible.  The closest honest proxy is a **frozen-policy replay**: take the
fully pre-registered rule (등락율>=2% + ts_imb + TP5/SL1/09:25) AND the Page A
operating policy (sizing f, top-K concurrency, consecutive-loss + monthly
de-risk, daily-loss halt) — change NOTHING — and walk it chronologically over a
recent holdout window as if it had been traded day by day.  This is the first
time the SIZING rules touch an actual trade SEQUENCE (Page A was static
formulas), so it tests whether the operating policy produces a sane ACCOUNT
equity path, not just a per-trade %.

Honest limits: same triggered-subset DB (not a live feed, not new data); the
rule has no fitted parameters so the whole history is effectively out-of-sample
for the rule, but a recent-window replay is NOT a substitute for real forward
observation.  Within-day entries fire near-simultaneously at the open, so the
daily-loss halt is modelled by processing the day's top-K in signal order and
stopping further entries once the day's realized loss reaches the limit — a mild
approximation (real opens are simultaneous), not a precise intraday sequence.
The consecutive-loss halt is a CIRCUIT BREAKER: when the streak reaches the halt
tier the day is skipped and the streak resets (cooldown), so trading resumes —
this replay surfaced that the literal Page A "halt" (size 0 until a win) deadlocks,
since a halted account takes no trades and so can never win to reset the streak.
Note the reset re-arms FULL size the next day (a sawtooth that deploys MORE capital
into a sustained drawdown than the tiered ladder alone — a recovery convenience,
not extra safety).  The daily-loss limit is measured against the start-of-day
account (not running intraday equity), and ``n_skipped_halt`` aggregates BOTH the
consecutive-loss circuit-breaker skips and the intraday daily-loss skips.

Core is PURE (no I/O); the CLI reads the gitignored ``instances.json`` artifact.
"""

from __future__ import annotations

from itertools import groupby
from typing import Any, Dict, List, Optional, Sequence

from stom_rl.gap_up_risk_sizing import (
    RiskConfig,
    effective_fraction,
    position_notional_won,
    should_halt_day,
)


def simulate_paper_account(
    trades: Sequence[Dict[str, Any]],
    config: RiskConfig,
    *,
    initial_account_won: float,
    compounding: bool = True,
) -> Dict[str, Any]:
    """Replay the frozen rule+sizing policy over a chronological trade sequence.

    ``trades`` items: ``{"date": "YYYYMMDD", "strength": float, "sec_amount_won":
    float|None, "net_pct": float}`` where ``net_pct`` is the rule's per-trade net
    return (% of notional) for the primary TP5/SL1 cell.  Each day the top-``K``
    (= ``config.max_concurrent``) candidates by ``strength`` are taken; each is
    sized by ``effective_fraction`` (consecutive-loss + monthly de-risk) times the
    sizing base (current equity if ``compounding`` else the initial account),
    capped by liquidity (``sec_amount_won``).  The daily-loss halt stops further
    same-day entries once the day's realized loss reaches the limit.  Returns the
    account path and summary (final equity, total return %, max drawdown %, and
    how many signals were taken / skipped by the K cap or a halt).
    """

    if initial_account_won <= 0:
        raise ValueError("initial_account_won must be > 0")
    k = config.max_concurrent

    ordered = sorted(trades, key=lambda t: str(t["date"]))
    account = float(initial_account_won)
    peak = account
    max_dd_pct = 0.0
    streak = 0
    n_signals = 0
    n_taken = 0
    n_skipped_cap = 0
    n_skipped_halt = 0
    n_days = 0
    n_days_daily_limit_hit = 0
    month: Optional[str] = None
    month_start_account = account
    equity_curve: List[float] = [account]

    for date, group in groupby(ordered, key=lambda t: str(t["date"])):
        day = sorted(group, key=lambda t: (t.get("strength") or 0.0), reverse=True)
        n_signals += len(day)
        n_days += 1

        m = str(date)[:6]
        if month is None or m != month:
            month = m
            month_start_account = account
        month_return_pct = (
            (account / month_start_account - 1.0) * 100.0
            if month_start_account > 0
            else 0.0
        )
        f_eff = effective_fraction(config, streak, month_return_pct)
        sizing_base = account if compounding else float(initial_account_won)

        taken_today = day[:k]
        n_skipped_cap += max(0, len(day) - k)

        if f_eff <= 0.0:
            # Consecutive-loss circuit breaker tripped (streak at the halt tier):
            # sit the day out, then RESET the streak (cooldown complete) so trading
            # resumes next day.  Without this reset a halted account takes no
            # trades, so it can never win to reset the streak and would freeze
            # FOREVER — a deadlock this replay surfaced in the literal Page A policy.
            n_skipped_halt += len(taken_today)
            streak = 0
            equity_curve.append(account)
            continue

        day_pnl = 0.0
        day_nets: List[float] = []
        halted = False
        for t in taken_today:
            if should_halt_day(day_pnl, account, config):
                n_skipped_halt += 1
                halted = True
                continue
            notional = position_notional_won(
                sizing_base,
                config,
                fraction=f_eff,
                entry_liquidity_won=t.get("sec_amount_won"),
            )
            pnl = notional * float(t["net_pct"]) / 100.0
            day_pnl += pnl
            day_nets.append(float(t["net_pct"]))
            n_taken += 1
        if halted:
            n_days_daily_limit_hit += 1

        account += day_pnl
        # Update the consecutive-loss streak from the day's taken trades (the
        # next day sizes off this).  A win resets; a loss extends.
        for net in day_nets:
            streak = 0 if net > 0.0 else streak + 1

        peak = max(peak, account)
        if peak > 0:
            dd_pct = (account / peak - 1.0) * 100.0
            max_dd_pct = min(max_dd_pct, dd_pct)
        equity_curve.append(account)

    total_return_pct = (account / float(initial_account_won) - 1.0) * 100.0
    return {
        "initial_account_won": float(initial_account_won),
        "final_account_won": account,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_dd_pct,
        "n_days": n_days,
        "n_signals": n_signals,
        "n_taken": n_taken,
        "n_skipped_cap": n_skipped_cap,
        "n_skipped_halt": n_skipped_halt,
        "n_days_daily_limit_hit": n_days_daily_limit_hit,
        "compounding": compounding,
        "equity_curve": equity_curve,
    }


# ---------------------------------------------------------------------------
# CLI: read instances.json (ts_imb) -> frozen-policy replay (full + holdout).
# ---------------------------------------------------------------------------
def _load_trades(
    instances_path: str,
    *,
    net_pct_key: str = "tp5_sl1_net_pct",
    sec_amount_unit_won: float = 1_000_000.0,
) -> List[Dict[str, Any]]:
    import json
    from pathlib import Path

    # utf-8-sig tolerates a BOM if a sibling writer added one (plain utf-8 would
    # leave ﻿ on the first key and break json.loads).
    rows = json.loads(Path(instances_path).read_text(encoding="utf-8-sig"))
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not r.get("pass_ts_imb"):
            continue
        net = r.get(net_pct_key)
        if net is None:
            continue
        sa = r.get("entry_sec_amount")
        out.append(
            {
                "date": str(r["session"]),
                "strength": r.get("entry_trade_strength"),
                "sec_amount_won": (float(sa) * sec_amount_unit_won) if sa is not None else None,
                "net_pct": float(net),
            }
        )
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
        description="Frozen-policy paper replay (RULE NOT RL) - Page D."
    )
    parser.add_argument(
        "--instances",
        default=str(project_root / ".omx" / "artifacts" / "gap_up_full" / "instances.json"),
    )
    parser.add_argument("--net-pct-key", default="tp5_sl1_net_pct")
    parser.add_argument("--initial-account-won", type=float, default=100_000_000.0)
    parser.add_argument(
        "--holdout-start",
        default="20250901",
        help="YYYYMMDD; trades on/after this date form the recent forward-proxy holdout.",
    )
    parser.add_argument(
        "--no-compounding", action="store_true", help="Size off the initial account (fixed)."
    )
    parser.add_argument(
        "--json-out",
        default=str(project_root / ".omx" / "artifacts" / "paper_sim" / "summary.json"),
    )
    args = parser.parse_args(argv)

    trades = _load_trades(args.instances, net_pct_key=args.net_pct_key)
    holdout = [t for t in trades if t["date"] >= args.holdout_start]
    config = RiskConfig()
    compounding = not args.no_compounding

    def run(label: str, ts: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not ts:
            print(f"-- {label}: no trades --")
            return {"label": label, "n_signals": 0}
        s = simulate_paper_account(
            ts, config, initial_account_won=args.initial_account_won, compounding=compounding
        )
        dmin = min(t["date"] for t in ts)
        dmax = max(t["date"] for t in ts)
        print(f"-- {label}  dates {dmin}->{dmax} --")
        print(
            f"  signals={s['n_signals']} taken={s['n_taken']} "
            f"skipped(cap/halt)={s['n_skipped_cap']}/{s['n_skipped_halt']} "
            f"days={s['n_days']} daily_limit_days={s['n_days_daily_limit_hit']}"
        )
        print(
            f"  account {s['initial_account_won']:,.0f} -> {s['final_account_won']:,.0f}  "
            f"return={s['total_return_pct']:+.1f}%  maxDD={s['max_drawdown_pct']:+.1f}%  "
            f"(compounding={s['compounding']})"
        )
        s.pop("equity_curve", None)  # keep JSON small
        s["label"] = label
        return s

    print("=== frozen-policy paper replay (RULE strategy, NOT RL) - Page D ===")
    print(
        f"filter=ts_imb f={config.per_trade_fraction:g} K={config.max_concurrent} "
        f"daily_limit={config.daily_loss_limit_pct:g}% net_pct_key={args.net_pct_key} "
        f"(NOT a live feed; frozen-policy replay on a fixed DB)"
    )
    results = [run("FULL", trades), run(f"HOLDOUT(>={args.holdout_start})", holdout)]

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "instances": args.instances,
                "net_pct_key": args.net_pct_key,
                "initial_account_won": args.initial_account_won,
                "holdout_start": args.holdout_start,
                "compounding": compounding,
                "runs": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        "\nread: a sane holdout account path (positive return, drawdown within the "
        "Page A envelope, most signals actually taken) supports moving toward a "
        "REAL forward/paper run (still required before any live order)."
    )
    print(f"wrote summary -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
