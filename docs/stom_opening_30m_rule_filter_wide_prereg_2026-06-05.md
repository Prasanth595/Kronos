# STOM Opening 30m Rule Filter Wide OOS Preregistration ? 2026-06-05

## Purpose

Run a wider bounded realdata OOS validation for the opening 30m `RULE`/meta-label filter. This is research evidence only. It is not a live-trading approval, not broker readiness, not a profit guarantee, and not a reinforcement-learning success claim.

## Prior diagnostic evidence

| Field | Value |
|---|---:|
| Prior run | `opening_30m_rule_filter_realdata_oos_2026_06_05` |
| Prior verdict | `NO-GO_CONTROL` |
| Frozen diagnostic split | `37664423068ddeca` |
| Prior cost | `23bp` |
| Prior OOS TAKE count | `2` |
| Prior minimum OOS TAKE count | `3` |

The prior split `37664423068ddeca` is diagnostic-only and must not be used to tune thresholds, features, labels, actions, or policy rules.

## Primary run

| Field | Value |
|---|---:|
| Selected run id | `opening_30m_rule_filter_realdata_oos_wide_2026_06_05` |
| max_tables | `10` |
| max_sessions_per_table | `5` |
| max_rows_per_session | `1800` |
| min_rows_per_session | `120` |
| time window | `090000-093000` |
| cost | `23bp` |
| min_oos_take_trades | `10` |
| timeout ceiling | `1800s` |

```powershell
py -3.11 -m stom_rl.opening_30m_rule_filter_cli --db _database/stock_tick_back.db --output-dir webui/rl_runs --run-id opening_30m_rule_filter_realdata_oos_wide_2026_06_05 --create-split --max-tables 10 --max-sessions-per-table 5 --max-rows-per-session 1800 --min-rows-per-session 120 --time-start 090000 --time-end 093000 --cost-bps 23 --min-oos-take-trades 10
```

## Fallback policy

Fallback is allowed only before OOS interpretation and only if primary preflight/runtime/artifact production fails. A bad primary verdict is not a fallback trigger.

Fallback run id: `opening_30m_rule_filter_realdata_oos_wide_fallback_2026_06_05`

```powershell
py -3.11 -m stom_rl.opening_30m_rule_filter_cli --db _database/stock_tick_back.db --output-dir webui/rl_runs --run-id opening_30m_rule_filter_realdata_oos_wide_fallback_2026_06_05 --create-split --max-tables 5 --max-sessions-per-table 5 --max-rows-per-session 1800 --min-rows-per-session 120 --time-start 090000 --time-end 093000 --cost-bps 23 --min-oos-take-trades 10
```

Fallback uses `--max-tables 5` and must be labeled separately.

## Promotion criteria

`GO_RULE_FILTER` is allowed only if all are true:

- OOS TAKE count >= `10`.
- Filter beats `no_trade`, `buy_and_hold`, and `ts_imb RULE baseline` after `23bp`.
- Validation net return is non-negative.
- Negative controls pass: `shuffled_labels`, `time_session_shuffle`, `randomized_features`.
- Ablations pass or remain inconclusive with no promotion.
- Max drawdown remains within the existing gate limit.
- No OOS tuning or post-OOS rerun with changed bounds.

## Guardrails

- `ts_imb` is a RULE baseline, never RL.
- Participant/supply-demand fields are proxy evidence only, not actual participant identity.
- Dashboard is read-only evidence viewer.
- PPO/DQN remains blocked unless this RULE/meta-label track passes baseline/control/ablation gates.
