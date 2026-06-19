# Daily OHLCV RL Continuation Preregistration

Date: 2026-06-14 KST  
Status: `PREREGISTERED_RESEARCH_ONLY`  
Source plan: `.gjc/plans/ralplan/2026-06-11-0158-38ea/pending-approval.md`  
Generated artifact: `webui/rl_runs/daily_ohlcv_rl_prereg/prereg_2026_06_14_g001_rl_continuation/preregistration_manifest.json`

## Guardrail snapshot

| Surface | Locked state | Consequence |
|---|---|---|
| D0 price basis | `unknown` / `UNKNOWN_CONFIRMED` | Return evidence is not decision-grade until price basis is independently verified. |
| D1 universe | `WATCH_HEURISTIC_UNIVERSE` | Official/manual KRX common-equity validation remains required. |
| D3 baseline | `WATCH` / `D3_WATCH_RESEARCH_ONLY` | Frozen D3 is a comparator, not model-build approval. |
| D4 RL | `RESEARCH_ONLY` | RL graphs are diagnostics only. |
| D5 gate | `NO-GO` | No model-build, paper-forward, or readiness promotion. |
| Global flags | `model_build_allowed=false`, `go_summary_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false` | Must remain false until D0/D1/D3/D5 gates pass in a later approved workflow. |

This preregistration keeps: no live/broker/orders, no profit claims, 23bp round-trip default cost, no `_database` mutation, and leading-zero stock codes as strings.

## Selected hypothesis

**Option A — conservative constrained-action reward redesign** is frozen as the next Daily OHLCV RL research path.

Hypothesis: a constrained daily-portfolio RL policy with explicit 23bp turnover cost, drawdown/concentration/churn penalties, invalid-action handling, and no-trade/hold behavior may reduce prior D4 failure modes. It must still beat no-trade, deterministic shuffle, and frozen D3 baselines on fresh OOS before any promotion discussion.

This is not a deployable model, paper-forward approval, broker/order readiness, or profit claim.

## Current reference evidence

| Reference | Value |
|---|---:|
| Prior D4 policy total net return, val+test | -42.12% |
| Prior D4 policy NAV, val+test | 0.5788 |
| Prior D4 max drawdown, val+test | -81.91% |
| Best frozen D3 baseline | `equal_weight_topk_momentum` |
| Best frozen D3 total net return | +31.37% |
| Prior D4 delta vs best D3 | -73.49pp |
| Prior D5 status | `NO-GO` |
| Prior D5 forward folds | 5 |

These numbers are research evidence only and remain blocked by D0/D1/D3/D5 locks.

## Frozen reward/action contract for the next implementation stories

| Contract | Requirement |
|---|---|
| Net return after cost | Use 23bp round-trip cost by default and preserve 0/46bp as labeled sensitivity. |
| Drawdown penalty | Penalize current/realized drawdown and classify drawdown-only gains as failure. |
| Turnover/churn penalty | Penalize avoidable rebalance churn after costs. |
| Concentration penalty | Penalize overconcentration relative to configured max positions / target diversification. |
| Invalid actions | Count, penalize, and surface invalid or masked actions; do not hide them. |
| No-trade/hold | Keep no-trade/hold as a valid action/control, not an implicit failure. |
| Leading-zero codes | Preserve codes such as `000250` as strings in artifacts and UI samples. |

## Required controls

- `no_trade_cash`
- deterministic shuffle with recorded seed/hash
- frozen D3 best baseline, currently `equal_weight_topk_momentum`
- prior D4 policy comparison
- 23bp default cost and 0/46bp sensitivity

## D4 evidence required before D5

The next D4 artifact must remain `RESEARCH_ONLY` and include:

- `learning_curve.csv`
- `reward_breakdown.csv`
- `reward_component_summary.json`
- `action_distribution.csv`
- `invalid_actions.csv`
- `turnover.csv`
- `drawdown.csv`
- `policy_nav.csv`
- `state_observations.csv`
- `observation_manifest.json`
- `baseline_comparison.json`
- false `model_build_allowed`, `go_summary_allowed`, `paper_forward_allowed`, and `live_broker_order_allowed`
- deltas vs no-trade, deterministic shuffle, and frozen D3

## D5 threshold contract

| Gate item | Frozen threshold |
|---|---|
| Forward folds | at least 5 |
| Purge / embargo | at least 5 days each unless justified in artifact |
| OOS retuning | `retuned_on_oos=false` |
| Cost sensitivity | 0bp / 23bp / 46bp |
| Controls | no-trade, deterministic shuffle, frozen D3 baseline |
| Current blocker behavior | D5 remains `NO-GO` while D0/D1/D3 blockers remain |

Promotion preconditions remain: D0 price basis verified, D1 official/manual universe review complete, D3 no longer `WATCH`, D4 no longer underperforms D3, and D5 passes fresh OOS fold/cost/drawdown/turnover checks.

## No-retuning / no-cherry-pick rules

- Freeze reward terms and action space before running the new OOS workflow.
- Do not choose policies by OOS metrics.
- Do not change thresholds after seeing OOS results.
- Any material reward/action change after inspection requires a new preregistered hypothesis.
- Report failure plainly as `NO-GO` or `RESEARCH_ONLY` rather than hiding it behind a favorable chart.

## Failure categories to classify

| Category | Meaning |
|---|---|
| `reward_hacking` | Reward improves while actual NAV/drawdown/control deltas worsen. |
| `action_collapse` | Policy degenerates into one action or ignores no-trade/hold. |
| `drawdown_or_concentration_failure` | Return comes from unacceptable drawdown or concentrated exposure. |
| `cost_sensitivity_failure` | Edge disappears under 23bp or 46bp. |
| `fold_instability` | Few folds drive the result or worst-fold risk dominates. |
| `D0_price_basis_blocker` | Price basis remains unknown. |
| `D1_universe_blocker` | Universe remains heuristic/watch. |
| `D3_underperformance` | RL underperforms frozen D3. |
| `artifact_or_provenance_drift` | Hash/source/data/code provenance changes unexpectedly. |

## Next executable story

The next Ultragoal story may implement D4 portfolio environment reward and action changes. This preregistration story intentionally does not implement training or environment changes.
