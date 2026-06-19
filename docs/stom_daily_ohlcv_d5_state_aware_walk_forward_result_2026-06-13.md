# STOM Daily OHLCV D5 State-Aware Walk-Forward Gate Result (2026-06-13)

## Verdict

`NO-GO` is preserved. D5 now consumes the revised D4 observation/state manifest artifacts before evaluating forward folds, and it still keeps `model_build_allowed=false` and `go_summary_allowed=false`.

This is research-only gate evidence, not a live-trading model, broker/order readiness, deployable-model claim, or profit claim.

## Artifact

- Walk-forward run: `walk_forward_2026_06_13_g004_state_aware_gate`
- Directory: `webui/rl_runs/daily_ohlcv_walk_forward/walk_forward_2026_06_13_g004_state_aware_gate/`
- Source D3 run: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_13_d3_baseline_hardened/`
- Source D4 run: `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_13_g003_state_visualization/`
- Cost ladder: `0bp / 23bp / 46bp`
- Purge/embargo: `5 / 5` days
- Status: `NO-GO`; `model_build_allowed=false`; `go_summary_allowed=false`

Generated/wired files include:

- `walk_forward_manifest.json`
- `gate_verdict.json`
- `d4_state_contract.json`
- `folds.csv`
- `fold_assignments.csv`
- `fold_metrics.csv`
- `shuffle_control.csv`
- `cost_sensitivity.csv`
- `rl_fold_metrics.csv`

## Gate coverage

| Requirement | Current surface |
|---|---|
| D4 state-aware artifact consumption | `d4_state_contract.json` and manifest fields show `D4_OBSERVATION_STATE_MANIFEST`, validation `PASS`, 1,098 state rows, no missing artifacts, and `reward_action_telemetry_sufficient_for_d4=false`. |
| Forward-only folds | `folds.csv` has 5 folds, `forward_only=true`, `retuned_on_oos=false`, and explicit purge/embargo windows. |
| No OOS retuning | Gate reason includes `FORWARD_FOLDS_COMPLETE_NO_OOS_RETUNING`; verdict field `no_oos_retuning=true`. |
| Shuffle/no-trade controls | `fold_metrics.csv` includes selected, no-trade, and shuffled-score rows with deltas vs no-trade and shuffled control. |
| Cost sensitivity | `cost_sensitivity.csv` and API chart expose 0/23/46bp results. |
| MDD/turnover/fold consistency | `fold_consistency` includes positive/negative folds, folds beating no-trade/shuffle, worst fold drawdown, and mean fold turnover. |
| D4 RL lock | `RL_POLICY_UNDERPERFORMS_D3_BASELINE` and `D4_RL_RESEARCH_ONLY_LOCK` remain explicit reasons. |
| Dashboard visibility | `/api/daily-ohlcv/walk-forward/latest` and `/api/daily-ohlcv/charts/walk-forward` expose D4 state contract, fold windows, controls, cost sensitivity, and reasons; `DailyModelResultsCard.svelte` renders the new D5 boxes. |

## Result numbers

- Selected strategy: `equal_weight_topk_momentum`
- Folds: `5`
- Positive/negative folds: `3 / 2`
- Folds beating no-trade/shuffle: `3 / 4`
- Selected total net return sum: `0.3025311454569617`
- Shuffled total net return sum: `-0.10855269295505843`
- RL total net return sum: `0.0`
- RL delta vs best D3 total net return: `-0.31367982153964924`
- Worst fold drawdown: `-0.16996776547953385`
- Mean fold turnover: `0.34576943416181916`

## NO-GO reasons

- `RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM`
- `FORWARD_FOLDS_COMPLETE_NO_OOS_RETUNING`
- `D4_OBSERVATION_STATE_MANIFEST_CONSUMED`
- `PRICE_BASIS_UNKNOWN`
- `UNIVERSE_WATCH_HEURISTIC`
- `RL_POLICY_UNDERPERFORMS_D3_BASELINE`
- `D4_RL_RESEARCH_ONLY_LOCK`

## Verification

Commands run:

```powershell
py -3.11 -m py_compile stom_rl/daily_walk_forward.py webui/daily_ohlcv_dashboard.py tests/test_stom_rl_daily_walk_forward.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
py -3.11 -m pytest tests/test_stom_rl_daily_walk_forward.py -q
py -3.11 -m pytest tests/test_stom_rl_daily_walk_forward.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
cd webui/v2_src; npm run check
cd webui/v2_src; npm run build
browser smoke at http://127.0.0.1:60084/daily-ohlcv
```

Observed results:

- Python compile: passed.
- Walk-forward unit tests before final cleanup fixes: `3 passed`.
- Final focused walk-forward/dashboard/API/tab tests: `25 passed`.
- `npm run check`: 0 errors, 4 pre-existing unrelated warnings.
- `npm run build`: Svelte check passed and Vite build succeeded with the same warnings plus bundle-size warning.
- Browser smoke: D5 chart, D4 state contract, controls, 0/23/46bp sensitivity, fold windows, `D4_OBSERVATION_STATE_MANIFEST_CONSUMED`, `no_oos_retuning`, `NO-GO`, `model_build_allowed=false`, `RESEARCH_ONLY`, and `no live/broker/orders` were visible.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing path was added.
- No profit/deployable-model claim is made.
- D5 remains `NO-GO`; model build stays locked until D0/D1/D3/D5 blockers are resolved with decision-grade evidence.
