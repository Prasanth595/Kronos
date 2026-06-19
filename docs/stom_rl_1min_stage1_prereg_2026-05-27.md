# Stage 1 — 1-Min-Horizon Signal Probe: Feasibility + Pre-Registration (2026-05-27)

Plan: `.omx/plans/ralplan-stom-rl-1min-signal-2026-05-27.md` (Stage 1 EXIT gates)
Repo: `Kronos` · Branch: `feature/stom-rl-lab` · Baseline: `e5a1116` · Python `py -3.11` · Windows
DB: `_database/stock_tick_back.db` (29.7 GB, read-only `mode=ro` / `query_only=ON`)
Probe (read-only, bounded — NOT committed): `.omx/artifacts/stom_rl_1min_stage1/stage1_1min_prereg_probe.py`
Probe artifact (NOT committed): `.omx/artifacts/stom_rl_1min_stage1/stage1_probe.json`

> This document is the anti-data-mining PRE-REGISTRATION. Every value in §4 is
> LOCKED here, BEFORE any model/training run, and copied verbatim into the
> Stage-4 run report. No post-hoc tuning may alter these constants.

---

## GO / NO-GO — conclusion first

**GO for Stage 2.** All Stage-1 EXIT gates pass:

- **Trend-feature feasibility:** the three source columns backing the four trend
  features are **100.0% non-null post-1-min-resample in every sampled session**
  (worst-case = 1.0, threshold = 0.80) → all `add`, no fallback/drop.
- **`amount` identity (CRITICAL gate):** resolves to **`초당거래대금` (per-second)**,
  EMPIRICALLY confirmed → **1-min aggregation = SUM**; no cumulative-delta
  recomputation needed.
- **V-COVERAGE:** every sampled session yields **27–31 distinct 1-minute buckets**
  (20/20 sessions ≥ 6) → `n_folds ≥ 5` (= 6 disjoint segments) is achievable on a
  **single session**; no stacking required for the fold-count gate. A co-dated
  universe for cross-sectional ranking width is available (≥6 symbols share single
  dates even in a bounded 60-table scan; the prior 1s phase used 111 co-dated).
- **Causal slope formula:** the locked trailing-OLS slope `cov(x,y)/var(x)` over
  the last N bars passed the no-look-ahead self-check (appending future bars
  leaves earlier rows byte-identical).

---

## Method (bounded, read-only, NO full-DB scan)

- Reused the established read-only helpers: `connect_readonly` (`mode=ro`,
  `query_only=ON`), `list_stock_tables`, `_decode_table_columns`,
  `_resolve_source_column`, and `STOM_RL_SOURCE_COLUMNS` — so the probe inspects
  EXACTLY the columns the live feed path (`read_stom_table_rl_source`) resolves.
- **Sample:** 8 symbol tables (`000020 000040 000050 000060 000070 000080 000100
  000120`) × up to 3 distinct sessions each = **20 sessions**, each bounded to
  ≤25 000 rows over the recorded morning window (`ORDER BY index LIMIT 25000`).
- 1-min buckets via `timestamp.dt.floor("min")` (bucket-start labeling, matching
  the planned Stage-2 resampler).
- `amount` identity decided EMPIRICALLY from within-session value shape
  (monotonicity), cross-checked against which candidate column the resolver picks.

---

## 1. Trend-feature feasibility (C-0 style, bounded)

The four trend features derive from three existing source columns. Coverage is
the **worst (minimum) post-1-min-resample non-null %** across all 20 sessions.

| Trend feature(s) | Korean ref | Source column (resolved) | Worst post-resample non-null | Threshold | Verdict |
|---|---|---|---|---|---|
| `ma_close_n`, `volatility_n` | 이동평균(N) / 변동성(N) | `현재가` → `close` | **100.0%** | ≥80% | **add** |
| `amount_slope_n` | 거래대금각도 | `초당거래대금` → `amount` | **100.0%** | ≥80% | **add** |
| `change_rate_slope_n`, `volatility_n` | 등락율각도 / 변동성(N) | `등락율` → `change_rate` | **100.0%** | ≥80% | **add** |

