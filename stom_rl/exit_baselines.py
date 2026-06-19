"""Causal exit baselines + honest evaluation toolkit (Page R1b).

**RULE strategy, NOT reinforcement learning.**  R1 showed a large perfect-foresight
exit ceiling (capture ~18%), but that is a *necessary-not-sufficient* signal.  R1b
asks the decisive question with CAUSAL (executable, no look-ahead) exit rules:

    Does ANY simple causal exit (wider SL / trailing stop) beat the fixed
    TP5 / SL1 / 09:25 rule OUT-OF-SAMPLE, after costs, once the search is
    deflated for the number of variants tried?

If yes -> the R1 headroom is partly causally capturable -> an RL/optimal-stopping
exit (R3) is justified.  If no -> the headroom is pure hindsight -> do NOT build
RL; return to the operational track.

This module provides:
* :func:`simulate_trailing_stop` — a causal trailing-stop simulator (the fixed
  SL/TP rule is reused from :mod:`stom_rl.gap_up_backtest`).
* per-trade Sharpe + the **Deflated Sharpe Ratio** (Bailey & Lopez de Prado 2014)
  and its expected-maximum-Sharpe term — the multiple-testing guard R0 mandates.
* :func:`evaluate_exit_candidates` / :func:`walk_forward_select` — apply a grid of
  candidate exits, select on IN-SAMPLE, report OUT-OF-SAMPLE (leakage-free) and the
  DSR of the selection.

All core functions are PURE (no I/O); the CLI reuses ``collect_gap_up_instances``
for the same bounded DB reads.  Sharpe here is PER-TRADE (not annualized): a
relative/deflation diagnostic, NOT a deployment Sharpe.
"""

from __future__ import annotations

import math
from statistics import NormalDist, mean, stdev, variance
from typing import Any, Dict, List, Optional, Sequence

from stom_rl.gap_up_backtest import (
    EXIT_SL,
    EXIT_TIME,
    EXIT_TP,
    GapUpInstance,
    TradeResult,
    simulate_trade,
    split_instances_by_date,
)

DEFAULT_TP_PCT: float = 5.0
DEFAULT_SL_PCT: float = 1.0
DEFAULT_COST_BPS: float = 23.0
EULER_MASCHERONI: float = 0.5772156649015329
EXIT_TRAIL: str = "trail"

_TRAIL_FILL_MODES = frozenset({"idealized", "realized"})


