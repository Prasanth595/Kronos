# STOM Opening 30m Rule Filter Simplified Result - 2026-06-05

## 결론

- Verdict: `NO-GO_CONTROL`
- Manual decision: `NO-GO_CONTROL`
- Run id: `opening_30m_rule_filter_simplified_oos_2026_06_05`
- Feature set: `minimal_ts_imb`
- Split hash: `bc4384540145ce12`
- Cost: `23bp`

이 실행은 강화학습 성공 결과가 아니다. `minimal_ts_imb`는 `ts_imb RULE baseline` 경로를 단순화해 검증한 RULE/meta-label evidence run이다. 결과는 OOS 손실과 control 실패 때문에 `NO-GO_CONTROL`이다.

## Exact command

```powershell
py -3.11 -m stom_rl.opening_30m_rule_filter_cli --db _database/stock_tick_back.db --output-dir webui/rl_runs --run-id opening_30m_rule_filter_simplified_oos_2026_06_05 --create-split --feature-set minimal_ts_imb --max-tables 10 --max-sessions-per-table 5 --max-rows-per-session 1800 --min-rows-per-session 120 --time-start 090000 --time-end 093000 --cost-bps 23 --min-oos-take-trades 10
```

## Bounds

- max_tables: 10
- max_sessions_per_table: 5
- max_rows_per_session: 1800
- min_rows_per_session: 120
- time_start: 090000
- time_end: 093000
- DB read-only evidence: sqlite `mode=ro`, `query_only=true`
- Frame count: 39

## Metrics

| Metric | Value |
|---|---:|
| validation net return | 6.034562888623697% |
| OOS net return | -0.5448716160851159% |
| OOS TAKE count | 6 / 10 |
| max drawdown | 8.133029466690743% |
| max allowed drawdown | 5.0% |
| skipped opportunity cost | 0.0% |

## Blocking reasons

- `insufficient_oos_take_trades`
- `failed_risk:max_drawdown`
- `failed_baseline:no_trade`
- `failed_baseline:buy_and_hold`
- `failed_baseline:ts_imb_rule`
- `failed_controls`
- `failed_ablations`

## Baseline comparison

| Baseline | Filter OOS | Baseline OOS | Passed |
|---|---:|---:|---|
| no_trade | -0.5448716160851159% | 0.0% | False |
| buy_and_hold | -0.5448716160851159% | -0.5448716160851159% | False |
| ts_imb_rule | -0.5448716160851159% | -0.5448716160851159% | False |


## Baseline semantics

- Artifact `buy_and_hold` equality: True
- Artifact `ts_imb_rule` equality: True
- Guardrail: `Do not report artifact baseline equality as independent outperformance.`

해석: 이번 `minimal_ts_imb` 결과는 artifact `buy_and_hold`/`ts_imb_rule`와 구조적으로 같은 수익률을 보였다. 이것은 독립 baseline을 이긴 증거가 아니다.

## Controls

| Control | Control return | Passed |
|---|---:|---|
| no_trade | 0.0% | False |
| buy_and_hold | -0.5448716160851159% | False |
| ts_imb_rule | -0.5448716160851159% | False |
| shuffled_labels | -3.3356245549756265% | True |
| time_session_shuffle | -0.5448716160851159% | False |
| randomized_features | -0.5448716160851159% | False |

## Ablations

| Ablation | Return | Delta vs full | Passed |
|---|---:|---:|---|
| no_participant_pressure | -0.5448716160851159% | 0.0% | False |
| no_orderbook_imbalance | -0.5448716160851159% | 0.0% | False |
| no_orderbook_persistence | -0.5448716160851159% | 0.0% | False |
| no_overheat_upper_wick | -0.5448716160851159% | 0.0% | False |
| no_time_bucket | -0.5448716160851159% | 0.0% | False |
| context_only | -0.5448716160851159% | 0.0% | False |
| tick_only | -0.5448716160851159% | 0.0% | False |
| shuffled_participant_context | -0.5448716160851159% | 0.0% | False |


## Dashboard visibility

| Table alias | Rows | Status |
|---|---:|---|
| rule_filter_controls | 6 | OK |
| rule_filter_ablations | 8 | OK |
| rule_filter_proxy_availability | 5 | OK |
| rule_filter_orderbook_persistence | 10 | OK |


Dashboard role is read-only evidence viewing. It is not a profitability proof and not an order/broker surface.

## Prior split policy

Prior diagnostic split hashes `37664423068ddeca` and `bc4384540145ce12` were not used for tuning. The emitted split for this run is frozen after first emission: `bc4384540145ce12`.

## Guardrails

- `ts_imb` remains a RULE baseline, not RL.
- PPO/DQN remains blocked.
- No live trading readiness claim.
- No broker readiness claim.
- No guaranteed profit claim.
- Participant/proxy fields are proxy evidence only, not actual participant identity.

## Next decision

Recommended next command:

```text
$ulw-plan baseline-only termination and data expansion audit for opening 30m rule-filter track
```

Reason: current simplified OOS run reproduced the same `NO-GO_CONTROL`. The next useful step is not PPO/DQN; it is either stop this track or audit independent baselines/sample expansion before any model expansion.
