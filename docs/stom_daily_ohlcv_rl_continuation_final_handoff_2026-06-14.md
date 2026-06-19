# STOM Daily OHLCV RL Continuation Final Handoff (2026-06-14)

## Verdict

`PASS` for the research/evidence handoff. `NO-GO` for model build, paper-forward, live trading, broker routing, and order submission.

This document closes the 2026-06-14 Daily OHLCV RL continuation stories G001-G006. The work produced a stricter research loop and clearer dashboard evidence, not a deployable trading model and not a profit claim.

## Guardrail snapshot

| Surface | Current state | Meaning |
|---|---|---|
| D0 price basis | `unknown` / `UNKNOWN_CONFIRMED` | Daily return labels are still not decision-grade until adjusted/raw/split/dividend basis is independently verified. |
| D1 universe | `WATCH_HEURISTIC_UNIVERSE` | Official or manually reviewed KRX common-equity universe validation is still required. |
| D3 baseline | `WATCH` / `D3_WATCH_RESEARCH_ONLY` | Frozen D3 remains a comparator and blocker, not model-build approval. |
| D4 RL | `RESEARCH_ONLY` | RL environment/training telemetry exists for diagnostics only. |
| D5 fresh OOS gate | `NO-GO` / `D5_NO_GO_RESEARCH_ONLY_GATE` | The fresh OOS walk-forward gate remains blocked by D0/D1/D3 and RL-underperformance evidence. |
| Model/paper/live flags | `model_build_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false` | No model creation/promotion, paper-forward, live/broker/order readiness is allowed. |
| Cost assumption | 23bp round trip default; 0bp/46bp sensitivity only | Cost sensitivity is diagnostic and must not be cherry-picked. |
| Data safety | No `_database` mutation; leading-zero codes preserved as strings | Generated artifacts are read-only evidence. |

## What was developed

| Story | Result | Main artifact/docs | Verification status |
|---|---|---|---|
| G001 preregistration | Froze Option A constrained-action reward/action redesign, controls, thresholds, and failure taxonomy before implementation. | `docs/stom_daily_ohlcv_rl_continuation_prereg_2026-06-14.md`; `webui/rl_runs/daily_ohlcv_rl_prereg/prereg_2026_06_14_g001_rl_continuation/` | Complete; architect/QA approved. |
| G002 D4 environment | Hardened reward/action contract: 23bp turnover cost, drawdown/concentration/churn penalties, invalid-action reasons, no-trade/hold behavior, action masks, leading-zero code preservation. | `stom_rl/daily_portfolio_env.py`; `docs/stom_daily_ohlcv_rl_continuation_g002_env_reward_action_result_2026-06-14.md`; `webui/rl_runs/daily_ohlcv_portfolio_env/env_contract_2026_06_14_g002_reward_action/` | Complete; focused tests passed. |
| G003 D4 telemetry | Added learning/reward/action telemetry, reward/action ablations, invalid-action rows, turnover/drawdown, policy NAV, state observations, source hashes, and D3 overlay. | `stom_rl/daily_rl_train.py`; `docs/stom_daily_ohlcv_rl_continuation_g003_training_telemetry_result_2026-06-14.md`; `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_14_g003_training_telemetry/` | Complete; focused tests passed. |
| G004 D5 gate | Re-ran/hardened fresh OOS walk-forward: 5 folds, 5/5 purge/embargo, no OOS retuning, no-trade/shuffle/D3 controls, 0/23/46bp sensitivity, MDD/turnover checks, fail-closed D4 evidence. | `stom_rl/daily_walk_forward.py`; `docs/stom_daily_ohlcv_rl_continuation_g004_walk_forward_gate_result_2026-06-14.md`; `webui/rl_runs/daily_ohlcv_walk_forward/walk_forward_2026_06_14_g004_fresh_oos_gate/` | Complete; gate remains `NO-GO`. |
| G005 dashboard/API | Updated Daily OHLCV backend and Svelte dashboard surfaces so D4/D5 evidence is read-only, false promotion flags are visible, D0/D1/D3 blockers propagate, and stale/optimistic artifacts fail closed. | `webui/daily_ohlcv_dashboard.py`; `webui/v2_src/src/lib/dailyOhlcvApi.ts`; `webui/v2_src/src/tabs/dailyOhlcv/DailyModelResultsCard.svelte`; `webui/rl_runs/daily_ohlcv_dashboard/dashboard_2026_06_14_g005_evidence_surfaces/` | Complete; API/tab tests, build, route/dist tests, browser audit, architect/QA approved. |
| G006 handoff | Documents what users can do, what remains blocked, graph interpretation, and failure-analysis loop. | This document; `webui/rl_runs/daily_ohlcv_final_handoff/rl_continuation_final_2026_06_14_g006/` | Complete; final aggregate checkpoint recorded in `.gjc/ultragoal/ledger.jsonl`. |

## Was an RL model created?

