# STOM Portfolio — Ranker-First NON-ADVISORY Signal Test (Stage D, n_folds≥5)

Plan: `.omx/plans/ralplan-stom-rl-deep-rl-2026-05-27.md` (P0-1 alpha gate, §7 shuffle test, §7a supervised-ranker floor)
Repo: `Kronos` · Branch: `feature/stom-rl-lab` · Baseline: `dd5fd7a` · Python `py -3.11` (3.11.9) · Windows
Evidence artifacts (NOT committed, `.omx/` is gitignored): `.omx/artifacts/deep_rl/signal_test/`
Date: 2026-05-27

---

## 0. The decisive question (and the answer up front)

> **Before committing expensive multi-hour deep-RL (MaskablePPO), answer cheaply and NON-ADVISORY: does ANY tradeable selection edge exist in this data?**

**NON-ADVISORY VERDICT: NO. There is no tradeable stock-selection edge in this data/feature set.**

The cheap `supervised_ranker` was given its *best fair shot* — the most permissive candidate
pool (`buy_demand_pressure`, 11,336 candidates), the largest co-dated universe we could find
(111 symbols on 2022-08-30), and a real `n_folds = 5` expanding-window holdout (which **lifts the
P0-1 advisory-only restriction** — alpha may now be claimed *or rejected* non-advisory). The result:

- The ranker's **mean cost-adjusted return (−0.1472%) is WORSE than `equal_weight` (−0.1206%)**.
- **Neither beats `no_trade` (exactly 0.000%)** — every active policy *loses money* after 25 bps cost.
- The ranker's nominal "3/5 fold majority" over `equal_weight` is a **mirage**: it is driven by one
  0.0001%-margin tie (the ranker degenerating to equal-weight) plus one 0.0298% win, and it
  **does NOT survive the mandatory shuffle test** (collapses to 1/5 and 2/5 under two shuffle seeds).

So even the cheap supervised model — which has no MaskablePPO masking pathology — finds nothing.
**The binding constraint is SIGNAL / DATA, not the algorithm. Deep-RL (MaskablePPO) is NOT worth
the compute on this data/feature set.** This confirms, now at the non-advisory `n_folds ≥ 5` power
level, the advisory direction already recorded in `docs/stom_rl_deep_rl_verdict_2026-05-27.md`.

A documented negative is the expected, valid outcome of this phase (plan §0, Principle 4). The
result is reported with real per-fold numbers and is not massaged.

---

## 1. Universe / window chosen (and why)

`n_folds` splits the **TIME axis** (expanding-window holdout), not symbols — so `n_folds ≥ 5` is
achieved with a single session by using a longer window and more co-dated symbols, **without a
full-universe run**.

| Choice | Value | Rationale |
|---|---|---|
| Session | **2022-08-30** | Probed the DB (bounded per-table `DISTINCT substr(index,1,8)` column scans, never a full payload scan): this session has the **most co-dated symbols (112 tables → 111 real 6-digit stock tables** after dropping the `moneytop` metadata table). |
| Window | **09:00:00 – 09:30:00** | The *full* recorded window for these symbols (recording itself is bounded to the open + first 30 min; there is no later data to widen into). 1,800-second common grid. |
| Symbols | **111** | Bounded read (one session, 111 symbols, 30-min window). NOT the 2,427-table full universe. |
| Rule | **`buy_demand_pressure`** | The most permissive of the three rules — gives the ranker the largest, fairest candidate pool to find selection signal in (a more permissive pool is *fairer* for a "does selection signal exist?" test). |
| Cost | **`cost_bps = 25`** (explicit) | No zero-cost victory laps. |

Candidate-pool comparison across the three rules on this universe (why `buy_demand_pressure` was chosen):

| Rule | Candidates | Distinct timestamps | Timestamps with ≥2 candidates | Mean / max passing per ts |
|---|---|---|---|---|
| **`buy_demand_pressure`** (chosen) | **11,336** | **1,795** | **1,750** | **6.32 / 22** |
| `buy_widev1` | 1,574 | 1,025 | 392 | 1.54 / 6 |
| `buy_widev2` | 1,055 | 823 | 196 | 1.28 / 4 |

