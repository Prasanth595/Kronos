# stom_rl Knowledge

## Overview

`stom_rl/` contains STOM trading research: gap-up rules, supervised gates,
portfolio/RL environments, orderbook RL readiness, and experiment CLIs.

## Current Boundary

- Main useful baseline is the `ts_imb` opening gap-up RULE strategy.
- RL/orderbook code is experimental unless it beats explicit baselines under
  cost-aware OOS gates.
- Skip-gate and state-exit gate have documented full-universe `NO-GO` results;
  do not rerun/tune them without a new preregistered hypothesis.

## Key Files

| File | Role |
|---|---|
| `gap_up_backtest.py` | Main gap-up rule/backtest machinery. |
| `marketable_fill.py` | Marketable-fill accounting for buy/exit assumptions. |
| `skip_gate.py` | Entry skip-gate; documented `NO-GO`. |
| `state_exit_gate.py` | 30-second early-exit gate; documented `NO-GO`. |
| `orderbook_rl_env.py` | Orderbook RL environment and readiness scan. |
| `orderbook_sb3_adapter.py` | SB3 adapter with invalid-action constraints. |
| `orderbook_sb3_smoke.py` | Orderbook RL smoke/evaluation CLI. |
| `portfolio_*` | Portfolio-level RL/walk-forward experiments. |

## Rules

- Label each strategy as `RULE`, `supervised gate`, `portfolio RL`, or
  `orderbook RL`. Do not blur these labels.
- Cost-aware net return is the default evaluation target.
- Do not claim alpha from `n_folds < 5` or from a single favorable split.
- Include no-trade/rule/baseline comparisons for any new RL result.
- For sparse action spaces, track invalid-action rate or use masked/constrained
  actions. Plain PPO/DQN churn is not a useful success signal.
- Generated artifacts should be written under `.omx/artifacts/` or
  `webui/rl_runs/`, not mixed into source directories.

## Verification

```powershell
py -3.11 -m pytest tests/test_stom_rl_gap_up_backtest.py tests/test_stom_rl_marketable_fill.py -q
py -3.11 -m pytest tests/test_stom_rl_orderbook_env.py tests/test_stom_rl_orderbook_sb3.py -q
py -3.11 -m pytest tests/test_stom_rl_skip_gate.py tests/test_stom_rl_state_exit_gate.py -q
```

## Anti-Patterns

- Retuning after seeing OOS/full-universe results.
- Calling a rule-generated equity curve "RL".
- Hiding `NO-GO` behind dashboard cosmetics.
- Evaluating high-frequency trades without spread/marketable-fill assumptions.
