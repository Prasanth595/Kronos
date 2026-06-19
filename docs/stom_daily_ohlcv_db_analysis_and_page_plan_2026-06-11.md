# STOM Daily OHLCV DB Analysis and Development Page Plan (2026-06-11)

## Status

Planning / pending execution approval.

User-provided DB:

```text
_database/Stock_Database_ohlcv_1day.db
```

Supporting metadata DB inspected:

```text
_database/stock_tick_back.db:stockinfo
```

This document is research/planning only. It does not claim profitability, live/broker/order readiness, or completed RL model creation.

## 1. DB inspection summary

### 1.1 Daily OHLCV DB shape

| Item | Observed value |
|---|---:|
| SQLite tables | 4,727 |
| `A` tables | 4,166 |
| numeric `A######` tables | 3,823 |
| alphanumeric `A*` tables | 343 |
| `Q` tables | 561 |
| total OHLCV rows | 14,691,020 |
| min row count/table | 3 |
| median row count/table | 1,966 |
| max row count/table | 10,488 |
| global first date | 1986-04-15 |
| global latest date | 2026-06-12 |
| tables reaching latest date | 4,287 |

All inspected tables share one schema:

| Column | Type | Meaning |
|---|---|---|
| `date` | INTEGER | YYYYMMDD trading date |
| `open` | INTEGER | daily open |
| `high` | INTEGER | daily high |
| `low` | INTEGER | daily low |
| `close` | INTEGER | daily close |
| `volume` | INTEGER | daily volume |
| `상장주식수` | INTEGER | listed shares |
| `외국인주문한도수량` | INTEGER | foreign order limit qty |
| `외국인현보유수량` | INTEGER | foreign holding qty |
| `외국인현보유비율` | REAL | foreign holding ratio |
| `기관순매수` | INTEGER | institutional net buy |
| `기관누적순매수` | INTEGER | cumulative institutional net buy |

### 1.2 Sample table

`A005930` sample starts at `19860415` and has 10,488 rows. It includes OHLCV plus foreign/institutional columns, which makes daily prediction/ranking richer than plain OHLCV.

### 1.3 Metadata availability

The daily DB itself has only per-symbol OHLCV tables. Market/name metadata was found in `_database/stock_tick_back.db:stockinfo`:

| Column | Type | Meaning |
|---|---|---|
| `index` | TEXT | stock/product code without `A`/`Q` prefix |
| `종목명` | TEXT | Korean instrument name |
| `코스닥` | INTEGER | `1` = KOSDAQ, `0` = non-KOSDAQ/KOSPI-side metadata |

Join result between daily table names and `stockinfo`:

| Item | Count |
|---|---:|
| daily tables matched to `stockinfo` | 4,229 |
| daily tables not matched | 498 |

Unmatched examples: `A000075`, `A000885`, `A001140`, `A003410`, `A003560`, `A005390`, `A006390`, `A010420`, `A010600`, `A010620`.

These unmatched instruments must be quarantined until name/market metadata is resolved.

### 1.4 Data quality flags

Observed issues that the DB Analysis tab must expose:

| Check | Observation |
|---|---|
| Null core OHLCV values | none found in quick aggregate scan |
| zero/non-positive OHLC examples | `A004360`, `A006280` each had 1 flagged row |
| OHLC consistency issues | examples include `A000050`, `A000100`, `A000155`, `A000220`, `A000440` |
| very short histories | examples include `A0017J0` 3 rows, `A0189Z0` 4 rows |

These are not fatal, but they must be visible and excluded from training windows when invalid.

## 2. Universe classification requirement

Goal: train/evaluate only KOSPI/KOSDAQ equity symbols, excluding ETF/ETN and similar listed products.

### 2.1 Classification sources

Use layered metadata, not table-name guessing alone:

1. Daily DB table name: `A######`, `A*`, `Q*`.
2. `stock_tick_back.db:stockinfo` for `종목명` and `코스닥`.
3. Optional later: KRX official listed-product metadata export for exact ETF/ETN/SPAC/REIT/common/preferred type.

### 2.2 Proposed instrument taxonomy

| `instrument_type` | Include by default? | Rule |
|---|---:|---|
| `common_equity` | yes | matched metadata, normal numeric code, not product/SPAC/REIT/preferred |
| `preferred_stock` | no by default, optional | names ending with common preferred markers like `우`, `우B`, `우C`, alphanumeric preferred codes |
| `ETF` / `ETN` / `fund_product` | no | `Q*`, KODEX/TIGER/RISE/ACE/SOL/HANARO/ARIRANG/KOSEF/KBSTAR/TIMEFOLIO/TREX/HK/PLUS prefix, ETN/ETF/futures/bond/covered-call names |
| `SPAC` | no | name contains `스팩` / `SPAC` |
| `REIT` | no by default, optional | exact REIT classification; avoid false positives like `메리츠` by using official metadata or strict suffix rules |
| `unknown_unmatched` | no | not found in metadata |