`buy_demand_pressure` has ~10× the candidates and, critically, **1,750 timestamps with ≥2 competing
candidates** — i.e. 1,750 real selection decisions for the ranker to get right. This is the data
giving any selection model its best chance.

### Per-fold candidate counts (`n_folds = 5`, expanding window)

| Fold | TRAIN candidates | TEST candidates | TEST window |
|---|---|---|---|
| 0 | 3,366 | 2,169 | 09:05:01–09:09:59 |
| 1 | 5,535 | 1,806 | 09:10:00–09:14:58 |
| 2 | 7,341 | 1,428 | 09:14:59–09:19:59 |
| 3 | 8,769 | 1,235 | 09:20:00–09:25:00 |
| 4 | 10,004 | 1,332 | 09:25:01–09:30:00 |

Every fold has >1,200 held-out candidates — far above the thin 3-symbol / 09:00–09:30 advisory
setup of the prior Stage-E verdict. The `n_folds ≥ 5` power floor (P0-1) is genuinely cleared.

---

## 2. Pre-registration (P0-1 — recorded BEFORE reading the test-fold metrics)

Per the plan's hard data-mining guard, the search space is pre-registered so the verdict cannot be
a post-hoc cherry-pick:

- **Primary config (the ONE pre-named config):** `policy = supervised_ranker`, `rule = buy_demand_pressure`,
  `n_folds = 5`, `top_k_candidates = 3`, `max_positions = 2`, `seed = 100`, `max_steps_per_fold = 24`,
  `cost_bps = 25.0`.
- **Full candidate config set:** exactly one — the primary config above.
- **`M` = distinct configs evaluated on test folds = 1.** (`trained_ppo` was deferred — it needs
  MaskablePPO/`sb3-contrib` for a fair attempt, and per the ranker-first plan it is only worth
  installing *if the ranker shows an edge*. The ranker did not, so RL was correctly not run.)
- **Multiplicity note:** `M = 1` ⇒ **no Bonferroni/BH correction is owed** (there is nothing to
  correct across — a single pre-registered config, no config search). The second seed (200) and the
  two shuffle seeds (100, 7) are **robustness checks on the same primary config**, not new configs,
  so they do not inflate `M`.
- **`n_folds = 5 ≥ 5`** ⇒ the P0-1 power floor is cleared ⇒ **this verdict is NON-ADVISORY.**

---

## 3. The numbers (real, cost-adjusted `return_pct`, `cost_bps = 25`, `n_folds = 5`)

### REAL data — per-fold cost-adjusted return %

| Policy | f0 | f1 | f2 | f3 | f4 | **mean** | vs `no_trade` |
|---|---|---|---|---|---|---|---|
| `no_trade` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **0.0000** | — (baseline) |
| `equal_weight_candidate` | −0.2148 | −0.0360 | −0.0724 | −0.1548 | −0.1250 | **−0.1206** | loses |
| `buy_and_hold` | −0.2148 | −0.0360 | −0.0724 | −0.1548 | −0.1250 | **−0.1206** | loses |
| `rule_baseline` | −1.4794 | −1.1614 | −1.3828 | −1.5225 | −1.5348 | **−1.4162** | loses badly |
| **`supervised_ranker`** | −0.1480 | −0.1250 | −0.2134 | −0.1250 | −0.1250 | **−0.1472** | **loses** |

### MDD / turnover / trades (REAL, mean over folds)

| Policy | worst-fold MDD % | mean turnover | mean trades |
|---|---|---|---|
| `no_trade` | 0.0000 | 0 | 0.0 |
| `equal_weight_candidate` | −0.2148 | 499,900 | 2.0 |
| `supervised_ranker` | **−0.3420** | 499,844 | 2.0 |

The ranker's worst-fold MDD (−0.3420%) is **worse** than equal_weight's (−0.2148%), and its mean
return is worse — so even the components of the alpha gate beyond the fold-majority point the wrong way.

### `supervised_ranker` vs `equal_weight_candidate` — per-fold win/loss (REAL, seed 100)

