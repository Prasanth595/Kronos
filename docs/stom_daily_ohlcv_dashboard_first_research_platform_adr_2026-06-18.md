# Daily OHLCV Dashboard-first Research Platform ADR — 2026-06-18

Date: 2026-06-18 UTC  
Status: `ACCEPTED_FOR_RESEARCH_PLATFORM_EXECUTION` / implementation guardrail `RESEARCH_ONLY`  
Decision scope: Kronos Dashboard workflow UX, research job-intent contract, CLI demotion, and no-live product boundary  
Related plan: `.gjc/plans/ralplan/2026-06-11-0158-38ea/stage-357-final.md` / `.gjc/plans/ralplan/2026-06-11-0158-38ea/pending-approval.md`

## Decision

Kronos Daily OHLCV/RL work will continue as a **dashboard-first research and verification platform**, not a live-trading product.

The accepted implementation direction is:

1. Remove 실거래/live trading from the platform goal.
2. Keep broker integration, order submission, live account connectivity, paper-forward unlock, model-build unlock, and profit claims out of scope.
3. Make `Kronos Dashboard` / `Kronos 대시보드` the primary user surface for seeing, inspecting, configuring, requesting, and monitoring research-only workflows.
4. Treat CLI commands as backend/internal provenance or maintainer/admin detail only, not the public user workflow.
5. Allow dashboard POST behavior only for immutable, approval-linked research **job-intent records**; POST routes must not execute arbitrary shell, spawn workers synchronously, submit orders, unlock paper-forward, or start model builds.
6. Add a falsifiable hypothesis rejection / early-dropout audit lane to test whether research hypotheses are rejected too often or too early.

## Non-goals

| Excluded goal | Status |
|---|---|
| Live trading | Removed from goal set |
| Broker/order integration | Forbidden |
| Paper-forward unlock | Forbidden until a future fresh gate explicitly changes it |
| Model-build unlock | Forbidden until a future fresh gate explicitly changes it |
| Profitability claim | Forbidden |
| Arbitrary CLI/shell execution from dashboard | Forbidden |
| Reversing old `NO-GO` verdicts by dashboard presentation | Forbidden |

## Decision drivers

1. **User-facing workflow must be dashboard-first.** Users should not need to copy CLI commands to understand or request research workflows.
2. **Governance locks must remain fail-closed.** D0 price basis, D1 universe, D5 NO-GO, model/paper/live locks, 23bp cost, and 0/23/46bp sensitivity remain visible and enforced.
3. **Research quality must be measured, not marketed.** Rejection/false-negative analytics can improve hypothesis triage, but cannot promote models without new preregistered gates.

## Job-intent contract v1

A job intent is an immutable generated record under `webui/rl_runs/` or `artifacts/`. It is a request to run a research workflow after approval validation; it is not the run itself.

### Allowed workflow ids

Initial allowlist:

- `D0_D1_DATA_GOVERNANCE_REVIEW`
- `D3_D4_SIGNAL_QUALITY_AUDIT`
- `PAST_ONLY_MARKET_REGIME_AUDIT`
- `D4_RL_OVERLAY_ABLATION`
- `SCENARIO_BATCH_RESEARCH_ONLY`
- `HYPOTHESIS_REJECTION_AUDIT`

Unknown workflow ids must fail closed.

### Required fields

