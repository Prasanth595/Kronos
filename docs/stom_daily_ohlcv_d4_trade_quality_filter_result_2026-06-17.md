# Daily OHLCV D4 Trade-Quality Filter Result — 2026-06-17

Date: 2026-06-17 UTC  
Status: `NO-GO_RESEARCH_ONLY`  
Experiment type: `RL experiment` / diagnostic filter research  
Parent preregistration: `docs/stom_daily_ohlcv_d4_trade_quality_filter_prereg_2026-06-17.md`  
Parent result: `docs/stom_daily_ohlcv_d4_action_induction_v2_result_2026-06-17.md`  
Default cost: 23bp round trip; D5 scenario manifests record 0/23/46bp cost sensitivity, while the result table below reports 23bp net-return figures.

## Verdict

The D4 trade-quality filter lane implemented the preregistered confidence/margin/risk-regime abstention telemetry and produced `abstention_reasons.csv` for every scenario. The feature is useful as a **diagnostic and governance artifact**, but it does not improve the research verdict.

All five scenarios remain `NO-GO` under the D5 research gate. The best comparator in this bounded batch is still `no_trade_cash` at 0.00% total net return on `val+test`; every D4 filter/control variant lost after 23bp costs. No model-build, paper-forward, live, broker, order, or profit claim is opened.

## What changed in this research lane

| Element | Implementation | Governance note |
|---|---|---|
| State | Kept v2 causal state: `position_count`, `top_score_bucket`, `score_margin_bucket`, `candidate_count_bucket`, `recent_score_volatility_bucket`, `d3_confidence_bucket` | No current/future `future_return_1d` in state/filter selection. |
| Action | Existing hold/buy/add/sell/reduce masks plus decision-time buy/add filter | Filter blocks only new entries and records exact reasons; it does not silently coerce without telemetry. |
| Policy/filter | `tabular_q_trade_quality_filter_v1` for confidence/margin/joint/risk variants; `tabular_q` for prior-disabled control | Filter is diagnostic-only, not deployable RL. |
| Reward | Existing net-return-after-cost reward accounting remains unchanged | Filter diagnostics are separate from realized return. |
| Diagnostics | New `abstention_reasons.csv` plus existing state observations, invalid actions, reward breakdown, no-trade diagnostics, baseline comparison | Future labels remain post-action reward/diagnostic inputs only. |

