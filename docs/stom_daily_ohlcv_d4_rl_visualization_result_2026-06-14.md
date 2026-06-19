# STOM Daily OHLCV D4 RL Environment/Reward/Visualization Result (2026-06-14)

## Verdict

`RESEARCH_ONLY` / `D4_RESEARCH_ONLY_DIAGNOSTICS`. D4 now consumes the hardened G004 D3 frozen baseline artifact and emits a constrained daily portfolio RL diagnostic run with learning/reward/NAV/drawdown/turnover/action/state visual evidence. It does **not** unlock model building, paper-forward readiness, live/broker/order workflows, or profit claims.

Blocking context remains:

- D0 price basis: `unknown` / `UNKNOWN_CONFIRMED`.
- D1 universe: `WATCH_HEURISTIC_UNIVERSE`; official/manual evidence is still missing.
- D3 baseline: `WATCH` / `D3_WATCH_RESEARCH_ONLY`.
- D5 walk-forward gate: not pass / still blocks promotion.
- `model_build_allowed=false`, `go_summary_allowed=false`, `paper_forward_allowed=false`, and `live_broker_order_allowed=false` remain required.

## Artifact

- Run: `portfolio_2026_06_14_g005_d4_visualization`
- Directory: `webui/rl_runs/daily_ohlcv_portfolio/portfolio_2026_06_14_g005_d4_visualization/`
- Prediction input: `webui/rl_runs/daily_ohlcv_prediction/prediction_2026_06_14_g004_d3_baseline_hardened/`
- Prediction manifest SHA-256: `b1d4b26d8561444dd826c66bb1fdc092200f52d0dd1d05a0ab6f24b4c0439936`
- RL manifest SHA-256: `5f103d446be2a84833e381f721ce7b388c090dd6e88889d166fd0b65ab659ff6`
- Upstream predictions SHA-256: `78ad01d796ae75bccbe87753c7843f256cf2af28cf0ce8b24249c1989daa344a`
- Upstream baseline metrics SHA-256: `d142cdc89ea17f4d6f799e15228707079dbdba1bf663590e6a73bd33631d0009`
- Upstream verdict SHA-256: `634e12e4fe40a36ef151eef4f5bb65a50d6df0c380ad85fe89e8cbac9d62205c`
- Upstream hash mismatches: `[]`
- Cost: 23bp round trip
- Fill/reward assumption: close-to-next-close research label only; no broker/order fill is inferred.
- Policy: `tabular_q_constrained_daily_portfolio_rl`
- Episodes: 12
- Seed: 7
- Max positions: 5
- Candidate limit: 20

Generated evidence files include `rl_manifest.json`, `training_manifest.json`, `observation_manifest.json`, `policy_metrics.json`, `episode_metrics.csv`, `learning_curve.csv`, `reward_breakdown.csv`, `reward_component_summary.json`, `action_distribution.csv`, `invalid_actions.csv`, `turnover.csv`, `drawdown.csv`, `policy_baseline_comparison.csv`, `policy_nav.csv`, `policy_evaluation_manifest.json`, `baseline_comparison.json`, and `verdict.json`.

## D4 diagnostic outcome after 23bp cost

| Metric | Value |
|---|---:|
| D4 status | `RESEARCH_ONLY` |
| Readiness | `D4_RESEARCH_ONLY_DIAGNOSTICS` |
| Gate dependency | `D3_WATCH_D5_NOT_RUN` |
| Policy total net return | -42.12% |
| Policy NAV | 0.5788 |
| Policy max drawdown | -81.91% |
| Policy mean turnover | 0.2000 |
| Invalid action rate | 0.00% |
| Best D3 baseline | `equal_weight_topk_momentum` |
| Best D3 total net return | +31.37% |
| Delta vs best D3 | -73.49 percentage points |

This is a useful RL environment/telemetry and failure-analysis artifact, not a tradable model. The policy underperforms no-trade, shuffle, and the best D3 rule baseline after the current research accounting.

## Visualization/usage surfaces

| Surface | Evidence |
|---|---|
| Learning graph | `learning_curve.csv`, dashboard `data-daily-rl-learning-curve` |
| Reward/return curve | `reward_breakdown.csv`, dashboard `data-daily-rl-reward-return-curve` |
| Reward stack | `reward_component_summary.json`, dashboard `data-daily-rl-reward-components` |
| NAV / portfolio trajectory | `policy_nav.csv`, dashboard `data-daily-rl-portfolio-trajectory` |
| Drawdown | `drawdown.csv`, dashboard `data-daily-rl-turnover-drawdown` |
| Turnover/cost | `turnover.csv`, reward breakdown cost/slippage columns |
| Action distribution | `action_distribution.csv`, dashboard `data-daily-rl-action-distribution` |
| Invalid action evidence | `invalid_actions.csv`, `invalid_action_rate=0.0` |
| State contract | `observation_manifest.json`, `state_observations.csv` |
| Frozen D3 overlay | `policy_baseline_comparison.csv`, dashboard `data-daily-rl-policy-baseline-comparison` |

## Provenance hardening

| Evidence | SHA-256 |
|---|---|
| `policy_metrics.json` | `bf1f88bab622463e1a496c2cc502e0b109886fd99dc3900c0aee27ba69ff7c18` |
| `policy_nav.csv` | `cdc631abf56c463d95c9c4b46ca33dcc810c4254882dcb9c08b505c79b7f2268` |
| `policy_baseline_comparison.csv` | `cff6d20b5d16dc01e299ec3d44d7bfe110bedce9cdf4f156d44577f574e4e5e6` |
| `learning_curve.csv` | `01de8fcff71791b4cc065492982cec5fa3b65e5274d58d90221a0b9e54444f58` |

The Flask D4 portfolio API now fail-closes stale/optimistic generated artifacts, including nested `training_manifest.json` and `policy_evaluation_manifest.json`, to `RESEARCH_ONLY` and `D4_RESEARCH_ONLY_DIAGNOSTICS`, with `model_build_allowed=false`, `go_summary_allowed=false`, `paper_forward_allowed=false`, and `live_broker_order_allowed=false`. The dashboard D4 card displays upstream and D4 artifact hashes through `data-daily-rl-provenance-hashes`, and regression tests cover declared upstream hash mismatches.

## Guardrails

- No `_database/*` mutation was performed.
- No live trading, broker, order-routing, or paper-forward readiness is implied.
- No profit claim is made.
- Default cost assumption remains 23bp round trip.
- Leading-zero stock codes remain strings in dataset/prediction/portfolio evidence.
- D4 is an RL experiment/diagnostic, but it remains `RESEARCH_ONLY` and under D5 gate control.
- `model_build_allowed=false` remains required until D0/D1/D3/D5 gates pass.

## Verification

Current focused verification after D4 hardening:

```powershell
py -3.11 -m py_compile stom_rl/daily_rl_train.py webui/daily_ohlcv_dashboard.py tests/test_stom_rl_daily_rl_gate.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py
# PASS

py -3.11 -m pytest tests/test_stom_rl_daily_portfolio_env.py tests/test_stom_rl_daily_rl_gate.py tests/test_stom_rl_daily_prediction.py tests/test_daily_ohlcv_dashboard_api.py tests/test_daily_ohlcv_dashboard_tab.py -q
# 42 passed

cd webui/v2_src
npm run build
# svelte-check 0 errors, 4 pre-existing warnings; Vite build PASS
```
