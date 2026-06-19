# STOM Opening 30m Rule Filter Wide Failure Decision ? 2026-06-05

## Decision

```text
STOP_RL_EXPANSION + SIMPLIFY_FEATURES + PROXY_AUDIT_REQUIRED
```

This decision is based on the wider bounded realdata OOS run:

| Field | Value |
|---|---:|
| Run | `opening_30m_rule_filter_realdata_oos_wide_2026_06_05` |
| Verdict | `NO-GO_CONTROL` |
| Split hash | `bc4384540145ce12` |
| Cost | `23.0bp` |
| Frame count | `39` |
| Validation net return pct | `6.034562888623697` |
| OOS net return pct | `-0.5448716160851159` |
| OOS TAKE count | `6` |
| Minimum OOS TAKE count | `10` |
| Max drawdown pct | `8.133029466690743` |
| Max allowed drawdown pct | `5.0` |

## Guardrails

This is `RULE` / meta-label research evidence, not RL success. `ts_imb` remains the `ts_imb RULE baseline`, never RL. Participant/proxy fields are proxy evidence only, not actual participant identity. The dashboard is a read-only evidence viewer. This is not live-ready, not broker-ready, and not a profit model.

## Blocking reasons

- `insufficient_oos_take_trades`
- `failed_risk:max_drawdown`
- `failed_baseline:no_trade`
- `failed_baseline:buy_and_hold`
- `failed_baseline:ts_imb_rule`
- `failed_controls`
- `failed_ablations`

## Failure interpretation

The wider run is a stronger negative result than the prior bounded run. Validation was positive at `6.034562888623697%`, but OOS was negative at `-0.5448716160851159%`. OOS TAKE count was `6`, below the preregistered minimum `10`. Drawdown exceeded the gate. The filter failed no-trade, buy-and-hold, and `ts_imb RULE baseline` checks.

All eight ablations matched the full OOS return and failed. This is interpreted as attribution collapse / threshold-insensitivity / insufficient OOS action diversity, not as proof that any feature works.

## Decision matrix

| Decision | Meaning | Next action |
|---|---|---|
| `STOP_RL_EXPANSION` | Current evidence blocks PPO/DQN/opening 30m RL expansion. | Keep RL work paused until future RULE/meta-label gates pass. |
| `SIMPLIFY_FEATURES` | Current feature stack is not attributable. | Plan a minimal preregistered RULE/meta-label experiment. |
| `PROXY_AUDIT_REQUIRED` | Participant/proxy context is not proven useful. | Audit proxy definitions and shuffled proxy behavior before adding features. |

## Next recommended command

```text
$ulw-plan Create a simplified RULE/meta-label experiment plan that removes unproven context features, audits buy_and_hold vs ts_imb baseline semantics, and keeps PPO/DQN blocked until gates pass.
```


Guardrail marker: cost assumption is 23bp.
