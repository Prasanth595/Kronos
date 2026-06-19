# STOM Daily OHLCV D5 Fresh OOS Walk-forward Gate Result (2026-06-14)

## Verdict

`NO-GO`. The D5 artifact is fresh OOS/walk-forward evidence for the daily OHLCV research track. It is not a profit proof, not a deployable model, not paper-forward approval, and not live/broker/order readiness.

## Artifact

| Field | Value |
|---|---|
| Run | `walk_forward_2026_06_14_g006_d5_fresh_oos_gate` |
| Directory | `webui/rl_runs/daily_ohlcv_walk_forward/walk_forward_2026_06_14_g006_d5_fresh_oos_gate/` |
| D3 input | `prediction_2026_06_14_g004_d3_baseline_hardened` |
| D4 input | `portfolio_2026_06_14_g005_d4_visualization` |
| Selected policy | `equal_weight_topk_momentum` preregistered baseline |
| Folds | 5 |
| Purge/embargo | 5/5 days |
| Cost | 23bp round trip, plus 0/23/46bp stress rows |
| Readiness | `D5_NO_GO_RESEARCH_ONLY_GATE` |
| model_build_allowed | `false` |
| go_summary_allowed | `false` |
| paper_forward_allowed | `false` |
| live_broker_order_allowed | `false` |
| no_live_broker_order_readiness | `true` |

Generated files:

- `walk_forward_manifest.json`
- `gate_verdict.json`
- `d4_state_contract.json`
- `folds.csv`
- `fold_assignments.csv`
- `fold_metrics.csv`
- `shuffle_control.csv`
- `cost_sensitivity.csv`
- `rl_fold_metrics.csv`

## Provenance hashes

| Artifact | SHA-256 |
|---|---|
| D5 `walk_forward_manifest.json` | `3f1e9a84f4b75343f725ab084ea6e89ea6c49197cf3d1fe8cbb7c61b1c0be905` |
| D5 `gate_verdict.json` | `dd74b12c6dd56a7143376d83f45c1ad89d05596906ea0d23132c75770b6d95b9` |
| D5 `fold_metrics.csv` | `1de2740ebbd2ee90877040e163a6eb97a8d44fa4aa905a35351099de2ac018ad` |
| D5 `cost_sensitivity.csv` | `7afe7cbf5e1d5cb6c8982912a5278dc7de5d1807fc1863b78b932efba6b68131` |
| D5 `rl_fold_metrics.csv` | `74fe3fe0352d6f1f16828a3535a0a764491e6193b5c12f9cd69eef47c0333886` |
| D4 `rl_manifest.json` input | `5f103d446be2a84833e381f721ce7b388c090dd6e88889d166fd0b65ab659ff6` |
| D4 `state_observations.csv` input | `f3a5400611ab7c12bf6556fca27daa821369845f7e5e84a07ef7327d9ee68002` |
| D3 `prediction_manifest.json` input | `b1d4b26d8561444dd826c66bb1fdc092200f52d0dd1d05a0ab6f24b4c0439936` |
| D3 `predictions.csv` input | `78ad01d796ae75bccbe87753c7843f256cf2af28cf0ce8b24249c1989daa344a` |

## Gate reasons

- `RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM`
- `FORWARD_FOLDS_COMPLETE_NO_OOS_RETUNING`
- `D4_OBSERVATION_STATE_MANIFEST_CONSUMED`
- `PRICE_BASIS_UNKNOWN`
- `UNIVERSE_WATCH_HEURISTIC`
- `RL_POLICY_UNDERPERFORMS_D3_BASELINE`
- `D4_RL_RESEARCH_ONLY_LOCK`

## Main metrics

| Metric | Value |
|---|---:|
| Selected fold net-return sum | `0.3025311454569617` |
| Shuffled fold net-return sum | `-0.10855269295505843` |
| RL fold net-return sum | `0.159625021888819` |
| RL delta vs best D3 total net return | `-0.7349004887361696` |
| Positive selected folds | `3 / 5` |
| Folds beating no-trade | `3 / 5` |
| Folds beating shuffle | `4 / 5` |
| Worst fold max drawdown | `-0.16996776547953385` |
| Mean fold turnover | `0.34576943416181916` |
| D4 state observation rows consumed | `1098` |

Interpretation: although the selected preregistered D3 baseline has positive folds and beats shuffle on four folds, the D4 RL policy still underperforms the hardened D3 baseline, while D0 price basis and D1 official/manual universe evidence remain unresolved. Therefore promotion stays blocked.

## Dashboard/API changes

| Surface | Evidence exposed |
|---|---|
| `/api/daily-ohlcv/walk-forward/latest` | Fail-closed `NO-GO`, D5 readiness, false model/go/paper/live flags, D3/D4 provenance hashes, fold samples |
| `/api/daily-ohlcv/charts/walk-forward` | D5 chart data plus `D5_NO_GO_RESEARCH_ONLY_GATE`, upstream hashes, D5 artifact hashes, D4 state contract |
| `/api/daily-ohlcv/charts/walk-forward-heatmap` | Fail-closed model/go/paper/live flags and effective blockers |
| Daily OHLCV model card | D5 readiness line, provenance hash block, no-OOS-retuning/fold/cost/RL fold evidence |

Stale optimistic D5 artifacts that claim `PASS`, `GO`, `READY`, `LIVE_READY`, or any other loaded non-NO-GO status are normalized back to `NO-GO` with model/go/paper/live flags set to `false`. Fresh D5 generation also emits `NO-GO/D5_NO_GO_RESEARCH_ONLY_GATE` on favorable, blocked, and missing-evidence paths until the broader D0/D1/D3/D5 promotion contract is actually satisfied and explicitly redesigned.

## Verification

Commands run:

```powershell
py -3.11 -m py_compile stom_rl/daily_walk_forward.py webui/daily_ohlcv_dashboard.py tests/test_stom_rl_daily_walk_forward.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
py -3.11 -m pytest tests/test_stom_rl_daily_walk_forward.py -q
py -3.11 -m pytest tests/test_stom_rl_daily_walk_forward.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
cd webui/v2_src
npm run build
browser/API check at http://127.0.0.1:58242/daily-ohlcv
```

Observed results:

- Python compile: passed.
- D5 unit tests: `11 passed`.
- Focused D5/API/frontend marker tests: `41 passed`.
- Svelte check/build: 0 errors, 4 pre-existing warnings in unrelated files (`ForecastWorkbenchTab.svelte`, `DocsTab.svelte`), Vite build passed.
- Browser/API surface check: passed; `browser_api_report.json` and `g006_d5_dashboard_verified.png` were written under the D5 artifact directory.

Additional verification still required before Ultragoal G006 checkpoint: architect review and executor QA/red-team lane.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- `model_build_allowed=false` remains in force.
- `paper_forward_allowed=false` remains in force.
- `live_broker_order_allowed=false` remains in force.
- Price basis remains `unknown`; model build stays blocked until independently verified.
- Universe remains `WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW`; official/manual evidence is still required.
