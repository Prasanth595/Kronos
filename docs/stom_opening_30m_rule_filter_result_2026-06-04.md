# STOM Opening 30m Rule Filter Result - 2026-06-04

## Guardrails

This is a `RULE` / meta-label filter result, not RL.
It is not live-ready, not broker-ready, and not a profit model.
The base policy remains `ts_imb RULE baseline`.
Participant fields are proxy evidence only, not actual participant identity.
The cost assumption is `23bp` round trip.

## Actual bounded smoke result

| Field | Value |
|---|---|
| Run | `opening_30m_rule_filter_smoke` |
| Verdict | `NO-GO_CONTROL` |
| Split hash | `225356e7f771784c` |
| Cost | `23.0bp` |
| OOS net return pct | `-3.7771389861260922` |
| OOS TAKE count | `3` |
| Skipped opportunity cost pct | `0.0` |

## Dashboard table counts

| Table | Rows |
|---|---:|
| `rule_filter_controls` | 6 |
| `rule_filter_ablations` | 8 |
| `rule_filter_equity_curve` | 2 |
| `rule_filter_time_buckets` | 1 |
| `rule_filter_opportunity_cost` | 2 |


## Controls and ablations

- Control rows: `6`
- Ablation rows: `8`
- Blocking reasons: `['failed_baseline:no_trade', 'failed_baseline:buy_and_hold', 'failed_baseline:ts_imb_rule', 'failed_controls', 'failed_ablations']`

## Interpretation

The bounded smoke artifact is now dashboard-visible and falsifiable. If the verdict is not `GO_RULE_FILTER`, full OOS RL expansion remains deferred. If future work attempts RL expansion, it must first update this result with a bounded gate that beats no-trade, buy-and-hold, and the `ts_imb RULE baseline` after `23bp`, with controls and feature ablations passing.

## Artifact source

- `webui/rl_runs/opening_30m_rule_filter_smoke/opening_rule_filter_lifecycle.json`
- `webui/rl_runs/opening_30m_rule_filter_smoke/opening_rule_filter_gate.json`
- `webui/rl_runs/opening_30m_rule_filter_smoke/opening_rule_filter_controls.json`
- `webui/rl_runs/opening_30m_rule_filter_smoke/opening_rule_filter_ablations.json`
