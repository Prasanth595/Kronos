# STOM Daily OHLCV Deep Learning / RL Plan (2026-06-11)

## Verdict

Daily OHLCV is worth adding as a separate model track, but it must not be treated as a direct replacement for the current 1s/opening execution research.

- **Best fit:** swing selection, next-day/next-N-day ranking, portfolio rebalancing, market/regime filters.
- **Weak fit:** same-day intraday scalping. Daily OHLCV can create a watchlist before/after market, but intraday entry/exit still needs 1m/1s execution evidence.
- **Possible but limited:** long-term stock selection from OHLCV alone. For robust long-horizon selection, fundamentals/news/macro/sector data should be added later.

This plan is research-only. No profit guarantee, no live/broker/order readiness. Existing `ts_imb` opening-gap curve remains a RULE baseline, not RL. Costs and drawdown gates remain mandatory.

## What daily OHLCV can support

| Goal | Feasibility | Best model type | Comment |
|---|---:|---|---|
| Same-day scalping / intraday 단타 | Low with daily-only | Not recommended | Daily bars do not contain intraday path, spread, SL/TP order, or liquidity timing. Use daily only as prefilter/watchlist; execute/validate with 1m/1s. |
| Next-day direction prediction | Medium | Supervised DL/classifier/ranker | Predict `ret_1d > cost`, gap risk, downside risk, hit probability. Must beat persistence and simple momentum/mean-reversion baselines. |
| Swing trading 2-10 days | Medium-High | Supervised ranker + rule baseline, then RL portfolio | Daily OHLCV is naturally matched to swing horizons; evaluate turnover, MDD, capacity, and walk-forward stability. |
| Long-term selection 20-120 days | Medium | Ranking model + portfolio optimizer/RL | OHLCV alone may capture trend/volatility but lacks valuation/fundamentals. Treat as technical factor model until additional data exists. |
| Portfolio allocation/rebalancing | Medium | Daily portfolio RL | Existing `PortfolioEnv` can be adapted to daily candidate rows. RL action should be constrained and compared against fixed Top-K/risk-parity/no-trade. |
| Risk regime filter | High | Supervised/regime classifier | Index trend/volatility/breadth from daily data can decide when to disable or reduce strategies. |

## Required separation from existing opening/1s track

| Layer | Daily OHLCV role | Existing 1s/opening role |
|---|---|---|
| Universe | select symbols and regimes across days | validate opening execution and intraday fill realism |
| Signal horizon | 1d, 3d, 5d, 20d returns | 09:00-09:30 / seconds-level paths |
| Execution proof | daily close/open assumptions only, low fidelity | marketable fill, SL/TP order, gap-through, VI/halt, capacity |
| RL environment | daily portfolio rebalance | orderbook/opening/sizing experiments |

Daily results must not be mixed with `ts_imb` as if they were the same strategy family.

## Development plan to add to the current roadmap

### D1. Daily OHLCV dataset builder

Build a true daily dataset with one row per symbol/day.

Expected file targets:

```text
stom_rl/daily_ohlcv_dataset.py
tests/test_stom_rl_daily_ohlcv_dataset.py
```

Required columns:

| Column | Meaning |
|---|---|
| `symbol` | string stock code; preserve leading zero |
| `date` | trading date |
| `open`, `high`, `low`, `close` | daily adjusted or raw OHLC, explicitly labeled |
| `volume`, `amount` | daily liquidity |
| `market_cap` optional | later capacity/ranking feature |
| `tradable` | false for halt/suspension/invalid bars |

Hard rules:

- No lookahead in adjustment, ranking, or normalization.
- Split by date, not random rows.
- Record market calendar and missing-bar handling.
- If Korean stocks: handle ±30% limit-up/down and suspension flags when available.

### D2. Daily supervised prediction/ranking baseline

Before RL, build supervised daily prediction and ranking baselines.

Expected file targets:

```text
stom_rl/daily_prediction.py
stom_rl/daily_ranker.py
tests/test_stom_rl_daily_prediction.py
tests/test_stom_rl_daily_ranker.py
```

Targets:

| Target | Use |
|---|---|
| `ret_1d` | next-day watchlist / close-to-close |
| `ret_3d`, `ret_5d` | swing |
| `ret_20d` | medium-term selection |
| `downside_5d` | risk filter |
| `hit_5d_after_cost` | cost-aware classification |

Baselines to beat:

- no-trade/cash
- equal-weight Top-K momentum
- volatility-adjusted momentum
- simple mean-reversion
- market/index beta proxy where available

### D3. Daily portfolio RL environment

Adapt the existing portfolio action pattern to daily bars.

Expected file targets:

```text
stom_rl/daily_portfolio_env.py
stom_rl/daily_rl_train.py
stom_rl/daily_rl_gate.py
tests/test_stom_rl_daily_portfolio_env.py
tests/test_stom_rl_daily_rl_gate.py
```

Recommended first action contract:

| Action | Meaning |
|---|---|
| `0` | hold / no rebalance |
| `1..K` | buy/add selected candidate slot |
| `K+1..K+M` | sell/reduce holding slot |

Reward:

```text
reward = daily_nav_return
         - turnover_cost
         - drawdown_penalty
         - concentration_penalty
         - invalid_action_penalty
```

Do not start with a free-form continuous allocation policy. Use masks and constrained actions first.

### D4. Walk-forward validation gate

Expected file targets:

```text
stom_rl/daily_walk_forward.py
stom_rl/daily_model_gate.py
tests/test_stom_rl_daily_walk_forward.py
```

Required gates:

| Gate | Requirement |
|---|---|
| date split | purged/embargoed or strictly forward-only |
| cost | include commissions/slippage assumption |
| turnover | measured and penalized |
| drawdown | maxDD and worst month/session visible |
| baseline | Top-K/rule/no-trade comparison |
| robustness | multiple folds, not one lucky split |
| selection | no retuning on OOS results |

### D5. Dashboard integration

Expected file targets:

```text
webui/rl_dashboard_daily.py
webui/v2_src/src/tabs/rlTrading/DailyOhlcvModelCard.svelte
```

Dashboard should show:

- horizon: `1d`, `3d`, `5d`, `20d`
- model type: supervised / RL / baseline
- split metadata
- Top-K hit rate and return after cost
- drawdown, turnover, concentration
- `GO/NO-GO`, never profit guarantee

## What becomes possible after this track exists

| User goal | Possible implementation |
|---|---|
| 당일 단타 종목 후보 | previous-day daily OHLCV watchlist + intraday 1m/1s execution validation |
| 스윙 종목 선별 | daily Top-K ranker over `ret_3d`/`ret_5d` with risk filter |
| 장기 후보 | `ret_20d`/`ret_60d` ranker, preferably with fundamentals later |
| 예측 | probability/ranking, not exact price promise |
| 강화학습 | daily portfolio rebalance RL after supervised/rule baselines pass |

## Recommended immediate next work

1. Build `daily_ohlcv_dataset.py` with small deterministic fixtures and strict date splits.
2. Create a daily supervised Top-K baseline before RL.
3. Add daily model gate and dashboard evidence.
4. Only after the baseline passes, implement daily portfolio RL.

Daily RL should be treated as a new independent track, not as an unlock shortcut for the current opening/fresh-validation lock.
