# STOM Daily OHLCV D2 Dataset Refresh Result (2026-06-14)

## Status

`PASS` for D2 leakage/split artifact checks, but `DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS` for model readiness.

This is research-only dataset evidence. It is not training, not RL execution, not live/broker/order readiness, and not a profit claim.

## Source and generated artifacts

| Item | Value |
|---|---|
| Daily DB | `_database/Stock_Database_ohlcv_1day.db` |
| D1 universe manifest | `webui/rl_runs/daily_ohlcv_universe/universe_official_watch_2026_06_14_g002/universe.json` |
| Generated D2 artifact | `webui/rl_runs/daily_ohlcv_dataset/dataset_2026_06_14_g003_d2_refresh/` |
| Manifest | `dataset_manifest.json` |
| Panels | `feature_panel.csv`, `label_panel.csv`, `rl_candidate_panel.csv` |
| Split/audit files | `split_assignments.csv`, `normalization_stats.json`, `leakage_report.json`, `blocked_windows.csv` |

## Current counts

| Metric | Result |
|---|---:|
| Feature rows | 80,000 |
| Label rows | 80,000 |
| RL candidate rows | 80,000 |
| Eligible rows | 78,880 |
| Blocked windows | 14 |
| Leakage status | `PASS` |
| Split chronology status | `PASS` |
| Price basis | `unknown` / `UNKNOWN_CONFIRMED` |
| D1 universe | `WATCH_HEURISTIC_UNIVERSE` |
| D1 certification | `BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW` |

## Implemented hardening

| Area | Result |
|---|---|
| D0/D1 propagation | Dataset manifest/API/UI now carry `upstream_gate_blockers`. |
| Model readiness | D2 no longer reads as promotable while D0 price basis and D1 universe are blocked. |
| Evidence contract | Added required evidence, allowed uses, blocked uses, and user guidance. |
| Stale artifact guardrail | D2 latest/chart/artifact-list surfaces now recompute/union D0/D1 blockers and force blocked readiness instead of trusting stale optimistic manifests. |
| Dashboard | D2 card displays upstream blockers and blocked uses. |
| Generated artifact | New G003 D2 dataset uses the G002 universe manifest SHA/path. |

## Current upstream blockers

```text
D0_PRICE_BASIS_NOT_VERIFIED
D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED
```

These are expected guardrails. D2 can be inspected as a research dataset preview, but it cannot justify model build, candidate promotion, paper-forward/live readiness, or decision-grade return labels until D0 and D1 clear.

## Verification performed

```powershell
py -3.11 -m py_compile stom_rl/daily_ohlcv_dataset.py webui/daily_ohlcv_dashboard.py webui/app.py tests/test_stom_rl_daily_ohlcv_dataset.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
# passed

py -3.11 -m pytest tests/test_stom_rl_daily_ohlcv_dataset.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
# 32 passed

cd webui/v2_src
npm run check
# 0 errors, 4 pre-existing warnings
npm run build
# built, 0 errors, 4 pre-existing warnings, existing bundle-size warning
```

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- Default cost assumption remains 23bp round trip.
- Leading-zero stock codes remain strings in dataset/API/dashboard evidence.
- `model_build_allowed=false` remains required until D0/D1/D3/D5 gates pass.
