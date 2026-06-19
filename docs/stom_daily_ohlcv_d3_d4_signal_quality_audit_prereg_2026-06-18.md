# Daily OHLCV D3/D4 Signal-Quality Audit Preregistration — 2026-06-18

Date: 2026-06-18 UTC  
Status: `PREREGISTERED_RESEARCH_ONLY`  
Experiment type: `supervised gate` / `RL experiment` diagnostic audit  
Parent result: `docs/stom_daily_ohlcv_d4_trade_quality_filter_result_2026-06-17.md`  
Governance index: `docs/stom_daily_ohlcv_research_governance_index_2026-06-17.md`  
Default cost: 23bp round trip; scenario/gate outputs must retain 0/23/46bp sensitivity before any promotion discussion.

## Objective

The 2026-06-17 D4 trade-quality filters produced useful abstention telemetry but every scenario still underperformed `no_trade_cash` / best D3 after 23bp costs. The next research step is therefore **not** another threshold-tuning pass. It is a preregistered D3/D4 signal-quality audit that asks whether the D3 scores, score margins, confidence buckets, and past-only risk/regime proxies contain enough causal information to justify any future D4 overlay work.

This document freezes the next diagnostic contract before any new scenario execution.

## Non-negotiable guardrails

| Guardrail | Required state |
|---|---|
| Live/broker/order use | Forbidden. |
| Profit claim | Forbidden. All returns are research diagnostics only. |
| Model build / paper-forward | Forbidden unless a later fresh D5 gate passes under an approved workflow. |
| Default cost | 23bp round trip in all primary comparisons. |
| Cost sensitivity | Keep 0/23/46bp sensitivity in scenario or gate manifests; do not promote a lane without 46bp stress evidence. |
| D5 status | `NO-GO` until a fresh gate passes. |
| Future labels | `future_return_1d`, realized fold outcomes, and post-action rewards may not enter score buckets, margin buckets, confidence buckets, or risk/regime proxy construction. They are evaluation labels only. |
| Baselines | no-trade cash, shuffle/control, equal-weight top-k, and frozen D3 baseline remain mandatory. |
| Generated artifacts | Generated evidence belongs under `webui/rl_runs/` or `artifacts/`; durable decisions belong under `docs/`. |
| Leading-zero codes | Stock codes must stay strings. |

## Frozen research questions

| ID | Question | Required evidence | Failure interpretation |
|---|---|---|---|
| `Q1_SCORE_MONOTONICITY` | Do higher D3 score-magnitude buckets have better next-day research returns or hit rates? | bucketed score table across train/val/test and folds | If not monotonic or only one split works, D3 score scale is not reliable enough for D4 filters. |
| `Q2_MARGIN_QUALITY` | Does a larger top-1 minus top-2 score margin identify cleaner opportunities? | margin bucket return/hit-rate/turnover table | If margin buckets do not separate outcomes, margin-based abstention is weak. |
| `Q3_CONFIDENCE_QUALITY` | Does the confidence bucket used by D4 trade-quality filters map to better realized outcomes? | confidence bucket table and calibration diagnostics | If confidence bucket does not improve outcome separation, confidence abstention should remain diagnostic only. |
| `Q4_RISK_PROXY` | Can past-only daily OHLCV or generated-artifact proxies identify regimes where D3/D4 fails? | volatility/drawdown/breadth/score-dispersion/turnover-pressure regime table | If proxies are stale, future-dependent, or not separative, do not add them to D4 state. |
| `Q5_OVERLAY_READINESS` | Is there enough causal signal to justify a future D4 overlay action schema? | baseline-relative summary with D3/no-trade/shuffle controls | If D3/no-trade controls still dominate, keep D4/model-build/paper-forward `NO-GO`. |

## Causal bucket contract

| Bucket / proxy | Source timing | Frozen construction | Forbidden shortcut |
|---|---|---|---|
| `score_magnitude_bucket` | current date candidate panel before action | frozen absolute top-score thresholds `(0.001, 0.005, 0.02)` with missing/zero in bucket 0; no quantile fitting in this preregistered lane | no fold-retuning; no future return lookup; no ad hoc threshold search |
| `score_sign_bucket` | current date candidate panel before action | negative / zero / positive top D3 score sign | no filtering based on later realized direction |
| `score_margin_bucket` | current date candidate panel before action | top-1 minus top-2 D3 score bucketed with frozen absolute thresholds `(0.001, 0.005, 0.02)` matching action-induction v2 state | no train/val/test retuning; no use of top-1 future return or fold outcome |
| `d3_confidence_bucket` | current date candidate panel before action | absolute top D3 score bucketed with frozen thresholds `(0.001, 0.005, 0.02)`; if the top-score source is missing, emit `MISSING_D3_CONFIDENCE_SOURCE` and fail the scenario closed | no realized label, D5 verdict, or fallback threshold injection |
| `candidate_count_bucket` | current date candidate panel before action | number of current date candidates after score sorting and candidate-limit truncation | no post-hoc removal of losing symbols |
| `score_dispersion_bucket` | current date candidate panel before action | cross-sectional dispersion among current D3 scores | no future-return dispersion |
| `recent_score_volatility_bucket` | `t-1` lookback before action | rolling volatility of prior top D3 scores | no current/future label leakage |
| `past_return_volatility_bucket` | `t-1` lookback before action if daily OHLCV artifacts are available | rolling past-only volatility of returns/prices; if unavailable, mark `MISSING_PAST_OHLCV_PROXY` | no using next-day returns |
| `drawdown_bucket` | `t-1` equity/state only | rolling drawdown from past research equity or D3 baseline path | no using current test-fold final equity to classify earlier dates |
| `breadth_proxy_bucket` | current/past candidate universe before action | share of candidate scores positive or breadth from available past-only OHLCV universe fields | no future label aggregation |
| `turnover_pressure_bucket` | current/past positions/candidate changes before action | expected turnover pressure from prior holdings and current candidate replacement rate | no post-action realized turnover to decide action |

