# STOM Opening 30m Simplified RULE/meta-label Preregistration — 2026-06-05

## Purpose

This preregisters a future simplified opening 30m `RULE`/meta-label validation. It is not an executed experiment. It is not RL, not live-ready, not broker-ready, and not a profit model.

## Prior diagnostic evidence

| Field | Value |
|---|---:|
| Prior bounded split | `37664423068ddeca` |
| Prior wide split | `bc4384540145ce12` |
| Prior wide verdict | `NO-GO_CONTROL` |
| Prior decision | `STOP_RL_EXPANSION + SIMPLIFY_FEATURES + PROXY_AUDIT_REQUIRED` |
| Cost assumption | `23bp` |

Both prior splits are diagnostic-only. They must not be used to tune thresholds, features, labels, actions, proxy definitions, or policy rules.

## Simplified feature set

The future simplified run must use:

```text
--feature-set minimal_ts_imb
```

`minimal_ts_imb` uses the base `ts_imb RULE baseline` action path and excludes unproven context features from the decision score:

- participant pressure
- `proxy_*`
- orderbook imbalance
- orderbook persistence
- overheat
- upper-wick / wick
- broad context-only path

## Future command shape

```powershell
py -3.11 -m stom_rl.opening_30m_rule_filter_cli --db _database/stock_tick_back.db --output-dir webui/rl_runs --run-id opening_30m_rule_filter_simplified_oos_2026_06_05 --create-split --feature-set minimal_ts_imb --max-tables 10 --max-sessions-per-table 5 --max-rows-per-session 1800 --min-rows-per-session 120 --time-start 090000 --time-end 093000 --cost-bps 23 --min-oos-take-trades 10
```

## Gates

`GO_RULE_FILTER` is allowed only if all pass:

- OOS TAKE count >= `10`.
- OOS net return beats no-trade, independent buy-and-hold, and `ts_imb RULE baseline` after `23bp`.
- Validation net return is non-negative.
- Max drawdown <= `5.0%`.
- Negative controls pass.
- No OOS tuning or post-OOS rerun with changed bounds.

## Baseline semantics

Future result docs must distinguish artifact controls from the independent opening baseline comparator. Current artifact equality between `buy_and_hold` and `ts_imb_rule` must not be reported as independent outperformance.

## RL gate

PPO/DQN and opening 30m RL expansion remain blocked until a future simplified RULE/meta-label run passes the preregistered gates.
