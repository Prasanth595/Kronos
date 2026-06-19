# Daily OHLCV Hypothesis Rejection / Early-dropout Audit Preregistration — 2026-06-18

Date: 2026-06-18 UTC  
Status: `PREREGISTERED_RESEARCH_ONLY`  
Scope: Diagnose whether Kronos Daily OHLCV hypotheses are rejected too often or too early before/inside research workflows  
Related ADR: `docs/stom_daily_ohlcv_dashboard_first_research_platform_adr_2026-06-18.md`  
Guardrails: no live trading, no broker/orders, no paper-forward/model-build unlock, no profit claims.

## Objective

Create a falsifiable research audit that measures gate-level hypothesis attrition and distinguishes justified rejection from possible early dropout. The audit is designed to improve research triage quality, not to promote a model.

The central question is:

> Are Daily OHLCV research hypotheses being rejected too often or too early before enough decision-time evidence is collected?

## Non-goals

- This audit does not reverse any existing `NO-GO` result.
- This audit does not unlock D5, model build, paper-forward, live trading, broker integration, or order submission.
- False-negative candidates are not promotion candidates.
- The audit must not retune thresholds on OOS outcomes.
- The audit must not use `future_return_1d` or any future label as a decision-time feature.

## Fixed policies

| Policy | Value |
|---|---|
| Default cost | 23bp round trip |
| Sensitivity grid | 0/23/46bp |
| Baseline controls | no-trade, shuffle, frozen-D3 where applicable |
| Promotion status | `NO-GO_RESEARCH_ONLY` unless a later approved gate changes it |
| Candidate semantics | review-only, requires new preregistration |
| Generated artifact root | `webui/rl_runs/daily_ohlcv_rejection_audit/` |

## Data sources

Allowed source evidence:

- Dated docs under `docs/`.
- Existing run manifests under `webui/rl_runs/`.
- Existing batch manifests under `webui/rl_runs/`.
- Existing scenario plans under `artifacts/`.
- Governance index `docs/stom_daily_ohlcv_research_governance_index_2026-06-18.md`.

Disallowed source evidence:

- Unhashed ad-hoc notebook/manual notes.
- Same-run post-hoc threshold changes.
- Future labels used as features.
- Live/broker/order logs.
- Any result lacking manifest/source path provenance.

## Required artifacts

The audit run must generate:

| Artifact | Purpose |
|---|---|
| `gate_funnel_metrics.csv` / `.json` | Count hypotheses entering, passing, watching, rejecting, or dropping out at each gate |
| `rejection_reason_taxonomy.csv` / `.json` | Normalize why hypotheses are blocked/NO-GO/WATCH |
| `calibration_metrics.csv` | Compare prior confidence/score buckets with later gate outcomes |
| `threshold_sensitivity.csv` | Show how frozen thresholds affect pass/watch/reject counts without OOS retune |
| `false_negative_candidates.csv` | Review-only list of hypotheses that may deserve new preregistration |
| `audit_manifest.json` | Source hashes, artifact hashes, policies, row counts, guardrails |

## Schema contracts

### `gate_funnel_metrics`

Required columns:

- `run_id`
- `workflow_id`
- `hypothesis_id`
- `scenario_id`
- `gate_id`
- `gate_order`
- `denominator_group`
- `denominator_count`
- `entered_count`
- `passed_count`
- `watch_count`
- `rejected_count`
- `early_dropout_count`
- `missing_artifact_count`
- `stale_artifact_count`
- `cost_bp`
- `fold_id`
- `split`
- `decision_time_utc`
- `evidence_manifest_path`
- `evidence_manifest_sha256`
- `decision_rule_id`
- `retuned_on_oos`

Denominator rule: `denominator_count` is fixed before seeing the gate outcome. It is the number of preregistered hypotheses/scenarios eligible to enter the gate.

Timing rule: `decision_time_utc` is when the gate decision was made from then-available evidence. Later evidence must not rewrite historical rows.

### `rejection_reason_taxonomy`

Required columns:

- `reason_id`
- `reason_family`
- `severity`
- `gate_id`
- `human_readable_reason_ko`
- `remediable`
- `required_next_evidence`
- `source_artifact_path`
- `source_artifact_sha256`
- `applies_to_workflow_ids`

Allowed `reason_family` values:

- `DATA_GOVERNANCE`
- `LEAKAGE_RISK`
- `COST_FAILURE`
- `BASELINE_UNDERPERFORMANCE`
- `FOLD_INCONSISTENCY`
- `ACTION_COLLAPSE`
- `MISSING_ARTIFACT`
- `STALE_ARTIFACT`
- `GOVERNANCE_LOCK`
- `INVALID_CONFIG`

### `calibration_metrics`

Required columns:

- `run_id`
- `hypothesis_id`
- `score_source`
- `score_bucket`
- `confidence_bucket`
- `decision_gate`
- `denominator_count`
- `observed_pass_rate`
- `observed_watch_rate`
- `observed_reject_rate`
- `brier_score_optional`
- `ece_optional`
- `split`
- `fold_id`
- `cost_bp`
- `evidence_timing`
- `future_label_used_as_feature`

`future_label_used_as_feature` must be `false`.

### `threshold_sensitivity`

Required columns:

- `run_id`
- `hypothesis_id`
- `threshold_id`
- `threshold_value`
- `threshold_freeze_time_utc`
- `cost_bp`
- `fold_id`
- `split`
- `pass_count`
- `watch_count`
- `reject_count`
- `baseline_delta`
- `no_trade_delta`
- `shuffle_delta`
- `d3_delta`
- `retuned_on_oos`

`retuned_on_oos` must be `false`.

### `false_negative_candidates`

Required columns:

- `candidate_id`
- `original_hypothesis_id`
- `original_rejection_gate`
- `original_rejection_time_utc`
- `original_reason_id`
- `original_evidence_manifest_path`
- `later_independent_evidence_manifest_path`
- `later_independent_evidence_sha256`
- `independence_rule_id`
- `why_candidate_ko`
- `review_status`
- `promotion_allowed`
- `requires_new_preregistration`

`review_status` must be `REVIEW_ONLY`.  
`promotion_allowed` must be `false`.  
`requires_new_preregistration` must be `true`.

## Independent evidence rule

Later evidence can support a false-negative candidate only if it comes from:

1. A later timestamped manifest, or
2. A later fold/window not available at the original decision time, or
3. A separately preregistered follow-up diagnostic.

Same-run cherry-pick, same-fold threshold changes, missing hashes, stale artifacts, or optimistic generated payloads fail closed.

## Planned acceptance criteria

The audit passes as a research diagnostic only if:

1. Every generated artifact has source paths and hashes.
2. Every cost-bearing table has 0/23/46bp rows or a documented not-applicable reason.
3. Every candidate is explicitly review-only.
4. No candidate can set model/paper/live readiness true.
5. The audit manifest records source hashes, artifact hashes, denominator policy, timing policy, independent evidence policy, and guardrails.
6. Focused tests prove missing/stale/optimistic artifacts fail closed.

## Expected interpretation

| Outcome | Meaning |
|---|---|
| High justified rejection | Governance is strict but working |
| High early dropout with remediable reasons | Data/process quality work is needed before new model experiments |
| False-negative candidates present | New preregistration may be justified, not promotion |
| No false-negative candidates | Current rejection gates may be conservative but not obviously over-pruning |

## Final guardrail

This preregistration is about **research process quality**. It is not a trading strategy, not an RL performance result, and not evidence of live-trading readiness.
