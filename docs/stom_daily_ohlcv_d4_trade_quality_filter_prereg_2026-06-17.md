# Daily OHLCV D4 Trade-Quality Filter Preregistration — 2026-06-17

Date: 2026-06-17 UTC  
Status: `PREREGISTERED_RESEARCH_ONLY`  
Experiment type: `RL experiment` / diagnostic filter research  
Parent result: `docs/stom_daily_ohlcv_d4_action_induction_v2_result_2026-06-17.md`  
Default cost: 23bp round trip

## Objective

The D4 action-induction v2 run proved that non-hold actions can be made reachable, but all v2 policies still underperformed the best D3/no-trade baseline on `val+test`. The next research lane must therefore test **trade quality and abstention**, not more action forcing.

This preregistration freezes the next hypothesis before further scenario execution.

## Non-negotiable guardrails

| Guardrail | Required state |
|---|---|
| Live/broker/order use | Forbidden. |
| Profit claim | Forbidden. |
| Paper-forward/model-build promotion | Forbidden until D0/D1/D3/D4/D5 gates pass in a later approved workflow. |
| Default cost | 23bp round trip; include 46bp stress before any promotion claim. |
| D5 status | `NO-GO` unless a fresh gate run passes. |
| Future labels | Current/future labels may not enter state/action/filter selection. They are allowed only after decision for reward and diagnostics. |
| Action prior | Freeze as diagnostic-only or disable; do not tune upward to chase a curve. |
| Generated artifacts | Write generated evidence under `webui/rl_runs/`; durable conclusions under `docs/`. |

## Hypothesis

A D4 policy/filter may improve trade quality if it abstains from weak D3 signals and trades only when **decision-time confidence and margin** are high enough. The expected success condition is not action frequency; it is whether fewer, higher-quality actions reduce drawdown/turnover and improve comparison against no-trade, shuffle, and frozen D3 baselines.

## Frozen research variants

| Variant | Change | Rationale | Failure mode to test |
|---|---|---|---|
| `confidence_abstain_v1` | Permit buy/add only when `d3_confidence_bucket` is above a frozen threshold. | v2 traded too often without enough signal strength. | May revert to no-trade or miss positive days. |
| `margin_abstain_v1` | Permit buy/add only when `score_margin_bucket` is above a frozen threshold. | Top candidate must be meaningfully separated from alternatives. | May overfit score scale and still lose. |
| `confidence_margin_joint_v1` | Require both confidence and margin thresholds. | Tests strict quality filter versus action reachability. | Lower turnover may still not beat no-trade. |
| `risk_regime_abstain_v1` | Block new entries when past-only `recent_score_volatility_bucket` is high. | v2 drawdowns suggest unstable regimes may be harmful. | Proxy may not represent price risk. |
| `prior_disabled_control_v1` | Keep v2 state but disable entry prior. | Separates filter effects from action-forcing effects. | Actions may become sparse again. |

## State/action/reward/environment contract

| RL element | Requirement | Forbidden shortcut |
|---|---|---|
| State | Keep v2 causal fields: `position_count`, `top_score_bucket`, `score_margin_bucket`, `candidate_count_bucket`, `recent_score_volatility_bucket`, `d3_confidence_bucket`. | Do not expose current/future `future_return_1d` or fold outcomes. |
| Action | Keep hold/buy/add/sell/reduce with valid masks. Filter may block buy/add and must record the exact reason. | Do not silently coerce blocked actions without telemetry. |
| Reward | Keep actual net return after 23bp cost separate from shaping/filter diagnostics. | Do not report filter reward as realized return. |
| Environment | Daily OHLCV research environment only. | No live fills, broker, orders, or market simulation claims. |
| Policy/filter | Label as `D4 trade-quality filter diagnostic`; compare to tabular-Q v2 and D3 baselines. | Do not call filter pass a deployable RL policy. |
| Diagnostics | Emit action reachability, abstention reason counts, no-trade opportunity diagnostics, and baseline deltas. | Do not use hindsight diagnostics to choose actions in the same run. |

## Required artifacts for each run

| Artifact | Purpose |
|---|---|
| `rl_manifest.json` | D4 lineage, guardrails, status, hashes. |
| `observation_manifest.json` | State/filter contract and leakage checks. |
| `state_observations.csv` | Decision-time state rows with no future labels. |
| `action_distribution.csv` | Whether actions remain reachable. |
| `invalid_actions.csv` | Valid mask and blocked-action telemetry. |
| `abstention_reasons.csv` | New required filter decision reasons. |
| `reward_breakdown.csv` | Actual accounting terms. |
| `policy_baseline_comparison.csv` | no-trade/shuffle/frozen D3 comparison under 23bp. |
| `no_trade_opportunity_summary.json` | Post-policy missed/avoided opportunity analysis. |
| `scenario_batch_manifest.json` | Scenario matrix status and blockers. |
| `*_result_YYYY-MM-DD.md` | Durable result report under `docs/`. |

## Acceptance criteria

A result is acceptable as research evidence only if all are true:

1. State/filter artifacts prove current/future labels are not used in action selection.
2. Action distribution and abstention reasons are emitted for every split.
3. Net return after cost remains separate from filter/shaping diagnostics.
4. Comparisons include no-trade, shuffle, equal-weight top-k, and frozen D3 baselines.
5. D5 remains `NO-GO` unless a separate fresh gate passes.
6. A dated result document is created under `docs/`.
7. `model_build_allowed=false`, `paper_forward_allowed=false`, and `live_broker_order_allowed=false` remain true in manifests.

## Planned executable next step

Implement a bounded `D4 trade-quality filter` scenario lane:

1. Add filter/abstention telemetry without changing existing reward accounting.
2. Add tests for filter no-leakage, blocked-action reasons, and baseline manifest fields.
3. Run a small preregistered scenario batch comparing confidence, margin, joint, regime, and control variants.
4. Publish `docs/stom_daily_ohlcv_d4_trade_quality_filter_result_YYYY-MM-DD.md` and update the governance index.

## Current promotion status

`NO-GO_RESEARCH_ONLY`.

This preregistration approves diagnostics only. It does not approve model build, paper-forward, live trading, broker integration, or profit claims.