# ---------------------------------------------------------------------------
# Causal trailing-stop simulator (no look-ahead; the SL/TP rule is reused).
# ---------------------------------------------------------------------------
def simulate_trailing_stop(
    prices: Sequence[float],
    *,
    trail_pct: float,
    tp_pct: Optional[float] = None,
    cost_bps: float = DEFAULT_COST_BPS,
    fill_mode: str = "realized",
    seconds: Optional[Sequence[int]] = None,
) -> TradeResult:
    """Walk the forward path and exit on a CAUSAL trailing stop.

    The stop ratchets up with the running peak since entry: at each forward bar
    the stop level is ``peak * (1 - trail_pct/100)``; the trade exits the first
    time the price falls to/through it.  Because the initial peak is the entry,
    ``trail_pct`` also acts as the initial stop (so trail=1% starts like SL1% but
    follows the price up).  An optional hard ``tp_pct`` take-profit is checked
    first each bar.  ``realized`` fills book the actual breaching price (the
    honest assumption, matching :mod:`stom_rl.exit_oracle`); ``idealized`` books
    the stop/TP level.  No look-ahead: only prices up to the current bar are used.
    """

    if fill_mode not in _TRAIL_FILL_MODES:
        raise ValueError(f"fill_mode must be one of {sorted(_TRAIL_FILL_MODES)!r}")
    if trail_pct <= 0:
        raise ValueError("trail_pct must be > 0")
    if tp_pct is not None and tp_pct <= 0:
        raise ValueError("tp_pct must be > 0 when given")
    if cost_bps < 0:
        raise ValueError("cost_bps must be >= 0")
    if not prices:
        raise ValueError("prices must contain at least the entry bar")
    entry = float(prices[0])
    if entry <= 0:
        raise ValueError("entry price must be positive")

    cost_pct = float(cost_bps) / 100.0
    tp_level = entry * (1.0 + tp_pct / 100.0) if tp_pct is not None else None
    peak = entry

    def _elapsed(idx: int) -> int:
        if seconds is not None and idx < len(seconds):
            return int(seconds[idx]) - int(seconds[0])
        return int(idx)

    exit_idx = len(prices) - 1
    exit_price = float(prices[-1])
    exit_reason = EXIT_TIME

    for idx in range(1, len(prices)):
        price = float(prices[idx])
        if tp_level is not None and price >= tp_level:
            booked = price if fill_mode == "realized" else tp_level
            exit_idx, exit_price, exit_reason = idx, booked, EXIT_TP
            break
        peak = max(peak, price)
        stop_level = peak * (1.0 - trail_pct / 100.0)
        if price <= stop_level:
            booked = price if fill_mode == "realized" else stop_level
            exit_idx, exit_price, exit_reason = idx, booked, EXIT_TRAIL
            break

    gross = (exit_price / entry - 1.0) * 100.0
    return TradeResult(
        entry_price=entry,
        exit_price=float(exit_price),
        exit_reason=exit_reason,
        hold_seconds=_elapsed(exit_idx),
        gross_return_pct=float(gross),
        net_return_pct=float(gross - cost_pct),
    )


# ---------------------------------------------------------------------------
# Per-trade Sharpe + Deflated Sharpe Ratio (multiple-testing guard).
# ---------------------------------------------------------------------------
def per_trade_sharpe(net_returns: Sequence[float]) -> Optional[float]:
    """Per-trade Sharpe = mean / sample-stdev of net returns (None if undefined).

    NOT annualized — a relative/deflation diagnostic over the trade sample, not a
    deployment Sharpe.  Returns ``None`` for fewer than 2 trades or zero variance.
    """

    if len(net_returns) < 2:
        return None
    sd = stdev(net_returns)
    if sd <= 0.0:
        return None
    return mean(net_returns) / sd