| Fold | ranker % | equal_weight % | diff | result |
|---|---|---|---|---|
| 0 | −0.1480 | −0.2148 | +0.0668 | WIN |
| 1 | −0.1250 | −0.0360 | −0.0889 | lose |
| 2 | −0.2134 | −0.0724 | −0.1409 | lose |
| 3 | −0.1250 | −0.1548 | +0.0298 | WIN |
| 4 | −0.1250 | −0.1250 | **+0.0001** | WIN (a tie — ranker ≈ equal_weight) |

Nominal score: **3/5 folds** (strict majority threshold = ⌈6/2⌉ = 3, so the fold-count criterion is
*nominally* met). **But this is a mirage:** fold 4 is a +0.0001% "win" (the ranker degenerated to the
same top-k as equal-weight — a tie, not selection skill), and the ranker's MEAN is still worse than
equal-weight and worse than `no_trade`. A fold majority that vanishes when you look at magnitude,
mean, drawdown, and the shuffle test (§4) is not an edge.

---

## 4. Mandatory shuffle / permutation sanity check (plan §7, V8/V8b)

**Mechanism (implemented this session, `stom_rl/portfolio_walk_forward.py:shuffle_candidate_signal`):**
within each timestamp, the values of `rank_score` AND every `feature_*` column are **OVERWRITTEN**
with an independent within-timestamp permutation. This is critical: `PortfolioEnv._current_candidates`
re-sorts by `rank_score` before `head(top_k)` (`portfolio_env.py:374`), so shuffling row *order* alone
is a no-op — only overwriting the score *values* changes which candidates the env selects.
`price` / `fill_price` / `symbol` / `timestamp` / `fillable` are left untouched, so fills and cost
accounting are byte-identical to the real run; ONLY the selection signal is destroyed.

A unit test (V8b, `test_shuffle_changes_candidate_selection_order`) asserts the shuffle yields a
*different* top-k selection at ≥1 timestamp (it is not silently cancelled by the env re-rank), and a
companion test asserts `price`/`fill_price`/`symbol` are untouched.

### Real vs shuffled — `supervised_ranker` win-rate over `equal_weight`

| Run | ranker wins vs EW | ranker mean % | EW mean % | ranker beats `no_trade`? |
|---|---|---|---|---|
| REAL, seed 100 | **3/5** | −0.1472 | −0.1206 | NO |
| REAL, seed 200 | **3/5** | −0.1472 | −0.1206 | NO |
| SHUFFLE, seed 100 | **1/5** | −0.2469 | −0.2508 | NO |
| SHUFFLE, seed 7 | **2/5** | −0.1011 | −0.1190 | NO |

**Reading the shuffle result:** the nominal 3/5 real majority collapses to 1/5 and 2/5 once the
selection signal is destroyed — so the 3/5 is *partly* a property of the real signal (good: it is not
purely noise-mined; if it were, the shuffle would also produce ~3/5). **But the real edge is itself so
thin that it loses to `equal_weight` on the mean and loses to `no_trade` in every case** — there is no
positive edge for the shuffle to "fail to reproduce." The shuffle confirms the marginal fold-majority
is not a robust, magnitude-bearing selection edge.

**Seed agreement (V9):** seed 100 and seed 200 produce identical real results — the eval is
deterministic on this data; the negative direction is not a single-seed fluke.

---

## 5. Anti-false-alpha guard status

| Guard | Status |
|---|---|
| Column leakage canary (real signal-test data path: inject perfect-foresight future column → fold report unchanged) | **PASS** |
| Disjoint, strictly-later holdout (runtime asserts `portfolio_walk_forward.py` L460-465) | **PASS** (run exited 0; no AssertionError across all 5 folds) |
| Explicit non-zero `cost_bps` in eval | **PASS** — `cost_bps = 25` logged on every fold row |
| **Mandatory shuffle / permutation test (§7, V8/V8b)** | **RUN** — implemented + unit-tested; real 3/5 → shuffle 1/5 & 2/5 (marginal majority does not survive) |
| Supervised-ranker floor (P1-5 / §7a) | **REPORTED** — the ranker (the floor model) itself finds no edge over `no_trade`/`equal_weight`; RL was not run because the floor failed |
| ≥2-seed agreement (V9) | **PASS** — seed 100 ≡ seed 200 (identical), both shuffle seeds agree on direction |
| Multiplicity + power (P0-1 / V9c) | `M = 1` (no correction owed) AND `n_folds = 5 ≥ 5` → **NON-ADVISORY**; verdict is a real rejection, not advisory |

