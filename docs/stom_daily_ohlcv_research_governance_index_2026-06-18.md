# Daily OHLCV Research Governance Index — 2026-06-18

Date: 2026-06-18 UTC  
Status: `ACTIVE_RESEARCH_LEDGER`  
Supersedes: `docs/stom_daily_ohlcv_research_governance_index_2026-06-17.md`  
Scope: Daily OHLCV D0-D9 research, D3 baseline, D4 RL diagnostics, D5 gate, scenario automation, data governance

## Purpose

This index keeps the Daily OHLCV research history findable and auditable. It separates durable decisions in `docs/`, preregistered plans in `artifacts/`, generated/session evidence in `webui/rl_runs/`, and source/tests in `stom_rl/`, `webui/`, and `tests/`.

The system remains research-only: no live/broker/orders, no profit claims, no paper-forward/model-build promotion while D5 is `NO-GO`.

## Current latest D4/D3 research chain

| Order | Document | Type | Status | Artifact anchor |
|---:|---|---|---|---|
| 1 | `docs/stom_daily_ohlcv_rl_continuation_prereg_2026-06-14.md` | preregistration | `PREREGISTERED_RESEARCH_ONLY` | D4 reward/action continuation plan |
| 2 | `docs/stom_daily_ohlcv_d4_rl_visualization_result_2026-06-14.md` | result | `RESEARCH_ONLY` | D4 visual/telemetry evidence |
| 3 | `docs/stom_daily_ohlcv_d4_no_trade_diagnostic_result_2026-06-16.md` | result | `NO-GO_RESEARCH_ONLY` | `scenario_batch_no_trade_diag_001` |
| 4 | `docs/stom_daily_ohlcv_d4_action_induction_v2_prereg_2026-06-16.md` | preregistration | `PREREGISTERED_RESEARCH_ONLY` | D4 action-induction v2 frozen plan |
| 5 | `docs/stom_daily_ohlcv_d4_action_induction_v2_result_2026-06-17.md` | result | `NO-GO_RESEARCH_ONLY` | `scenario_batch_d4_action_induction_v2_001` |
| 6 | `docs/stom_daily_ohlcv_d4_trade_quality_filter_prereg_2026-06-17.md` | preregistration | `PREREGISTERED_RESEARCH_ONLY` | D4 trade-quality/abstention plan |
| 7 | `docs/stom_daily_ohlcv_d4_trade_quality_filter_result_2026-06-17.md` | result | `NO-GO_RESEARCH_ONLY` | `scenario_batch_d4_trade_quality_filter_001` |
| 8 | `docs/stom_daily_ohlcv_d3_d4_signal_quality_audit_prereg_2026-06-18.md` | preregistration | `PREREGISTERED_RESEARCH_ONLY` | D3/D4 signal-quality diagnostic contract |
| 9 | `docs/stom_daily_ohlcv_d3_d4_signal_quality_audit_result_2026-06-18.md` | result | `WATCH_DIAGNOSTIC_ONLY` / `NO-GO_RESEARCH_ONLY` | `scenario_batch_signal_quality_audit_001` |
| 10 | `docs/stom_daily_ohlcv_dashboard_scenario_generator_result_2026-06-18.md` | dashboard result | `IMPLEMENTED_RESEARCH_ONLY_DASHBOARD` / `NO-GO_RESEARCH_ONLY` | Daily RL Guide priority 1-5 scenario generator/maturity UI |
| 11 | `docs/stom_daily_ohlcv_dashboard_first_research_platform_adr_2026-06-18.md` | ADR | `ACCEPTED_FOR_RESEARCH_PLATFORM_EXECUTION` / `RESEARCH_ONLY` | Dashboard-first, CLI-internal, no-live job-intent contract |
| 12 | `docs/stom_daily_ohlcv_hypothesis_rejection_audit_prereg_2026-06-18.md` | preregistration | `PREREGISTERED_RESEARCH_ONLY` | Gate-funnel / early-dropout / false-negative audit contract |
| 13 | `docs/stom_daily_ohlcv_dashboard_first_research_platform_completion_result_2026-06-18.md` | result | `IMPLEMENTED_RESEARCH_ONLY_DASHBOARD_PLATFORM` | Non-live dashboard/research platform `100%`; live/model/paper readiness `0%` |

## Latest generated evidence