def expected_max_sharpe(n_trials: int, sharpe_variance: float) -> float:
    """Expected maximum Sharpe under the null over ``n_trials`` (Bailey-LdP).

    ``E[max] = sqrt(Var(SR)) * [ (1-gamma)*Z^-1(1 - 1/N) + gamma*Z^-1(1 - 1/(N*e)) ]``
    with ``gamma`` the Euler-Mascheroni constant.  This is the SR threshold a
    strategy must clear just to beat the best of ``N`` independent random trials.
    Returns 0.0 for a single trial (no selection inflation).
    """

    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    if sharpe_variance < 0:
        raise ValueError("sharpe_variance must be >= 0")
    if n_trials == 1 or sharpe_variance == 0.0:
        return 0.0
    norm = NormalDist()
    z1 = norm.inv_cdf(1.0 - 1.0 / n_trials)
    z2 = norm.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(sharpe_variance) * ((1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)


def deflated_sharpe_ratio(
    observed_sharpe: float,
    *,
    n_trials: int,
    sharpe_variance: float,
    n_samples: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014), in [0, 1].

    The probability that the true Sharpe is positive AFTER correcting for (a)
    selection under ``n_trials`` multiple tests, and (b) non-normal returns
    (``skew``, non-excess ``kurtosis``, normal = 3).  ``DSR > 0.95`` is the usual
    significance bar.  ``n_samples`` is the trade count T.
    """

    if n_samples < 2:
        raise ValueError("n_samples must be >= 2")
    sr0 = expected_max_sharpe(n_trials, sharpe_variance)
    denom = math.sqrt(
        max(1e-12, 1.0 - skew * observed_sharpe + (kurtosis - 1.0) / 4.0 * observed_sharpe ** 2)
    )
    z = (observed_sharpe - sr0) * math.sqrt(n_samples - 1) / denom
    return NormalDist().cdf(z)


# ---------------------------------------------------------------------------
# Candidate exit policies + grid evaluation + walk-forward selection.
# ---------------------------------------------------------------------------
def _resolve_trade(
    inst: GapUpInstance,
    candidate: Dict[str, Any],
    *,
    cost_bps: float,
    fill_mode: str,
) -> TradeResult:
    """Resolve one instance under one candidate exit policy."""

    kind = candidate.get("kind")
    if kind == "fixed":
        return simulate_trade(
            inst.prices,
            tp_pct=candidate["tp_pct"],
            sl_pct=candidate["sl_pct"],
            cost_bps=cost_bps,
            seconds=inst.seconds,
            fill_mode=fill_mode,
        )
    if kind == "trail":
        return simulate_trailing_stop(
            inst.prices,
            trail_pct=candidate["trail_pct"],
            tp_pct=candidate.get("tp_pct"),
            cost_bps=cost_bps,
            fill_mode=fill_mode,
            seconds=inst.seconds,
        )
    raise ValueError(f"unknown candidate kind: {kind!r}")


def _aggregate(trades: Sequence[TradeResult]) -> Dict[str, Any]:
    """n, mean net, win rate, per-trade Sharpe over a set of resolved trades."""

    n = len(trades)
    if n == 0:
        return {"n": 0, "mean_net_pct": None, "win_rate": None, "sharpe": None}
    nets = [t.net_return_pct for t in trades]
    wins = sum(1 for v in nets if v > 0.0)
    return {
        "n": n,
        "mean_net_pct": mean(nets),
        "win_rate": wins / n,
        "sharpe": per_trade_sharpe(nets),
    }


def evaluate_exit_candidates(
    instances: Sequence[GapUpInstance],
    candidates: Sequence[Dict[str, Any]],
    *,
    cost_bps: float = DEFAULT_COST_BPS,
    fill_mode: str = "realized",
) -> List[Dict[str, Any]]:
    """Aggregate metrics for each candidate exit policy over the instances."""

    if fill_mode not in _TRAIL_FILL_MODES:
        raise ValueError(
            f"fill_mode must be one of {sorted(_TRAIL_FILL_MODES)!r} for the exit "
            "grid (sl_gap_stress is unsupported because trailing stops use only "
            "idealized/realized fills)"
        )
    out: List[Dict[str, Any]] = []
    for cand in candidates:
        trades = [
            _resolve_trade(inst, cand, cost_bps=cost_bps, fill_mode=fill_mode)
            for inst in instances
        ]
        agg = _aggregate(trades)
        agg["name"] = cand["name"]
        out.append(agg)
    return out


def default_candidate_grid() -> List[Dict[str, Any]]:
    """The pre-registered causal exit grid (fixed-SL widen + trailing stops).

    ``fixed_tp5_sl1`` is the incumbent rule (the baseline every variant must beat).
    The SL widen targets the R1 finding that 55% of regret comes from SL exits.
    """

    return [
        {"name": "fixed_tp5_sl1", "kind": "fixed", "tp_pct": 5.0, "sl_pct": 1.0},
        {"name": "fixed_tp5_sl1.5", "kind": "fixed", "tp_pct": 5.0, "sl_pct": 1.5},
        {"name": "fixed_tp5_sl2", "kind": "fixed", "tp_pct": 5.0, "sl_pct": 2.0},
        {"name": "fixed_tp5_sl3", "kind": "fixed", "tp_pct": 5.0, "sl_pct": 3.0},
        {"name": "trail_1", "kind": "trail", "trail_pct": 1.0},
        {"name": "trail_2", "kind": "trail", "trail_pct": 2.0},
        {"name": "trail_3", "kind": "trail", "trail_pct": 3.0},
        {"name": "trail_2_tp5", "kind": "trail", "trail_pct": 2.0, "tp_pct": 5.0},
        {"name": "trail_3_tp5", "kind": "trail", "trail_pct": 3.0, "tp_pct": 5.0},
    ]


def walk_forward_select(
    instances: Sequence[GapUpInstance],
    candidates: Sequence[Dict[str, Any]],
    *,
    in_sample_fraction: float = 0.7,
    cost_bps: float = DEFAULT_COST_BPS,
    fill_mode: str = "realized",
    baseline_name: str = "fixed_tp5_sl1",
    select_by: str = "sharpe",
) -> Dict[str, Any]:
    """Select the best candidate IN-SAMPLE, report it OUT-OF-SAMPLE + DSR.

    The selection metric (``select_by``) is read on the IN-SAMPLE split only; the
    headline is the selected candidate's OUT-OF-SAMPLE mean net vs the baseline's
    OOS mean net (leakage-free).  The Deflated Sharpe Ratio is computed on the
    selected candidate's OOS per-trade Sharpe with ``n_trials = len(candidates)``
    and the cross-candidate IN-SAMPLE Sharpe variance — so a variant that wins OOS
    only because many were tried is exposed.

    ``oos_improvement_pct`` is cost-invariant: both legs pay the same additive
    round-trip cost, so it cancels in the difference (same property as the
    exit-oracle regret).  Honesty note: the DSR here is a HYBRID directional guard
    — its deflation threshold uses IN-SAMPLE cross-candidate Sharpe dispersion
    while the observed Sharpe / T are OUT-OF-SAMPLE.  It is not the canonical
    single-sample DSR; the leakage-free OOS net comparison is the primary headline
    and the DSR is the secondary multiple-testing check.
    """

    in_sample, out_sample, boundary = split_instances_by_date(
        instances, in_sample_fraction=in_sample_fraction
    )
    is_res = evaluate_exit_candidates(in_sample, candidates, cost_bps=cost_bps, fill_mode=fill_mode)
    oos_res = evaluate_exit_candidates(out_sample, candidates, cost_bps=cost_bps, fill_mode=fill_mode)
    is_by = {r["name"]: r for r in is_res}
    oos_by = {r["name"]: r for r in oos_res}

    rankable = [r for r in is_res if r.get(select_by) is not None]
    if not rankable:
        return {
            "boundary_date": boundary,
            "selected": None,
            "reason": f"no candidate has a defined in-sample {select_by}",
        }
    best = max(rankable, key=lambda r: r[select_by])
    sel = best["name"]
    sel_oos = oos_by.get(sel, {})
    base_oos = oos_by.get(baseline_name, {})

    is_sharpes = [r["sharpe"] for r in is_res if r["sharpe"] is not None]
    sharpe_var = variance(is_sharpes) if len(is_sharpes) >= 2 else 0.0
    sel_oos_sharpe = sel_oos.get("sharpe")
    sel_oos_n = sel_oos.get("n", 0)
    dsr = (
        deflated_sharpe_ratio(
            sel_oos_sharpe,
            n_trials=len(candidates),
            sharpe_variance=sharpe_var,
            n_samples=sel_oos_n,
        )
        if (sel_oos_sharpe is not None and sel_oos_n >= 2)
        else None
    )

    sel_oos_net = sel_oos.get("mean_net_pct")
    base_oos_net = base_oos.get("mean_net_pct")
    improvement = (
        sel_oos_net - base_oos_net
        if (sel_oos_net is not None and base_oos_net is not None)
        else None
    )
    return {
        "boundary_date": boundary,
        "n_in_sample": len(in_sample),
        "n_out_of_sample": len(out_sample),
        "n_trials": len(candidates),
        "select_by": select_by,
        "selected": sel,
        "selected_is_baseline": sel == baseline_name,
        "selected_oos_mean_net_pct": sel_oos_net,
        "selected_oos_sharpe": sel_oos_sharpe,
        "baseline_oos_mean_net_pct": base_oos_net,
        "baseline_oos_sharpe": base_oos.get("sharpe"),
        "oos_improvement_pct": improvement,
        "deflated_sharpe_ratio": dsr,
    }


# ---------------------------------------------------------------------------
# CLI: bounded DB read -> candidate grid table + walk-forward verdict.
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json
    import sys
    from pathlib import Path

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
        description="Causal exit baselines + Deflated Sharpe (RULE NOT RL) - Page R1b."
    )
    parser.add_argument("--db", default=str(project_root / "_database" / "stock_tick_back.db"))
    parser.add_argument("--max-symbols", type=int, default=120)
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    parser.add_argument("--in-sample-fraction", type=float, default=0.7)
    parser.add_argument("--filter", choices=list(ENTRY_FILTERS.keys()), default="ts_imb")
    parser.add_argument("--fill-mode", choices=["idealized", "realized"], default="realized")
    parser.add_argument(
        "--json-out",
        default=str(project_root / ".omx" / "artifacts" / "exit_baselines" / "summary.json"),
    )
    args = parser.parse_args(argv)

    config = GapUpBacktestConfig(
        db_path=args.db, max_symbols=args.max_symbols, cost_bps=args.cost_bps
    )
    instances = collect_gap_up_instances(config)
    kept = filter_instances(instances, ENTRY_FILTERS[args.filter])
    grid = default_candidate_grid()

    all_res = evaluate_exit_candidates(kept, grid, cost_bps=args.cost_bps, fill_mode=args.fill_mode)
    wf = walk_forward_select(
        kept,
        grid,
        in_sample_fraction=args.in_sample_fraction,
        cost_bps=args.cost_bps,
        fill_mode=args.fill_mode,
    )

    def f(v: Optional[float], spec: str = "+.3f") -> str:
        return "n/a" if v is None else format(v, spec)

    print("=== causal exit baselines (RULE strategy, NOT RL) - Page R1b ===")
    print(
        f"filter={args.filter} N={len(kept)} cost={args.cost_bps:g}bp fill={args.fill_mode} "
        f"IS_frac={args.in_sample_fraction}"
    )
    print("-- all-sample per-candidate (mean_net / win / per-trade Sharpe) --")
    for r in all_res:
        print(
            f"  {r['name']:<16} n={r['n']:<5} mean_net={f(r['mean_net_pct'])}% "
            f"win={f(r['win_rate'], '.0%')} sharpe={f(r['sharpe'])}"
        )
    print("-- walk-forward selection (select IN-SAMPLE, report OUT-OF-SAMPLE) --")
    print(
        f"  boundary={wf.get('boundary_date')} N(IS/OOS)={wf.get('n_in_sample')}/"
        f"{wf.get('n_out_of_sample')} n_trials={wf.get('n_trials')}"
    )
    print(
        f"  selected={wf.get('selected')} (is_baseline={wf.get('selected_is_baseline')})  "
        f"selected_OOS_net={f(wf.get('selected_oos_mean_net_pct'))}%  "
        f"baseline_OOS_net={f(wf.get('baseline_oos_mean_net_pct'))}%"
    )
    print(
        f"  OOS_improvement={f(wf.get('oos_improvement_pct'))}%  "
        f"deflated_sharpe_ratio={f(wf.get('deflated_sharpe_ratio'), '.3f')}"
    )
    print(
        "\nread: a causal variant must (1) beat the baseline OOS net AND "
        "(2) clear DSR>0.95 to justify an RL exit (R3); else exit headroom is "
        "hindsight -> do NOT build RL, return to operational track."
    )

    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "filter": args.filter,
                "n": len(kept),
                "cost_bps": args.cost_bps,
                "fill_mode": args.fill_mode,
                "all_sample": all_res,
                "walk_forward": wf,
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
