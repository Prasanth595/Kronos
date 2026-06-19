# STOM Daily OHLCV D0 Price-basis Confirmation Result — 2026-06-14

## Verdict

`UNKNOWN_CONFIRMED` / `WATCH_PRICE_BASIS_UNKNOWN_CONFIRMED`.

This is a research-only D0 evidence update. It does not claim profitability, live/broker/order readiness, paper-forward permission, or model-build readiness.

## Scope

| Item | Value |
|---|---|
| Approved plan | `.gjc/plans/ralplan/2026-06-11-0158-38ea/pending-approval.md` |
| Source DB | `_database/Stock_Database_ohlcv_1day.db` |
| Generated artifact | `webui/rl_runs/daily_ohlcv_db_summary/daily_ohlcv_price_basis_2026_06_14_g001/` |
| Audit JSON | `webui/rl_runs/daily_ohlcv_db_summary/daily_ohlcv_price_basis_2026_06_14_g001/price_basis_audit.json` |
| Representative windows CSV | `webui/rl_runs/daily_ohlcv_db_summary/daily_ohlcv_price_basis_2026_06_14_g001/price_basis_windows.csv` |
| Guardrails | no live/broker/orders, no profit claims, 23bp default cost for later comparisons, no `_database` mutation, leading-zero codes preserved |

## Finding

The daily OHLCV DB has broad coverage, but it still does **not** declare whether prices are adjusted or raw. No split factor, dividend, total-return, or corporate-action table exists in the daily DB contract, so decision-grade return labels and model promotion remain blocked.

| Check | Result |
|---|---:|
| Tables scanned | 4,727 |
| Rows | 14,691,020 |
| Date range | 19860415 ~ 20260612 |
| Quality scan scope | all_tables |
| `price_basis` | `unknown` |
| `price_basis_status` | `UNKNOWN_CONFIRMED` |
| Decision-grade return status | `BLOCKED_UNTIL_PRICE_BASIS_VERIFIED` |
| Split-like tables in scan | 281 |
| Split-like window samples | 326 |

Component status:

| Component | Status |
|---|---|
| adjusted price | `not_declared_in_daily_db_schema` |
| raw price | `not_declared_in_daily_db_schema` |
| split adjustment | `not_declared_no_split_factor_or_corporate_action_table` |
| dividend adjustment | `not_declared_no_dividend_or_total_return_field` |

Representative split-like evidence includes `A000180` on `20260303` with open/previous-close ratio about `4.96`, `A000300` on `20241021` with ratio about `8.23`, and `A000670` on `20250113` with ratio about `0.10`. These windows support the unknown-adjustment blocker but are not corporate-action proof.

## Required evidence to unlock D0

| Required evidence | Meaning |
|---|---|
| `official_or_vendor_field_declaring_adjusted_or_raw_close` | Independent source declares whether the OHLC columns are adjusted or raw. |
| `split_factor_or_corporate_action_reference_for_split_like_windows` | Split-like jumps can be explained or excluded by a dated corporate-action source. |
| `dividend_or_total_return_policy_if_returns_claim_dividend_adjustment` | Dividend/total-return handling is explicit if return labels claim that basis. |
| `dated_audit_artifact_showing_rows_windows_and_downstream_blocker_effect` | The artifact records scan scope, rows/windows, and downstream lock impact. |

## User-facing usage guidance

| Section | Can do | Must not do | Next action |
|---|---|---|---|
| D0 summary | Inspect table count, date coverage, OHLC quality flags, and representative split-like windows. | Treat D0 returns as decision-grade labels while `price_basis` is unknown. | Provide independent adjusted/raw and split/dividend policy evidence, or keep the blocker visible. |
| D2/D3 downstream | Build preview datasets and baselines with inherited price-basis warnings. | Freeze or promote baselines without a verified price-basis policy. | Rerun dataset and baseline verification after price-basis status changes. |
| D4-D9 promotion | Use D4-D9 charts as research diagnostics only. | Set `model_build_allowed` or `paper_forward_allowed` from unknown-basis evidence. | Keep `D0_PRICE_BASIS_NOT_VERIFIED` in effective gate blockers until D0 is verified. |

## Decision

D0 remains usable as a DB analysis surface, but the model/research decision label remains:

```text
D0 = PASS but price_basis unknown / UNKNOWN_CONFIRMED
```

Blocking implications:

1. Decision-grade return labels remain blocked until adjusted/raw basis is independently verified.
2. Split-like discontinuities must be flagged or excluded from model decision windows.
3. Dashboard/API must keep `model_build_allowed=false` until price basis and downstream gates pass.
4. D8/D9 must keep `paper_forward_allowed=false` until candidate-specific D5 gate passes.

## Verification performed

```powershell
py -3.11 -m py_compile stom_rl/daily_ohlcv_db.py webui/daily_ohlcv_dashboard.py webui/app.py tests/test_stom_rl_daily_ohlcv_db.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
py -3.11 -m pytest tests/test_stom_rl_daily_ohlcv_db.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
```

Result: `34 passed`.

Additional verification:

```powershell
cd webui/v2_src
npm run check
npm run build
```

Result: `0 errors`, 4 pre-existing Svelte warnings in `ForecastWorkbenchTab.svelte` and `DocsTab.svelte`; Vite build passed with bundle-size warning.

Browser/API evidence: `/daily-ohlcv` showed `data-daily-price-basis-usage`, `UNKNOWN_CONFIRMED`, `model_build_allowed=false`/effective blockers, and no `data-daily-api-error`; `/api/daily-ohlcv/db-summary` returned 200 with D0 blocked uses and user guidance; `PATCH /api/daily-ohlcv/db-summary` returned 405; the walk-forward heatmap remained `model_build_allowed=false` with D0/D1/D3/D5 effective blockers.

## Interpretation

This completes the G001 D0 price-basis confirmation pass for the new approved plan by making the blocker more explicit in generated artifacts, API payloads, tests, and UI usage guidance. It does **not** unlock model build, paper-forward continuation, or live/broker/order use.
