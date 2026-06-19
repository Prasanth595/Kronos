# STOM Portfolio — 1-Minute-Horizon Tradeable-Selection-Alpha Verdict (NON-ADVISORY)

Plan: `.omx/plans/ralplan-stom-rl-1min-signal-2026-05-27.md` (Stages 3–5)
Pre-registration (LOCKED, M=1): `docs/stom_rl_1min_stage1_prereg_2026-05-27.md`
Repo: `Kronos` · Branch: `feature/stom-rl-lab` · Baseline: `20fb0fe` · Python `py -3.11` (3.11.9) · Windows
Evidence artifacts (NOT committed — `.omx/` is gitignored): `.omx/artifacts/stom_rl_1min_signal/`
Date: 2026-05-27

---

## 0. The decisive question + the answer up front

> Does tradeable stock-selection alpha appear at the **1-minute** horizon (with the four new
> causal trend features), NON-ADVISORY (`n_folds = 5 ≥ 5`), measured by the cheap
> `supervised_ranker` vs baselines after **25 bps** cost + the **mandatory shuffle test**?
> This directly contrasts the PROVEN-null 1-second result.

### NON-ADVISORY VERDICT: **NO.** There is no tradeable stock-selection edge at the 1-minute horizon either.

Widening the decision horizon 60× (1s → 1min) and adding the trend/momentum feature class the
1s set lacked (이동평균 / 변동성 / 거래대금각도 / 등락율각도) **did not change the conclusion.**
On the same co-dated universe (111 symbols, 2022-08-30, 09:00–09:30), with the same harness and the
same 25 bps cost, the cheap `supervised_ranker`:

- **Beats `equal_weight` on only 2 of 5 disjoint folds** — FAILS the pre-registered strict-majority
  threshold of 3/5.
- **Loses to `no_trade` on the mean** (ranker mean cost-adjusted return **−0.1023%** vs `no_trade`
  **0.0000%**) — every active policy bleeds money after cost.
- **Does NOT survive the shuffle test — and fails it in the most damning way possible:** the SHUFFLED
  signal scores a **3/5** majority over `equal_weight` while the REAL signal scores only **2/5**. The
  real selection signal is **no better than (indeed slightly worse than) destroyed-signal noise**, so
  there is no real edge for the shuffle to "fail to reproduce."

This is the expected, valid completion (plan §0, Principle 4): a documented NON-ADVISORY negative,
reported with real per-fold numbers, not massaged. **Deep-RL (MaskablePPO, `sb3-contrib`) is NOT
justified** — the cheap falsifier finds nothing at 1-min, so the expensive path stays DEFERRED. The
honest next direction is a **daily / multi-day horizon or external signal**, NOT more intraday RL.

---

## 1. Universe / session + per-fold candidate counts

| Choice | Value | Rationale |
|---|---|---|
| Session | **2022-08-30** (`20220830`) | The most-co-dated session established by the 1s phase (112 tables → **111** real 6-digit stock tables). Reused verbatim for a clean **1s↔1min controlled contrast** on the identical harness/universe/cost (bounded co-dated probe, NO full-DB scan). |
| Window | **09:00:00 – 09:30:00** | The full recorded window for these symbols (open + first 30 min). |
| Symbols | **111 co-dated** (67 produced ≥1 candidate) | Bounded read of one session × 111 tables × 30-min window. NOT a full-universe scan. |
| Rule | **`buy_demand_pressure`** | The most permissive rule — gives the ranker the largest, fairest candidate pool to find selection signal in. |
| Freq | **`1min`** | Stage-2 net-new RL resampler (per-column SUM/LAST semantics, `floor("min")`, `close=last`); resampled BEFORE the feature builder. |
| Cost | **`cost_bps = 25`** (explicit) | Reused from the 1s phase for a clean decision-rate contrast. No zero-cost victory laps. |

### 1-min candidate generation (Stage 3)

`py -3.11 -m stom_rl.candidate_gen --freq 1min` →
**296 candidates · 292 fillable · 4 unfillable (last-bar T+1=NaN) · 31 distinct 1-min timestamps.**
T+1 fill contract preserved (grid-agnostic `condition_screener.py:274` `shift(-1)` = next 1-min bar).

### Per-fold candidate counts (`n_folds = 5`, expanding-window disjoint holdout)

| Fold | TRAIN candidates | TEST candidates | TEST window (disjoint, strictly later) |
|---|---|---|---|
| 0 | 118 | 67 | 09:06:00 – 09:10:00 |
| 1 | 185 | 38 | 09:11:00 – 09:15:00 |
| 2 | 223 | 24 | 09:16:00 – 09:20:00 |
| 3 | 247 | 20 | 09:21:00 – 09:25:00 |
| 4 | 267 | 29 | 09:26:00 – 09:30:00 |

