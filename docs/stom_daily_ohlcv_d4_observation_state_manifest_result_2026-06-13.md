# STOM Daily OHLCV D4 Observation/State Manifest Gate Result (2026-06-13)

## Verdict

`PASS_RESEARCH_ONLY_STATE_CONTRACT` for the D4 environment/state manifest gate.

This is **not** a usable trading model, not live/broker/order readiness, and not a profit claim. It only confirms that D4 has an explicit observation/state contract separate from reward/action telemetry.

## Artifact

- Run: `env_inspection_2026_06_13_g002_state_manifest`
- Directory: `webui/rl_runs/daily_ohlcv_portfolio_env/env_inspection_2026_06_13_g002_state_manifest/`
- Source D3 candidate panel: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_13_d3_baseline_hardened/`
- Cost: 23bp round trip
- Fill assumption: `close_to_next_close_research_label; no live/broker/order fill is inferred from daily OHLCV`
- Status: research-only; `model_build_allowed=false`

Generated files:

- `env_manifest.json`
- `observation_manifest.json`
- `state_observations.csv`
- `reward_breakdown.csv`
- `action_masks.csv`
- `positions.csv`

## Manifest coverage

| Required area | Current contract |
|---|---|
| Feature timing | D3 score columns are current-date candidate features before action; `future_return_1d` availability must not filter the pre-action candidate/state/mask universe and is reward-only after action. |
| Holdings identity | Codes remain six-digit strings via `zfill(6)` and are used for masks, positions, and accounting. |
| Cash/exposure | `cash_fraction` and `exposure_fraction` derive from current `position_count / max_positions`; `state_observations.csv` records both before action. |
| Candidate rank/score | Candidates are sorted by current score descending within date before candidate limit truncation; `top_score_bucket` is the compact state feature. |
| Horizon alignment | Daily rebalance step with one-day future return reward label; close-to-next-close research label only. |
| Action mask semantics | `hold/buy/add/sell/reduce` validity is documented and tested. |
| Leakage checks | Future labels are excluded from state and action mask; missing future labels remain eligible candidates and are zero-filled only during post-action reward accounting. |
| Frozen D3 comparison | Required baselines are declared: no-trade, shuffle, equal-weight momentum, volatility-adjusted momentum, supervised ranker, supervised classifier. |

## Guardrail that remains locked

Reward/action telemetry alone is explicitly insufficient for D4 promotion:

```text
reward_action_telemetry_sufficient_for_d4=false
```

D4 remains `RESEARCH_ONLY`; D5 OOS/walk-forward/shuffle/no-trade gates and D0/D1 blockers still prevent model build.

## Verification

Commands run:

```powershell
py -3.11 -m py_compile stom_rl/daily_portfolio_env.py stom_rl/daily_rl_train.py tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_rl_gate.py
py -3.11 -m pytest tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_rl_gate.py -q
```

Observed result:

- Python compile: passed.
- Focused D4 env/RL tests: `9 passed`.

## Research-only constraints

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing path was added.
- No profit, deployable-model, or broker readiness claim is made.
- Leading-zero codes remain string-preserved.
- `model_build_allowed=false` remains in force until D0/D1/D3/D5 gates pass.
