# STOM/Kronos development progress and RL feasibility — 2026-06-05

## Purpose

This document consolidates the STOM opening-research and dashboard direction as of 2026-06-05. It is an evidence ledger, not a marketing or live-trading readiness document.

The current mainline remains the `ts_imb` opening gap-up **RULE** baseline. PPO/DQN/orderbook RL work remains an isolated research and falsification lane. The official dashboard should make evidence, costs, splits, baselines, controls, and failure reasons visible.

## Current verdict summary

| Area | Status | Reason |
|---|---|---|
| `ts_imb RULE baseline` | Main research baseline | Strongest current opening reference; must not be called RL. |
| Skip-gate | `NO-GO` | Full-universe checks did not justify promotion. |
| State-conditioned early-exit gate | `NO-GO` | Primary model failed GO criteria; negative controls behaved as expected. |
| Opening PPO/DQN candidate | `NO-GO_BASELINE` / research-only | Candidate failed no-trade or buy-and-hold baseline gates under the 23bp assumption. |
| Realdata RL smoke | `INCONCLUSIVE` | OOS split, controls, ablations, and baseline superiority were not sufficient for promotion. |
| Rule/meta-label filter | `NO-GO_CONTROL` | Rule-filter evidence did not pass the preregistered control/ablation/baseline gate. |
| Live/broker readiness | `NO-GO` | There is no live-ready model, no broker integration, and no profitability claim. |

## Evidence trail

| Date | Artifact | Notes |
|---|---|---|
| 2026-06-01 | `docs/stom_rl_resume_handoff_2026-06-01.md` | Resume context for RL/RULE split and `ts_imb` 23bp guardrails. |
| 2026-06-01 | `docs/stom_rl_opening_ppo_candidate_2026-06-01.md` | Historical PPO opening candidate record; `NO-GO_USABLE_MODEL`. |
| 2026-06-01 | `docs/stom_skip_gate_prereg_2026-06-01.md` | Skip-gate preregistration. |
| 2026-06-01 | `docs/stom_skip_gate_result_2026-06-01.md` | Full-universe `NO-GO`, negative-control context, 23bp/marketable-fill accounting. |
| 2026-06-01 | `docs/stom_state_exit_prereg_2026-06-01.md` | State-conditioned early-exit preregistration. |
| 2026-06-02 | `docs/stom_state_exit_result_2026-06-02.md` | State-exit `NO-GO`; primary model did not satisfy GO criteria. |
| 2026-06-03 | `docs/stom_development_direction_review_2026-06-03.md` | Mainline is `ts_imb` RULE; RL is evidence/falsification lane. |
| 2026-06-03 | `docs/stom_opening_30m_rl_workflow_2026-06-03.md` | Opening-30m workflow with OOS, controls, ablations, and 23bp constraints. |
| 2026-06-04 | `docs/stom_opening_30m_rl_realdata_validation_2026-06-04.md` | Realdata RL smoke remains `INCONCLUSIVE`. |
| 2026-06-04 | `docs/stom_opening_30m_rl_oos_candidate_validation_2026-06-04.md` | DQN/PPO OOS candidate rejected by baseline gate. |
| 2026-06-04 | `docs/stom_opening_30m_rl_feature_revalidation_2026-06-04.md` | Feature/ablation review; final verdict remains `NO-GO_BASELINE`. |
| 2026-06-04 | `docs/stom_opening_30m_rule_filter_prereg_2026-06-04.md` | Rule/meta-label filter preregistration. |
| 2026-06-04 | `docs/stom_opening_30m_rule_filter_result_2026-06-04.md` | Rule-filter smoke `NO-GO_CONTROL`, split hash `225356e7f771784c`. |
| 2026-06-05 | `.omo/plans/rule-filter-realdata-oos-expansion.md` | Bounded realdata OOS expansion plan for rule/RL separation and control evidence. |

## Completion and feasibility status

