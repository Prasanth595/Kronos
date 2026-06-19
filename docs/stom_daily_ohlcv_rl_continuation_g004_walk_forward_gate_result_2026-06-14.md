# STOM Daily OHLCV RL Continuation G004 Walk-Forward Gate Result (2026-06-14)

## Verdict

`NO-GO` / `D5_NO_GO_RESEARCH_ONLY_GATE`. G004 hardens and reruns the Daily OHLCV D5 fresh OOS walk-forward gate. This is research-only validation evidence, not a profit result, not a deployable model, and not live/broker/order readiness.

## Artifact

- Run: `walk_forward_2026_06_14_g004_fresh_oos_gate`
- Directory: `webui/rl_runs/daily_ohlcv_walk_forward/walk_forward_2026_06_14_g004_fresh_oos_gate/`
- Input D3 run: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_14_g004_d3_baseline_hardened/`
- Input D4 run: `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_14_g003_training_telemetry/`
- Cost sensitivity: 0bp / 23bp / 46bp
- Purge/embargo: 5 days / 5 days
- Forward folds: 5
- `model_build_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false`

## Gate result

| Check | Result |
|---|---|
| D4 state contract consumed | `PASS`; state observations, reward breakdown, invalid actions, policy NAV, D3 overlay, reward/action ablations, ablation summary, and source hashes were present. |
| Forward folds | 5 folds assigned with purge/embargo windows, minimum purge/embargo validation, and `retuned_on_oos=false`. |
| No-trade/shuffle/D3 controls | No-trade, shuffled-score, and frozen D3 baseline rows remain in gate evidence. |
| Cost sensitivity | 0bp, 23bp, and 46bp rows generated for each fold. |
| MDD/turnover limits | Checked; latest selected-fold worst MDD and mean turnover did not exceed configured research limits. |
| D0/D1 blockers | `PRICE_BASIS_UNKNOWN` and `UNIVERSE_WATCH_HEURISTIC` remain. |
| RL vs D3 | `RL_POLICY_UNDERPERFORMS_D3_BASELINE` remains. |
| D4 lock | `D4_RL_RESEARCH_ONLY_LOCK` remains. |

## Why the result remains NO-GO

The gate is intentionally conservative. Even though the forward folds completed and D4 artifacts were consumed, model building remains locked because D0 price basis is still unknown, D1 universe review is still WATCH/heuristic, D4 is research-only, and the RL policy does not beat the frozen D3 baseline evidence under the current gate.

## Verification

Commands run:

```powershell
py -3.11 -m py_compile stom_rl/daily_walk_forward.py tests/test_stom_rl_daily_walk_forward.py
py -3.11 -m pytest tests/test_stom_rl_daily_walk_forward.py -q
py -3.11 -c "import json; from stom_rl.daily_walk_forward import run_and_write_daily_walk_forward; out=run_and_write_daily_walk_forward(run_id='walk_forward_2026_06_14_g004_fresh_oos_gate', overwrite=True, prediction_run_dir='webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_14_g004_d3_baseline_hardened', portfolio_run_dir='webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_14_g003_training_telemetry', n_folds=5, purge_days=5, embargo_days=5, top_k=20, seed=17); print(json.dumps({'run_id': out['written']['run_id'], 'artifact_dir': out['written']['artifact_dir'], 'status': out['result']['gate_verdict']['status'], 'readiness_status': out['result']['gate_verdict']['readiness_status'], 'model_build_allowed': out['result']['gate_verdict']['model_build_allowed'], 'n_folds': out['result']['gate_verdict']['n_folds'], 'cost_sensitivity_bp': out['result']['gate_verdict']['cost_sensitivity_bp'], 'd4_reward_action_ablation_rows': out['result']['gate_verdict']['d4_reward_action_ablation_rows'], 'd4_source_hash_count': out['result']['gate_verdict']['d4_source_hash_count'], 'reasons': out['result']['gate_verdict']['reasons']}, ensure_ascii=False))"
py -3.11 -m py_compile stom_rl/daily_rl_train.py stom_rl/daily_portfolio_env.py stom_rl/daily_walk_forward.py tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_walk_forward.py
py -3.11 -m pytest tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_walk_forward.py -q
```

Observed results:

- `tests/test_stom_rl_daily_walk_forward.py`: `42 passed`.
- Combined G003/G004 focused regression: `55 passed`.
- Artifact generation wrote `walk_forward_2026_06_14_g004_fresh_oos_gate` with `status=NO-GO`, `readiness_status=D5_NO_GO_RESEARCH_ONLY_GATE`, 5 folds, 5/5 purge/embargo, 0/23/46bp cost sensitivity, 28 consumed D4 ablation rows, 3 D4 source hashes, `d4_artifact_issues=[]`, and false model/paper/live flags.
- Cleaner/review blocker fixes: empty required D4 state observations, reward breakdown, invalid actions, policy baseline comparison, policy NAV, reward/action ablations, reward/action ablation summary, and source hashes now fail closed; missing/zero purge or embargo now fails closed; malformed/unreadable/wrong-schema required D4 JSON/CSV and missing/malformed frozen baseline requirements now fail closed; malformed/unreadable D4 baseline comparison JSON now fails closed instead of defaulting to neutral evidence.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- 23bp round-trip cost remains the default accounting assumption, with 0bp/46bp sensitivity shown only as diagnostics.
- Leading-zero stock codes remain string-preserved in source and upstream artifacts.
- D5 remains `NO-GO`; model building remains disallowed.
