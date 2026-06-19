# STOM Opening 30m Rule Filter Realdata OOS Result — 2026-06-05 — NO-GO_CONTROL

## Guardrails

This is a `RULE` / meta-label filter result, not RL.
It is not live-ready, not broker-ready, and not a profit model.
The base policy remains the `ts_imb RULE baseline`.
Participant fields are proxy evidence only, not actual participant identity.
The cost assumption is `23bp` round trip.
This is a bounded real tick DB sample, not full-universe validation.

## Exact command

```powershell
py -3.11 -m stom_rl.opening_30m_rule_filter_cli --db _database/stock_tick_back.db --output-dir webui/rl_runs --run-id opening_30m_rule_filter_realdata_oos_2026_06_05 --create-split --max-tables 3 --max-sessions-per-table 5 --max-rows-per-session 1800 --min-rows-per-session 120 --time-start 090000 --time-end 093000 --cost-bps 23 --min-oos-take-trades 3
```

The command was executed inside a 900-second first-pass ceiling. It completed without timeout in `3.219` seconds.

## Actual bounded realdata result

| Field | Value |
|---|---:|
| Run | `opening_30m_rule_filter_realdata_oos_2026_06_05` |
| Verdict | `NO-GO_CONTROL` |
| split hash | `37664423068ddeca` |
| Cost | `23bp` |
| Adapter frame count | `11` |
| Bounded tables | `3` |
| Max sessions per table | `5` |
| OOS net return pct | `3.576084196458389` |
| OOS TAKE count | `2` |
| Minimum OOS TAKE count | `3` |
| Validation net return pct | `-1.6100862564692298` |
| Max drawdown pct | `1.2345662100456654` |
| Skipped opportunity cost pct | `0.0` |

## DB bounds and read-only evidence

| Field | Value |
|---|---:|
| DB path | `_database/stock_tick_back.db` |
| DB access | SQLite `mode=ro`, `query_only=true` |
| Time window | `090000` to `093000` |
| max_tables | `3` |
| max_sessions_per_table | `5` |
| max_rows_per_session | `1800` |
| min_rows_per_session | `120` |

Sampled symbols preserved leading zero codes: `000020`, `000040`, `000050`.

## Sampled sessions

| Symbol | Eligible sessions / row counts |
|---|---|
| `000020` | `20221212` / 446 |
| `000040` | `20230906` / 1525; `20240221` / 1292; `20240222` / 1529; `20250723` / 1340; `20250731` / 1660 |
| `000050` | `20220531` / 1309; `20250512` / 1770; `20251215` / 1646; `20260204` / 1463; `20260205` / 1545 |

## Baseline gate

| Baseline | Filter OOS net % | Baseline net % | Passed |
|---|---:|---:|---:|
| `no_trade` | `3.576084196458389` | `0.0` | `true` |
| `buy_and_hold` | `3.576084196458389` | `3.576084196458389` | `false` |
| `ts_imb_rule` | `3.576084196458389` | `3.576084196458389` | `false` |

Interpretation: the filter beat no-trade in this bounded sample, but it did not beat buy-and-hold or the `ts_imb RULE baseline`. That blocks promotion.

## Controls

| Control | Control net % | Passed |
|---|---:|---:|
| `no_trade` | `0.0` | `true` |
| `buy_and_hold` | `3.576084196458389` | `false` |
| `ts_imb_rule` | `3.576084196458389` | `false` |
| `shuffled_labels` | `4.810650406504054` | `false` |
| `time_session_shuffle` | `3.576084196458389` | `false` |
| `randomized_features` | `0.0` | `true` |

Negative/control evidence is not clean: shuffled labels outperformed the filter, and time-session shuffle matched the filter. The result remains `NO-GO_CONTROL`.

## Feature ablations

| Ablation | Ablated net % | Delta vs full OOS % | Passed |
|---|---:|---:|---:|
| `no_participant_pressure` | `0.0` | `3.576084196458389` | `true` |
| `no_orderbook_imbalance` | `3.576084196458389` | `0.0` | `false` |
| `no_orderbook_persistence` | `0.0` | `3.576084196458389` | `true` |
| `no_overheat_upper_wick` | `3.576084196458389` | `0.0` | `false` |
| `no_time_bucket` | `0.0` | `3.576084196458389` | `true` |
| `context_only` | `3.576084196458389` | `0.0` | `false` |
| `tick_only` | `0.0` | `3.576084196458389` | `true` |
| `shuffled_participant_context` | `3.576084196458389` | `0.0` | `false` |

Interpretation: participant pressure and orderbook persistence matter in this sample, but orderbook imbalance, overheat/upper-wick, context-only, and shuffled participant context do not prove stable incremental value. This blocks promotion.

## Blocking reasons

- `insufficient_oos_take_trades`
- `failed_baseline:buy_and_hold`
- `failed_baseline:ts_imb_rule`
- `failed_controls`
- `failed_ablations`

## Dashboard evidence

The dashboard API can discover this run as `opening_30m_rule_filter` and returns non-RL strategy context:

| Table | Rows |
|---|---:|
| `rule_filter_controls` | `6` |
| `rule_filter_ablations` | `8` |
| `rule_filter_proxy_availability` | `5` |
| `rule_filter_orderbook_persistence` | `10` |

Frontend source now uses the run strategy label for participant proxy evidence. For this run the label is `RULE FILTER EVIDENCE`, not an RL label.

## Artifact source

- `webui/rl_runs/opening_30m_rule_filter_realdata_oos_2026_06_05/opening_rule_filter_summary.json`
- `webui/rl_runs/opening_30m_rule_filter_realdata_oos_2026_06_05/opening_rule_filter_lifecycle.json`
- `webui/rl_runs/opening_30m_rule_filter_realdata_oos_2026_06_05/opening_rule_filter_controls.json`
- `webui/rl_runs/opening_30m_rule_filter_realdata_oos_2026_06_05/opening_rule_filter_ablations.json`
- `webui/rl_runs/opening_30m_rule_filter_realdata_oos_2026_06_05/opening_rule_filter_gate.json`
- `webui/rl_runs/opening_30m_rule_filter_realdata_oos_2026_06_05/opening_rule_filter_split_manifest.json`
- `webui/rl_runs/opening_30m_rule_filter_realdata_oos_2026_06_05/realdata_adapter/realdata_adapter_summary.json`

## Next decision

Do not scale RL from this result. The bounded realdata rule-filter produced a positive OOS net in this small sample, but it failed the promotion gate because it did not beat buy-and-hold or the `ts_imb RULE baseline`, failed controls, failed feature ablations, and had only 2 OOS TAKE trades against the required 3.

The next safe step is blocker analysis, not PPO/DQN expansion.