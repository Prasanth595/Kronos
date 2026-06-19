# STOM Daily OHLCV D3 Baseline Hardening Result (2026-06-13)

## Verdict

`WATCH` / research-only. D3 baselines were hardened with an explicit deterministic shuffle control and baseline-delta evidence, but this does **not** unlock RL model building or any live/broker/order workflow.

Blocking context remains:

- D0 price basis: `unknown` / `UNKNOWN_CONFIRMED`; decision-grade return labels remain blocked until adjusted/raw/split/dividend basis is independently verified.
- D1 universe: `WATCH_HEURISTIC_UNIVERSE`; official KRX/manual universe evidence is still missing.
- D5 walk-forward gate: existing latest gate remains `NO-GO`.
- `model_build_allowed=false` and `go_summary_allowed=false` remain the correct interpretation.

## Artifact

- Run: `prediction_2026_06_13_d3_baseline_hardened`
- Directory: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_13_d3_baseline_hardened/`
- Dataset input: `webui/rl_runs/daily_ohlcv_dataset/dataset_2026_06_12_d2_preview/`
- Evaluation split: `val` + `test`
- Fit policy: supervised ranker/classifier fitted on `train` only (`fit_train_split_only_no_oos_retuning`)
- Cost: 23bp round trip
- Top-K: 20
- Manifest SHA-256: `ec5368fd1883ab3d8a19bf373513cc7026c75148d8cf8075994c533a54ece75f`
- Baseline delta summary SHA-256: `3c0cc843c4ed69be0308ec468796bff657390b86a9c9e34bdd345d439fff4487`
- Baseline metrics SHA-256: `d142cdc89ea17f4d6f799e15228707079dbdba1bf663590e6a73bd33631d0009`

Generated evidence files include:

- `prediction_manifest.json`
- `baseline_metrics.json`
- `baseline_delta_summary.json`
- `model_metrics.json`
- `topk_positions.csv`
- `calibration.csv`
- `turnover.csv`
- `drawdown.csv`
- `predictions.csv`
- `verdict.json`

## Baseline comparison after 23bp cost

| strategy | family | total net | hit rate | max DD | mean turnover | delta vs shuffle |
|---|---:|---:|---:|---:|---:|---:|
| `no_trade_cash` | control | 0.00% | 0.00% | 0.00% | 0.0000 | +22.86% |
| `shuffle_control` | control | -22.86% | 46.28% | -27.70% | 0.8010 | 0.00% |
| `equal_weight_topk_momentum` | rule baseline | +31.37% | 52.10% | -17.45% | 0.3367 | +54.23% |
| `vol_adjusted_momentum` | rule baseline | +26.63% | 55.02% | -16.51% | 0.3730 | +49.49% |
| `mean_reversion` | rule baseline | -0.89% | 51.78% | -25.98% | 0.3702 | +21.97% |
| `market_proxy` | rule baseline | -32.11% | 43.04% | -36.35% | 1.0000 | -9.25% |
| `supervised_linear_ranker` | supervised baseline | +4.67% | 48.22% | -28.01% | 0.6508 | +27.53% |
| `supervised_direction_classifier` | supervised baseline | +4.92% | 50.16% | -23.33% | 0.4489 | +27.78% |

Summary:

- Best overall/rule baseline: `equal_weight_topk_momentum`.
- Best supervised baseline: `supervised_direction_classifier`.
- Best supervised vs best rule baseline: -26.45 percentage points.
- Best supervised vs shuffle control: +27.78 percentage points.
- Best rule baseline vs shuffle control: +54.23 percentage points.

## Interpretation

D3 now has the required no-trade, shuffle/control, Top-K momentum, volatility-adjusted momentum, transparent supervised ranker/classifier, cost-aware hit-rate/MDD/turnover/calibration, and baseline-delta evidence. The supervised baselines beat shuffle but do not beat the strongest rule baseline, so RL remains unjustified as a replacement claim.

This is evidence for further research triage only. It is not live-trading readiness, not broker readiness, not a profit guarantee, and not a model-build approval.

## Verification

Commands run:

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_prediction.py -q
py -3.11 -m pytest tests/test_stom_rl_daily_prediction.py tests/test_stom_rl_daily_ranker.py tests/test_stom_rl_daily_ohlcv_dataset.py tests/test_stom_rl_daily_ohlcv_universe.py tests/test_stom_rl_daily_ohlcv_db.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
py -3.11 -m py_compile stom_rl/daily_prediction.py stom_rl/daily_ranker.py webui/daily_ohlcv_dashboard.py webui/app.py
npm run check && npm run build  # from webui/v2_src
```

Observed results:

- `tests/test_stom_rl_daily_prediction.py`: 2 passed.
- Daily D0-D3/dashboard targeted set: 46 passed.
- Python compile: passed.
- Svelte check/build: 0 errors, 4 pre-existing warnings in unrelated files (`ForecastWorkbenchTab.svelte`, `DocsTab.svelte`).
- Browser/API smoke: `/daily-ohlcv` D3 card rendered `WATCH`, `shuffle_control`, `supervised vs shuffle`, `model_build_allowed=false`, and no API error. Screenshot: `.omx/artifacts/daily_ohlcv_d3_baseline_hardened_2026_06_13.png`.
