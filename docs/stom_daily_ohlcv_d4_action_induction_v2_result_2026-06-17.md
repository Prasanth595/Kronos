# Daily OHLCV D4 Action-Induction v2 Result — 2026-06-17

Date: 2026-06-17 UTC  
Status: `NO-GO_RESEARCH_ONLY`  
Experiment type: `RL experiment`  
Parent preregistration: `docs/stom_daily_ohlcv_d4_action_induction_v2_prereg_2026-06-16.md`  
Parent diagnostic: `docs/stom_daily_ohlcv_d4_no_trade_diagnostic_result_2026-06-16.md`  
Default cost: 23bp round trip

## Verdict

D4 action-induction v2 is useful as a **failure-analysis diagnostic** because it made non-hold actions reachable and produced richer state/action telemetry. It is not a model-build, paper-forward, live, broker, order, or profit claim.

All three scenarios remain `NO-GO` under the D5 research gate. The best D3/no-trade baseline for this bounded batch is `no_trade_cash` at 0.00% total net return, while every v2 RL policy lost money on `val+test` after 23bp costs.

## What changed in this research lane

| Element | v2 implementation | Governance note |
|---|---|---|
| State | `position_count`, `top_score_bucket`, `score_margin_bucket`, `candidate_count_bucket`, `recent_score_volatility_bucket`, `d3_confidence_bucket` | Current decision-time score/position features only. `recent_score_volatility_bucket` is a past-score volatility proxy because raw OHLCV volatility is not present in prediction artifacts. |
| Action | Existing constrained actions: hold, buy, add, sell, reduce | Valid masks and invalid-action reasons remain emitted. |
| Policy | `tabular_q` and diagnostic `tabular_q_action_prior_v2` | Entry prior is policy-selection telemetry only; it does not alter realized reward or gates. |
| Reward | Existing net-return-after-cost accounting with penalties | Reward/accounting stayed separate from post-policy diagnostics. |
| Diagnostics | No-trade opportunity summary, state key, policy values, action priors, action scores | Future labels are used only after policy decision for reward/diagnostic analysis. |

## Exact commands

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_scenario_runner.py -q
py -3.11 -m stom_rl.daily_scenario_batch --plan artifacts/scenario_batch_d4_action_induction_v2_001_plan.json --batch-id scenario_batch_d4_action_induction_v2_001 --overwrite
```

Verification result:

```text
20 passed in 1.41s
scenario_count=3, completed_count=3, failed_count=0, gate_status_counts={"NO-GO": 3}
```

## Durable artifacts

| Artifact | Path |
|---|---|
| Scenario plan | `artifacts/scenario_batch_d4_action_induction_v2_001_plan.json` |
| Batch manifest | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_d4_action_induction_v2_001/scenario_batch_manifest.json` |
| Batch research summary | `webui/rl_runs/daily_ohlcv_scenario_batches/scenario_batch_d4_action_induction_v2_001/action_induction_v2_research_summary.json` |
| State-only portfolio manifest | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_action_induction_v2_001__v2_state_only_top10_pos3/rl_manifest.json` |
| Entry-prior portfolio manifest | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_action_induction_v2_001__v2_entry_prior_top10_pos3/rl_manifest.json` |
| Single-slot entry-prior portfolio manifest | `webui/rl_runs/daily_ohlcv_portfolio/_scenario_runs/scenario_batch_d4_action_induction_v2_001__v2_entry_prior_single_slot_top5/rl_manifest.json` |

## Scenario results (`val+test`)

| Scenario | State/action setting | D5 status | RL total net return | NAV | MDD | Turnover | Best D3 baseline | Delta vs best D3 | Action reachability |
|---|---|---|---:|---:|---:|---:|---|---:|---|
| `v2_state_only_top10_pos3` | v2 state, no prior | `NO-GO` | -11.29% | 0.8871 | -15.09% | 10.81% | `no_trade_cash` 0.00% | -11.29% | buy=4, add=2, sell=4, reduce=2, flat no-trade=20 |
| `v2_entry_prior_top10_pos3` | v2 state, `entry_bias_v1=0.0005` | `NO-GO` | -12.53% | 0.8747 | -14.88% | 24.32% | `no_trade_cash` 0.00% | -12.53% | buy=7, add=7, sell=6, flat no-trade=5 |
| `v2_entry_prior_single_slot_top5` | v2 state, one slot, `entry_bias_v1=0.0005` | `NO-GO` | -11.77% | 0.8823 | -17.77% | 27.03% | `no_trade_cash` 0.00% | -11.77% | buy=5, sell=5, flat no-trade=12 |

## No-trade diagnostic movement

| Scenario | `val+test` no-trade rate | Missed positive no-trade count | Risk avoided no-trade count | Interpretation |
|---|---:|---:|---:|---|
| `v2_state_only_top10_pos3` | 54.05% | 10 | 10 | v2 state alone reduced the previous all-hold collapse but still traded into losses. |
| `v2_entry_prior_top10_pos3` | 13.51% | 2 | 3 | Entry prior strongly induced actions, but turnover/exposure rose and returns worsened. |
| `v2_entry_prior_single_slot_top5` | 32.43% | 7 | 5 | One-slot constraint reduced action complexity but did not control drawdown/cost enough. |

## Interpretation

1. The original all-hold/no-trade collapse is no longer the only blocker: v2 can make actions reachable.
2. Once actions are reachable, the next blocker becomes **trade quality**: the policy increases exposure/turnover without beating the no-trade/D3 baseline.
3. The action prior is not sufficient as a research direction by itself. It proves reachability, not alpha.
4. D5 remains `NO-GO`. No paper-forward/model-build/live/broker/order path is opened.

## Data governance record

| Governance area | Evidence |
|---|---|
| Lineage | Parent preregistration and no-trade diagnostic are linked above. Batch manifest and per-run manifests are listed in durable artifacts. |
| Reproducibility | Scenario plan stores defaults, overrides, seeds, folds, purge/embargo, cost assumptions, candidate limits, max positions, and episodes. |
| Schema control | New state fields are declared in `observation_manifest.json` and tested in `tests/test_stom_rl_daily_portfolio_env.py` / `tests/test_stom_rl_daily_rl_gate.py`. |
| Leakage control | Tests prove current reward-label changes do not change v2 state; manifests state future labels are excluded from current observation/action mask. |
| Retention | Generated evidence stays under `webui/rl_runs/`; this dated decision record stays under `docs/`. |
| Safety | `model_build_allowed=false`, `paper_forward_allowed=false`, `live_broker_order_allowed=false` remain enforced. |

## Next allowed research action

Do **not** tune the action prior upward to chase a favorable curve. The next recommended research is a new preregistered **trade-quality filter / uncertainty abstention** lane:

- keep v2 causal state fields,
- remove or freeze the entry prior as diagnostic-only,
- add explicit D3 confidence/margin abstention tests,
- evaluate whether trades can be limited to days with stronger current-score separation,
- compare against no-trade, shuffle, equal-weight top-k, and frozen D3 baselines under 23bp/46bp sensitivity.

Promotion status remains `NO-GO_RESEARCH_ONLY` until a fresh D5 gate passes.
