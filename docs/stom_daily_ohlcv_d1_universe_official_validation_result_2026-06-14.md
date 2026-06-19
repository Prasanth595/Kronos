# STOM Daily OHLCV D1 Universe Official Validation Result (2026-06-14)

## Status

`WATCH_HEURISTIC_UNIVERSE` / `BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW`.

This is research-only D1 evidence. It is not a live/broker/order surface, not a profit claim, and not model-build readiness.

## Source and generated artifacts

| Item | Value |
|---|---|
| Daily DB | `_database/Stock_Database_ohlcv_1day.db` |
| Local metadata | `_database/stock_tick_back.db:stockinfo` |
| Expected official/manual CSV | `_database/krx_listed_products.csv` |
| Generated artifact | `webui/rl_runs/daily_ohlcv_universe/universe_official_watch_2026_06_14_g002/` |
| Manifest | `universe.json` |
| Symbol/exclusion CSVs | `symbols.csv`, `exclusions.csv` |
| Quarantine evidence | `quarantine.csv` |
| Official metadata audit | `official_metadata_audit.json` |

## Finding

No official/manual KRX listed-product CSV was present at `_database/krx_listed_products.csv`, so the current universe remains a WATCH preview based on stockinfo plus conservative name/prefix rules.

The ingestion contract is explicit:

```text
code,name,market,instrument_type[,source]
```

Codes must remain six-character strings. Short numeric codes such as `250` are rejected instead of being silently accepted because they weaken leading-zero provenance.

## Current counts

| Metric | Result |
|---|---:|
| Verdict | `WATCH_HEURISTIC_UNIVERSE` |
| Certification | `BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW` |
| Official metadata status | `MISSING` |
| Official metadata coverage | `MISSING` |
| Tables | 4,727 |
| Included symbols | 2,599 |
| Excluded symbols | 2,128 |
| stockinfo matched tables | 4,229 |
| stockinfo unmatched tables | 498 |
| official metadata unmatched tables | 4,727 |
| quarantine rows | 575 |

## Implemented hardening

| Area | Result |
|---|---|
| Explicit D1 evidence contract | Added required evidence, allowed uses, blocked uses, and Korean dashboard guidance. |
| Fail-closed certification | Missing/partial official metadata keeps `universe_certification_status=BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW`. |
| Complete official metadata path | Only complete official/manual coverage can emit `OFFICIAL_OR_MANUAL_REVIEWED` / `OFFICIAL_VERIFIED`. |
| Gate compatibility | Effective model gate requires exact D1 verified verdict, official status, and certification status. |
| Dashboard/API | D1 card/API expose coverage status, certification status, required evidence, allowed uses, blocked uses, and user guidance. |
| Generated artifacts | New D1 manifest/audit/quarantine artifacts written under `webui/rl_runs/daily_ohlcv_universe/`. |

## User interpretation

| User question | Current answer |
|---|---|
| Can this universe be used for research preview? | Yes, for evidence review, exclusion reason review, quarantine backlog triage, and dashboard navigation. |
| Can it promote model builds or candidates? | No. D1 remains blocked until official/manual coverage is complete. |
| Can it support paper/live readiness claims? | No. Paper/live/broker/order readiness remains explicitly blocked. |
| Does this prove KOSPI/KOSDAQ common-equity coverage? | No. It shows the current heuristic preview and the exact evidence needed to clear D1. |

## Verification performed

```powershell
py -3.11 -m py_compile stom_rl/daily_ohlcv_universe.py webui/daily_ohlcv_dashboard.py webui/app.py tests/test_stom_rl_daily_ohlcv_universe.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
# passed

py -3.11 -m pytest tests/test_stom_rl_daily_ohlcv_universe.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
# 42 passed
```

Additional frontend/browser verification is recorded in the Ultragoal G002 quality gate artifacts.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- Leading-zero stock codes remain strings in universe, API, and dashboard evidence.
- `model_build_allowed=false` remains required until D0/D1/D3/D5 gates pass.