| Surface | Role | Completion estimate | Remaining gap |
|---|---|---:|---|
| `/` dashboard shell | Official dashboard entry | 70% | Keep route labels product-facing, not version/lab-facing. |
| `/rl` RL evidence route | RULE/RL evidence viewer | 80% | Keep rule/RL labels, failure reasons, and costs visible. |
| RL Trading / Evidence tab | Candidate lifecycle, split, controls, ablations, equity evidence | 75% | Strengthen OOS/control/failure panels and avoid success-looking charts without baseline context. |
| Forecast Workbench | Kronos prediction inspection | 60% | Keep separate from STOM/RL trading evidence. |
| History / Runs | Run discovery and evidence navigation | 70% | Keep rule-filter realdata runs discoverable. |
| Artifacts / Models | Read-only artifact inspection | 60% | Label RULE artifacts and RL artifacts separately. |
| STOM Diagnostics | Prediction/backtest diagnostics | 65% | Improve OOS diagnostics and data-quality context. |
| System Health | Runtime/data health | 55% | Distinguish infrastructure readiness from model usability. |
| Docs Page | Decision/evidence ledger surface | 65% | Link durable result docs and preserve verdict labels. |
| RL evidence tables | Controls, ablations, failure reasons, time buckets | 80% | Keep controls and baseline gates visible. |
| Participant Proxy / Orderbook cards | Participant proxy, imbalance, persistence, overheat/upper-wick context | 55-65% | Treat features as research evidence until ablations and controls pass. |
| Cumulative equity curve | Evidence visualization | 60% | Always show baseline/no-trade/cost context; do not imply profitability. |

## Research feasibility

| Track | Feasibility | Evidence boundary |
|---|---|---|
| `ts_imb` RULE baseline | Mainline research candidate | Still requires OOS discipline, sizing/risk constraints, and drawdown/cost gates. |
| PPO/DQN RL candidates | Research-only | Current evidence is `NO-GO_BASELINE`, `NO-GO_USABLE_MODEL`, or `INCONCLUSIVE`. |
| Rule/meta-label filter | Research-only | Latest rule-filter family verdict is `NO-GO_CONTROL`. |
| Orderbook/imbalance features | Research feature lane | Requires same-split controls, feature ablation, OOS evidence, and marketable-fill accounting. |
| Participant proxy | Research feature lane | Proxy quality and ablation evidence are required before any promotion claim. |
| Live/broker path | Not feasible from current evidence | No live forward evidence, no broker integration, no live-ready model. |

## Required guardrails for the next loop

1. Keep `ts_imb` labeled as a RULE baseline.
2. Preserve 23bp round-trip cost unless a preregistered test explicitly states otherwise.
3. Require OOS split metadata, negative/shuffle controls, feature ablations, drawdown, and cost gates for any alpha claim.
4. Show `NO-GO`, `NO-GO_BASELINE`, `NO-GO_CONTROL`, and `INCONCLUSIVE` plainly in docs and UI.
5. Keep the dashboard read-only; do not add broker/live-order side effects.
6. Do not call dashboard curves proof of profitability.

## Recommended next work

1. Commit hygiene and generated-artifact separation before more experiments.
2. Dashboard rule/RL label hardening, including evidence panels for cost, split, baseline delta, controls, ablations, and failure reasons.
3. Bounded realdata OOS rule-filter validation only under preregistered controls.
4. JSON/evidence validators for missing split/control/ablation/gate fields.
5. Feature availability audit for orderbook imbalance, persistence, OFI, participant proxy, and overheat/upper-wick features.
6. Only after those pass, compare constrained RL candidates against no-trade, buy-and-hold, and `ts_imb` RULE baseline under 23bp costs.

## Bottom line

The repository is useful as a research and operations evidence platform. It is not live-trading ready. The safest current direction is to keep the `ts_imb` RULE baseline as the mainline evidence anchor and use RL/orderbook experiments to falsify hypotheses under strict OOS, cost, control, and ablation gates.
