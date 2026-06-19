# Daily OHLCV Research Governance Index — 2026-06-17

Date: 2026-06-17 UTC  
Status: `ACTIVE_RESEARCH_LEDGER`  
Supersedes: `docs/stom_daily_ohlcv_research_governance_index_2026-06-16.md`  
Scope: Daily OHLCV D0-D9 research, D3 baseline, D4 RL diagnostics, D5 gate, scenario automation, data governance

## Purpose

This index keeps the Daily OHLCV research history findable and auditable. It separates:

- durable human-readable decisions in `docs/`
- preregistered scenario plans in `artifacts/`
- generated/session evidence in `webui/rl_runs/`
- code/tests in `stom_rl/`, `webui/`, and `tests/`

The system remains research-only: no live/broker/orders, no profit claims, no paper-forward/model-build promotion while D5 is `NO-GO`.

## Current latest D4 research chain

| Order | Document | Type | Status | Artifact anchor |
|---:|---|---|---|---|
| 1 | `docs/stom_daily_ohlcv_rl_continuation_prereg_2026-06-14.md` | preregistration | `PREREGISTERED_RESEARCH_ONLY` | D4 reward/action continuation plan |
| 2 | `docs/stom_daily_ohlcv_d4_rl_visualization_result_2026-06-14.md` | result | `RESEARCH_ONLY` | D4 visual/telemetry evidence |
| 3 | `docs/stom_daily_ohlcv_final_usage_handoff_2026-06-14.md` | handoff | `PASS` handoff with global locks | D0-D9 dashboard usage map |
| 4 | `docs/stom_daily_ohlcv_d4_no_trade_diagnostic_result_2026-06-16.md` | result | `NO-GO_RESEARCH_ONLY` | `scenario_batch_no_trade_diag_001` |
| 5 | `docs/stom_daily_ohlcv_d4_action_induction_v2_prereg_2026-06-16.md` | preregistration | `PREREGISTERED_RESEARCH_ONLY` | D4 action-induction v2 frozen plan |
| 6 | `docs/stom_daily_ohlcv_d4_action_induction_v2_result_2026-06-17.md` | result | `NO-GO_RESEARCH_ONLY` | `scenario_batch_d4_action_induction_v2_001` |
| 7 | `docs/stom_daily_ohlcv_d4_trade_quality_filter_prereg_2026-06-17.md` | preregistration | `PREREGISTERED_RESEARCH_ONLY` | next D4 trade-quality/abstention plan |
| 8 | `docs/stom_daily_ohlcv_d4_trade_quality_filter_result_2026-06-17.md` | result | `NO-GO_RESEARCH_ONLY` | `scenario_batch_d4_trade_quality_filter_001` |

## Latest generated evidence

| Evidence | Path | Meaning |
|---|---|---|
| Trade-quality filter batch | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_d4_trade_quality_filter_001/scenario_batch_manifest.json` | Five D4 confidence/margin/joint/risk/control scenarios, all `NO-GO`. |
| Trade-quality filter summary | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_d4_trade_quality_filter_001/trade_quality_filter_research_summary.json` | Aggregated filter returns, abstention counts, action distribution, and baseline deltas. |
| Trade-quality filter plan | `artifacts/scenario_batch_d4_trade_quality_filter_001_plan.json` | Frozen run matrix for the 2026-06-17 trade-quality filter preregistration. |
| Trade-quality source hashes | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__confidence_abstain_v1/source_hashes.json` | Representative source provenance artifact; each trade-quality portfolio run keeps the same `source_hashes.json` contract. |
| Action-induction v2 batch | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_d4_action_induction_v2_001/scenario_batch_manifest.json` | Three D4 v2 state/action-prior scenarios, all `NO-GO`. |
| Action-induction v2 summary | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_d4_action_induction_v2_001/action_induction_v2_research_summary.json` | Aggregated v2 state/action reachability and baseline comparison. |
| Action-induction v2 plan | `artifacts/scenario_batch_d4_action_induction_v2_001_plan.json` | Frozen run matrix for v2 state and action-prior diagnostics. |
| Per-run v2 portfolio artifacts | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_action_induction_v2_001__*/` | D4 RL manifests, rewards, actions, state observations, no-trade diagnostics. |
| No-trade diagnostic batch | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_no_trade_diag_001/scenario_batch_manifest.json` | Prior four D4 stress scenarios, all `NO-GO`. |
| No-trade diagnostic summary | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_no_trade_diag_001/no_trade_diagnostic_research_summary.json` | Prior missed/avoided no-trade diagnostic. |

