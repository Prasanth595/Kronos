# STOM Daily OHLCV D5 RL Walk-forward Gate Result (2026-06-13)

## Verdict

`NO-GO`. This is a read-only walk-forward/gate artifact for the daily RL candidate, not a profit result, not a deployable model, and not live/broker/order readiness.

## Artifact

- Run: `walk_forward_2026_06_13_d5_rl_gate_hardened`
- Directory: `webui/rl_runs/daily_ohlcv_walk_forward/walk_forward_2026_06_13_d5_rl_gate_hardened/`
- Portfolio input: `portfolio_2026_06_13_d4c_policy_eval`
- Selected preregistered D3 baseline: `equal_weight_topk_momentum`
- Cost: 23bp round trip, plus 0bp/23bp/46bp cost-sensitivity rows
- Folds: 5
- Purge/embargo: 5/5 days
- `model_build_allowed=false`
- `go_summary_allowed=false`

Generated files:

- `walk_forward_manifest.json`
- `gate_verdict.json`
- `folds.csv`
- `fold_assignments.csv`
- `fold_metrics.csv`
- `shuffle_control.csv`
- `cost_sensitivity.csv`
- `rl_fold_metrics.csv`

## Gate reasons

- `RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM`
- `FORWARD_FOLDS_COMPLETE_NO_OOS_RETUNING`
- `PRICE_BASIS_UNKNOWN`
- `UNIVERSE_WATCH_HEURISTIC`
- `RL_POLICY_UNDERPERFORMS_D3_BASELINE`
- `D4_RL_RESEARCH_ONLY_LOCK`

## Dashboard integration

The existing D5 dashboard surfaces load this run as the latest walk-forward artifact:

- `/api/daily-ohlcv/walk-forward/latest`
- `/api/daily-ohlcv/gate/latest`
- `/api/daily-ohlcv/charts/walk-forward`
- `/api/daily-ohlcv/charts/walk-forward-heatmap`
- `/api/daily-ohlcv/charts/decision-cockpit`
- `/api/daily-ohlcv/charts/flow`

The dashboard shows fold metrics, shuffled controls, cost sensitivity, RL fold metrics, fold assignments, heatmap cells, decision-cockpit blockers, and the locked model-build state.

## Verification

Commands run:

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_walk_forward.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
py -3.11 -m py_compile stom_rl/daily_walk_forward.py webui/daily_ohlcv_dashboard.py
cd webui/v2_src
npm run check
npm run build
```

Observed result:

- Targeted walk-forward/API/frontend marker tests: `14 passed`.
- Python compile: passed.
- Svelte check/build: passed with 0 errors and 4 pre-existing warnings in unrelated files (`ForecastWorkbenchTab.svelte`, `DocsTab.svelte`).

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- D5 remains `NO-GO`.
- `model_build_allowed=false` remains in force.
- No OOS retuning is allowed; the selected D3 baseline is preregistered rather than selected by favorable OOS fold results.