---

## 6. NON-ADVISORY verdict + recommendation

**Does `supervised_ranker` beat `equal_weight` after cost on a strict majority of the ≥5 disjoint
folds AND survive the shuffle test?**

- Beat `equal_weight` on a strict majority of folds? **Nominally 3/5 — but a mirage** (one 0.0001%
  tie + mean return *worse* than equal_weight + worse worst-fold MDD).
- Survive the shuffle test? **NO** — the 3/5 collapses to 1/5 / 2/5 under shuffle.
- Beat `no_trade`? **NO** — every active policy loses money after 25 bps cost.

> ### VERDICT: There is NO tradeable stock-selection edge in this data/feature set.
> ### Deep-RL (MaskablePPO) is NOT worth the compute. STOP — do not invest more in RL machinery.

**Why this is the honest reading:** the cheapest model that does NOT suffer PPO's masking pathology
(the supervised ranker, on the same causal features and the same disjoint holdout) cannot beat
doing nothing after cost, even given the most permissive candidate pool and the largest co-dated
universe available in a single session. Per the plan's P1-5 supervised-ranker floor and the
ranker-first decision rule, deep-RL is only worth the multi-hour MaskablePPO compute *if the ranker
shows an edge first*. It does not. The binding constraint is **signal / data**, not the algorithm.

**Recommended next direction (invest in SIGNAL, not algorithm):**
1. The 18-feature set + `buy_demand_pressure` selection captures no post-cost selection alpha at the
   1-second open-auction horizon on this universe. Before any RL: test **richer / different features**
   (e.g. longer trailing windows, cross-sectional ranks, order-book microstructure) and/or a
   **longer holding horizon** where a 25 bps round-trip cost is less dominant — the open-auction
   1-second churn is heavily cost-bound (the active policies bleed ~0.12–0.15% to cost while the
   underlying moves are tiny).
2. Only if a *supervised* ranker clears the alpha gate (beats `no_trade` AND `equal_weight` on a
   strict majority of `n_folds ≥ 5` folds AND survives shuffle) should `sb3-contrib`/MaskablePPO be
   installed and a fair RL attempt made. That precondition is **not met**.
3. A multi-hour full-universe run is **not** justified by this evidence — it would most likely
   reproduce the same no-edge result at higher compute cost.

---

## 7. Reproduction

All commands `py -3.11`, from repo root. Artifacts land under `.omx/artifacts/deep_rl/signal_test/`
(gitignored).

```bash
# Real run (n_folds=5, all baselines, explicit cost):
py -3.11 -m stom_rl.portfolio_walk_forward \
  --candidate-csv .omx/artifacts/deep_rl/signal_test/cand_buy_demand_pressure_20220830.csv \
  --output-dir .omx/artifacts/deep_rl/signal_test/real \
  --baselines no_trade,equal_weight_candidate,buy_and_hold,rule_baseline,supervised_ranker \
  --n-folds 5 --cost-bps 25 --top-k-candidates 3 --max-positions 2 --seed 100

# Mandatory shuffle test (same config + --shuffle-signal):
py -3.11 -m stom_rl.portfolio_walk_forward \
  --candidate-csv .omx/artifacts/deep_rl/signal_test/cand_buy_demand_pressure_20220830.csv \
  --output-dir .omx/artifacts/deep_rl/signal_test/shuffled \
  --baselines no_trade,equal_weight_candidate,buy_and_hold,rule_baseline,supervised_ranker \
  --n-folds 5 --cost-bps 25 --top-k-candidates 3 --max-positions 2 --seed 100 \
  --shuffle-signal --shuffle-seed 100
```

Both exit 0 with real 5-fold output. The panel/candidate build (111 symbols, 2022-08-30, 09:00–09:30)
is a bounded per-session read — never a full-DB scan.

---

*Stage-D non-advisory signal test. Doc-only deliverable (+ minimal shuffle-test plumbing in
`stom_rl/portfolio_walk_forward.py` and its tests); the supporting `.omx/` artifacts are
intentionally not committed.*
