# Daily OHLCV D4 Action-Induction v2 Preregistration — 2026-06-16

Date: 2026-06-16 KST  
Status: `PREREGISTERED_RESEARCH_ONLY`  
Experiment type: `RL experiment`  
Parent result: `docs/stom_daily_ohlcv_d4_no_trade_diagnostic_result_2026-06-16.md`  
Default cost: 23bp round trip

## Objective

Continue the Daily OHLCV D4 RL research by testing whether a policy can learn non-trivial actions without using future labels in state/action selection.

The immediate failure to address is:

> Current D4 tabular-Q policies collapse to all-hold/no-trade even when candidate breadth, max positions, and training length change.

This preregistration freezes the next research lane before further code or scenario tuning.

## Non-negotiable guardrails

| Guardrail | Required state |
|---|---|
| Live/broker/order use | Forbidden. |
| Profit claim | Forbidden. |
| Paper-forward/model-build promotion | Forbidden until D0/D1/D3/D4/D5 gates pass in a later approved workflow. |
| Default cost | 23bp round trip, with explicit 0bp/46bp sensitivity where applicable. |
| D5 status | `NO-GO` unless a fresh gate run passes. |
| Future labels | May appear in labels/reward after the decision and in post-policy diagnostics only; never in current state/action selection. |
| Leading-zero stock codes | Preserve as strings. |
| Generated artifacts | Write under `webui/rl_runs/`; durable conclusions under `docs/`. |

## Hypothesis

A D4 policy may stop collapsing to no-trade if the state contains richer **decision-time causal context** and the action-selection experiment explicitly measures whether buy/add/sell/reduce become reachable without hindsight leakage.

This is a failure-analysis hypothesis, not an alpha or trading-readiness claim.

## Frozen research variants

| Variant | Change | Rationale | Expected failure mode to test |
|---|---|---|---|
| `state_margin_bucket_v1` | Add score-margin bucket between top-1 and top-2 candidates. | The policy may need confidence separation, not only top-score sign. | Still no-trade if score sign is too weak. |
| `candidate_count_bucket_v1` | Add candidate-count bucket. | Sparse/low-candidate days may need different action preference. | Over-generalization across unlike days. |
| `recent_volatility_bucket_v1` | Add past-only realized-volatility bucket from available historical bars/features. | High-volatility regimes may explain avoided buys. | Drawdown/concentration failure. |
| `d3_confidence_bucket_v1` | Add D3 prediction-confidence bucket using current D3 score distribution only. | D4 needs D3 confidence context to decide whether to trust a candidate. | D3-underperformance persists. |
| `action_prior_exploration_v1` | Add explicit exploration/action-prior diagnostics without changing OOS thresholds. | Current Q-table tie behavior favors hold. Need to measure action reachability. | Forced actions raise turnover/cost without D3 outperformance. |

## State/action/reward/environment contract

| RL element | v2 requirement | Forbidden shortcut |
|---|---|---|
| State | Use only information available at decision time: position count, top score bucket, score margin bucket, candidate count bucket, past-only volatility/regime bucket, D3 confidence bucket. | Do not expose `future_return_1d`, future NAV, or fold outcome in state. |
| Action | Keep constrained actions: hold, buy, add, sell, reduce. Record valid mask and invalid reason per row. | Do not hide invalid actions or silently coerce action results without telemetry. |
| Reward | Keep actual net return after cost separate from shaping/diagnostic terms. | Do not report shaping reward as realized return. |
| Environment | Daily OHLCV research environment only, no broker/order simulation. | No live fills, market orders, or broker integration. |
| Policy | Current lane may remain tabular-Q or introduce an explicitly labelled experimental policy; policy type must be emitted in manifests. | Do not call a rule baseline or forced action script an RL policy. |
| Diagnostics | Keep no-trade opportunity diagnostics post-policy only. | Do not use hindsight diagnostics to choose actions inside the same evaluation. |

## Required artifacts for each v2 run

| Artifact | Required? | Purpose |
|---|---:|---|
| `rl_manifest.json` | yes | Top-level D4 lineage, guardrails, hashes, status. |
| `observation_manifest.json` | yes | State contract and leakage checks. |
| `state_observations.csv` | yes | Decision-time state rows, no future labels. |
| `action_distribution.csv` | yes | Whether actions moved beyond all-hold. |
| `invalid_actions.csv` | yes | Valid-mask and invalid-action telemetry. |
| `reward_breakdown.csv` | yes | Actual reward/accounting terms. |
| `policy_baseline_comparison.csv` | yes | Frozen D3/no-trade/shuffle comparisons under 23bp. |
| `policy_nav.csv` | yes | Research-only NAV diagnostics. |
| `no_trade_opportunity_diagnostics.csv` | yes | Post-policy missed/avoided opportunity analysis. |
| `no_trade_opportunity_summary.json` | yes | Aggregated no-trade diagnostic summary. |
| `scenario_batch_manifest.json` | yes for batch | Scenario-level comparison and blocker summary. |
| `*_result_YYYY-MM-DD.md` | yes | Durable human-readable research report in `docs/`. |

## Data governance requirements

| Governance area | Requirement |
|---|---|
| Lineage | Every result document must link parent preregistration, scenario plan, batch manifest, per-run manifests, and verification commands. |
| Versioning | Material changes to state/action/reward/schema require a new dated preregistration document. Do not overwrite a prior result to soften `NO-GO`. |
| Reproducibility | Record CLI command, run id, seed, split, folds, purge/embargo, top-k/candidate limits, max positions, episodes, and cost assumptions. |
| Schema control | Add schema/field lists to manifests and tests when introducing new artifacts. |
| Hash/provenance | Keep source/artifact hashes in generated manifests; report drift as blocker, not cosmetic noise. |
| Access/safety | Dashboard/API surfaces remain read-only; no broker/live/order side effects. |
| Retention | Generated files stay under `webui/rl_runs/`; durable decision history stays under `docs/`. |
| Discoverability | Update or create dated docs using prefixes `stom_daily_ohlcv_d4_*_prereg_*`, `*_result_*`, or `*_handoff_*`. |
| Auditability | Each report must include verdict, blockers, exact command, verification result, and next allowed research action. |
| Data mutation | Do not mutate `_database` or prior generated evidence to improve results. New evidence requires a new run id. |

## Acceptance criteria for the next implementation

A v2 run can be considered a successful **research diagnostic** only if all are true:

1. State artifacts prove future labels are not used in action selection.
2. Action distribution shows whether non-hold actions are reachable and why.
3. Net return after cost remains separate from shaping/diagnostic rewards.
4. Policy is compared against no-trade, deterministic shuffle, and frozen D3 baselines.
5. D5 remains `NO-GO` unless a separate fresh OOS gate passes.
6. A dated result document is created under `docs/` after the run.
7. All model/paper/live/broker flags remain false.

## Planned executable next step

Implement **D4 action-induction v2** as a bounded research lane:

1. Add decision-time state buckets to the D4 observation contract.
2. Emit schema and tests proving no future label leakage.
3. Run a small scenario batch with v2 state/action diagnostics.
4. Publish a dated result document and update the governance index.

## Current promotion status

`NO-GO_RESEARCH_ONLY`.

This preregistration approves research diagnostics only. It does not approve model build, paper-forward, live trading, broker integration, or profit claims.