(31 distinct 1-min timestamps → 6 disjoint time segments → 5 evaluated folds. V-COVERAGE cleared:
31 ≥ 6.)

---

## 2. Gate ordering (R7) — feature-integrity gates BEFORE the alpha verdict

The plan makes feature non-degeneracy a hard precondition for the alpha verdict (a constant/zero
feature shuffles to itself and would pass the shuffle test vacuously, manufacturing a false null).

### V-NONDEGEN (ran FIRST, on the actual 1-min candidate set) — **PASS**

Every gate-named 1-min feature column has strictly non-zero variance and ≥2 distinct values, so the
silent-zero false-null hazard (pre-mortem #4) is ruled out. Critically, the **four new trend features
are genuinely non-degenerate at 1-min**:

| 1-min feature (`feature_*`) | variance (ddof=0) | distinct values | non-degenerate? |
|---|---|---|---|
| `trade_strength` | 9,706.74 | 271 | yes |
| `bid_ask_imbalance` | 0.008552 | 289 | yes |
| `change_rate` | 14.3024 | 176 | yes |
| `moving_average_n` (이동평균) | 2,798,169,941.18 | 266 | yes |
| `volatility_n` (변동성) | 0.7232 | 250 | yes |
| `amount_slope_n` (거래대금각도) | 77,422.78 | 262 | yes |
| `change_rate_slope_n` (등락율각도) | 0.4170 | 255 | yes |

### V-COVERAGE — **PASS** (31 distinct 1-min timestamps ≥ 6; 67 symbols produced candidates)

Because V-NONDEGEN + V-COVERAGE PASS, the alpha verdict below counts: the features are real, so the
shuffle/majority gates have teeth.

---

## 3. Pre-registration (LOCKED at Stage 1 — copied verbatim, M=1, NO post-hoc tuning)

| Item | LOCKED value |
|---|---|
| freq | **1min** |
| Trailing window `N` | **10** one-min bars |
| 변동성 ddof | **0** (population std) |
| `cost_bps` | **25.0** |
| `M` (config count) | **1** |
| Primary policy | **`supervised_ranker`** (`trained_ppo` DEFERRED) |
| `top_k` / `max_positions` | **10 / 10** |
| `n_folds` / majority | **5** / **⌈6/2⌉ = 3 of 5** |
| Holding / fill | **1-bar step**; fill at **T+1** (next 1-min bar) |
| Turnover gate | ranker mean turnover ≤ `equal_weight` × **1.25** |
| `amount` aggregation | **SUM** (`초당거래대금`, per-second — Stage-1 §2) |
| Shuffle seed | **0** (paired real-vs-shuffle) |

`M = 1` ⇒ no Bonferroni/BH correction owed (single pre-registered config; no config search).
`n_folds = 5 ≥ 5` ⇒ the verdict is **NON-ADVISORY**. The pre-registration was honored exactly; no
constant was tuned after seeing results. (`--max-steps-per-fold 0` = no truncation, so the full TEST
segment of each fold is evaluated — the only run parameter not numerically pinned by the
pre-registration, chosen for honesty, not to favor any policy.)

---

## 4. The numbers (REAL, cost-adjusted `return_pct`, `cost_bps = 25`, `n_folds = 5`)

### Per-fold cost-adjusted return % (REAL, seed 100)

| Policy | f0 | f1 | f2 | f3 | f4 | **mean** | vs `no_trade` |
|---|---|---|---|---|---|---|---|
| `no_trade` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **0.0000** | — (baseline) |
| `equal_weight_candidate` | −0.1420 | −0.2194 | −0.1856 | −0.2041 | −0.5391 | **−0.2580** | loses |
| `buy_and_hold` | −0.1420 | −0.2194 | −0.1856 | −0.2041 | −0.5391 | **−0.2580** | loses |
| `rule_baseline` | −0.2372 | −0.2500 | −0.2784 | −0.0961 | −0.6016 | **−0.2927** | loses |
| **`supervised_ranker`** | −0.7843 | +0.8141 | −0.2469 | −0.2203 | −0.0739 | **−0.1023** | **loses** |

### Worst-fold MDD / mean turnover / mean trades (REAL)

| Policy | worst-fold MDD % | mean turnover | mean trades |
|---|---|---|---|
| `no_trade` | 0.0000 | 0 | 0.0 |
| `equal_weight_candidate` | −0.5391 | 997,506 | 4.0 |
| **`supervised_ranker`** | **−0.7843** | 997,506 | 4.0 |

The ranker's **worst-fold MDD (−0.7843%) is worse than equal_weight's (−0.5391%)**. Its single
positive fold (f1, +0.8141%) is one lucky draw against four losing/break-even folds — the mean stays
negative and below `no_trade`.

### `supervised_ranker` vs `equal_weight_candidate` — per-fold win/loss (REAL)

| Fold | ranker % | equal_weight % | diff | result |
|---|---|---|---|---|
| 0 | −0.7843 | −0.1420 | −0.6424 | lose |
| 1 | +0.8141 | −0.2194 | +1.0335 | WIN |
| 2 | −0.2469 | −0.1856 | −0.0613 | lose |
| 3 | −0.2203 | −0.2041 | −0.0162 | lose |
| 4 | −0.0739 | −0.5391 | +0.4652 | WIN |

**REAL majority over `equal_weight`: 2/5 folds** → strict-majority threshold (3/5) **NOT met.**

---

## 5. Mandatory shuffle / permutation sanity check (LOCKED shuffle-seed 0)

Mechanism (`stom_rl/portfolio_walk_forward.py:shuffle_candidate_signal`): within each timestamp, the
values of `rank_score` AND every `feature_*` column are **OVERWRITTEN** with an independent
within-timestamp permutation, while `price`/`fill_price`/`symbol`/`fillable` are left untouched — so
fills and cost accounting are byte-identical and ONLY the selection signal is destroyed.

### REAL vs SHUFFLE — `supervised_ranker` win-rate over `equal_weight`

| Run | ranker wins vs EW | ranker mean % | EW mean % | ranker beats `no_trade`? |
|---|---|---|---|---|
| REAL, seed 100 | **2/5** | −0.1023 | −0.2580 | NO |
| SHUFFLE, seed 0 | **3/5** | −0.0436 | −0.2353 | NO |

**Reading the shuffle result (decisive):** the destroyed-signal SHUFFLE achieves a **higher** majority
(3/5) and a **better** mean (−0.0436%) than the REAL signal (2/5, −0.1023%). When random noise
out-selects your model, the model carries **no real selection information**. There is no positive,
shuffle-surviving edge — the alpha gate's shuffle clause fails outright. (Neither REAL nor SHUFFLE
beats `no_trade`: every active policy loses to cash after 25 bps.)

