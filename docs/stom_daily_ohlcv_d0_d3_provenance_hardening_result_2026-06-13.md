# STOM Daily OHLCV D0-D3 Provenance Hardening Result (2026-06-13)

## Verdict

`RESEARCH_ONLY` / `MODEL_BUILD_LOCKED`.

This update hardens the Daily OHLCV D0-D3 progress/provenance surface. It does not claim profitability, live/broker/order readiness, or model-build readiness.

## Scope

- Backend progress payload: `webui/daily_ohlcv_dashboard.py`
- Frontend progress card: `webui/v2_src/src/tabs/dailyOhlcv/DailyProgressTimeline.svelte`
- API/types: `webui/v2_src/src/lib/dailyOhlcvApi.ts`
- Tests: `tests/test_daily_ohlcv_dashboard_api.py`, `tests/test_daily_ohlcv_dashboard_tab.py`

## Current truth preserved

| Stage | Status | Lock/evidence preserved |
|---|---|---|
| D0 DB/price | `PASS` surface with blocker | `price_basis=unknown`, `UNKNOWN_CONFIRMED`, `BLOCKED_UNTIL_PRICE_BASIS_VERIFIED` |
| D1 universe | `WATCH` | `WATCH_HEURISTIC_UNIVERSE`, official/manual metadata required |
| D2 dataset | `PASS` preview | date split, no future leakage, inherited D0/D1 guardrails |
| D3 baseline | `WATCH` | 23bp cost, no-trade/shuffle controls, frozen baseline deltas, `model_build_allowed=false` |

## Change

The `/api/daily-ohlcv/progress` payload now exposes:

- per-stage `lock_labels` for D0-D3;
- per-stage `verification_commands` with exact targeted pytest, `py_compile`, frontend check/build, and browser/e2e expectations;
- `provenance_matrix` for D0-D3 audit display;
- richer D0-D3 evidence text including price-basis status, official metadata status, dataset inherited blockers, D3 shuffle/no-trade/frozen-baseline/cost evidence.

The Daily OHLCV progress card now displays the D0-D3 provenance matrix, all lock labels, and all exact verification commands per stage.

## Verification

```powershell
py -3.11 -m py_compile webui/daily_ohlcv_dashboard.py webui/app.py
```

Result: passed.

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_ohlcv_db.py tests/test_stom_rl_daily_ohlcv_universe.py tests/test_stom_rl_daily_ohlcv_dataset.py tests/test_stom_rl_daily_prediction.py tests/test_stom_rl_daily_ranker.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
```

Result: `50 passed`.

```powershell
cd webui/v2_src
npm run check
npm run build
```

Result: 0 errors, 4 pre-existing unrelated Svelte warnings in `ForecastWorkbenchTab.svelte` and `DocsTab.svelte`; Vite build succeeded.

Browser/API check:

- Route: `http://127.0.0.1:58211/daily-ohlcv`
- API: `GET /api/daily-ohlcv/progress`
- Required evidence present: `[data-daily-ohlcv-progress]`, `[data-daily-d0-d3-provenance-matrix]`, `UNKNOWN_CONFIRMED`, `WATCH_HEURISTIC_UNIVERSE`, `shuffle_control`, `MODEL_BUILD_ALLOWED_FALSE`, `no live/broker/orders`, exact pytest command text.
- Required failure absent: `[data-daily-api-error]`.
- Screenshot: `webui/rl_runs/daily_ohlcv_provenance_g001/provenance_dashboard_after_cleanup.png`.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- The default cost assumption remains 23bp round trip.
- Leading-zero stock codes remain strings.
- `ts_imb` remains an opening-gap RULE baseline, not RL.
- `model_build_allowed=false` remains in force until D0/D1/D3/D5 gates pass.
