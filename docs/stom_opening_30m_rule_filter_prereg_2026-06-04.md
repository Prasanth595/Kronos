# STOM Opening 30m Rule Filter Preregistration - 2026-06-04

## Status

This branch is a `RULE` / meta-label risk-control experiment, not RL.
It is not live-ready, not broker-ready, and not a profit model.
The base policy is `ts_imb RULE baseline`.
Participant and supply-demand variables are proxy evidence only; they do not identify actual foreign, institution, retail, or big-money actors.
The default round-trip cost is `23bp`.

## Why this branch exists

The latest bounded opening 30m DQN/PPO feature revalidation remains `NO-GO_BASELINE` at `23bp` with split hash `cb46cac3fd20651f`.
Full OOS RL expansion remains deferred until a bounded branch beats no-trade, buy-and-hold, and the `ts_imb RULE baseline` with controls and ablations.

## Hypothesis

A deterministic TAKE/SKIP filter around the `ts_imb RULE baseline` can reduce low-quality opening entries using:

- participant proxy pressure
- orderbook imbalance and orderbook persistence
- overheat / upper-wick risk
- time-bucket behavior

The filter may return `TAKE` or `SKIP` only. Position sizing, exit management, live trading, broker execution, and RL policy training are out of scope.

## Labels

- `TAKE`: execute the base `ts_imb RULE baseline` decision in the bounded research backtest.
- `SKIP`: do not take the base decision.
- `skipped_opportunity_net_return_pct`: what the base rule would have earned if skipped; this prevents hiding skipped winners.

## Controls

Required controls:

- no-trade
- buy-and-hold same opening horizon
- base `ts_imb RULE baseline`
- shuffled labels
- time/session shuffle
- randomized features within split boundaries

## Feature ablations

Required ablations:

- no participant proxy pressure
- no orderbook imbalance
- no orderbook persistence
- no overheat/upper-wick
- no time bucket
- context-only
- tick-only
- shuffled participant context

## Decision labels

- `GO_RULE_FILTER`
- `NO-GO_BASELINE`
- `NO-GO_CONTROL`
- `NO-GO_ABLATION`
- `INCONCLUSIVE`

## Dashboard fields

The dashboard must expose read-only `rule_filter_*` tables, including lifecycle, splits, controls, ablations, equity curve, time buckets, failure reasons, opportunity cost, proxy availability, orderbook persistence, and context sample.

## Guardrails

- Do not call this RL.
- Do not tune on OOS.
- Do not claim profitability.
- Do not claim actual participant identity.
- Do not add broker/live-order paths.
