# STOM Daily OHLCV Universe Official Validation Result (2026-06-13)

## Status

`WATCH_HEURISTIC_UNIVERSE` with official metadata ingestion path added.

This is research-only D1 evidence. It does not claim profitability, live/broker/order readiness, or model-build readiness.

## Source and artifacts

- Daily DB: `_database/Stock_Database_ohlcv_1day.db`
- Local stockinfo metadata: `_database/stock_tick_back.db:stockinfo`
- Expected official/manual metadata CSV path: `_database/krx_listed_products.csv`
- Generated universe artifact: `webui/rl_runs/daily_ohlcv_universe/universe_official_watch_2026_06_13/`
- Manifest: `webui/rl_runs/daily_ohlcv_universe/universe_official_watch_2026_06_13/universe.json`
- Include/exclude CSVs: `symbols.csv`, `exclusions.csv`
- Quarantine evidence: `quarantine.csv`
- Official metadata audit: `official_metadata_audit.json`

## Finding

No official KRX/manual listed-product CSV was present at `_database/krx_listed_products.csv` during this run, so the current universe remains WATCH. The code now has an explicit ingestion contract for a future official/manual CSV:

```text
code,name,market,instrument_type[,source]
```

Codes are handled as six-character strings to preserve leading zeros.

| Item | Result |
|---|---:|
| Verdict | `WATCH_HEURISTIC_UNIVERSE` |
| Official metadata status | `MISSING` |
| Tables | 4,727 |
| Included symbols | 2,599 |
| Excluded symbols | 2,128 |
| stockinfo unmatched tables | 498 |
| official metadata unmatched tables | 4,727 |
| quarantine.csv rows | 575 |
| quarantine reasons | `METADATA_UNMATCHED` 232 + `ALPHANUMERIC_CODE_UNREVIEWED` 343 |

## Implemented validation path

The official/manual CSV path supports:

- `common_equity` / common / stock / ordinary share inclusion for KOSPI/KOSDAQ.
- Official ETF/ETN/fund exclusion.
- Official SPAC exclusion.
- Official preferred-share exclusion.
- Official REIT exclusion.
- Unknown/missing official metadata remains quarantined or WATCH.

Unit tests cover common-equity inclusion, ETF exclusion, SPAC exclusion, preferred-share exclusion, missing official metadata, leading-zero preservation, unsafe artifact path rejection, and quarantine artifact writing.

## Decision

D1 remains:

```text
D1 = WATCH_HEURISTIC_UNIVERSE
```

The current `stockinfo` + name/prefix rules are still a useful preview, but not an official universe certification. D3/D4/D5 model claims must not treat this as a fully verified KRX common-stock universe until the official/manual CSV is supplied and reviewed.

## Verification performed

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_ohlcv_universe.py -q
```

Result: `15 passed`.

```powershell
py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py tests/test_stom_rl_daily_ohlcv_universe.py -q
```

Result: `27 passed`.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- `ts_imb` remains an opening-gap RULE baseline, not RL.
- Leading-zero stock codes remain strings in universe, API, and dashboard evidence.