## Exact commands

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_scenario_runner.py -q
py -3.11 -m stom_rl.daily_scenario_batch --plan artifacts/scenario_batch_d4_trade_quality_filter_001_plan.json --batch-id scenario_batch_d4_trade_quality_filter_001 --overwrite
```

Observed output:

```text
21 passed in 1.46s
scenario_count=5, completed_count=5, failed_count=0, gate_status_counts={"NO-GO": 5}
```

## Durable artifacts

| Artifact | Path |
|---|---|
| Scenario plan | `artifacts/scenario_batch_d4_trade_quality_filter_001_plan.json` |
| Batch manifest | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_d4_trade_quality_filter_001/scenario_batch_manifest.json` |
| Batch research summary | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_d4_trade_quality_filter_001/trade_quality_filter_research_summary.json` |
| Confidence filter portfolio artifacts | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__confidence_abstain_v1/` |
| Margin filter portfolio artifacts | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__margin_abstain_v1/` |
| Joint confidence+margin portfolio artifacts | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__confidence_margin_joint_v1/` |
| Risk-regime portfolio artifacts | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__risk_regime_abstain_v1/` |
| Prior-disabled control artifacts | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__prior_disabled_control_v1/` |
| Representative source-hash artifact | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_trade_quality_filter_001__confidence_abstain_v1/source_hashes.json` (same `source_hashes.json` contract per scenario portfolio directory) |

Each portfolio directory includes `rl_manifest.json`, `observation_manifest.json`, `source_hashes.json`, `state_observations.csv`, `abstention_reasons.csv`, `action_distribution.csv`, `reward_breakdown.csv`, `policy_baseline_comparison.csv`, `no_trade_opportunity_summary.json`, and `verdict.json`.

## Scenario results (`val+test`)

| Scenario | Filter setting | D5 status | RL total net return | NAV | MDD | Turnover | Best D3 baseline | Delta vs best D3 | Abstention / action behavior |
|---|---|---|---:|---:|---:|---:|---|---:|---|
| `confidence_abstain_v1` | buy/add require `d3_confidence_bucket >= 3` | `NO-GO` | -10.11% | 0.8989 | -11.84% | 9.91% | `no_trade_cash` 0.00% | -10.11% | 30 blocked-entry rows; buy=5, add=1, sell=4, reduce=1, hold=26 |
| `margin_abstain_v1` | buy/add require `score_margin_bucket >= 3` | `NO-GO` | -11.99% | 0.8801 | -23.53% | 2.70% | `no_trade_cash` 0.00% | -11.99% | 35 blocked-entry rows; buy=1, add=1, reduce=1, hold=34 |
| `confidence_margin_joint_v1` | require both confidence and margin thresholds | `NO-GO` | -11.99% | 0.8801 | -23.53% | 2.70% | `no_trade_cash` 0.00% | -11.99% | 35 blocked-entry rows; same action profile as margin filter |
| `risk_regime_abstain_v1` | block entries only when past-score volatility bucket is above threshold | `NO-GO` | -12.53% | 0.8747 | -14.88% | 24.32% | `no_trade_cash` 0.00% | -12.53% | 0 blocked rows in this bounded run; buy=7, add=7, sell=6, hold=17 |
| `prior_disabled_control_v1` | v2 state, no prior, no filter | `NO-GO` | -11.29% | 0.8871 | -15.09% | 10.81% | `no_trade_cash` 0.00% | -11.29% | control: buy=4, add=2, sell=4, reduce=2, hold=25 |

## Interpretation

1. Abstention telemetry works: the confidence/margin/joint filters produced explicit `abstention_reasons.csv` rows and blocked buy/add decisions without using future labels.
2. The best filter by return was `confidence_abstain_v1`, but it still lost -10.11% versus 0.00% no-trade/best D3 and therefore remains `NO-GO`.
3. Margin and joint filters lowered turnover sharply, but drawdown worsened in this bounded run; lower turnover alone did not create a usable policy.
4. The risk-regime proxy did not block entries in this bounded matrix, so the current past-score-volatility proxy is not a useful risk gate as configured.
5. The prior-disabled control still lost, confirming that richer v2 state alone is not enough.

## Data governance record

| Governance area | Evidence |
|---|---|
| Lineage | Parent preregistration/result are linked above; batch plan and batch manifest are listed in durable artifacts. |
| Reproducibility | Scenario plan stores frozen defaults, overrides, seeds, folds, purge/embargo, candidate limits, max positions, episodes, action prior, and filter mode; the executed batch manifest records `cost_sensitivity_bp=[0,23,46]`, generated artifact paths, and per-scenario statuses. |
| Schema control | `observation_manifest.json` declares `trade_quality_filter`; `rl_manifest.json` records `action_filter_mode` and thresholds. |
| Leakage control | Tests cover filter no-leakage and `abstention_reasons.csv` rows set `future_label_exposed=false`; reward labels remain post-action diagnostics only. |
| Baseline controls | Batch includes D5 gate output and frozen baseline comparison against no-trade, shuffle, equal-weight top-k, and D3 strategies. |
| Generated vs durable separation | Generated evidence stays under `webui/rl_runs/`; this dated result record stays under `docs/`. |
| Safety locks | `model_build_allowed=false`, `go_summary_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false` remain enforced. |

## Current promotion status

`NO-GO_RESEARCH_ONLY`.

D5 remains blocked. This run does not approve model build, paper-forward, live trading, broker integration, order placement, or any profit/readiness claim.

## Next allowed research action

Do **not** tune thresholds against this result without a new preregistration. The next useful research should move upstream to a preregistered D3/D4 signal-quality audit:

- verify whether D3 score magnitude and score margin are calibrated enough to support abstention,
- add a better past-only risk/regime proxy if available from daily OHLCV artifacts,
- keep no-trade, shuffle, equal-weight top-k, and frozen D3 baselines mandatory,
- keep `abstention_reasons.csv` and no-leakage tests as required artifacts,
- keep D5/model-build/paper-forward status `NO-GO` until a fresh gate passes.