Frozen threshold policy: this audit does **not** permit train-set threshold search, train-only quantile selection, or post-hoc bucket count changes. A later quantile/calibration experiment requires a new preregistration. This lane uses the absolute thresholds above so D3 calibration is evaluated, not tuned.

## Frozen diagnostic tables

| Artifact | Required fields | Purpose |
|---|---|---|
| `signal_quality_bucket_metrics.csv` | split, fold, bucket_name, bucket_value, count, mean_future_return_1d, median_future_return_1d, hit_rate, mean_score, mean_margin, cost_bp | score/margin/confidence outcome separation |
| `signal_quality_rank_correlations.csv` | split, fold, score_field, spearman_rank_corr, pearson_corr, n | rank/linear relation between D3 scores and labels |
| `risk_proxy_bucket_metrics.csv` | split, fold, proxy_name, bucket_value, count, policy_delta_vs_d3, future_return_mean, mdd_proxy, turnover_proxy, cost_bp | past-only regime separability |
| `signal_quality_leakage_audit.json` | feature_name, timing, source_artifact, future_label_used, verdict | prove no decision-time future-label leakage |
| `signal_quality_manifest.json` | run_id, source_hashes, input_artifacts, split policy, thresholds, costs, baselines, guardrails | reproducibility and provenance |
| `scenario_batch_manifest.json` | scenario IDs, statuses, cost_sensitivity_bp, artifact paths, blockers | batch governance |
| `abstention_reasons.csv` | split, date, action/filter/proxy reason, entry_abstained_by_filter, future_label_exposed | required for any follow-up D4 filter/overlay scenario; if a pure diagnostic scenario has no abstention action, emit an explicit `not_applicable` manifest reason |
| `*_result_YYYY-MM-DD.md` | commands, result tables, limitations, next action, data governance | durable decision record |

## Frozen scenario matrix

| Scenario ID | Diagnostic focus | Required controls | Promotion rule |
|---|---|---|---|
| `score_magnitude_audit_v1` | score magnitude/sign bucket separability | no-trade, shuffle, equal-weight top-k, frozen D3 | diagnostic only; no promotion |
| `score_margin_audit_v1` | top-1/top-2 margin quality | same controls | diagnostic only; no promotion |
| `confidence_bucket_audit_v1` | D3/D4 confidence bucket calibration | same controls | diagnostic only; no promotion |
| `risk_proxy_audit_v1` | past-only volatility/drawdown/breadth/dispersion/turnover proxy usefulness | same controls | diagnostic only; no promotion |
| `combined_signal_proxy_audit_v1` | whether score + margin + confidence + past-only proxy jointly explain failures | same controls plus fold consistency | diagnostic only; no promotion |

## Acceptance criteria

A completed result may be accepted as **research evidence only** if all are true:

1. Every bucket/proxy row identifies its source timing (`t/current/pre_action` or `t-1/lookback/pre_action`).
2. `future_return_1d` is used only as an evaluation label after bucket/proxy construction.
3. Score, margin, confidence, and risk-proxy buckets use the frozen preregistered thresholds/policies above; no train-set threshold search, quantile search, bucket-count change, or OOS retuning is allowed.
4. Tables cover train/val/test and available folds, or explicitly mark missing folds as blockers.
5. no-trade, shuffle, equal-weight top-k, and frozen D3 comparisons remain visible.
6. 23bp default cost is primary; 0/23/46bp sensitivity remains in scenario/gate manifests.
7. Leading-zero stock codes remain string values in all artifacts.
8. `model_build_allowed=false`, `go_summary_allowed=false`, `paper_forward_allowed=false`, and `live_broker_order_allowed=false` remain enforced.
9. A dated result document and governance-index update are written under `docs/`.
10. Any future D4 filter/overlay candidate that uses this audit must keep or newly emit `abstention_reasons.csv`; pure diagnostics may mark it not-applicable only with an explicit manifest reason.

## Planned executable next step

Implement a bounded signal-quality audit lane:

1. Add or reuse a diagnostic runner that reads existing D3/D4 generated artifacts and emits the frozen signal-quality tables above.
2. Add leakage tests proving no bucket/proxy uses `future_return_1d` before evaluation and that no train-set threshold/quantile search changes the frozen bucket policy.
3. Run a small preregistered scenario/audit batch with the five scenario IDs above.
4. Publish `docs/stom_daily_ohlcv_d3_d4_signal_quality_audit_result_YYYY-MM-DD.md` and update the governance index.

## Current promotion status

`NO-GO_RESEARCH_ONLY`.

This preregistration approves diagnostics only. It does not approve model build, paper-forward, live trading, broker integration, order placement, or profit/readiness claims.
