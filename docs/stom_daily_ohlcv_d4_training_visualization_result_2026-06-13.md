# STOM Daily OHLCV D4 Training/Evaluation Visualization Result (2026-06-13)

## Verdict

`RESEARCH_ONLY` visualization wiring is complete for the D4 daily portfolio RL evidence surface.

This is not a live-trading model, not broker/order readiness, and not a profit claim. The dashboard now visualizes training/evaluation diagnostics and the state contract while preserving `model_build_allowed=false`.

## Artifact

- Portfolio run: `portfolio_2026_06_13_g003_state_visualization`
- Directory: `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_13_g003_state_visualization/`
- Source D3 run: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_13_d3_baseline_hardened/`
- Screenshot: `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_13_g003_state_visualization/g003_dashboard_state_visualization.png`
- Final screenshot after final build: `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_13_g003_state_visualization/g003_dashboard_state_visualization_final.png`
- Cost: 23bp round trip
- Status: `RESEARCH_ONLY`; `go_summary_allowed=false`; `model_build_allowed=false`

Generated/wired files now include:

- `observation_manifest.json`
- `state_observations.csv`
- `learning_curve.csv`
- `reward_breakdown.csv`
- `reward_component_summary.json`
- `action_distribution.csv`
- `invalid_actions.csv`
- `turnover.csv`
- `drawdown.csv`
- `policy_baseline_comparison.csv`
- `policy_nav.csv`

## Page coverage

| Required visualization | Current surface |
|---|---|
| State contract | `data-daily-rl-state-contract` shows `D4_OBSERVATION_STATE_MANIFEST`, validation status, model/go locks, telemetry insufficiency, and observation fields. |
| State observations | `data-daily-rl-state-observations` shows cash, exposure, current position count, top candidate, and `future_label_exposed=false`. |
| Leakage checks | `data-daily-rl-leakage-checks` shows required leakage checks and fail-closed wording for missing/duplicate/failing checks. |
| Learning curve | `data-daily-rl-learning-curve` shows episode reward, rolling mean reward, and best reward. |
| Reward/return curve | `data-daily-rl-reward-return-curve` shows date/action gross return, reward, equity, and missing label count. |
| Reward stack | `data-daily-rl-reward-components` shows gross/cost/exposure/concentration/invalid/churn/drawdown/reward stack by split. |
| Action distribution | `data-daily-rl-action-distribution` shows split/action/invalid/action-rate. |
| Invalid actions | `data-daily-rl-invalid-actions` shows action, invalid flag, and action mask string. |
| Turnover/drawdown | `data-daily-rl-turnover-drawdown` shows turnover and current drawdown. |
| Portfolio trajectory | `data-daily-rl-portfolio-trajectory` shows policy NAV, drawdown, concentration, and turnover. |
| Frozen D3 comparison | `data-daily-rl-policy-baseline-comparison` shows policy vs no-trade/shuffle/rule/supervised baselines. |

## Backend/API wiring

- `/api/daily-ohlcv/portfolio/latest` now exposes `observation_manifest`, `observation_manifest_validation`, and `samples.state_observations`.
- `/api/daily-ohlcv/charts/portfolio` now exposes `observation_manifest`, `observation_manifest_validation`, `state_observations`, `invalid_actions`, `portfolio_trajectory`, and `reward_stack` alongside existing learning/action/reward/turnover/drawdown/baseline series.
- `DailyPortfolioResponse` and `DailyModelChartResponse` frontend types include the new fields.

## Verification

Commands run:

```powershell
py -3.11 -m py_compile stom_rl/daily_rl_train.py stom_rl/daily_portfolio_env.py webui/daily_ohlcv_dashboard.py webui/app.py tests/test_stom_rl_daily_rl_gate.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
py -3.11 -m pytest tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_rl_gate.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
cd webui/v2_src; npm run check
cd webui/v2_src; npm run build
```

Observed results:

- Python compile: passed.
- Focused Python tests: `25 passed`.
- `npm run check`: 0 errors, 4 pre-existing unrelated warnings.
- `npm run build`: Vite build succeeded with the same warnings.
- Browser/API smoke at `/daily-ohlcv`: all D4 state/learning/reward/action/trajectory/baseline markers were present; screenshot saved.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing path was added.
- No profit or deployable-model claim is made.
- D4 remains `RESEARCH_ONLY` and cannot unlock model build without D0/D1/D3/D5 gates.
