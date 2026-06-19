# Daily OHLCV D3/D4 Signal-Quality Audit Result — 2026-06-18

Date: 2026-06-18 UTC  
Status: `WATCH_DIAGNOSTIC_ONLY` / promotion `NO-GO_RESEARCH_ONLY`  
Experiment type: `supervised gate` / `RL experiment` diagnostic audit  
Parent preregistration: `docs/stom_daily_ohlcv_d3_d4_signal_quality_audit_prereg_2026-06-18.md`  
Parent result: `docs/stom_daily_ohlcv_d4_trade_quality_filter_result_2026-06-17.md`  
Default cost: 23bp round trip; generated metrics carry 0/23/46bp sensitivity rows.

## Verdict

The D3/D4 signal-quality audit is implemented and reproducible as a research-only diagnostic lane. It fixes the prior D4 trade-quality follow-up problem by moving upstream: score magnitude, score margin, confidence, and past-only/generated-artifact risk proxies are now visible with fold/split metadata, source timing, baseline controls, and no-future-label provenance.

The result does **not** unlock D5/model-build/paper-forward/live trading. The evidence is mixed and remains diagnostic: some folds show positive score calibration, but other folds are weak or negative, and `no_trade_cash` remains an active comparator. The correct promotion status is still `NO-GO_RESEARCH_ONLY`.

