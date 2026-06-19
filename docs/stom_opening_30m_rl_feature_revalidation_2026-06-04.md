# Opening 30M RL Feature Revalidation — preregistered dashboard/feature update (2026-06-04)

## Status

This track is an `RL EXPERIMENT`, not live-ready, not broker-ready, and not a profit model.
The `ts_imb RULE baseline` remains a RULE baseline and must not be relabeled as RL.
The default cost assumption is `23bp` round trip.

Current actual model verdict before the new bounded revalidation run remains `NO-GO_BASELINE` from the existing 2026-06-04 OOS candidate validation. The feature revalidation run below is preregistered and must publish its actual verdict after Task12; do not promote a model before that evidence exists.

## Hypothesis under test

Add causal opening context features to the opening 30m DQN/PPO candidate path:

| Feature group | Examples | Missing policy |
|---|---|---|
| `price_volume` | returns, volume, time fraction | required base observation |
| `participant_pressure` | participant proxy pressure, transaction value surge, signed amount persistence | proxy evidence only |
| `orderbook_imbalance` | bid/ask depth imbalance, microprice pressure, spread penalty | fail closed or mark unavailable |
| `orderbook_persistence` | bid depth persistence, OFI, signed flow persistence | fail closed or mark unavailable |
| `overheat_upper_wick` | overheat penalty, upper-wick ratio, pullback reacceleration | penalty/evidence only |
| `optional_investor_flow` | foreign/institution/program net buy if present | missing/None; never zero-filled as truth |

Participant variables are `proxy evidence`; they do not identify actual foreign, institution, retail, or big-money actors.

## Canonical ablations

Required IDs:

- `full_context`
- `no_participant_pressure`
- `no_orderbook_imbalance`
- `no_orderbook_persistence`
- `no_overheat_upper_wick`
- `minimal_price_volume`
- `shuffled_participant_context`
- `ts_imb_rule_baseline`

Legacy aliases such as `full`, `no_participant`, `no_orderbook`, and `no_overheat` are accepted only as compatibility input and are normalized before dashboard/gate interpretation.

## Revalidation command

```powershell
py -3.11 -m stom_rl.opening_30m_rl_realdata --db _database/stock_tick_back.db --run-id opening_30m_rl_feature_revalidation_smoke --output-dir webui/rl_runs/opening_30m_rl_feature_revalidation --max-tables 10 --max-sessions-per-table 2 --time-start 090000 --time-end 093000 --candidate-algos dqn,ppo --create-split --tiny-train
```

Expected artifact root:

```text
webui/rl_runs/opening_30m_rl_feature_revalidation/opening_30m_rl_feature_revalidation_smoke
```

## Dashboard tables to inspect

| Table alias | Purpose |
|---|---|
| `candidate_lifecycle` | DQN/PPO candidate rows and status |
| `candidate_splits` | frozen train/validation/OOS sessions and split hash |
| `candidate_controls` | no-trade, buy-and-hold, `ts_imb RULE baseline`, random/shuffle controls |
| `candidate_ablations` | canonical feature-ablation rows |
| `candidate_equity_curve` | cumulative equity curve evidence, not a profit claim |
| `candidate_time_buckets` | time-bucket trade result rows |
| `candidate_failure_reasons` | explicit `NO-GO` blockers |
| `proxy_availability` | participant proxy availability and missing proxy columns |
| `orderbook_persistence` | orderbook imbalance/persistence/overheat components |
| `context_feature_sample` | RL observation context feature sample |

## Promotion rule

A candidate can only be promoted if it beats no-trade, buy-and-hold, and the `ts_imb RULE baseline` after `23bp`, passes negative controls, and remains stable under feature ablation. Otherwise the dashboard must show `NO-GO`, `NO-GO_BASELINE`, `NO-GO_CONTROL`, `NO-GO_ABLATION`, or `INCONCLUSIVE` visibly.

## Current interpretation

The dashboard and feature path are now designed to falsify the RL candidate more clearly. This is not evidence that DQN/PPO is profitable.

## Actual bounded run result

The preregistered bounded real-data smoke run completed and the actual verdict is still `NO-GO_BASELINE`.

| Field | Value |
|---|---|
| Run | `opening_30m_rl_feature_revalidation_smoke` |
| Artifact root | `webui/rl_runs/opening_30m_rl_feature_revalidation/opening_30m_rl_feature_revalidation_smoke` |
| Split hash | `cb46cac3fd20651f` |
| Candidate count | `2` |
| Cost | `23bp` round trip |
| Candidate verdict | `NO-GO_BASELINE` |
| Baseline label | `ts_imb RULE baseline` |

Dashboard API evidence parsed these table row counts:

| Table alias | Rows |
|---|---:|
| `candidate_lifecycle` | 2 |
| `candidate_splits` | 18 |
| `candidate_controls` | 6 |
| `candidate_ablations` | 7 |
| `candidate_equity_curve` | 2 |
| `candidate_time_buckets` | 2 |
| `candidate_failure_reasons` | 2 |
| `proxy_availability` | 10 |
| `orderbook_persistence` | 10 |
| `context_feature_sample` | 8 |

Interpretation: the new context features, ablations, and dashboard tables are now visible and test-covered, but the model did not beat the required baseline gates in this bounded OOS smoke. It remains an `RL EXPERIMENT`, not live-ready and not a profit model.

Known verification notes:

- Targeted pytest passed for participant proxy, orderbook persistence, market participant studies, RL context, dashboard APIs, candidate training, ablation, gate, and real-data OOS CLI (`40 passed` after the context-ablation fix).
- The final run artifacts now prove `no_participant_pressure` zeroes appended context features and `shuffled_participant_context` records shuffled participant context metadata.
- `npm --prefix webui/v2_src run build` passed with 0 errors and 4 pre-existing Svelte/CSS warnings in `DocsTab.svelte` and `ForecastWorkbenchTab.svelte`.
- `cmd /c "git diff --check"` passed after normalizing generated dashboard HTML line endings; only Git CRLF conversion warnings remain.