| Evidence | Path | Meaning |
|---|---|---|
| Signal-quality audit manifest | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/signal_quality_manifest.json` | Main run metadata, source hashes, cost sensitivity, guardrails, and required artifact map. |
| Signal-quality bucket metrics | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/signal_quality_bucket_metrics.csv` | Score/sign/margin/confidence buckets with source timing, future-label flags, split/fold metadata, and 0/23/46bp rows. |
| Risk proxy metrics | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/risk_proxy_bucket_metrics.csv` | Past/current pre-action risk proxy buckets with proxy status, D3 deltas, turnover proxy, and cost rows. |
| Baseline controls | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/baseline_control_metrics.csv` | Measured no-trade, shuffle, equal-weight top-k, and frozen D3 controls. |
| Leakage audit | `webui/rl_runs/daily_ohlcv_signal_quality/signal_quality_audit_2026_06_18_001/signal_quality_leakage_audit.json` | Feature timing and future-label evaluation-only audit. |
| Signal-quality batch plan | `artifacts/scenario_batch_signal_quality_audit_001_plan.json` | Frozen five-scenario diagnostic matrix. |
| Signal-quality batch manifest | `webui/rl_runs/daily_ohlcv_signal_quality_batches/scenario_batch_signal_quality_audit_001/scenario_batch_manifest.json` | Five preregistered scenarios completed, `WATCH: 5`, no failures, promotion remains `NO-GO_RESEARCH_ONLY`. |
| Trade-quality filter batch | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_d4_trade_quality_filter_001/scenario_batch_manifest.json` | Prior D4 confidence/margin/joint/risk/control scenarios, all `NO-GO`. |
| Daily RL Guide scenario/maturity result | `docs/stom_daily_ohlcv_dashboard_scenario_generator_result_2026-06-18.md` | Dashboard priority 1-5 completion report: scenario draft generator, signal-quality binding, market-regime readiness, AI queue, scenario comparison, and maturity percentages. |
| Dashboard-first research platform ADR | `docs/stom_daily_ohlcv_dashboard_first_research_platform_adr_2026-06-18.md` | Freezes no-live product scope, CLI-internal UX, approval-gated intent-record-only POST boundary, forbidden command/live fields, and fail-closed job-intent lifecycle. |
| Hypothesis rejection audit preregistration | `docs/stom_daily_ohlcv_hypothesis_rejection_audit_prereg_2026-06-18.md` | Freezes falsifiable gate-funnel, rejection taxonomy, calibration, threshold-sensitivity, false-negative review-only, denominator/timing, and independent-evidence schema. |
| Hypothesis rejection analytics manifest | `webui/rl_runs/daily_ohlcv_rejection_audit/hypothesis_rejection_audit_2026_06_18_001/audit_manifest.json` | Gate-funnel, rejection taxonomy, calibration, threshold sensitivity, false-negative review-only row counts, hashes, and research-only locks. |
| Hypothesis rejection follow-up evidence | `webui/rl_runs/daily_ohlcv_rejection_audit/hypothesis_rejection_audit_2026_06_18_001/follow_up_review_evidence_manifest.json` | Separately hashed independent-evidence manifest for the review-only false-negative candidate; does not reverse NO-GO. |
| Dashboard-first final completion evidence | `docs/stom_daily_ohlcv_dashboard_first_research_platform_completion_result_2026-06-18.md` | Final report: non-live dashboard/research platform completion `100%`, live/model/paper readiness `0%`, and verified UI/API/build evidence. |
| Dashboard-first browser completion screenshot | `artifacts/dashboard_first_g005_completion_report.png` | Browser evidence for the final completion panel and Korean guardrails. |

## Current findings snapshot

| Finding | Evidence | Status |
|---|---|---|
| D4 trade-quality filters | Abstention telemetry works, but all five D4 scenarios underperformed no-trade/best D3 after 23bp cost. | `NO-GO_RESEARCH_ONLY` |
| D3/D4 signal quality | New diagnostic artifacts expose score/margin/confidence/risk proxy timing and baseline controls. Fold evidence is mixed: test F05 favorable, test F03 negative, F04 near zero. | `WATCH_DIAGNOSTIC_ONLY` |
| Baseline controls | Signal-quality audit now measures no-trade, shuffle, equal-weight top-k, and frozen D3 controls instead of listing them only in a manifest. | Required comparator visibility restored |
| Label leakage | Bucket/proxy rows include source timing and future-label flags; lagged drawdown-path proxies are t-1 generated-artifact inputs. | Current audit passes no-leakage checks |
| D5 gate | Latest signal-quality run is diagnostic only and does not run or pass a D5 promotion gate. | Model-build/paper/live blocked |
| Dashboard scenario generator | Daily RL Guide now exposes fixed JSON scenario drafts, signal-quality result binding, market-regime readiness, AI improvement queue, scenario comparison, and numeric maturity reporting. | `IMPLEMENTED_RESEARCH_ONLY_DASHBOARD`; live/model/paper readiness still 0% |
| Dashboard-first platform governance | ADR removes live trading from product goals, demotes CLI commands to backend provenance/admin detail, and requires dashboard POST behavior to create immutable research job-intent records only. | `ACCEPTED_FOR_RESEARCH_PLATFORM_EXECUTION`; no execution/live/model unlock |
| Hypothesis over-rejection audit contract | Preregistration defines how to test whether hypotheses are rejected too often or too early without hindsight promotion. False-negative candidates are review-only and require new preregistration. | `PREREGISTERED_RESEARCH_ONLY` |
| Hypothesis over-rejection audit | Generated rejection analytics now expose gate-funnel counts, rejection taxonomy, calibration, threshold sensitivity, and review-only false-negative candidates with independent evidence hashes. | `COMPLETED_RESEARCH_ONLY`; no NO-GO reversal |
| Dashboard-first completion | Workflow center, workflow inspector, safe config preview, approval-gated intent ledger, rejection analytics, and final completion panel are integrated into the user-facing dashboard. | Non-live platform `100%`; live/model/paper readiness `0%` |

## Document naming contract

| Document type | Required pattern | When to create |
|---|---|---|
| Preregistration | `docs/stom_daily_ohlcv_<lane>_prereg_YYYY-MM-DD.md` | Before changing hypotheses, reward/state/action contract, gates, or scenario matrix. |
| Result report | `docs/stom_daily_ohlcv_<lane>_result_YYYY-MM-DD.md` | After a run/test produces evidence. |
| Handoff | `docs/stom_daily_ohlcv_<lane>_handoff_YYYY-MM-DD.md` | When another agent/session should continue from current evidence. |
| Verdict | `docs/stom_daily_ohlcv_<lane>_verdict_YYYY-MM-DD.md` | When a GO/WATCH/NO-GO decision must be frozen. |
| Governance index | `docs/stom_daily_ohlcv_research_governance_index_YYYY-MM-DD.md` | When research history or data governance rules materially change. |

Do not edit old result documents to hide or soften failed experiments. Create a new dated document that references the old evidence.

## Minimum report fields

Every new result report must include: date/status, experiment type, guardrails, default cost and sensitivity, exact commands, generated artifact paths, split/fold details, baseline/no-trade/shuffle controls, verification output, verdict, next allowed action, and data-governance notes.

## Data governance checklist

| Check | Required evidence |
|---|---|
| Source provenance | Source hashes in run manifests or a documented commit/session reference. |
| Artifact provenance | Manifest paths and artifact hashes for generated outputs. |
| Cost accounting | 23bp default cost in docs and manifests; 0/23/46bp sensitivity before promotion discussion. |
| Split integrity | Train/val/test or fold metadata; no OOS retuning. |
| Label leakage | State/feature manifest and tests showing future labels are not used in decision-time features. |
| Baseline controls | no-trade, shuffle, equal-weight top-k, and frozen D3 comparison for D4/D5 claims. |
| Status flags | `model_build_allowed=false`, `go_summary_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false` unless a later approved gate changes them. |
| Generated vs durable separation | Generated artifacts under `webui/rl_runs/`; decisions under `docs/`. |
| Leading-zero codes | Codes preserved as strings in examples/artifacts. |
| Failure visibility | `NO-GO`/blocker reasons visible in docs and dashboard; no marketing language. |

## Current blockers that remain active

| Blocker | Current meaning |
|---|---|
| D0 price basis | Return labels are not independently verified as adjusted/raw/split/dividend safe. |
| D1 universe | Universe remains heuristic/WATCH without complete official/manual validation. |
| D3 baseline | Frozen D3 remains a comparator, not model-build approval. Signal-quality evidence is mixed and diagnostic only. |
| D4 RL | Action reachability and abstention telemetry exist, but D4 variants still lack cost-aware, fold-consistent superiority. |
| D5 gate | `NO-GO`; no model build, paper-forward, live trading, broker integration, or orders. |
| D8/D9 registry | Audit evidence only; live/broker/order readiness blocked. |

## Next research pointer

The dashboard-first research platform is now the latest completed lane. It should be used to inspect evidence, blockers, workflows, generated artifacts, and review-only false-negative candidates, not to unlock live/model/paper behavior. The next useful research remains a **past-only market-regime data quality audit** under a fresh preregistration:

- validate adjusted/raw/split/dividend basis for daily OHLCV labels,
- verify universe breadth and missing-data behavior,
- build better past-only volatility/drawdown/breadth proxies from validated OHLCV artifacts,
- keep no-trade, shuffle, equal-weight top-k, and frozen D3 controls mandatory,
- keep D5/model-build/paper-forward/live status `NO-GO` until a fresh gate passes.

Latest completed result document:

`docs/stom_daily_ohlcv_dashboard_first_research_platform_completion_result_2026-06-18.md`