| Question | Answer |
|---|---|
| Was a deployable RL trading model created? | No. `model_build_allowed=false` remains locked. |
| Was an RL research policy/artifact generated? | Yes. D4 research-only portfolio artifacts and telemetry were generated for diagnostics. |
| Is RL research continuing? | Yes, but only inside the read-only research loop with preregistered hypotheses, controls, D3 baseline comparison, 23bp cost, fresh OOS, and explicit failure labels. |
| Can the dashboard be used to trade or submit orders? | No. The dashboard is an evidence viewer. It has no live/broker/order approval. |

## What users can do now

| Capability | How to use it | Current boundary |
|---|---|---|
| Inspect daily DB coverage and price-basis blocker | Open `/daily-ohlcv`, D0 section, or call `/api/daily-ohlcv/db-summary`. | Price basis remains `unknown`; do not treat returns as adjusted/decision-grade. |
| Inspect universe/quarantine evidence | Use D1 section or `/api/daily-ohlcv/universe/preview`. | Universe remains `WATCH_HEURISTIC_UNIVERSE`; official/manual KRX validation is still required. |
| Inspect D2 dataset readiness | Use D2 section or `/api/daily-ohlcv/dataset/latest`. | D0/D1 blockers propagate into dataset interpretation. |
| Compare D3 baselines | Use D3 section or `/api/daily-ohlcv/prediction/latest`. | Baselines are controls/comparators only; not trading signals. |
| Inspect D4 RL diagnostics | Use D4 model evidence card or `/api/daily-ohlcv/portfolio/latest`. | D4 is `RESEARCH_ONLY`; learning/reward/NAV/drawdown/action graphs diagnose failure modes. |
| Inspect D5 fresh OOS gate | Use D5 walk-forward card or `/api/daily-ohlcv/walk-forward/latest`. | D5 remains `NO-GO`; no model build or paper-forward unlock. |
| Use dashboard charts | Use `/api/daily-ohlcv/charts/*` through the Daily OHLCV page: decision cockpit, research diagnostics, flow, cost sensitivity, heatmap, equity overlay, run scatter, universe breakdown. | Charts explain evidence and blockers; they do not prove profitability. |
| Audit generated artifacts | Inspect `webui/rl_runs/daily_ohlcv_*` directories and source hashes. | Generated/session artifacts are evidence; do not mutate `_database`. |
| Plan next research iteration | Use the failure taxonomy below and start a new preregistered plan before changing reward/action/environment again. | No OOS retuning or cherry-picking after seeing gate results. |

## Page/table usage guide

| Page/table | Current status | What to read first | Use it for | Do not use it for |
|---|---|---|---|---|
| D0 Daily DB Analysis | `PRICE_BASIS_UNKNOWN` | Price-basis status, table/date coverage, quality flags, split-like windows | Confirm why all downstream return evidence is blocked. | Claim adjusted/raw/total-return correctness. |
| D1 Universe Management | `WATCH_HEURISTIC_UNIVERSE` | Include/exclude counts, quarantine reasons, official metadata status, preview rows | Review common-equity candidate universe and exclusion reasons. | Claim official KRX universe finality. |
| D2 Dataset Builder | Research preview | Manifest, split chronology, leakage status, invalid-bar status, target windows | Check dataset construction and no-lookahead evidence. | Promote training while D0/D1 blockers remain. |
| D3 Prediction / Top-K | `WATCH` | Frozen baseline metrics, no-trade/shuffle rows, D3 blockers, 23bp cost | Compare RL against no-trade/shuffle/rule/supervised baselines. | Treat baseline/ranker output as a tradable model. |
| D4 Daily Portfolio RL | `RESEARCH_ONLY` | Learning curve, reward breakdown, reward/action ablations, action distribution, invalid actions, turnover, drawdown, policy NAV, D3 overlay | Diagnose reward/action/environment behavior and failure modes. | Claim RL profitability, paper-forward, live readiness, or order instructions. |
| D5 Walk-forward / Gate | `NO-GO` | Fold table, purge/embargo, no-OOS-retuning flag, D4 state contract, cost sensitivity, failure reasons | Determine why the research policy fails/blocks under fresh OOS controls. | Retune on OOS or ignore no-trade/shuffle/D3 controls. |
| D6 Decision Cockpit / Visual Lab | Evidence viewer | Decision flags, evidence flow, glossary, cost/fold visualizations | Navigate D0-D9 evidence and see blocker propagation. | Treat visual curves as proof of returns. |
| D7 Research Diagnostics | Diagnostic/WATCH | Failure cards, symbol preview, feature/regime guidance | Decide what diagnostic artifact should be produced next. | Use diagnostics as alpha or buy/sell recommendations. |
| D8 Registry | `RESEARCH_ONLY_BLOCKED` | Candidate registry, hashes, drift, blockers, decision log | Audit candidate status and prove promotion is blocked. | Override D0-D5 gates. |
| D9 Paper-forward | `BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER` | Paper-selected row, realized-return/drawdown evidence, no-live/broker/order cards | Confirm paper/live/broker/order use is blocked. | Submit orders, connect brokers, or present paper-forward readiness. |

## RL graph interpretation

