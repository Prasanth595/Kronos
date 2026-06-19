# STOM Daily OHLCV D4-A Environment Inspector Result (2026-06-13)

## Verdict

`RESEARCH_ONLY`. This is an environment/accounting inspection result, not a strategy result, not a trained policy, and not live/broker/order readiness.

The D4-A daily close-to-close / swing portfolio RL environment now exposes an explicit contract for state, constrained actions, action masks, fill assumption, reward components, 23bp turnover cost, drawdown/concentration/churn/invalid-action penalties, and generated inspection artifacts.

## Artifact

- Run: `env_inspection_2026_06_13_d4a_restart`
- Directory: `webui/rl_runs/daily_ohlcv_portfolio_env/env_inspection_2026_06_13_d4a_restart/`
- Input comparator/candidate source: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_13_d3_baseline_hardened/`
- Fill assumption: `close_to_next_close_research_label; no live/broker/order fill is inferred from daily OHLCV`
- Cost: 23bp round trip
- Status: `RESEARCH_ONLY`
- `model_build_allowed=false`

Generated files:

- `env_manifest.json`
- `reward_breakdown.csv`
- `action_masks.csv`
- `positions.csv`

## Environment contract

| Area | Contract |
|---|---|
| State | `(position_count, top_score_bucket)`; current holdings + current candidate score bucket only |
| Lookahead policy | `future_return_1d` labels are consumed only after action for reward accounting |
| Actions | `hold`, `buy`, `add`, `sell`, `reduce` |
| Action mask | buy/add/sell/reduce are valid only when position/candidate constraints allow them |
| Fill | close-to-next-close research label only; no broker/order fill claim |
| Accounting | equity, peak equity, current drawdown, turnover, exposure, concentration |
| Reward | gross return minus cost/risk/invalid/churn/drawdown penalties |

Reward formula:

```text
reward = gross_return
       - turnover_cost
       - exposure_penalty
       - concentration_penalty
       - invalid_action_penalty
       - churn_penalty
       - drawdown_penalty
```

## Inspection summary

The generated inspection used a deterministic scripted action sequence to exercise the environment. It is intentionally **not** a candidate strategy.

| Item | Value |
|---|---:|
| Steps | 309 |
| Invalid actions | 0 |
| Final equity | 0.1122517356 |
| Current drawdown | -0.8981224543 |

The poor final equity is acceptable for D4-A because the artifact is a stress/contract inspection of the environment path, not a trained policy. It confirms that reward breakdown, action masks, position logging, drawdown accounting, and guardrail metadata are generated.

## Verification

Commands run:

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_rl_gate.py -q
py -3.11 -m py_compile stom_rl/daily_portfolio_env.py stom_rl/daily_rl_train.py
```

Observed result:

- D4 environment/RL gate targeted tests: `8 passed`.
- Python compile: passed.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- D4 remains `RESEARCH_ONLY`.
- `model_build_allowed=false` remains in force until D0/D1/D3/D5 gates pass.
- Leading-zero stock codes are preserved in environment candidates and generated positions.
