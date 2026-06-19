# Daily OHLCV D6/D7 Dashboard Usage Result (2026-06-14)

## Verdict

`PASS` for D6/D7 usage-guide hardening as a read-only evidence surface.

This is not a trading-readiness, profit, live, broker, order, or deployable-model claim. The Daily OHLCV track remains research-only with `model_build_allowed=false` until D0/D1/D3/D5 gates pass.

## What changed

| Area | Result | Guardrail |
|---|---|---|
| D0-D9 progress guide | API now exposes per-page `usage_guide`, `can_do`, `must_not`, and `next_action` fields. | WATCH/NO-GO rows stay visible. |
| D6 visual lab | Dashboard shows a Korean D6/D7 usage panel explaining what can be read, what is forbidden, and the next evidence required. | Visual curves are evidence views, not profit proof. |
| D7 research diagnostics | Feature, regime, correlation/concentration, and failure-analysis cards expose allowed use, blocked use, how to read, and current artifact gap. | `PLACEHOLDER_READY` is not alpha/profit evidence. |
| Metric glossary | Added learning curve, action distribution, portfolio trajectory, and symbol drilldown explanations. | Graphs must be interpreted with controls and gates. |
| Symbol drilldown | Symbol OHLCV chart response and UI expose usage guidance. | Individual symbol view is not buy/sell recommendation. |

## Current user capabilities

| Page/table | Users can do | Users must not do | Next evidence |
|---|---|---|---|
| D6 Decision Cockpit | Read D3/D4/D5 lock status, blockers, and model-build lock reasons. | Treat `LOCKED`/`NO-GO` cards as promotion or readiness. | Resolve D0/D1/D3/D5 blockers. |
| D6 Evidence Flow | See D0-D9 dependency order and which stage blocks downstream work. | Skip failed upstream evidence. | Re-run stage checks after upstream fixes. |
| D6 Metric Glossary | Interpret MDD, turnover, shuffle, learning curve, action distribution, portfolio trajectory. | Use one metric or a rising curve as profitability proof. | Compare against no-trade/shuffle/D3 controls. |
| D6 Visual charts | Inspect overlays, heatmap, scatter, universe breakdown, symbol OHLCV preview. | Hide failed folds or call charts trading signals. | Keep provenance hashes and gate labels visible. |
| D7 Research Diagnostics | Plan feature/regime/correlation/failure attribution artifacts. | Use placeholders or explanation views as alpha claims. | Generate `feature_importance_by_fold.csv`, `regime_bucket_metrics.csv`, `correlation_cluster_summary.csv`, `failure_reason_attribution.csv`. |
| Symbol drilldown | Inspect leading-zero code preservation, range, OHLCV bars, and price-basis warning. | Treat a selected symbol as buy/sell guidance. | Confirm price basis before decision-grade returns. |

## Verification

| Command / evidence | Result |
|---|---|
| `py -3.11 -m py_compile webui/daily_ohlcv_dashboard.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py` | PASS |
| `py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q` | `30 passed` |
| `cd webui/v2_src && npm run check && npm run build` | PASS, 0 errors; 4 pre-existing warnings in `ForecastWorkbenchTab.svelte`/`DocsTab.svelte` |
| Browser/API check at `/daily-ohlcv` | PASS: D6/D7 usage guide visible, no API error, progress guide count 10, D7 diagnostics guidance present, symbol usage guide visible |
| Screenshot | `webui/rl_runs/daily_ohlcv_visual_lab/visual_lab_2026_06_14_g007_d6_d7_usage/g007_d6_d7_usage_verified.png` |
| API report | `webui/rl_runs/daily_ohlcv_visual_lab/visual_lab_2026_06_14_g007_d6_d7_usage/browser_api_report.json` |

## Remaining blocked states

- D0 price basis remains not independently verified.
- D1 universe remains WATCH until official/manual KRX review.
- D3 remains WATCH/research baseline evidence.
- D5 remains NO-GO.
- D8/D9 remain research-only / paper-forward locked.
- No live/broker/orders and no profit claim.