---

## 6. NON-ADVISORY verdict + the alpha gate, item by item

| Alpha-gate clause | Result |
|---|---|
| Ranker beats `equal_weight` on strict majority (≥3/5) — REAL | **FAIL** (2/5) |
| Ranker beats `no_trade` on the mean — REAL | **FAIL** (−0.1023% < 0.0000%) |
| Turnover gate (ranker ≤ EW × 1.25) | pass (ranker turnover ≈ EW; moot given the above) |
| Survives shuffle (real majority holds, shuffle does NOT reproduce it) | **FAIL** (shuffle 3/5 ≥ real 2/5) |
| Multiplicity (M=1, n_folds=5≥5, pre-registration honored) | clean (no correction owed) |

> ### VERDICT: There is NO tradeable stock-selection edge at the 1-minute horizon on this universe/feature set.
> ### Deep-RL (MaskablePPO) is NOT justified. PPO stays DEFERRED. STOP — do not spend RL compute here.

### Pivot recommendation (invest in SIGNAL/horizon, NOT more intraday RL)

1. **Pivot to a daily / multi-day horizon**, where a 25 bps round-trip is a far smaller fraction of the
   per-decision move and trend/momentum signals have a documented a-priori plausibility. The Stage-2
   net-new RL resampler + the four causal trend features are **durable, reusable infrastructure** for
   this pivot (daily relocates — does not escape — the same aggregation hazard, already solved).
2. **Or ingest an external / cross-sectional signal** (fundamentals, sector/regime context, news/flow)
   that the intraday tick feed does not contain.
3. **Do NOT** install `sb3-contrib`/MaskablePPO or launch a multi-hour full-universe RL run on this
   data — the cheap supervised floor failed at both 1s and 1min, so the binding constraint is
   confirmed to be **signal/data + intraday market efficiency**, not the algorithm.

---

## 7. Direct 1s ↔ 1min contrast — did widening the horizon change the conclusion?

**No.** Same universe (111 co-dated symbols, 2022-08-30), same harness, same 25 bps cost, same cheap
`supervised_ranker`, same mandatory shuffle test — only the decision horizon (and the added trend
feature class) changed.

| Dimension | 1-second (proven null) | **1-minute (this verdict)** |
|---|---|---|
| Decision rate | every 1s (~1,800 bars/session) | every 1min (~31 bars/session, ~60× fewer) |
| Features | 18 microstructure | 22 (incl. 4 causal trend features) |
| Ranker beats EW (REAL) | nominal 3/5 (a +0.0001% tie mirage) | **2/5 (majority NOT met)** |
| Ranker mean vs `no_trade` | loses (−0.1472% < 0) | loses (−0.1023% < 0) |
| Shuffle outcome | real 3/5 → shuffle 1/5 & 2/5 (thin edge, no magnitude) | **real 2/5 ≤ shuffle 3/5 (noise out-selects the model)** |
| Beats `no_trade`? | NO | **NO** |
| Verdict | NON-ADVISORY NO | **NON-ADVISORY NO** |

