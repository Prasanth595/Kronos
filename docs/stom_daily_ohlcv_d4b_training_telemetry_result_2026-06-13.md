# STOM Daily OHLCV D4-B Training Telemetry Result (2026-06-13)

## Verdict

`RESEARCH_ONLY`. This is daily portfolio RL training telemetry and visualization evidence, not a profit result, not a deployable model, and not live/broker/order readiness.

## Artifact

- Run: `portfolio_2026_06_13_d4b_telemetry`
- Directory: `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_13_d4b_telemetry/`
- Input D3 run: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_13_d3_baseline_hardened/`
- Cost: 23bp round trip
- Status: `RESEARCH_ONLY`
- `model_build_allowed=false` remains controlled by D5 and is not unlocked by this telemetry.

Generated telemetry files:

- `training_manifest.json`
- `episode_metrics.csv`
- `learning_curve.csv`
- `reward_breakdown.csv`
- `reward_component_summary.json`
- `action_distribution.csv`
- `invalid_actions.csv`
- `turnover.csv`
- `drawdown.csv`

Compatibility files retained for existing D4 readers:

- `rl_manifest.json`
- `policy_metrics.json`
- `positions.csv`
- `baseline_comparison.json`
- `verdict.json`

## Telemetry contract

| Area | Contract |
|---|---|
| Learning curve | Episode reward, rolling mean reward, best reward, final equity, invalid-action rate |
| Reward stack | Gross return, 23bp turnover cost, exposure, concentration, invalid-action, churn, drawdown, final reward |
| Action distribution | Split/action counts and action rates; all-hold outcomes are shown rather than hidden |
| Turnover/cost | Per-date turnover, turnover cost, churn penalty, reward, equity |
| Drawdown | Per-date equity, current drawdown, drawdown penalty, reward before/after drawdown |
| Dashboard payload | `/api/daily-ohlcv/portfolio/latest` and `/api/daily-ohlcv/charts/portfolio` expose telemetry samples/cards |
| Frontend | D4 card shows training status, telemetry stack, learning curve, action distribution, reward components, turnover/drawdown |

The current deterministic policy evaluates mostly/all hold on the latest artifact. That is acceptable and must be visible: it is evidence of the constrained research policy behavior, not a failure to hide or a profit claim.

## Visualization stack decision

- Canonical source of truth: generated CSV/JSON artifacts under `webui/rl_runs/`.
- Dashboard transport: Flask read-only JSON payloads.
- Frontend display: Svelte evidence cards with tabular/series summaries.
- Research plotting compatibility: the CSV series are Plotly-compatible.
- TensorBoard/SB3 Monitor logs are marked not emitted for this dependency-free tabular-Q run; they can be added only when a real SB3 training lane exists.

## Verification

Commands run:

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_rl_gate.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
py -3.11 -m py_compile stom_rl/daily_rl_train.py webui/daily_ohlcv_dashboard.py
cd webui/v2_src
npm run check
npm run build
```

Observed result:

- Targeted Python/API/frontend marker tests: `14 passed`.
- Python compile: passed.
- Svelte check: passed with 0 errors and 4 pre-existing warnings in unrelated files (`ForecastWorkbenchTab.svelte`, `DocsTab.svelte`).
- Svelte check/build: passed with 0 errors and 4 pre-existing warnings in unrelated files (`ForecastWorkbenchTab.svelte`, `DocsTab.svelte`).

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- D4 remains `RESEARCH_ONLY`.
- `model_build_allowed=false` remains in force until strict D5/fresh forward gates pass.
- Dashboard APIs are GET-only evidence payloads.