All three source columns are dense at 1-min after resample (no session below the
80% non-null threshold). No fallback or drop is required for any trend feature.
This is consistent with the C-0 probe (`docs/stom_rl_page_c0_feature_probe_2026-05-27.md`),
which already found `등락율` and OHLC ≥99.8% non-null at the 1-s grid.

> `변동성(N)` is computed as the trailing std of `change_rate` (등락율), per the
> plan's §5 table (population/sample std pre-registered in §4). `close` is the
> alternate source if a returns-from-close definition is later preferred — both
> source columns are 100% dense, so either is feasible.

---

## 2. `amount` source-identity verdict (CRITICAL Stage-1 EXIT gate)

**Verdict: `amount` = `초당거래대금` (PER-SECOND) → 1-min resample aggregation = SUM.**

### Resolution evidence
`STOM_RL_SOURCE_COLUMNS["amount"]` candidates (resolution order):
`["초당거래대금", "거래대금", "당일거래대금"]` (`finetune/qlib_stom_pipeline.py:271`).
`_resolve_source_column` returns the FIRST present candidate. Across all 12
tables inspected, every table carries BOTH `초당거래대금` and `당일거래대금`, and
because `초당거래대금` is first in the candidate list, **the resolver always
returns `초당거래대금`** (per-second), never the cumulative `당일거래대금`.

> Note: the C-0 doc's abbreviated column dump listed only `당일거래대금`, which
> could mislead into a "cumulative" assumption. The full column set contains
> `초당거래대금` (per-second), `당일거래대금` (cumulative-daily), and `거래대금증감`
> (per-tick delta); the live resolver picks `초당거래대금` first.

### Empirical per-second confirmation (monotonicity)
Inspecting the actual resolved-column values within each session:

| Symbol / session | first | last | min | max | #decreases | #increases | frac non-decreasing |
|---|---|---|---|---|---|---|---|
| 000020 / 20221212 | 139 | 0 | 0 | 139 | 43 | 44 | 0.903 |
| 000040 / 20230906 | 394 | 8 | 0 | 394 | 601 | 590 | 0.606 |
| 000040 / 20240222 | 700 | 4 | 0 | 700 | 661 | 649 | 0.567 |
| 000050 / 20250512 | 905 | 2 | 0 | 905 | 732 | 718 | 0.586 |
| 000050 / 20251215 | 609 | 10 | 0 | 609 | 741 | 740 | 0.550 |