Amortizing the cost 60× and adding trend/momentum features did NOT surface a tradeable selection
edge. If anything, the 1-min shuffle result is **more damning** than the 1s one: at 1s the real signal
at least beat its shuffle (3/5 vs 1–2/5, a thin but real-direction edge with no magnitude); at 1-min
the real signal is beaten BY its own shuffle (2/5 vs 3/5). The conclusion is robust across the horizon
change: **intraday stock-selection alpha is absent for this data/feature set** — the next informative
experiment is a longer (daily/multi-day) horizon or external data, not more intraday RL.

---

## 8. Anti-false-alpha guard status

| Guard | Status |
|---|---|
| V-NONDEGEN (1-min features non-zero variance — ran BEFORE the alpha gate, R7) | **PASS** (incl. all 4 trend features) |
| V-COVERAGE (≥6 distinct 1-min timestamps) | **PASS** (31) |
| Disjoint, strictly-later holdout (runtime asserts, `portfolio_walk_forward.py` L691-696) | **PASS** (both runs exited 0; no AssertionError across 5 folds) |
| Explicit non-zero `cost_bps` in eval | **PASS** (`cost_bps = 25` on every fold row) |
| Mandatory shuffle / permutation test (LOCKED shuffle-seed 0) | **RUN** — real 2/5 ≤ shuffle 3/5 (edge does NOT survive) |
| Supervised-ranker floor | **REPORTED** — the floor model finds no edge over `no_trade`/`equal_weight`; RL correctly NOT run |
| Multiplicity + power (M=1, n_folds=5≥5) | `M = 1` (no correction owed) AND `n_folds = 5 ≥ 5` → **NON-ADVISORY** |
| Pre-registration honored (M=1, no post-hoc tuning) | **YES** — §3 constants used verbatim from the LOCKED Stage-1 doc |

---

## 9. Reproduction

All commands `py -3.11`, from repo root, `PYTHONUTF8=1` (console encoding). Artifacts land under
`.omx/artifacts/stom_rl_1min_signal/` (gitignored). The candidate build (111 symbols, 2022-08-30,
09:00–09:30) is a bounded per-session read — never a full-DB scan.

```bash
# Stage 3 — 1-min candidates (buy_demand_pressure, top_k report=10):
py -3.11 -m stom_rl.candidate_gen \
  --db _database/stock_tick_back.db \
  --tables <111 co-dated symbols of 2022-08-30> \
  --session 20220830 --time-start 090000 --time-end 093000 \
  --freq 1min \
  --rules stom_rl/rules/buy_demand_pressure.json \
  --output  .omx/artifacts/stom_rl_1min_signal/cand_buy_demand_pressure_20220830_1min.csv \
  --topk-report .omx/artifacts/stom_rl_1min_signal/topk_report_1min.json --top-k 10

# Stage 4 (REAL) — n_folds=5, all baselines + ranker, explicit cost, top_k=max_pos=10:
py -3.11 -m stom_rl.portfolio_walk_forward \
  --candidate-csv .omx/artifacts/stom_rl_1min_signal/cand_buy_demand_pressure_20220830_1min.csv \
  --output-dir   .omx/artifacts/stom_rl_1min_signal/real \
  --baselines no_trade,equal_weight_candidate,buy_and_hold,rule_baseline,supervised_ranker \
  --n-folds 5 --cost-bps 25 --top-k-candidates 10 --max-positions 10 --max-steps-per-fold 0 --seed 100

# Stage 4 (SHUFFLE) — same config + LOCKED shuffle-seed 0:
py -3.11 -m stom_rl.portfolio_walk_forward \
  --candidate-csv .omx/artifacts/stom_rl_1min_signal/cand_buy_demand_pressure_20220830_1min.csv \
  --output-dir   .omx/artifacts/stom_rl_1min_signal/shuffled \
  --baselines no_trade,equal_weight_candidate,buy_and_hold,rule_baseline,supervised_ranker \
  --n-folds 5 --cost-bps 25 --top-k-candidates 10 --max-positions 10 --max-steps-per-fold 0 --seed 100 \
  --shuffle-signal --shuffle-seed 0
```

Both walk-forward runs exit 0 with real 5-fold output.

---

*Stage 3–5 NON-ADVISORY 1-min signal verdict. Doc-only deliverable; the supporting `.omx/` artifacts
are intentionally not committed. M=1 pre-registration (`docs/stom_rl_1min_stage1_prereg_2026-05-27.md`)
honored exactly — no post-hoc tuning.*
