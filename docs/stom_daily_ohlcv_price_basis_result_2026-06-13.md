# STOM Daily OHLCV Price Basis Confirmation Result (2026-06-13)

## Status

`UNKNOWN_CONFIRMED` / `WATCH_PRICE_BASIS_UNKNOWN_CONFIRMED`

This is a research-only D0 evidence update. It does not claim profitability, live/broker/order readiness, or model-build readiness.

## Source

- DB: `_database/Stock_Database_ohlcv_1day.db`
- Generated artifact: `webui/rl_runs/daily_ohlcv_db_summary/daily_ohlcv_price_basis_2026_06_13/`
- Audit JSON: `webui/rl_runs/daily_ohlcv_db_summary/daily_ohlcv_price_basis_2026_06_13/price_basis_audit.json`
- Representative windows CSV: `webui/rl_runs/daily_ohlcv_db_summary/daily_ohlcv_price_basis_2026_06_13/price_basis_windows.csv`

## Finding

The daily OHLCV DB has broad coverage but still does not declare whether prices are adjusted or raw.

| Item | Result |
|---|---:|
| Tables scanned | 4,727 |
| Rows | 14,691,020 |
| Date range | 19860415 ~ 20260612 |
| Quality scan scope | all_tables |
| `price_basis` | `unknown` |
| `price_basis_status` | `UNKNOWN_CONFIRMED` |
| Decision-grade return status | `BLOCKED_UNTIL_PRICE_BASIS_VERIFIED` |
| Split-like tables in representative scan | 281 |
| Split-like window samples | 326 |

Component status:

| Component | Status |
|---|---|
| adjusted price | `not_declared_in_daily_db_schema` |
| raw price | `not_declared_in_daily_db_schema` |
| split adjustment | `not_declared_no_split_factor_or_corporate_action_table` |
| dividend adjustment | `not_declared_no_dividend_or_total_return_field` |

Representative split-like evidence includes `A000180` on `20260303`, where open/previous-close ratio was about `4.96`, and `A000670` on `20250113`, where open/previous-close ratio was about `0.10`. These windows confirm adjustment-basis risk but are not themselves corporate-action proof.

## Decision

D0 remains usable as a DB analysis surface, but the model/research decision label is:

```text
D0 = PASS but price_basis unknown / UNKNOWN_CONFIRMED
```

Blocking implications:

1. Decision-grade return labels remain blocked until adjusted/raw basis is independently verified.
2. Split-like discontinuities must be flagged or excluded from model decision windows.
3. Dashboard/API must keep `model_build_allowed=false` until price basis and downstream gates pass.
4. The 23bp default cost assumption remains mandatory for later comparisons unless an artifact explicitly documents another cost basis.

## Verification performed

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_ohlcv_db.py -q
```

Result: `10 passed`.

```powershell
py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py tests/test_stom_rl_daily_ohlcv_db.py -q
```

Result: `21 passed`.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- `ts_imb` remains an opening-gap RULE baseline, not RL.
- Leading-zero stock codes remain strings in API/dashboard evidence.
