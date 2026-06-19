# STOM Opening 30M RL OOS Candidate Validation - 2026-06-04

## Verdict

`NO-GO_BASELINE` / candidate rejected by OOS baseline gate.

This is a bounded real tick/orderbook OOS smoke. It trained tiny DQN/PPO candidates and feature-ablation candidates, but the selected candidate failed no-trade and buy-and-hold after the 23bp cost assumption; the OOS-only `ts_imb RULE baseline` was lower than the candidate, but that is insufficient for promotion. Feature ablation also failed because masked variants outperformed the full feature set, indicating instability rather than a robust signal. It is not profitable and not live-ready.

## Command

```powershell
py -3.11 -m stom_rl.opening_30m_rl_realdata --db _database/stock_tick_back.db --run-id opening_30m_rl_oos_candidate_smoke --output-dir webui/rl_runs/opening_30m_rl_oos_validation --max-tables 10 --max-sessions-per-table 2 --time-start 090000 --time-end 093000 --candidate-algos dqn,ppo --create-split --tiny-train
```

## Artifacts

- Run directory: `webui/rl_runs/opening_30m_rl_oos_validation/opening_30m_rl_oos_candidate_smoke`
- Summary: `webui/rl_runs/opening_30m_rl_oos_validation/opening_30m_rl_oos_candidate_smoke/opening_30m_rl_workflow_summary.json`
- Candidate lifecycle: `webui/rl_runs/opening_30m_rl_oos_validation/opening_30m_rl_oos_candidate_smoke/opening_candidate_lifecycle.json`
- Split manifest: `webui/rl_runs/opening_30m_rl_oos_validation/opening_30m_rl_oos_candidate_smoke/opening_oos_split_manifest.json`
- Dataset artifact: `webui/rl_runs/opening_30m_rl_oos_validation/opening_30m_rl_oos_candidate_smoke/opening_oos_dataset_artifact.json`
- Evidence log: `.omo/evidence/oos-rl-task-10-smoke.txt`

## Sample Bounds

- DB: `_database/stock_tick_back.db`
- Access: read-only bounded smoke
- `max_tables`: 10
- `max_sessions_per_table`: 2
- Window: `090000` to `093000`
- Cost: `23bp`
- Split hash: `cb46cac3fd20651f`
- Dataset rows: `18` sampled symbol/sessions

## Candidate Results

| Candidate | Status | Model file | Eval log | Validation net % | OOS net % | OOS trades |
|---|---:|---:|---:|---:|---:|---:|
| `dqn_default_seed100` | `trained` | `True` | `True` | `-1.4638` | `-1.7512` | `8` |
| `ppo_default_seed100` | `trained` | `True` | `True` | `-1.4638` | `-2.4550` | `8` |

## Baseline Gate

| Baseline | Candidate OOS net % | Baseline net % | Passed |
|---|---:|---:|---:|
| `no_trade` | `-1.7512` | `0.0000` | `False` |
| `buy_and_hold` | `-1.7512` | `7.6032` | `False` |
| `ts_imb_rule` | `-1.7512` | `-2.5109` | `True` |

## Controls and Ablations

| Control | Net % | Source | Passed |
|---|---:|---|---:|
| `no_trade` | `0.0000` | `baseline_same_split` | `True` |
| `buy_and_hold` | `7.6032` | `baseline_same_split` | `True` |
| `ts_imb_rule` | `-2.5109` | `baseline_same_split` | `True` |
| `random_policy` | `-0.4899` | `policy_eval_oos` | `True` |
| `label_shuffle` | `-0.4899` | `label_shuffle_eval_oos` | `True` |
| `time_session_shuffle` | `-13.6313` | `time_session_shuffle_eval_oos` | `True` |

| Ablation | OOS net % | Comparison | Passed |
|---|---:|---|---:|
| `full` | `-2.4550` | `compared_to_full` | `True` |
| `no_participant` | `-2.1999` | `not_applicable_feature_absent` | `True` |
| `no_orderbook` | `-1.7512` | `compared_to_full` | `False` |
| `no_overheat` | `-0.2348` | `compared_to_full` | `False` |
| `minimal_price_volume` | `-3.0613` | `not_applicable_feature_absent` | `True` |

- Negative controls artifact: `passed`; baseline controls use `baseline_same_split`, and random/label-shuffle/time-session-shuffle controls are evaluated on the frozen OOS split with eval logs.
- Feature ablation artifact: `INCONCLUSIVE` / failed; `no_orderbook` and `no_overheat` outperformed the full feature set, so feature dependence is not stable. `no_participant` is explicitly marked not applicable because participant proxy columns are absent.
- Promotion gate: `NO-GO_BASELINE` with blockers `['failed_ablations', 'failed_baseline:no_trade', 'failed_baseline:buy_and_hold']`.

## Guardrails

- `RL EXPERIMENT`
- `not live-ready`
- `ts_imb RULE baseline`
- `23bp`
- no profitability claim
- no broker integration
- no live order path
- failed evidence remains visible as `NO-GO` or `INCONCLUSIVE`

## Next Decision

Do not promote the model. The next valid step is to improve hypotheses/features and rerun with the same OOS discipline; no `GO_CANDIDATE` label is allowed until PPO/DQN beats no-trade, buy-and-hold, and the `ts_imb RULE baseline` after 23bp with acceptable MDD and stable feature-ablation evidence.