### 2.3 Market classification

| `market` | Rule |
|---|---|
| `KOSDAQ` | `stockinfo.코스닥 == 1` |
| `KOSPI` | `stockinfo.코스닥 == 0` and type is allowed equity |
| `UNKNOWN` | no metadata match |

The first implementation should create a generated universe manifest, not mutate either DB.

Expected artifact:

```text
webui/rl_runs/daily_ohlcv_universe/universe_<date>/universe.json
webui/rl_runs/daily_ohlcv_universe/universe_<date>/symbols.csv
webui/rl_runs/daily_ohlcv_universe/universe_<date>/exclusions.csv
```

## 3. Development pages / dashboard plan

### Page D0 — Daily DB Analysis tab

Purpose: prove the DB is usable before model development.

| Section | Required fields |
|---|---|
| DB overview | path, table count, total rows, date range, latest coverage |
| Schema card | columns, types, one-schema or multi-schema status |
| Market/product counts | KOSPI/KOSDAQ/common/preferred/ETF/ETN/SPAC/REIT/unknown |
| Data quality | nulls, non-positive OHLC, OHLC consistency, short histories |
| Symbol drilldown | search by code/name, row count, date min/max, sample rows |
| Export buttons | read-only generated artifact links only |

Backend/API target:

```text
webui/daily_ohlcv_dashboard.py
/api/daily-ohlcv/db-summary
/api/daily-ohlcv/symbol/<code>
```

Frontend target:

```text
webui/v2_src/src/tabs/DailyOhlcvDbTab.svelte
```

### Page D1 — Daily Universe Management tab

Purpose: manage which symbols can enter training/evaluation without changing source DB.

| Feature | Rule |
|---|---|
| Exclusion rules | ETF/ETN/fund/SPAC/REIT/preferred/unknown toggle |
| Market filters | KOSPI, KOSDAQ, both |
| Minimum history | e.g. >= 252 / 756 / 1260 trading days |
| Liquidity filters | volume/amount rolling median thresholds |
| Data-quality filters | invalid OHLC rows, stale symbols, latest-date coverage |
| Manifest generation | writes generated universe artifact under `webui/rl_runs`, not DB |

Backend/API target:

```text
stom_rl/daily_ohlcv_universe.py
webui/daily_ohlcv_dashboard.py
/api/daily-ohlcv/universe/preview
/api/daily-ohlcv/universe/manifests
```

### Page D2 — Daily Dataset Builder page

Purpose: turn raw daily tables into model-ready supervised/RL datasets.

| Dataset | Target |
|---|---|
| Supervised ranker | symbol/date features and `ret_1d`, `ret_3d`, `ret_5d`, `ret_20d` targets |
| Portfolio RL | per-date top-K candidate panel + next-day return path |
| Regime model | index/breadth/volatility daily features |

Rules:

- split by date, not random rows;
- no future target in normalization;
- preserve stock codes as strings;
- record all feature/target definitions.

### Page D3 — Daily Prediction / Top-K page

Purpose: daily OHLCV deep learning without RL first.

Recommended first models:

| Model | Why |
|---|---|
| simple momentum/volatility baselines | hard to beat, easy to audit |
| supervised classifier | next-N-day positive after cost |
| supervised ranker | Top-K swing candidate selection |
| Kronos-style sequence predictor | use OHLCV/time sequence if daily CSV is built |

Acceptance: must beat no-trade, equal-weight Top-K momentum, and volatility-adjusted baseline after costs and drawdown.

### Page D4 — Daily Portfolio RL page

Purpose: only after D3 passes, train constrained daily RL.

Recommended action contract:

| Action | Meaning |
|---|---|
| `0` | hold/no rebalance |
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

Must compare against:

- no-trade/cash;
- equal-weight Top-K;
- momentum/volatility rule;
- supervised ranker portfolio;
- market index proxy where available.

### Page D5 — Daily Walk-forward / Gate page

Purpose: prevent one lucky split from becoming a false model claim.

Required gates:

| Gate | Required |
|---|---|
| date-based walk-forward | yes |
| purging/embargo | yes for overlapping N-day targets |
| cost/slippage | yes |
| turnover | visible |
| max drawdown | visible |
| fold consistency | multiple folds |
| shuffled/control baseline | yes for alpha claims |
| dashboard verdict | `GO`, `WATCH`, `NO-GO` only; no profit claim |

