# STOM Opening 30M RL Realdata Validation - 2026-06-04

## Verdict

`INCONCLUSIVE`

This is an `RL EXPERIMENT`, not live-ready, not broker-ready, and not a profit model.
The run used the `ts_imb RULE baseline` guardrail and 23bp cost assumption.

## Exact command

```powershell
py -3.11 -m stom_rl.opening_30m_rl_realdata --db _database/stock_tick_back.db --run-id opening_30m_rl_realdata_smoke --output-dir webui/rl_runs/opening_30m_rl_realdata_smoke --max-tables 5 --max-sessions-per-table 1 --time-start 090000 --time-end 093000
```

Missing DB negative check:

```powershell
py -3.11 -m stom_rl.opening_30m_rl_realdata --db _database/missing.db --run-id missing_db --output-dir .omo/evidence/missing_db --max-tables 1
```

## Sample bounds

| Field | Value |
|---|---:|
| max_tables | 5 |
| max_sessions_per_table | 1 |
| max_rows_per_session | 1800 |
| min_rows_per_session | 4 |
| time_start | `090000` |
| time_end | `093000` |
| cost_bps | 23.0 |

## Sampled tables/sessions

| Symbol | Session | Rows |
|---|---|---:|
| `000020` | `20221212` | 446 |
| `000040` | `20230906` | 1525 |
| `000050` | `20220531` | 1309 |
| `000060` | `20221108` | 625 |
| `000070` | `20250602` | 1296 |

Leading-zero symbols were preserved as strings.

## Gate status

| Gate | Status |
|---|---|
| OOS split | missing |
| negative/shuffle controls | missing |
| baseline superiority after 23bp | not proven |
| participant-pressure ablation | failed / missing |
| orderbook-persistence ablation | failed / missing |
| overheat-penalty ablation | failed / missing |
| model_status | `no_model_trained` |
| training_status | `available_not_requested` |

Blocking reasons:

- `missing_oos_split`
- `missing_negative_controls`
- `failed_baseline:no_trade`
- `failed_baseline:buy_and_hold`
- `failed_baseline:ts_imb_rule`
- `failed_ablation:orderbook_persistence`
- `failed_ablation:overheat_penalty`
- `failed_ablation:participant_pressure`

## Dashboard evidence

- Run summary: `webui/rl_runs/opening_30m_rl_realdata_smoke/opening_30m_rl_workflow_summary.json`
- Adapter summary: `webui/rl_runs/opening_30m_rl_realdata_smoke/realdata_adapter/realdata_adapter_summary.json`
- Validation gate: `webui/rl_runs/opening_30m_rl_realdata_smoke/realdata_validation_gate.json`
- Dashboard helper evidence: `.omo/evidence/realdata-task-8-real-run-dashboard.txt`

## Next decision

Do not tune on this smoke result. The next safe step is Task 10 final verification,
then a separate preregistered OOS/control/ablation run if the user wants a larger real-data validation.
