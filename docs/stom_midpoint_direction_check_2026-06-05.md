# STOM/Kronos Midpoint Direction Check — 2026-06-05

## Purpose

This document is a midpoint direction check for the opening 30m STOM/Kronos trading research track. It consolidates current progress, evidence quality, blockers, expected path to 100%, and the next recommended LazyCodex/OMO command sequence.

This is a research and dashboard evidence document. It is not a live-trading approval, not broker readiness, not a profit guarantee, and not a claim that reinforcement learning is currently successful.

## Current Direction

The correct direction remains:

1. Keep `ts_imb` as the main RULE baseline.
2. Treat the opening 30m rule/meta-label filter as the nearest practical candidate track.
3. Use participant/supply-demand fields only as proxy evidence.
4. Use orderbook/호가, 체결강도, overheat, and upper-wick features as hypotheses that must pass controls and ablations.
5. Do not promote PPO/DQN/RL until the simpler RULE/meta-label filter beats baselines and negative controls.
6. Keep the dashboard as a read-only evidence viewer, not as proof of profitability.

## Latest Evidence Snapshot

| Field | Value |
|---|---:|
| Latest realdata run | `opening_30m_rule_filter_realdata_oos_2026_06_05` |
| Verdict | `NO-GO_CONTROL` |
| Split hash | `37664423068ddeca` |
| Cost assumption | `23bp` |
| OOS net return | `+3.576084196458389%` |
| Validation net return | `-1.6100862564692298%` |
| OOS TAKE count | `2` |
| Minimum OOS TAKE count | `3` |
| Max drawdown | `1.2345662100456654%` |
| Sample scope | bounded real tick DB sample, not full-universe validation |

## Why The Current Result Is Not Yet Good Enough

| Blocker | Interpretation | Required Response |
|---|---|---|
| `insufficient_oos_take_trades` | OOS sample has only 2 TAKE trades vs minimum 3 | Wider preregistered sample required |
| `failed_baseline:buy_and_hold` | Filter matched buy-and-hold, so no incremental edge | Must beat buy-and-hold after 23bp |
| `failed_baseline:ts_imb_rule` | Filter matched `ts_imb RULE baseline` | Must beat the base RULE baseline |
| `failed_controls` | Shuffled labels/time shuffle did not fail cleanly | Need stronger negative-control evidence |
| `failed_ablations` | Orderbook/overheat/proxy feature contribution is unstable | Need feature attribution on larger sample |

The positive OOS return is not enough. The filter must beat baseline, cost, control, and ablation gates before it can be considered a serious candidate.

## Current Page / Area Progress

| Page/Area | Progress | Status |
|---|---:|---|
| Official Dashboard Shell | 70% | Integrated, but status/doc consolidation remains |
| Trading/RL Evidence Tab | 84% | Rule-filter evidence, controls, ablations visible |
| Participant Proxy Card | 82% | RULE/RL label blocker fixed; proxy validity unproven |
| Rule Filter Evidence Tables | 85% | Controls, ablations, proxy availability, orderbook persistence rows available |
| Orderbook/호가 Evidence | 60% | Display exists; alpha contribution not proven |
| Overheat/윗꼬리 Feature | 55% | Included in ablation set; contribution not proven |
| Docs/Research Page | 70% | Result docs exist; more roadmap/status linking needed |
| System Health/Data Readiness | 58% | Read-only DB preflight exists; UI readiness status partial |
| RL Model Performance | 20% | PPO/DQN/RL remains research-only |
| Rule/meta-label Filter | 60% | Realdata OOS complete, but `NO-GO_CONTROL` |
| Live/Broker/Order Execution | 0% | Intentionally out of scope |

## Expected Path To 100%

| Stage | Goal | Current | Estimated Time |
|---:|---|---:|---:|
| 1 | Dashboard evidence consolidation | 70–85% | 0.5–1 day |
| 2 | Current `NO-GO_CONTROL` blocker analysis | 100% | completed |
| 3 | Wider realdata OOS preregistration | 0% | 1–2 hours |
| 4 | Wider bounded realdata OOS execution | 0% | 2–6 hours |
| 5 | Baseline/control/ablation revalidation | 0% | 2–4 hours |
| 6 | Feature improvement: orderbook, 체결강도, overheat, upper-wick, proxy | 30% | 1–3 days |
| 7 | Rule/meta-label filter iteration | 30% | 2–5 days |
| 8 | PPO/DQN/RL reconsideration | 20% | 2–5 days |
| 9 | Dashboard history/performance management | 65% | 1–2 days |
| 10 | Final research report and operating decision | 50% | 0.5–1 day |

Practical estimate:

| Target | Estimate |
|---|---:|
| Minimum research-complete loop | 4–7 days |
| More credible OOS validation | 1–2 weeks |
| RL/PPO/DQN revalidation included | 2–3 weeks |
| Pre-live research quality | 3–6+ weeks |

## Can We Run All Remaining Steps At Once?

No. Running everything at once is technically possible in an automation sense, but it is not valid research practice here.

The reason is dependency order:

1. The wider OOS experiment must be preregistered before execution.
2. OOS results must not be used to tune thresholds or features.
3. PPO/DQN should not be expanded until the simpler rule/meta-label filter proves baseline/control/ablation stability.
4. Dashboard enhancements should follow evidence shape, not invent success narratives ahead of validation.

Safe parallelization is possible only inside a stage:

| Can Parallelize? | Work |
|---|---|
| Yes | Dashboard display polish and documentation linking |
| Yes | Artifact readers / evidence table QA |
| Yes | Post-run analysis of controls and ablations |
| No | Preregistration → OOS execution → interpretation |
| No | Rule-filter validation → PPO/DQN expansion |
| No | Failed control diagnosis → live-readiness work |

## Recommended Command Sequence

### Next command — highest priority

```text
$ulw-plan Create a preregistered wider bounded realdata OOS rule-filter experiment plan based on the blocker analysis, without tuning on split 37664423068ddeca.
```

### Then execute the generated plan

```text
$start-work .omo/plans/<generated-wide-oos-plan>.md
```

### After wider OOS result exists

If the wider run is still `NO-GO_*`:

```text
$ulw-plan Analyze wider OOS failure causes and decide whether to simplify features, revise proxy definitions, or stop the RL expansion path.
```

If the wider run passes baseline/control/ablation gates:

```text
$ulw-plan Plan PPO/DQN opening 30m RL revalidation using the passed rule/meta-label evidence as baseline, with no OOS tuning and 23bp cost.
```

## Decision

Continue, but continue sequentially and evidence-first. The project direction is still coherent. The dashboard and evidence system are ahead of the model. The model track must now earn promotion through a wider preregistered OOS experiment, not through dashboard visuals or RL complexity.