## Current D4 findings snapshot

| Finding | Evidence | Status |
|---|---|---|
| v1/no-trade diagnostic | Prior D4 policies collapsed to all-hold/no-trade under multiple capacity/training settings. | `NO-GO_RESEARCH_ONLY` |
| v2 action reachability | v2 state/action-prior scenarios produce buy/add/sell/reduce actions on `val+test`. | Diagnostic progress only |
| v2 trade quality | All v2 scenarios underperform the best D3/no-trade baseline after 23bp cost. | `NO-GO_RESEARCH_ONLY` |
| Trade-quality filters | Confidence/margin/joint filters emit `abstention_reasons.csv` and block weak entries, but all five scenarios remain below `no_trade_cash` / best D3. | `NO-GO_RESEARCH_ONLY` |
| D5 gate | Latest trade-quality batch: `gate_status_counts={"NO-GO": 5}`. | Model-build/paper/live blocked |

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

Every new result report must include:

1. Date and status.
2. Experiment type: `RULE`, `supervised gate`, `RL experiment`, or `baseline`.
3. Guardrails: no live/broker/orders, no profit claim, paper/model flags.
4. Default cost and sensitivity assumptions.
5. Exact command(s) run.
6. Generated artifact paths.
7. Split/OOS/fold details where applicable.
8. Baseline/no-trade/shuffle controls where applicable.
9. Test/verification command and observed output.
10. Verdict: `PASS`, `WATCH`, `NO-GO`, or `RESEARCH_ONLY` with reasons.
11. Next allowed research action.

## Data governance checklist

| Check | Required evidence |
|---|---|
| Source provenance | Source hashes in run manifests or a documented commit/session reference. |
| Artifact provenance | Manifest paths and artifact hashes for generated outputs. |
| Cost accounting | 23bp default cost in docs and manifests; add 46bp sensitivity when promoting a lane. |
| Split integrity | Train/val/test or fold metadata; no OOS retuning. |
| Label leakage | State/feature manifest and tests showing future labels are not used in decision-time features. |
| Baseline controls | no-trade, shuffle, and frozen D3 baseline comparison for D4/D5 claims. |
| Status flags | `model_build_allowed=false`, `go_summary_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false` unless a later approved gate changes them. |
| Generated vs durable separation | Generated artifacts under `webui/rl_runs/`; decisions under `docs/`. |
| Leading-zero codes | Codes preserved as strings in examples/artifacts. |
| Failure visibility | `NO-GO`/blocker reasons visible in docs and dashboard; no marketing language. |

## Current blockers that remain active

| Blocker | Current meaning |
|---|---|
| D0 price basis | Return labels are not independently verified as adjusted/raw/split/dividend safe. |
| D1 universe | Universe remains heuristic/WATCH without complete official/manual validation. |
| D3 baseline | Frozen D3 remains a comparator, not model-build approval. |
| D4 RL | v2 made actions reachable and trade-quality filters emit abstention telemetry, but all D4 variants still underperform no-trade/best D3 baseline. |
| D5 gate | `NO-GO`; no model build or paper-forward. |
| D8/D9 registry | Audit evidence only; live/broker/order readiness blocked. |

## Next research pointer

The completed D4 trade-quality filter run remains `NO-GO_RESEARCH_ONLY`. The next executable research should not tune thresholds against this result without a new preregistration. Recommended next lane: D3/D4 signal-quality audit and past-only risk proxy improvement.

Minimum requirements for the next preregistration:

- verify whether D3 score magnitude and score margin are calibrated enough to support abstention,
- add a better past-only daily OHLCV risk/regime proxy if available from generated artifacts,
- keep no-trade, shuffle, equal-weight top-k, and frozen D3 baselines mandatory,
- keep `abstention_reasons.csv` and future-label no-leakage tests mandatory for any D4 filter,
- keep D5/model-build/paper-forward/live status `NO-GO` until a fresh gate passes.

Latest completed result document:

`docs/stom_daily_ohlcv_d4_trade_quality_filter_result_2026-06-17.md`
