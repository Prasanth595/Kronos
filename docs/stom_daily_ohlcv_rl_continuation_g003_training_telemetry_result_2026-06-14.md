# STOM Daily OHLCV RL Continuation G003 Training Telemetry Result (2026-06-14)

## Verdict

`RESEARCH_ONLY`. G003 hardens Daily OHLCV D4 RL training/evaluation telemetry for failure analysis. It is not a profit result, not a deployable model, and not live/broker/order readiness.

## Artifact

- Run: `portfolio_2026_06_14_g003_training_telemetry`
- Directory: `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_14_g003_training_telemetry/`
- Input D3 run: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_14_g004_d3_baseline_hardened/`
- Cost assumption: 23bp round trip
- Status: `RESEARCH_ONLY`
- `model_build_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false`

## What changed

| Area | Result |
|---|---|
| Reward breakdown | Adds `requested_action`, `executed_action`, `invalid_action_reason`, `no_trade_action`, `net_return_after_cost`, `no_trade_hold_reward`, and action-mask reason fields. |
| Action telemetry | Action distribution now separates requested vs executed actions, invalid reasons, and no-trade hold rows. |
| Reward/action ablations | Adds `reward_action_ablations.csv` and `reward_action_ablation_summary.json` with recorded reward and counterfactual removals of turnover cost, drawdown, concentration, churn, and invalid-action penalties. |
| Turnover/drawdown telemetry | Carries requested/executed/no-trade context and net-after-cost accounting into turnover/drawdown CSVs. |
| State observations | Adds action-mask bitset and per-action mask reasons while preserving `future_label_exposed=false`. |
| Provenance | Adds source hashes for `stom_rl/daily_rl_train.py`, `stom_rl/daily_portfolio_env.py`, and `stom_rl/daily_prediction.py`; generated `source_hashes.json`. |
| D3 overlay | Keeps frozen D3 baseline overlay in `policy_baseline_comparison.csv` with no-trade/shuffle/rule/supervised baselines at 23bp. |

## Current run interpretation

The generated policy remains a constrained D4 diagnostic path. On this run it records all/mostly no-trade hold behavior and does not unlock model building. That is visible evidence for failure analysis, not something to hide or re-label as success. D5 fresh OOS walk-forward, shuffle/no-trade controls, D0 price-basis confirmation, D1 universe review, and D3 baseline status still govern promotion.

## Verification

Commands run:

```powershell
py -3.11 -m py_compile stom_rl/daily_rl_train.py tests/test_stom_rl_daily_rl_gate.py
py -3.11 -m pytest tests/test_stom_rl_daily_rl_gate.py -q
py -3.11 -c "import json; from stom_rl.daily_rl_train import run_and_write_daily_rl; out=run_and_write_daily_rl(run_id='portfolio_2026_06_14_g003_training_telemetry', overwrite=True, prediction_run_dir='webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_14_g004_d3_baseline_hardened', episodes=8, candidate_limit=20, max_positions=5, seed=7); print(json.dumps({'run_id': out['written']['run_id'], 'artifact_dir': out['written']['artifact_dir'], 'status': out['result']['verdict']['status'], 'model_build_allowed': out['result']['manifest']['model_build_allowed'], 'reward_action_ablation_rows': out['result']['manifest']['row_counts']['reward_action_ablation_rows'], 'source_hash_count': len(out['result']['source_hashes'])}, ensure_ascii=False))"
py -3.11 -m py_compile stom_rl/daily_rl_train.py stom_rl/daily_portfolio_env.py tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_portfolio_env.py
py -3.11 -m pytest tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_portfolio_env.py -q
```

Observed results:

- `tests/test_stom_rl_daily_rl_gate.py`: `4 passed`.
- Combined focused RL/env regression: `13 passed`.
- Artifact generation wrote `portfolio_2026_06_14_g003_training_telemetry` with `status=RESEARCH_ONLY`, `model_build_allowed=false`, 28 reward/action ablation rows, and 3 source hashes.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- 23bp round-trip cost remains the default accounting assumption.
- Leading-zero stock codes remain string-preserved in source and artifact paths.
- D4 remains `RESEARCH_ONLY`; D5 remains required before any model-build claim.