All 20 sessions classified **per-second**. Decisive signals:
- Values oscillate up AND down every second (#decreases ≈ #increases); a
  cumulative-daily series would be (near-)monotone non-decreasing (frac ≈ 1.0).
- `min = 0` recurs and the series returns to near-0 — a cumulative total cannot
  decrease or reset.
- Magnitudes stay in the hundreds through 09:30; a cumulative daily amount would
  be orders of magnitude larger by mid-session.

### Resulting aggregation
- **`amount` → SUM** over each 1-min bucket (flow semantics).
- **`amount_slope_n` (거래대금각도)** is computed directly on the **per-bar SUMMED
  amount** — NO cumulative-delta (`amount.diff()`) recomputation is needed
  (that branch applies only to the cumulative `당일거래대금` case, which is NOT
  selected). The existing `amount_delta = groupby.diff()`
  (`qlib_stom_pipeline.py:215`) remains a per-bar change of the per-second flow,
  which is consistent.

---

## 3. V-COVERAGE (≥ n_folds+1 = 6 distinct 1-min timestamps)

**PASS on a single session.** Distinct 1-minute buckets per sampled session:

- Range: **27–31** distinct 1-min buckets per session.
- **20 / 20** sessions meet the ≥6 requirement (every session clears it ~5×).
- Recorded window per session ≈ **09:00–09:30 KST** (first ~30 min), e.g.
  `090005 … 092959` → ~30 one-minute bars. This is the expected recording shape
  (open + first 30 min), and ~30 one-min bars is ample for 6 disjoint
  expanding-window segments (n_folds = 5).

**Stacking decision:** single-session coverage already satisfies the fold-count
gate, so co-dated-session stacking is **NOT required** to reach n_folds ≥ 5.
However, the walk-forward ranker needs **cross-sectional width** (many symbols
per timestamp) to rank within each 1-min bar — exactly as the proven-null 1s
phase used 111 co-dated symbols. A co-dated universe is available: even a bounded
60-table scan found single dates shared by 6 symbols (`20231017`, `20230914`,
`20220415`), and the prior phase confirmed 111 co-dated symbols on the full DB.

**Recorded universe plan for Stage 3/4:** use a **co-dated symbol universe on a
single shared session date** (target the 1s-phase 111-symbol co-dated set on its
date), giving ~30 distinct 1-min timestamps (≥6 folds) × ~100+ symbols of
ranking width. If a future need for more timestamps arises, stack additional
co-dated dates for the SAME symbols along the time axis (preserving per-symbol /
per-session grouping) — but this is a contingency, not required for the gate.

---

## 4. LOCKED Pre-Registration (EXIT gates — fixed BEFORE any verdict)

These constants are FROZEN. They are copied verbatim into the Stage-4 run report
and MUST NOT be tuned post-hoc.

| Pre-registration item | LOCKED value | Rationale |
|---|---|---|
| **Trailing window `N`** | **10** (one-min bars) | Plan §10 proposed N=10; with ~30 one-min bars/session, N=10 leaves ample post-warmup rows for 6 folds. `min_periods=1` for level features, `min_periods=2` for slopes. |
| **변동성 ddof** | **0** (population std) | Population std of trailing returns; deterministic and avoids small-sample inflation at the window edge. Matches the plan §5 "population std" note. |
| **`cost_bps`** | **25.0** | Reuse the 1s value verbatim for a clean 1s↔1min decision-rate contrast on the same harness/cost. |
| **`M` (config count)** | **1** | Single pre-registered config — no multi-config search. Keeps the multiplicity correction trivial (no data-mining inflation). |
| **Primary config — algo/policy** | **`supervised_ranker`** | The cheap falsifier; `trained_ppo` is DEFERRED (authorized only if the ranker clears the gate). |
| **Primary config — `top_k`** | **10** | Reuse the 1s-phase top-k (positions selected per bar). |
| **Primary config — `max_positions`** | **10** (= top_k) | Hold the top-k selection; no extra position cap beyond top_k. |
| **Primary config — seed set** | **shuffle-seed `0`** for the mandatory paired shuffle run; ranker is deterministic (no stochastic training). | Reproducible paired real-vs-shuffle comparison. |
| **`n_folds`** | **5** (= 6 disjoint expanding-window segments) | Power floor from the plan (§1.1); avoids the "2/2 majority" trap. |
| **Majority threshold** | **⌈(N+1)/2⌉ = 3 of 5 folds** | The multiplicity-aware strict-majority already implemented in `portfolio_walk_forward.py`. |
| **Holding-period mapping** | **1-bar** = decide every 1-min bar; **fill at T+1** (next 1-min bar) | One-bar step (plan Open-Q §1 proposal CONFIRMED). T+1 fill via the grid-agnostic `condition_screener.py:274` `shift(-1)` = next 1-min bar. |
| **Turnover constraint** | ranker mean turnover ≤ `equal_weight` mean turnover × **1.25** | Plan §1 alpha-gate anti-churn clause. |

### Locked causal slope formula (거래대금각도 / 등락율각도)

**Trailing-OLS slope = `cov(x, y) / var(x)` over the last N bars**, where
`x = [0, 1, …, k-1]` is the within-window bar index and `y` is the series value:

```
slope_T = sum((x_i - x̄)(y_i - ȳ)) / sum((x_i - x̄)^2)   over bars i in [T-N+1, T]
```

implemented as `y.rolling(N, min_periods=2).apply(ols_slope, raw=False)`, grouped
per symbol/session.

- **Causal / trailing only:** window ⊆ `[T-N+1, T]` (bars ≤ current). **NO**
  `shift(-k)`, **NO** `center=True`, **NO** full-series fit.
- **`거래대금각도`** = trailing slope of the per-bar **SUMMED** `amount`
  (per-second → SUM; see §2). NOT a slope of a cumulative series.
- **`등락율각도`** = trailing slope of `change_rate` (등락율).
- **Self-check PASS:** appending future bars (`[…, 99.0, -50.0]`) left every
  earlier-row slope byte-identical to the un-extended computation
  (`extended_overlap_equal_to_base = True`). Base slopes for a monotone test
  series: `[NaN, 2.0, 0.5, 1.4, 1.1, 1.43, …]` — strictly trailing.

> A `min_periods=2` floor means the first bar of each symbol/session has an
> undefined slope → filled to 0.0 by the existing `replace([inf],0).fillna(0)`
> in `build_stom_rl_feature_frame` (`:246`); no look-ahead introduced.

---

## 5. Per-column 1-min resample aggregation table (pre-registered, R2)

The Stage-2 net-new RL resampler (keyed on `"timestamp"`, NOT the OHLCV-only
`_resample_group`) MUST aggregate all 18 canonical source inputs per this table.
Bar labeled at **bucket-start** via `floor("min")`, `close = last`.

| Source column(s) | Class | 1-min aggregation |
|---|---|---|
| `open` | OHLC | **first** |
| `high` | OHLC | **max** |
| `low` | OHLC | **min** |
| `close` (현재가) | OHLC | **last** |
| `초당매수수량` (buy_qty_1s) | flow | **SUM** |
| `초당매도수량` (sell_qty_1s) | flow | **SUM** |
| `volume` (= buy+sell, derived) | flow | **SUM** |
| **`amount` (`초당거래대금`, per-second — §2)** | flow | **SUM** |
| `매수총잔량` (bid total qty) | order-book | **last** |
| `매도총잔량` (ask total qty) | order-book | **last** |
| `매수호가1` (bid price 1) | order-book | **last** |
| `매도호가1` (ask price 1) | order-book | **last** |
| `등락율` (change_rate) | rate/snapshot | **last** |
| `회전율` (turnover_rate) | rate/snapshot | **last** |
| `시가총액` (market_cap) | rate/snapshot | **last** |
| `고저평균대비등락율` (high_low_mid) | rate/snapshot | **last** |
| `체결강도` (trade_strength) | rate/snapshot | **last** |

> `amount` is in the **flow → SUM** class because §2 resolved it to the
> per-second `초당거래대금`. (Had it resolved to cumulative `당일거래대금`, it would
> be order-book/rate → LAST with a per-bar-delta recompute — that branch does NOT
> apply.) Derived per-bar features (`net_buy_qty_1s`, `bid_ask_imbalance`,
> `spread_ticks`, `amount_delta`, trailing means/slopes) are recomputed by
> `build_stom_rl_feature_frame` on the already-resampled 1-min frame.

---

## 6. Gate summary

| Gate | Result |
|---|---|
| Trend-feature feasibility (≥80% non-null post-resample) | **PASS** (100% all sessions) |
| `amount` identity (per-second vs cumulative) | **per-second** (`초당거래대금`) → **SUM** |
| V-COVERAGE (≥6 distinct 1-min buckets) | **PASS** (27–31/session, 20/20) |
| Pre-registration locked (N, ddof, cost_bps, M, config, holding, slope) | **LOCKED** (§4) |
| Per-column aggregation table | **LOCKED** (§5) |
| Causal slope no-look-ahead self-check | **PASS** |

**GO for Stage 2** (net-new RL resampler + `freq` through the live feed + the four
causal trend features). PPO remains DEFERRED behind the Stage-4 alpha gate.

---

## Constraints honored
- Read-only DB (`mode=ro`, `query_only=ON`); bounded sampling only (8 symbols ×
  ≤3 sessions × ≤25 000 rows; column discovery ≤60 tables); **no full-DB scan**.
- No `eval` / `exec` / `__`-dunder tricks. No production code changes (this is a
  decisions/feasibility stage). Causal-only formulas (trailing windows ≤ T).
