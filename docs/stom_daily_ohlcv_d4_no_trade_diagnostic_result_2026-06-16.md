# Daily OHLCV D4 No-Trade Opportunity Diagnostic Result — 2026-06-16

Date: 2026-06-16 KST  
Status: `NO-GO_RESEARCH_ONLY`  
Experiment type: `RL experiment` / post-policy diagnostic  
Default cost: 23bp round trip  
Primary artifact: `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_no_trade_diag_001/no_trade_diagnostic_research_summary.json`

## Guardrail snapshot

| Surface | State | Meaning |
|---|---|---|
| Live/broker/orders | `blocked` | No live trading, broker connection, order routing, or paper-forward promotion. |
| Profit/model claim | `blocked` | This result is diagnostic evidence only, not a deployable model or profit claim. |
| D4 policy | `RESEARCH_ONLY` | Tabular-Q D4 remains a failure-analysis lane. |
| D5 gate | `NO-GO` | Model build and paper-forward remain blocked. |
| Future labels | post-policy diagnostic only | `future_return_1d` is not exposed in training state/action selection; it is used after the policy decision to explain no-trade behavior. |

## Research question

The prior D4 reward/action/environment stress matrix showed that all tested tabular-Q policies collapsed to all-hold/no-trade. This run asks:

> Did the policy skip many positive top-candidate opportunities, or did it mostly avoid negative candidates?

This question is diagnostic only. It does not change the trading policy, does not retune on OOS, and does not unlock model build.

## What changed

| Area | Change |
|---|---|
| D4 artifact contract | Added `no_trade_opportunity_diagnostics.csv` and `no_trade_opportunity_summary.json` to every portfolio run. |
| Training leakage control | Kept `future_label_used_for_training_state=false`; future labels are only emitted in a post-policy diagnostic artifact. |
| Manifest lineage | Added row counts and artifact hashes for the new diagnostic outputs. |
| Test coverage | Added focused assertions for diagnostic-only future-label usage and generated artifacts. |

## Executed command

```powershell
py -3.11 -m stom_rl.daily_scenario_batch --plan artifacts/scenario_batch_d4_action_reward_001_plan.json --batch-id scenario_batch_no_trade_diag_001 --overwrite
```

## Verification command

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_scenario_runner.py tests/test_stom_rl_daily_portfolio_env.py -q
```

Observed result:

```text
18 passed in 1.02s
```

## Scenario result table

| Scenario | Gate status | Val+Test action distribution | No-trade rows | Missed positive top-candidate rows | Avoided negative top-candidate rows | Diagnostic artifact |
|---|---|---:|---:|---:|---:|---|
| `control_top10_pos3_ep3` | `NO-GO` | hold 37 | 37 | 17 | 20 | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_no_trade_diag_001__control_top10_pos3_ep3/no_trade_opportunity_summary.json` |
| `single_slot_top5_pos1` | `NO-GO` | hold 37 | 37 | 16 | 21 | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_no_trade_diag_001__single_slot_top5_pos1/no_trade_opportunity_summary.json` |
| `wider_candidates_top20_pos5` | `NO-GO` | hold 37 | 37 | 17 | 20 | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_no_trade_diag_001__wider_candidates_top20_pos5/no_trade_opportunity_summary.json` |
| `longer_training_top10_ep12` | `NO-GO` | hold 37 | 37 | 17 | 20 | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_no_trade_diag_001__longer_training_top10_ep12/no_trade_opportunity_summary.json` |

## Interpretation

The D4 tabular-Q policy still selected only `hold` in val+test across all four stress scenarios. The new diagnostic shows a mixed no-trade profile:

- There were missed positive top-candidate days.
- There were also avoided negative top-candidate days.
- Therefore, a simple hindsight penalty or forced-buy rule would be unsafe and could create leakage or overfitting.

The next research must improve decision-time state/action learning, not claim success from hindsight labels.

## Data governance record

| Governance item | Current record |
|---|---|
| Durable report | This file under `docs/` is the human-readable dated result. |
| Generated summary | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_no_trade_diag_001/no_trade_diagnostic_research_summary.json` |
| Batch manifest | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_no_trade_diag_001/scenario_batch_manifest.json` |
| Source code | `stom_rl/daily_rl_train.py` |
| Tests | `tests/test_stom_rl_daily_rl_gate.py`, `tests/test_stom_rl_daily_scenario_runner.py`, `tests/test_stom_rl_daily_portfolio_env.py` |
| Cost assumption | 23bp round trip, recorded in artifacts. |
| Mutability | Generated artifacts are evidence; do not edit them to change verdicts. Create a new dated run/report instead. |
| Provenance | Portfolio manifests include source hashes and generated artifact hashes. |
| Safety flags | `model_build_allowed=false`, `go_summary_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false`. |

## Final verdict

`NO-GO_RESEARCH_ONLY`.

The result explains the current all-hold failure mode better, but it does not make D4 usable. The next recommended research is **D4 action-induction v2** with causal, decision-time state features and explicit exploration/action-prior tests.
