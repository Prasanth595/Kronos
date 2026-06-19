# STOM Daily OHLCV D4-C Policy Evaluation Result (2026-06-13)

## Verdict

`RESEARCH_ONLY`. This compares the constrained daily portfolio RL policy against frozen D3 baselines after the 23bp default cost. It is not a profit result, not a deployable model, and not live/broker/order readiness.

## Artifact

- Run: `portfolio_2026_06_13_d4c_policy_eval`
- Directory: `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_13_d4c_policy_eval/`
- Input D3 run: `prediction_2026_06_13_d3_baseline_hardened`
- Cost: 23bp round trip
- Status: `RESEARCH_ONLY`

New policy-evaluation files:

- `policy_evaluation_manifest.json`
- `policy_baseline_comparison.csv`
- `policy_nav.csv`

Required frozen D3 comparison set:

- `no_trade_cash`
- `shuffle_control`
- `equal_weight_topk_momentum`
- `vol_adjusted_momentum`
- `supervised_linear_ranker`
- `supervised_direction_classifier`

## Result summary

The current deterministic constrained policy is effectively an all-hold/no-position policy on val+test:

- policy NAV: `1.0`
- policy total net return: `0.0`
- policy MDD: `0.0`
- policy mean turnover: `0.0`
- policy mean concentration: `0.0`

This beats the negative shuffle control but ties no-trade cash and underperforms the positive D3 rule/supervised baselines. Therefore it remains `RESEARCH_ONLY` and cannot unlock model build.

## Comparison contract

| Field | Meaning |
|---|---|
| `policy_nav` | 1 + policy total net return on val+test |
| `baseline_nav` | 1 + frozen D3 baseline total net return |
| `baseline_delta_total_net_return` | policy total net return minus baseline total net return |
| `policy_max_drawdown` | policy MDD from D4 evaluation |
| `policy_mean_turnover` | policy turnover after constraints/cost |
| `policy_mean_concentration` | policy holdings concentration diagnostic |
| `comparison_status` | `POLICY_BEATS_BASELINE` or `POLICY_UNDERPERFORMS_OR_TIES` |

## Dashboard/API surface

- `/api/daily-ohlcv/portfolio/latest` exposes `policy_evaluation`, `samples.policy_baseline_comparison`, and `samples.policy_nav`.
- `/api/daily-ohlcv/charts/portfolio` exposes `policy_baseline_comparison`, `policy_nav`, and the policy-evaluation row counts.
- The D4 dashboard card shows frozen-baseline deltas and policy NAV/MDD/turnover while preserving `RESEARCH_ONLY` framing.

## Verification

Commands run:

```powershell
py -3.11 -m pytest tests/test_stom_rl_daily_rl_gate.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
py -3.11 -m py_compile stom_rl/daily_rl_train.py webui/daily_ohlcv_dashboard.py
cd webui/v2_src
npm run check
npm run build
```

Observed result:

- Targeted Python/API/frontend marker tests: `14 passed`.
- Python compile: passed.
- Svelte check/build: passed with 0 errors and 4 pre-existing warnings in unrelated files (`ForecastWorkbenchTab.svelte`, `DocsTab.svelte`).

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, or order-routing readiness is implied.
- No profit claim is made.
- D4 remains `RESEARCH_ONLY`.
- `model_build_allowed=false` remains in force until strict D5/fresh forward gates pass.
- The dashboard must show underperformance against D3 baselines instead of presenting the RL policy as usable.
