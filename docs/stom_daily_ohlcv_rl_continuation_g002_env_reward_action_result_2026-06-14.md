# Daily OHLCV RL Continuation G002: D4 Environment Reward/Action Hardening

Date: 2026-06-14 KST  
Status: `RESEARCH_ONLY`  
Source plan: `.gjc/plans/ralplan/2026-06-11-0158-38ea/pending-approval.md`  
Preregistration source: `docs/stom_daily_ohlcv_rl_continuation_prereg_2026-06-14.md`  
Generated artifact: `webui/rl_runs/daily_ohlcv_portfolio_env/env_contract_2026_06_14_g002_reward_action/`

## Scope

G002 implements/hardens only the D4 Daily Portfolio RL environment reward/action contract. It does not claim model readiness, paper-forward approval, live/broker/order readiness, or profit.

## Guardrails preserved

| Guardrail | Status |
|---|---|
| No live/broker/orders | Preserved in environment manifest and fill assumption |
| No profit claim | Preserved; artifacts are evidence/diagnostic only |
| Default round-trip cost | 23bp |
| `_database` mutation | Not used by this story |
| Leading-zero codes | Preserved through `str(code).zfill(6)` and positions/state artifacts |
| D4 status | `RESEARCH_ONLY` |
| `model_build_allowed` | `false` |

## Implementation result

| Area | Result |
|---|---|
| Net return after cost | `net_return_after_cost = gross_return - turnover_cost` is explicit in reward info, reward components, CSV artifacts, and environment manifest. |
| Drawdown penalty | Reward still subtracts drawdown penalty and exposes `current_drawdown` / `drawdown_penalty`. |
| Concentration penalty | Reward still subtracts concentration penalty and exposes concentration telemetry. |
| Turnover/churn penalty | 23bp turnover cost plus separate churn penalty remain explicit. |
| Invalid actions | Invalid action reason is now explicit (`invalid_action_reason`) for both masked actions and unknown out-of-range actions; action mask reasons are emitted. |
| No-trade/hold | `hold` is always valid; flat hold is explicitly marked `no_trade_action=true`. |
| Action masks | `action_mask_details()` exposes valid/blocked reasons for hold/buy/add/sell/reduce. |
| Generated inspection | `action_masks.csv` includes `mask_reason_*`; `reward_breakdown.csv` includes requested/executed action, invalid reason, no-trade flag, and net-return-after-cost. |

## Verification

```powershell
py -3.11 -m py_compile stom_rl/daily_portfolio_env.py tests/test_stom_rl_daily_portfolio_env.py
py -3.11 -m pytest tests/test_stom_rl_daily_portfolio_env.py -q
py -3.11 -m py_compile stom_rl/daily_rl_train.py tests/test_stom_rl_daily_rl_gate.py
py -3.11 -m pytest tests/test_stom_rl_daily_rl_gate.py -q
py -3.11 -c <generate env inspection artifact>
```

Observed result:

```text
tests/test_stom_rl_daily_portfolio_env.py + tests/test_stom_rl_daily_rl_gate.py: 12 passed
G002 env inspection artifact PASS
```

## Remaining state

This story only hardens the environment contract. D4 remains `RESEARCH_ONLY`, D5 remains `NO-GO`, and `model_build_allowed=false` remains locked until D0/D1/D3/D5 gates pass under later approved evidence.
