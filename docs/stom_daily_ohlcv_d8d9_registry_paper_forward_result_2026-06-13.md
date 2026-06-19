# STOM Daily OHLCV D8/D9 Registry / Paper-forward Result — 2026-06-13

## Verdict

`RESEARCH_ONLY_BLOCKED` / `NO-GO`.

D8/D9 records a reproducible daily RL candidate registry and paper-forward planning ledger from the current D4/D5 evidence contract. It remains blocked from model build, paper-forward promotion, live trading, broker integration, and order generation. This is an evidence surface, not a profit claim.

## Scope

- Source module: `stom_rl/daily_registry.py`
- Backend dashboard loader/API: `webui/daily_ohlcv_dashboard.py`, `webui/app.py`
- Frontend dashboard surface: `webui/v2_src/src/lib/dailyOhlcvApi.ts`, `webui/v2_src/src/tabs/DailyOhlcvTab.svelte`, `webui/v2_src/src/tabs/dailyOhlcv/DailyVisualLabCard.svelte`, `webui/v2_src/src/tabs/dailyOhlcv/DailyProgressTimeline.svelte`
- Tests: `tests/test_stom_rl_daily_registry.py`, `tests/test_daily_ohlcv_dashboard_api.py`, `tests/test_daily_ohlcv_dashboard_tab.py`
- Generated registry run: `webui/rl_runs/daily_ohlcv_registry/registry_2026_06_13_g006_paper_forward/`

## Generated artifacts

| Artifact | Purpose |
|---|---|
| `registry_manifest.json` | Registry metadata, run ids, hashes, row counts, effective D0/D1/D3/D4/D5 blockers, guardrails. |
| `candidate_registry.json` | Candidate id, source D4/D5 runs, config/data/code/source hashes, promotion status, lock reasons. |
| `paper_selected.csv` | Paper-only selection list. Current row is blocked, not a trade list. |
| `realized_returns.csv` | Read-only policy NAV-derived realized-return series from generated D4 artifact. |
| `drift.csv` | Price-basis, universe, D5, effective model gate, model-build, and hash drift/status checks. |
| `drawdown.csv` | Paper-forward drawdown series derived from policy NAV. |
| `decision_log.jsonl` | Registry creation, promotion block, and live/broker/order block decision log. |

## Current registry state

| Field | Value |
|---|---|
| Run | `registry_2026_06_13_g006_paper_forward` |
| Status | `RESEARCH_ONLY_BLOCKED` |
| Promotion status | `BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER` |
| D4 source | `portfolio_2026_06_13_g003_state_visualization` |
| D5 source | `walk_forward_2026_06_13_g004_state_aware_gate` |
| Cost assumption | 23bp round trip |
| `model_build_allowed` | `false` |
| `paper_forward_allowed` | `false` |
| `live_broker_order_allowed` | `false` |
| `no_live_broker_order_readiness` | `true` |
| Rows | paper selected 1, realized returns 309, drift 8, drawdown 309, decision log 3 |
| Source hashes | 9 tracked source files |

## Effective gate blockers

The registry now recomputes an effective cross-stage promotion gate instead of trusting optimistic artifact flags.

- `D0_PRICE_BASIS_NOT_VERIFIED`
- `D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED`
- `D3_BASELINE_NOT_PROMOTABLE`
- `D4_IMPLEMENTATION_NOT_UNLOCKED`
- `D5_WALK_FORWARD_NOT_PASS`

## Blocking reasons preserved

- `D0_PRICE_BASIS_NOT_VERIFIED`
- `D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED`
- `D3_BASELINE_NOT_PROMOTABLE`
- `D4_IMPLEMENTATION_LOCKED_RESEARCH_ONLY`
- `D4_IMPLEMENTATION_NOT_UNLOCKED`
- `D4_OBSERVATION_STATE_MANIFEST_CONSUMED`
- `D4_RL_RESEARCH_ONLY_LOCK`
- `D5_WALK_FORWARD_NOT_PASS`
- `FORWARD_FOLDS_COMPLETE_NO_OOS_RETUNING`
- `MODEL_BUILD_LOCKED_BY_D5_GATE`
- `NO_LIVE_BROKER_ORDER_SURFACE`
- `PRICE_BASIS_UNKNOWN`
- `RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM`
- `RL_POLICY_UNDERPERFORMS_D3_BASELINE`
- `UNIVERSE_WATCH_HEURISTIC`

## Dashboard behavior

The Daily OHLCV visual lab includes `data-daily-registry-paper-forward` with:

- model build, paper-forward, and live/broker/order locks;
- explicit `no_live_broker_order_readiness=true` meaning “explicitly not broker/order ready”; missing or false would be unsafe;
- config/data/code hash display plus source hashes for backend and frontend registry surfaces;
- drift cards for price basis, universe review, D5 status, model-build lock, effective D0/D1/D3/D4/D5 gate, and hashes;
- table rows for blocked paper selections, realized returns, drawdown, and decision log entries;
- explicit no-live/broker/orders and no-profit/no-deployable-readiness guardrail text;
- artifact invariant validation that forces unsafe/stale registry files back to `BLOCKED_UNSAFE_REGISTRY_ARTIFACT`;
- strict numeric evidence handling that marks malformed policy NAV/return/drawdown rows as `BLOCKED_NUMERIC_EVIDENCE` instead of rendering fake zeroes.

API endpoint:

```text
GET /api/daily-ohlcv/registry/latest?limit=15
```

The endpoint is read-only and returns generated artifact samples only.

## Verification

```powershell
py -3.11 -m py_compile stom_rl/daily_registry.py webui/daily_ohlcv_dashboard.py webui/app.py tests/test_stom_rl_daily_registry.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
# passed

py -3.11 -m pytest tests/test_stom_rl_daily_registry.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
# 26 passed
```

```powershell
cd webui/v2_src
npm run check
# 0 errors, 4 pre-existing warnings in ForecastWorkbenchTab.svelte and DocsTab.svelte

npm run build
# 0 errors, same 4 pre-existing warnings; Vite build passed with bundle-size warning
```

Browser/API check:

- Route: `http://127.0.0.1:58198/daily-ohlcv`
- Result: `data-daily-registry-paper-forward`, D0-D9 progress, D7 diagnostics, `NO-GO`, `RESEARCH_ONLY`, `model_build_allowed=false`, `no_live_broker_order_readiness`, and all D0/D1/D3/D4/D5 effective blocker text were visible.
- API result: `/api/daily-ohlcv/registry/latest` 200, `/api/daily-ohlcv/progress` 200, `/api/daily-ohlcv/charts/decision-cockpit` 200, unsafe `run=../bad` 400, registry POST 405.
- Evidence artifacts: `browser_verification.json`, `registry_api_snapshot.json`, `g006_registry_dashboard_final.png`, `verification_transcript.txt`, `adversarial_report.txt`, `cleanup_report.txt` under `webui/rl_runs/daily_ohlcv_registry/registry_2026_06_13_g006_paper_forward/`.

## Interpretation

This completes the registry/paper-forward planning surface required before any future daily RL candidate can be tracked reproducibly. It does **not** unlock model build or trading. The current candidate remains blocked because the price basis is unknown, the universe is still heuristic/WATCH, the D4 policy underperforms frozen D3 baselines, D4 implementation remains research-only, and D5 remains `NO-GO`.