| Graph/table | Correct interpretation | Failure signal to look for |
|---|---|---|
| Learning curve | Did the research policy optimize its training objective under fixed preregistered settings? | Flat/noisy curve, reward spike without NAV improvement, instability by episode. |
| Reward breakdown | Which reward terms dominate after 23bp cost, drawdown, concentration, churn, and invalid-action penalties. | Reward hacking: higher reward while net NAV, drawdown, or controls worsen. |
| Reward/action ablations | Sensitivity to removing reward penalties or action constraints. | Apparent edge only exists when costs/penalties are removed. |
| Action distribution | Whether actions are diverse, masked correctly, and invalid actions are controlled. | Action collapse into one action, excessive no-trade without explanation, invalid action clusters. |
| Turnover/cost | How much policy behavior is eaten by 23bp round-trip cost. | Cost sensitivity failure at 23bp or 46bp. |
| Policy NAV | Research trajectory of generated artifacts. | NAV underperforms no-trade, shuffle, or frozen D3; do not treat as account equity. |
| Drawdown | Risk/failure diagnostic and D5 gate input. | Drawdown/concentration failure even if average return looks acceptable. |
| D3 overlay | Direct comparison to no-trade/shuffle/rule/supervised baselines. | RL underperforms frozen D3 or wins only on cherry-picked folds/costs. |
| Fold/cost heatmap and scatter | Stability across OOS folds and cost assumptions. | Fold instability, worst-fold dominance, 0bp-only edge, inconsistent signs. |

## Failure-analysis loop

| Failure category | Trigger | Required next action |
|---|---|---|
| `reward_hacking` | Reward improves while NAV, drawdown, cost, or controls worsen. | Revise reward terms in a new preregistered plan; do not relabel as success. |
| `action_collapse` | Policy degenerates into one action or ignores no-trade/hold/masks. | Inspect action masks, invalid reasons, no-trade behavior, and reward/action ablations. |
| `drawdown_or_concentration_failure` | Return evidence depends on unacceptable drawdown or concentrated exposure. | Tighten risk penalties/limits and rerun D4/D5 under the same controls. |
| `cost_sensitivity_failure` | Edge disappears under 23bp or 46bp. | Keep `NO-GO`; cost-free curves are diagnostic only. |
| `fold_instability` | Few folds drive the result or worst-fold risk dominates. | Add/refresh OOS folds only under preregistered no-retuning rules. |
| `D0_price_basis_blocker` | `price_basis=unknown` remains. | Resolve adjusted/raw/split/dividend basis before decision-grade claims. |
| `D1_universe_blocker` | Universe remains heuristic/WATCH. | Supply official/manual KRX common-equity validation artifact. |
| `D3_underperformance` | RL policy underperforms frozen D3. | Treat RL as failed diagnostic and revise hypothesis before rerun. |
| `artifact_or_provenance_drift` | Source hashes, run ids, manifests, or registry evidence drift unexpectedly. | Fail closed, regenerate evidence with hashes, and record the drift. |

## Remaining blockers

| Priority | Blocker | Exit criterion |
|---:|---|---|
| 1 | D0 price basis unknown | Independent adjusted/raw/split/dividend/corporate-action audit removes `PRICE_BASIS_UNKNOWN`. |
| 2 | D1 universe heuristic/WATCH | Official KRX metadata or manually reviewed common-equity universe artifact removes `WATCH_HEURISTIC_UNIVERSE`. |
| 3 | D3 baseline WATCH | Frozen D3 rerun under verified D0/D1 clears controls and becomes a stable comparator. |
| 4 | D4 RL underperformance | A new preregistered RL hypothesis beats no-trade, shuffle, and frozen D3 after 23bp cost without reward hacking. |
| 5 | D5 NO-GO | Fresh OOS walk-forward passes 5+ folds, purge/embargo, no OOS retuning, D3/no-trade/shuffle controls, MDD/turnover, and 0/23/46bp sensitivity. |
| 6 | D8/D9 blocked registry/paper-forward | Only after D0/D1/D3/D4/D5 clear; paper/live/broker/order still requires a separate explicit plan. |

## Recommended commands

| Purpose | Command |
|---|---|
| Check durable execution state | `gjc ultragoal status --json` |
| Open local dashboard | `py -3.11 webui/run.py`, then visit `/daily-ohlcv` |
| Verify RL/env/walk-forward core | `py -3.11 -m pytest tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_walk_forward.py -q` |
| Verify Daily OHLCV dashboard/API | `py -3.11 -m pytest tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q` |
| Verify dashboard build/dist | `cd webui/v2_src && npm run build`; then `py -3.11 -m pytest tests/test_v2_route.py tests/test_v2_dist_marker.py -q` |
| Inspect G005 dashboard evidence | `webui/rl_runs/daily_ohlcv_dashboard/dashboard_2026_06_14_g005_evidence_surfaces/` |
| Inspect G004 D5 gate evidence | `webui/rl_runs/daily_ohlcv_walk_forward/walk_forward_2026_06_14_g004_fresh_oos_gate/` |

## Final decision

Daily OHLCV RL research can continue, but only as research. The current system now has better reward/action/environment telemetry, stricter D5 fail-closed OOS gating, and a dashboard that shows why promotion is blocked. It still has no deployable RL model, no paper-forward approval, no live/broker/order readiness, and no profit claim.