| Field | Requirement |
|---|---|
| `schema_version` | `daily_ohlcv_research_job_intent.v1` |
| `intent_id` | Safe generated id |
| `workflow_id` | One of the allowlisted ids |
| `approval_ref` | Dated prereg doc, approved `.gjc` plan/goal reference, or approved dashboard approval record |
| `approval_ref_sha256` | Hash of the approval reference |
| `requested_by` | Requesting local/operator identity |
| `requested_at_utc` | UTC timestamp |
| `idempotency_key` | Duplicate-control key |
| `plan_hash` | Hash of submitted plan/config preview |
| `config_hash` | Hash of normalized config |
| `source_governance_index_path` | Governance index in force |
| `default_cost_bp` | `23` |
| `cost_sensitivity_bp` | `[0, 23, 46]` |
| `baseline_controls` | Includes no-trade, shuffle, frozen-D3 controls where applicable |
| `no_retune` | `true` |
| `model_build_allowed` | `false` |
| `paper_forward_allowed` | `false` |
| `live_broker_order_allowed` | `false` |
| `artifact_root` | `webui/rl_runs` or `artifacts` only |
| `status` | Initial `INTENT_RECORDED` |
| `guardrails` | Research-only, no live/broker/orders, no profit claims, no paper/model unlock, no arbitrary shell |

### Forbidden fields

A dashboard/API request must reject fields named or semantically equivalent to:

`command`, `shell`, `argv`, `cwd`, `env`, `broker`, `account`, `order`, `symbol_order`, `live`, `paper_forward_unlock`, `model_build_unlock`, `profit_target`, `arbitrary_path`.

### Idempotency

- Same `idempotency_key` + same `plan_hash` + same `config_hash` returns the existing intent.
- Same `idempotency_key` with different `plan_hash` or `config_hash` fails with conflict.
- Duplicate intents must not create duplicate worker execution.

### Lifecycle

Allowed statuses:

```text
INTENT_RECORDED -> VALIDATED -> QUEUED -> RUNNING -> COMPLETED_RESEARCH_ONLY
INTENT_RECORDED -> VALIDATION_FAILED
QUEUED/RUNNING -> FAILED_RESEARCH_ONLY
QUEUED -> CANCELLED_BEFORE_RUN
```

No transition may set model, paper, live, broker/order, or profit readiness to true.

### POST guarantee

The POST route may write or return an intent record only. It must not:

- run arbitrary shell,
- spawn a worker synchronously,
- submit broker/order/live actions,
- unlock paper-forward,
- start model-build,
- create profit claims.

## CLI demotion rule

Existing CLI/quick-start command text may remain only as collapsed backend provenance or maintainer/admin detail. The public user workflow must be:

```text
workflow catalog -> inspector -> safe config -> approval blocker or intent creation -> ledger -> artifact review
```

## Hypothesis rejection / early-dropout contract

The platform must measure whether hypotheses are rejected too often or too early with a falsifiable audit, not with hindsight selection.

Required generated artifacts:

- `gate_funnel_metrics.csv/json`
- `rejection_reason_taxonomy.csv/json`
- `calibration_metrics.csv`
- `threshold_sensitivity.csv`
- `false_negative_candidates.csv`
- `audit_manifest.json`

False-negative candidates are review-only. They cannot reverse `NO-GO`, cannot unlock model/paper/live, and require a new preregistered hypothesis before any follow-up research.

## Consequences

| Consequence | Effect |
|---|---|
| Dashboard can become more interactive | Only through safe configs and job-intent records |
| CLI remains usable internally | But no longer the public workflow path |
| More generated evidence | Must remain under `webui/rl_runs/` or `artifacts/` |
| More docs | Durable decisions/prereg/results stay under `docs/` |
| Rejection analysis becomes possible | But cannot be used for promotion without new gates |
| Live readiness remains 0% | By design |

## Verification requirements for implementation

Future implementation must prove:

1. Public UI exposes dashboard-first workflow controls without CLI-first command copy.
2. Job-intent API rejects forbidden command/live/broker/order/model/paper fields.
3. Path traversal and unsafe artifact roots fail closed.
4. Missing/stale approval fails closed.
5. Idempotency behavior is deterministic.
6. All payloads preserve `model_build_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false`.
7. Rejection audit artifacts include denominator, timing, independent-evidence, and review-only fields.

## Current status after this ADR

This ADR freezes the decision and contract. It does **not** report a trading result, does **not** claim profitability, and does **not** unlock D5/model-build/paper-forward/live trading.
