# STOM Daily OHLCV D3 Baseline Hardening Result (2026-06-14)

## Verdict

`WATCH` / `D3_WATCH_RESEARCH_ONLY`. D3 was regenerated from the G003 D2 dataset refresh and hardened with fail-closed dashboard/API handling for stale optimistic baseline artifacts. This does **not** unlock RL model building, paper-forward readiness, live/broker/order workflows, or profit claims.

Blocking context remains:

- D0 price basis: `unknown` / `UNKNOWN_CONFIRMED`.
- D1 universe: `WATCH_HEURISTIC_UNIVERSE`; official/manual evidence is still missing.
- D5 walk-forward gate: not pass / still blocks promotion.
- `model_build_allowed=false` and `go_summary_allowed=false` remain required.

## Artifact

- Run: `prediction_2026_06_14_g004_d3_baseline_hardened`
- Directory: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_14_g004_d3_baseline_hardened/`
- Dataset input: `webui/rl_runs/daily_ohlcv_dataset/dataset_2026_06_14_g003_d2_refresh/`
- Dataset manifest SHA: `0b3ebec9ef8929ef1e26c8c2399a62fcb092fbd026f8e126e0c5f10f4e37ea74`
- Evaluation split: `val` + `test`
- Fit policy: supervised ranker/classifier fitted on `train` only (`fit_train_split_only_no_oos_retuning`)
- Deterministic shuffle: `sha256(date:code)_ascending`
- Cost: 23bp round trip
- Top-K: 20
- Baseline metrics SHA-256: `d142cdc89ea17f4d6f799e15228707079dbdba1bf663590e6a73bd33631d0009`
- Baseline delta summary SHA-256: `d7da6c79f09cbf0a0c7c989461766ba37c7e6963b4a8a1af312c1c03fd1770eb`
- Predictions SHA-256: `78ad01d796ae75bccbe87753c7843f256cf2af28cf0ce8b24249c1989daa344a`
- Prediction manifest SHA-256: `b1d4b26d8561444dd826c66bb1fdc092200f52d0dd1d05a0ab6f24b4c0439936`

Generated evidence files include `prediction_manifest.json`, `baseline_metrics.json`, `baseline_delta_summary.json`, `model_metrics.json`, `topk_positions.csv`, `calibration.csv`, `turnover.csv`, `drawdown.csv`, `predictions.csv`, and `verdict.json`.

## Baseline comparison after 23bp cost

| strategy | family | total net | hit rate | max DD | mean turnover | delta vs shuffle |
|---|---:|---:|---:|---:|---:|---:|
| `no_trade_cash` | control | +0.00% | 0.00% | 0.00% | 0.0000 | +22.86% |
| `shuffle_control` | control | -22.86% | 46.28% | -27.70% | 0.8010 | +0.00% |
| `equal_weight_topk_momentum` | rule_baseline | +31.37% | 52.10% | -17.45% | 0.3367 | +54.23% |
| `vol_adjusted_momentum` | rule_baseline | +26.63% | 55.02% | -16.51% | 0.3730 | +49.49% |
| `mean_reversion` | rule_baseline | -0.89% | 51.78% | -25.98% | 0.3702 | +21.97% |
| `market_proxy` | rule_baseline | -32.11% | 43.04% | -36.35% | 1.0000 | -9.25% |
| `supervised_linear_ranker` | supervised | +4.67% | 48.22% | -28.01% | 0.6508 | +27.53% |
| `supervised_direction_classifier` | supervised | +4.92% | 50.16% | -23.33% | 0.4489 | +27.78% |

Summary:

- Best overall/rule baseline: `equal_weight_topk_momentum`.
- Best supervised baseline: `supervised_direction_classifier`.
- Best supervised vs best rule baseline: -26.45 percentage points.
- Best supervised vs shuffle control: +27.78 percentage points.

## D3 blockers and guidance

```text
D0_PRICE_BASIS_NOT_VERIFIED
D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED
D5_WALK_FORWARD_NOT_PASS
D3_BASELINE_WATCH_RESEARCH_ONLY
```

D3 can be used as frozen research baseline evidence for D4 design, but it cannot justify candidate promotion, model build, GO summary, paper-forward/live readiness, or decision-grade return claims.

## Verification

```powershell
py -3.11 -m py_compile stom_rl/daily_prediction.py stom_rl/daily_ranker.py webui/daily_ohlcv_dashboard.py webui/app.py tests/test_stom_rl_daily_prediction.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
# passed

py -3.11 -m pytest tests/test_stom_rl_daily_prediction.py tests/test_stom_rl_daily_ranker.py tests/test_stom_rl_daily_ohlcv_dataset.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
# 38 passed

cd webui/v2_src
npm run check
npm run build
# 0 errors, 4 pre-existing warnings, existing bundle-size warning
```

Browser/API smoke: `/daily-ohlcv` D3 card rendered `WATCH`, D3 blockers, deterministic shuffle freeze, `model_build_allowed=false`, `go_summary_allowed=false`, nested stale optimistic statuses normalized to `WATCH`, and no API error. Screenshot: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_14_g004_d3_baseline_hardened/g004_d3_dashboard_final_current.png`.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, order-routing, or paper-forward readiness is implied.
- No profit claim is made.
- Default cost assumption remains 23bp round trip.
- Leading-zero stock codes remain strings in dataset/prediction/dashboard evidence.
- `model_build_allowed=false` remains required until D0/D1/D3/D5 gates pass.
