# STOM Opening 30m Rule Filter Wide Realdata OOS Result ? 2026-06-05 ? NO-GO_CONTROL

## Guardrails

This is a `RULE` / meta-label filter result, not RL. It is not live-ready, not broker-ready, and not a profit model. The base policy remains the `ts_imb RULE baseline`. Participant fields are proxy evidence only, not actual participant identity. The cost assumption is `23bp` round trip. This is a wider bounded real tick DB sample, not full-universe validation.

## Preregistration

Preregistration document was written before execution:

```text
docs/stom_opening_30m_rule_filter_wide_prereg_2026-06-05.md
```

Prior diagnostic split `37664423068ddeca` was not used for tuning.

## Exact command

```powershell
py -3.11 -m stom_rl.opening_30m_rule_filter_cli --db _database/stock_tick_back.db --output-dir webui/rl_runs --run-id opening_30m_rule_filter_realdata_oos_wide_2026_06_05 --create-split --max-tables 10 --max-sessions-per-table 5 --max-rows-per-session 1800 --min-rows-per-session 120 --time-start 090000 --time-end 093000 --cost-bps 23 --min-oos-take-trades 10
```

The command was executed inside a 1800-second ceiling. It completed without timeout in `5.313` seconds.

## Actual wider bounded realdata result

| Field | Value |
|---|---:|
| Run | `opening_30m_rule_filter_realdata_oos_wide_2026_06_05` |
| Verdict | `NO-GO_CONTROL` |
| Split hash | `bc4384540145ce12` |
| Cost | `23.0bp` |
| Adapter frame count | `39` |
| Bounded tables | `10` |
| Max sessions per table | `5` |
| OOS net return pct | `-0.5448716160851159` |
| OOS TAKE count | `6` |
| Minimum OOS TAKE count | `10` |
| Validation net return pct | `6.034562888623697` |
| Max drawdown pct | `8.133029466690743` |
| Max allowed drawdown pct | `5.0` |
| Skipped opportunity cost pct | `0.0` |

## DB bounds and read-only evidence

| Field | Value |
|---|---:|
| DB path | `_database/stock_tick_back.db` |
| DB access | SQLite `mode=ro`, `query_only=True` |
| Time window | `090000` to `093000` |
| max_tables | `10` |
| max_sessions_per_table | `5` |
| max_rows_per_session | `1800` |
| min_rows_per_session | `120` |

## Split ranges

| Split | Start | End | Sessions |
|---|---:|---:|---:|
| `train` | `20220325` | `20231114` | `23` |
| `validation` | `20231117` | `20241227` | `8` |
| `oos` | `20250512` | `20260205` | `8` |

## Blocking reasons

- `insufficient_oos_take_trades`
- `failed_risk:max_drawdown`
- `failed_baseline:no_trade`
- `failed_baseline:buy_and_hold`
- `failed_baseline:ts_imb_rule`
- `failed_controls`
- `failed_ablations`

## Baseline gate

| Baseline | Filter OOS net % | Baseline net % | Passed |
|---|---:|---:|---:|
| `no_trade` | `-0.5448716160851159` | `0.0` | `False` |
| `buy_and_hold` | `-0.5448716160851159` | `-0.5448716160851159` | `False` |
| `ts_imb_rule` | `-0.5448716160851159` | `-0.5448716160851159` | `False` |

Benchmark note: in this artifact, `buy_and_hold` and `ts_imb_rule` are equal to the filter result. This is reported as equality/failure, not as independent outperformance.

## Controls

| Control | Control net % | Passed |
|---|---:|---:|
| `no_trade` | `0.0` | `False` |
| `buy_and_hold` | `-0.5448716160851159` | `False` |
| `ts_imb_rule` | `-0.5448716160851159` | `False` |
| `shuffled_labels` | `-3.3356245549756265` | `True` |
| `time_session_shuffle` | `-0.5448716160851159` | `False` |
| `randomized_features` | `0.0` | `False` |

## Ablations

| Feature set | Full % | Ablated % | Delta % | Passed |
|---|---:|---:|---:|---:|
| `no_participant_pressure` | `-0.5448716160851159` | `-0.5448716160851159` | `0.0` | `False` |
| `no_orderbook_imbalance` | `-0.5448716160851159` | `-0.5448716160851159` | `0.0` | `False` |
| `no_orderbook_persistence` | `-0.5448716160851159` | `-0.5448716160851159` | `0.0` | `False` |
| `no_overheat_upper_wick` | `-0.5448716160851159` | `-0.5448716160851159` | `0.0` | `False` |
| `no_time_bucket` | `-0.5448716160851159` | `-0.5448716160851159` | `0.0` | `False` |
| `context_only` | `-0.5448716160851159` | `-0.5448716160851159` | `0.0` | `False` |
| `tick_only` | `-0.5448716160851159` | `-0.5448716160851159` | `0.0` | `False` |
| `shuffled_participant_context` | `-0.5448716160851159` | `-0.5448716160851159` | `0.0` | `False` |

## Dashboard availability

| Table | Rows | Source |
|---|---:|---|
| `rule_filter_controls` | `6` | `opening_rule_filter_lifecycle.json` |
| `rule_filter_ablations` | `8` | `opening_rule_filter_lifecycle.json` |
| `rule_filter_proxy_availability` | `5` | `opening_rule_filter_lifecycle.json` |
| `rule_filter_orderbook_persistence` | `10` | `opening_rule_filter_lifecycle.json` |

## Interpretation

The wider bounded realdata experiment is a stronger negative result than the prior tiny sample. It increased the frame count and generated dashboard-visible evidence, but the model/filter remains `NO-GO_CONTROL` because OOS return is negative, OOS TAKE count is below the preregistered minimum, drawdown exceeds the gate, baselines are not beaten, and controls/ablations fail.

Do not proceed to PPO/DQN expansion from this result. The next work should analyze this wider failure and decide whether to simplify features, revise proxy definitions, or stop the RL expansion path until the RULE/meta-label track improves.