## Exact commands and observed output

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_signal_quality.py -q
```

Observed:

```text
...                                                                      [100%]
3 passed in 0.44s
```

```powershell
py -3.11 -m stom_rl.daily_signal_quality --run-id signal_quality_audit_2026_06_18_001
```

Observed:

```json
{"run_id": "signal_quality_audit_2026_06_18_001", "status": "COMPLETED_RESEARCH_ONLY", "promotion_status": "NO-GO_RESEARCH_ONLY", "row_counts": {"predictions": 872, "bucket_metrics": 204, "rank_correlations": 7, "risk_proxy_metrics": 219, "baseline_control_metrics": 84, "leakage_audit": 7}, "output_dir": "webui\\rl_runs\\daily_ohlcv_signal_quality\\signal_quality_audit_2026_06_18_001"}
```

```powershell
py -3.11 -m stom_rl.daily_signal_quality_batch --plan artifacts/scenario_batch_signal_quality_audit_001_plan.json --batch-id scenario_batch_signal_quality_audit_001 --overwrite
```

Observed:

```json
{"batch_id": "scenario_batch_signal_quality_audit_001", "status": "COMPLETED_RESEARCH_ONLY", "scenario_count": 5, "completed_count": 5, "failed_count": 0, "gate_status_counts": {"WATCH": 5}}
```

## Durable artifacts

| Artifact | Path |
|---|---|
| Preregistration | `docs/stom_daily_ohlcv_d3_d4_signal_quality_audit_prereg_2026-06-18.md` |
| Scenario plan | `artifacts/scenario_batch_signal_quality_audit_001_plan.json` |
| Audit manifest | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/signal_quality_manifest.json` |
| Score/margin/confidence buckets | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/signal_quality_bucket_metrics.csv` |
| Rank correlations | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/signal_quality_rank_correlations.csv` |
| Past-only risk proxy metrics | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/risk_proxy_bucket_metrics.csv` |
| Baseline controls | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/baseline_control_metrics.csv` |
| Leakage audit | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/signal_quality_leakage_audit.json` |
| Batch manifest | `webui/rl_runs/daily_ohlcv_signal_quality_batches/scenario_batch_signal_quality_audit_001/scenario_batch_manifest.json` |

## Scenario batch summary

| Scenario | Focus | Status | Promotion |
|---|---|---|---|
| `score_magnitude_audit_v1` | score magnitude/sign bucket separability | `WATCH` | `NO-GO_RESEARCH_ONLY` |
| `score_margin_audit_v1` | top-1/top-2 margin quality | `WATCH` | `NO-GO_RESEARCH_ONLY` |
| `confidence_bucket_audit_v1` | D3/D4 confidence calibration | `WATCH` | `NO-GO_RESEARCH_ONLY` |
| `risk_proxy_audit_v1` | past-only/generated-artifact risk proxies | `WATCH` | `NO-GO_RESEARCH_ONLY` |
| `combined_signal_proxy_audit_v1` | joint signal/proxy diagnostics | `WATCH` | `NO-GO_RESEARCH_ONLY` |

Batch status: `completed_count=5`, `failed_count=0`, `gate_status_counts={"WATCH": 5}`. `WATCH` means the diagnostic artifacts are usable for analysis, not that a model or trading lane is approved.

## Main diagnostic observations

### Rank correlation by split/fold

| Split | Fold | Spearman | Pearson | n | Interpretation |
|---|---:|---:|---:|---:|---|
| train | FULL | 0.0108 | 0.1052 | 576 | weak relation; not enough for promotion |
| val | F01 | 0.1562 | -0.0382 | 64 | weak/mixed |
| val | F02 | 0.1295 | 0.0485 | 64 | weak positive |
| val | F03 | 0.0974 | 0.0655 | 24 | weak positive |
| test | F03 | -0.1167 | -0.0972 | 40 | negative OOS fold |
| test | F04 | 0.0310 | -0.0059 | 64 | near zero |
| test | F05 | 0.4233 | 0.3012 | 40 | favorable OOS fold, not consistent enough alone |

### 23bp baseline-control aggregate across val+test

These are research diagnostics from frozen candidate-panel selections, not deployable strategy results.

| Baseline control | Days | Mean net return/day @23bp | Mean turnover proxy | Status |
|---|---:|---:|---:|---|
| `no_trade_cash` | 37 | 0.0000 | 0.0000 | active comparator |
| `shuffle_control` | 37 | -0.00084 | 0.9459 | weak negative after cost |
| `equal_weight_topk` | 37 | -0.00278 | 0.4797 | negative after cost |
| `frozen_d3_baseline` | 37 | -0.00560 | 0.6486 | negative after cost |

## What changed technically

| Area | Change | Governance effect |
|---|---|---|
| Causal buckets | `score_magnitude_bucket`, `score_sign_bucket`, `score_margin_bucket`, and `d3_confidence_bucket` use frozen absolute thresholds `(0.001, 0.005, 0.02)` | No threshold search, no quantile fitting, no OOS retune |
| Risk proxies | `score_dispersion`, `recent_score_volatility`, `breadth`, `turnover_pressure`, and lagged generated `drawdown.csv` path proxies are emitted | Previous future-label-derived proxy blocker removed |
| Row provenance | Bucket/proxy CSV rows include source timing, source artifact, and future-label flags | Acceptance criterion 1 is directly auditable |
| Cost sensitivity | Bucket, risk-proxy, and baseline metrics emit 0/23/46bp rows | 23bp primary and 46bp stress remain visible |
| Baselines | `baseline_control_metrics.csv` measures no-trade, shuffle, equal-weight top-k, and frozen D3 controls | Baseline controls are no longer manifest-only labels |
| Batch governance | Five preregistered scenarios run through a manifest-backed batch | Scenario automation remains reproducible |

## Data governance record

| Governance area | Evidence |
|---|---|
| Source provenance | `signal_quality_manifest.json` records hashes for `predictions.csv`, `fold_assignments.csv`, and lagged `drawdown.csv`. |
| Artifact provenance | Run and batch manifests record all generated artifact paths under `webui/rl_runs/`. |
| Cost accounting | Primary cost is 23bp; metric artifacts carry 0/23/46bp rows. |
| Split integrity | Manifest records splits `train`, `val`, `test` and folds `F01`-`F05`; no threshold retune was performed. |
| Label leakage | `signal_quality_leakage_audit.json` and CSV flags mark future labels as evaluation-only. |
| Baseline controls | `baseline_control_metrics.csv` includes no-trade, shuffle, equal-weight top-k, and frozen D3 controls. |
| Generated vs durable separation | Generated evidence is under `webui/rl_runs/`; decisions are in this dated `docs/` report. |
| Leading-zero codes | Loader preserves stock codes with `zfill(6)`; focused tests use string codes such as `000001`. |
| Failure visibility | Promotion remains `NO-GO_RESEARCH_ONLY`; no D5/model-build/paper-forward/live readiness is implied. |

## Limitations

1. The signal relation is not fold-consistent: test F05 is favorable, but test F03 is negative and F04 is near zero.
2. Baseline controls are diagnostic selections from the existing candidate panel, not a full independent portfolio optimizer.
3. Lagged `drawdown.csv` proxies come from generated research artifacts; they are past-only in this audit, but they are not a substitute for a fully validated adjusted OHLCV market-regime dataset.
4. The current lane does not produce `abstention_reasons.csv` because it is pure diagnostics; the manifest explicitly marks that requirement as not applicable for this audit.
5. No D5 promotion gate is opened.

## Current promotion status

`NO-GO_RESEARCH_ONLY`.

This run does not approve model build, paper-forward, live trading, broker integration, order placement, or any profit/readiness claim.

## Next allowed research action

Recommended next lane: a preregistered **past-only market-regime data quality audit** before any new D4 overlay. It should validate adjusted/raw price basis, universe breadth, volatility/drawdown proxies, and whether those proxies are stable enough to use in D4 state. Do not tune D4 thresholds against this result without a new preregistration.