### Page D6 — Daily Dashboard Progress / Result Visualization layer

Purpose: make daily-model development observable from raw DB readiness through final gate decisions, not only after models finish.

| Visualization area | Required display |
|---|---|
| Development progress timeline | D0 DB analysis → D1 universe → D2 dataset → D3 supervised/ranker → D4 RL → D5 walk-forward gate |
| Stage status cards | `NOT_STARTED`, `RUNNING`, `PASS`, `WATCH`, `NO-GO`, `BLOCKED` with evidence links |
| Artifact registry | latest DB summary, universe manifest, dataset build, training run, prediction run, backtest, RL run, gate report |
| Data coverage charts | tables by market/type, rows by year, symbols with latest date, excluded/unmatched counts |
| Quality charts | invalid OHLC count, short-history distribution, missing latest-date count, stale symbols |
| Universe charts | KOSPI/KOSDAQ counts, common/preferred/ETF/ETN/SPAC/REIT/unknown exclusions |
| Prediction result charts | Top-K return by horizon, hit ratio, calibration/reliability, expected-return buckets |
| Portfolio/RL charts | NAV curve, drawdown, turnover, exposure count, concentration, action distribution, invalid actions |
| Walk-forward charts | fold-by-fold return/MDD/turnover, baseline deltas, shuffled-control comparison |
| Decision panel | final `GO/WATCH/NO-GO`, reasons, blocking gates, exact command/artifact evidence |
| Korean summary panel | user-readable interpretation: 단타/스윙/장기/종목선별 가능 범위 and current blocker |

Recommended backend endpoints:

```text
/api/daily-ohlcv/progress
/api/daily-ohlcv/artifacts
/api/daily-ohlcv/charts/coverage
/api/daily-ohlcv/charts/universe
/api/daily-ohlcv/charts/prediction
/api/daily-ohlcv/charts/portfolio
/api/daily-ohlcv/gate/latest
```

Recommended frontend components:

```text
webui/v2_src/src/tabs/DailyOhlcvTab.svelte
webui/v2_src/src/tabs/dailyOhlcv/DailyProgressTimeline.svelte
webui/v2_src/src/tabs/dailyOhlcv/DailyDbQualityCard.svelte
webui/v2_src/src/tabs/dailyOhlcv/DailyUniverseCard.svelte
webui/v2_src/src/tabs/dailyOhlcv/DailyPredictionResultCard.svelte
webui/v2_src/src/tabs/dailyOhlcv/DailyPortfolioRlCard.svelte
webui/v2_src/src/tabs/dailyOhlcv/DailyWalkForwardGateCard.svelte
```

Read-only rule: these pages may display generated artifacts and run status, but must not mutate `_database/*` or place broker/live orders. Any artifact generation action should be explicit CLI/API workflow under `webui/rl_runs/daily_*`, never hidden dashboard side effects.

## 4. Feasibility by trading style

| Trading style | Daily OHLCV role | Feasibility | Recommended path |
|---|---|---:|---|
| 당일 단타 | pre-market / previous-close watchlist only | low as standalone | daily selection + 1m/1s execution validation |
| 스윙 | 2-10 day Top-K/risk-managed selection | high | supervised ranker first, then daily portfolio RL |
| 장기 | 20-120 day technical selection | medium | add fundamentals/sector later |
| 종목 선별 | market/liquidity/regime filtered daily ranking | high | D1-D3 first |
| 예측 | probability/ranking, not exact price promise | medium | hit probability + expected return buckets |
| 강화학습 | portfolio rebalance after baselines pass | medium | D4 only after D3 gate |

## 5. Recommended execution sequence

| Phase | Deliverable | Status target |
|---|---|---|
| D0 | DB Analysis API/tab | first implementation |
| D1 | Universe Management API/tab and generated manifest | required before modeling |
| D2 | Dataset builder with date splits | required before prediction/RL |
| D3 | Supervised Top-K/ranker baseline | required before RL |
| D4 | Daily Portfolio RL env/train/gate | only after D3 beats baselines |
| D5 | Walk-forward / gate engine | final model decision logic |
| D6 | Dashboard progress/result visualization layer | evidence surface across all stages |

## 6. Non-goals / guardrails

- Do not mutate `_database/Stock_Database_ohlcv_1day.db`.
- Do not train on ETF/ETN/SPAC/REIT/unknown symbols by default.
- Do not call daily OHLCV predictions live-trading ready.
- Do not mix daily RL with opening `ts_imb` results as one strategy.
- Do not implement broker/order routing in dashboard.
