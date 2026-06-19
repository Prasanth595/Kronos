# STOM Portfolio Deep-RL — Honest Two-Track Verdict (Stage E)

Plan: `.omx/plans/ralplan-stom-rl-deep-rl-2026-05-27.md` (Stage E, §0 Two-Track, P0-1 multiplicity/power gate)
Repo: `Kronos` · Branch: `feature/stom-rl-lab` · Baseline: `d2104cc` · Python `py -3.11` (3.11.9) · Windows
Evidence artifact (NOT committed): `.omx/artifacts/deep_rl/stageB_train/stage_b_smoke_summary.json`
Date: 2026-05-27

---

## Pre-registration scaffold (P0-1 — recorded BEFORE the test-fold metrics below)

Per the plan's hard data-mining guard, the search space is pre-registered so the
verdict cannot be a post-hoc cherry-pick:

- **Primary config (the ONE pre-named config):** `algorithm=ppo`, `turnover_penalty_lambda=1.0`,
  `top_k_candidates=3`, `seed_set=[100]`, `cost_bps=25.0`.
- **Full candidate config set:** exactly one — `{ppo, λ=1.0, top_k=3, seed=100}`.
- **`M` = distinct configs tried = 1.**
- **`n_folds` = 2.**
- **`advisory_only = true`** — reason (verbatim from the artifact): *"n_folds=2 < 5 power
  floor (P0-1); 3-symbol universe. NO alpha claim. Real alpha verdict deferred to Stage E
  (n_folds>=5)."*

`M = 1` removes the multiple-comparisons multiplicity problem (nothing to Bonferroni/BH-correct
across), but it does **not** remove the **power** problem: `n_folds = 2 < 5` is below the plan's
hard power floor, so the gate is **advisory-only and NO alpha may be claimed** regardless of which
direction the numbers point. This is stated up front, before the numbers.

---

## 1. Bottom line (conclusion first)

**Track 1 (Engineering) is COMPLETE. Track 2 (Alpha) is ADVISORY-NEGATIVE, and an alpha
claim is FORBIDDEN at `n_folds = 2` per the P0-1 power gate.**

On the small co-dated 3-symbol universe, with explicit `cost_bps = 25`:

- the **trained PPO policy LOSES to a do-nothing baseline** (`no_trade`, exactly 0.000%), and
- it also **loses to a simple same-features supervised ranker**, and
- the **supervised ranker itself does NOT beat `no_trade`** — it merely matches `equal_weight`.

So no model — neither deep RL nor a cheap supervised ranker — found a tradeable stock-selection
edge in this data/feature set. The honest reading: **the binding constraint looks like
signal/data, not the algorithm.** Because `n_folds = 2` is a statistical coin flip, this is reported
as an **advisory direction only** — a real (non-advisory) verdict requires `n_folds ≥ 5`, which in
turn requires the Stage-D full-universe data that has **not yet been run**.

A documented negative is the expected, valid outcome of this phase (plan §0, §3 Stage E,
Principle 4). We are not massaging the result and we are not grinding compute hoping alpha appears.

---

## 2. Track 1 — Engineering (gateable, REQUIRED): COMPLETE

The full deterministic pipeline — Gymnasium adapter → SB3 PPO training → `_fit_policy` holdout
integration → supervised-ranker comparison → invalid-action/MaskablePPO trigger logging — now
exists, is leakage-guarded, and is reproducible. Every Track-1 criterion from plan §0 / §3 is met.

| Stage | Commit | What was delivered | Test / gate evidence |
|---|---|---|---|
| **C-0** (DB feature feasibility probe) | `fe632cb` | Read-only bounded probe (`finetune/stom_rl_c0_feature_probe.py`) confirming the four candidate source columns EXIST and are dense: `등락율`/`시가총액`/`고저평균대비등락율` at **100%** worst-session non-null, `체결강도` at **≥99.84%** worst-session non-zero (V10 PASS). | Per-session coverage reported; no feature added on assumption; decision = WAIT for minimal expansion. Probe artifact `.omx/artifacts/deep_rl/stageC_export/c0_probe.json` (not committed). |
| **C** (feature expansion) | `3976403` | Canonical features expanded **14 → 18**: added `change_rate`, `market_cap`, `high_low_mid_change_rate`, `trade_strength_avg_n` (the last as a **trailing/causal** N-bar mean) into `STOM_RL_CANONICAL_FEATURES` / `_FEATURE_MAPPING` / `_SOURCE_COLUMNS` (`finetune/qlib_stom_pipeline.py`). | Per-feature causality test (V11): `feature(T)` unchanged when bars > T removed. Suite green. |
| **A** (portfolio Gym adapter) | `84c91e9` | `PortfolioEnv` → Gymnasium adapter with fixed obs/action shapes and exposed `action_masks()` for MaskablePPO consumption. | SB3 `check_env` PASS — `observation_space=Box(-inf,inf,(68,),float32)`, `action_space=Discrete(6)` (V3); adapter contract + SB3-wrapper leakage canary (V2/V6b). |
| **B** (deterministic train + `_fit_policy` + ranker) | `d2104cc` (baseline) | `stom_rl/portfolio_sb3_train.py`: cost-aware SB3 PPO training with determinism pins (`torch.use_deterministic_algorithms(True)`, `set_num_threads(1)`, `device=cpu`, fixed seed) + `atol=1e-6, rtol=1e-5` reproducibility assertion. P0-2 plumbing = `TRAINED_BASELINES` key acceptance + module-level `TRAINED_POLICY_FACTORIES` registry consulted by `_fit_policy` *before* its `del` at L390. `supervised_ranker` baseline = sklearn `LogisticRegression`, TRAIN-fit / same disjoint strictly-later holdout-eval (no leaky strawman). | Trained `PolicyFn` runs through `run_portfolio_walk_forward` with runtime leakage guards (L460-465) passing (V5); column + SB3-wrapper leakage canaries PASS (V6/V6b); disjoint strictly-later holdout enforced; explicit non-zero `cost_bps=25` logged (V13). |

**Determinism (V4):** runtime pinned and logged in the artifact — `torch_version 2.9.0+cu128`,
`cuda_available=true` but `device_pinned=cpu`, `use_deterministic_algorithms=true`, `num_threads=1`,
`seed=100`. Determinism is enforced by the pins, not hoped for.

**Test suite (fresh, this stage, `py -3.11`):** **218 passed, 2 skipped** across the `tests/`
tree (which contains all the Stage A/B deep-RL adapter, P0-2 wiring, leakage-canary, masking, and
subprocess determinism tests). This is consistent with — and broader than — the **146 passed**
`stom_rl`-scoped count recorded in the `d2104cc` commit body (146 was the deep-RL module subset;
the full `tests/` tree is 218). Both clear the plan's ≥132/122-green floor.

> **Honest caveat on the test run:** a *whole-repo* `pytest -q` run additionally collects
> `finetune/qlib_test.py`, which this stage failed to **collect** with a transient torch DLL-init
> error (`OSError [WinError 1114]` loading `torch\lib\c10.dll`) — an environment/CUDA DLL
> initialization issue in that one qlib-import module, NOT a deep-RL test failure. The 218/2
> figure above is from `tests/ --ignore=finetune/qlib_test.py`; the deep-RL Stage A/B tests
> themselves all pass.

`ruff` clean on the deep-RL stage files (`stom_rl/portfolio_sb3_train.py`,
`portfolio_walk_forward.py`, `portfolio_sb3_adapter.py`, `finetune/stom_rl_c0_feature_probe.py` —
"All checks passed", re-confirmed this stage). Pre-existing lint debt elsewhere in the tree is
out of scope for this phase.

**Track-1 completion is valid regardless of whether the model makes money** (plan §0). It is complete.

---

## 3. Track 2 — Alpha (research outcome): ADVISORY-NEGATIVE

### The numbers (real, pulled from `stage_b_smoke_summary.json`, `cost_bps = 25`, `n_folds = 2`)

Mean cost-adjusted return across the 2 disjoint, strictly-later holdout folds
(`advisory_comparison.mean_return_pct_by_policy`):

| Policy | Mean return % (2 folds) | Fold 0 | Fold 1 | vs `no_trade` |
|---|---|---|---|---|
| `no_trade` | **0.000%** | 0.000% | 0.000% | — (baseline) |
| `equal_weight_candidate` | **−0.1049%** | −0.0859% | −0.1239% | loses |
| `supervised_ranker` | **−0.1049%** | −0.0859% | −0.1239% | loses |
| `trained_ppo` | **−1.5464%** | −1.4897% | −1.6031% | **loses badly** |

Artifact verdict fields (verbatim): `rl_vs_ranker = "RL_<=_ranker"`;
`ranker_floor_verdict = "RECOMMEND ABANDONING RL (trained_ppo <= supervised_ranker on holdout)"`;
`alpha_claim = "FORBIDDEN (advisory-only, n_folds<5 per P0-1)"`.

### Reading the result honestly — three findings

**(a) Plain PPO cannot learn this mostly-invalid action space without masking.**
The trained PPO churned (trade_count = 24/24 steps every fold, turnover ≈ 5.95M vs the
baselines' single trade of 250k), burning ≈14.9k in cost per fold to end at −1.55%. The raw
**invalid-action rate = 96.9% (62/64 steps)** on the unmasked policy — far above the 5% trigger
threshold — so the **MaskablePPO trigger FIRED** (`maskable_ppo_trigger_fired = true`,
recommendation `"ESCALATE: record sb3-contrib MaskablePPO recommendation (NOT installed in Stage B)"`).
A *fair* RL attempt would require `sb3-contrib`/MaskablePPO, which is **not yet installed**. So the
catastrophic PPO number is partly an artifact of an un-masked policy flailing in a sparse Discrete
action space — it is NOT, on its own, proof that "RL has no edge here."

**(b) But the supervised ranker — which sidesteps the masking problem entirely — ALSO fails.**
The `supervised_ranker` (a simple causal LogisticRegression on the same features, no invalid-action
problem) does not beat `no_trade`. In fact its returns are **byte-identical to `equal_weight`
(−0.10487592… on both folds)**: on this thin 3-symbol set the learned ranker degenerated to the
same selection as naive equal-weighting and still bled the same cost-driven −0.10%. Since the
cheap model that does NOT suffer PPO's masking pathology *also* finds nothing, the binding
constraint looks like **SIGNAL / DATA, not the algorithm.**

**(c) Why no alpha may be CLAIMED here (P0-1 power gate).**
`n_folds = 2` with a config search is statistically a coin flip — a "strict majority of 2" = 2/2 is
clearable by chance. The plan's hard power floor requires `n_folds ≥ 5` before any alpha claim.
`M = 1` means no multiplicity correction is owed, but the power floor alone forbids a claim. Hence
**advisory-only, no alpha claimed** — only the direction (no edge found) is reported. Reaching
`n_folds ≥ 5` requires the Stage-D full-universe data, which has not been run.

---

## 4. What would change the verdict (Stage D decision — NOT yet run)

The non-advisory test is gated behind the **full-universe run** (plan §3 Stage D), which has **not
been executed**:

- **Full-universe run** via the existing Page-16 checkpoint/resume harness (`stom_rl/full_universe.py`)
  — a multi-hour background job — would broaden the co-dated symbol universe and sessions enough to
  support **`n_folds ≥ 5`**, the precondition for a real (non-advisory) alpha test.
- **A fair RL attempt also needs MaskablePPO** (`sb3-contrib`, not yet installed), because the 96.9%
  invalid-action rate shows plain penalty-PPO cannot learn this action space cleanly.
- Stage D carries a fixed **kill criterion** (plan §3 Stage D): stop and go to verdict if, on the
  first `K = 5` evaluated sessions, the mean cost-adjusted return does not beat `equal_weight` by
  `≥ 0.10%` (10 bps) net of cost.

**Honest tempering:** the advisory signal already in hand — that even the cheap supervised ranker
has no edge over `no_trade` on this data — **lowers the expected payoff** of the multi-hour
full-universe run. We are not promising the full run will find alpha; the current evidence points
the other way.

---

## 5. Recommendation — prioritize SIGNAL over algorithm

**Do not invest in more deep-RL machinery next. Invest in signal first.** The data so far shows no
tradeable selection edge with the current features even for a *supervised* model — and a supervised
model is far cheaper than RL to evaluate. Concretely:

1. **Highest-value next step:** run the **full-universe + expanded-feature** export and re-evaluate
   the **supervised ranker first** (cheap). If the *ranker* finds an edge over `no_trade` at
   `n_folds ≥ 5`, then — and only then — is MaskablePPO / deep-RL worth the compute.
2. **Only after a ranker edge appears** should `sb3-contrib`/MaskablePPO be installed and a fair RL
   attempt made; spending RL compute before any model shows signal is the compute-blowup failure
   mode the plan explicitly guards against (Pre-mortem Scenario iii, R3).
3. **Abandon-RL-for-now is the honest reading** unless and until a full-universe supervised ranker
   demonstrates an edge. This matches the artifact's own `ranker_floor_verdict`
   ("RECOMMEND ABANDONING RL") and the plan's P1-5 supervised-ranker floor rule.

---

## 6. Anti-false-alpha guard status (plan §0, Stage E blocking criteria)

| Guard | Status at this stage |
|---|---|
| Column leakage canary (trained path) | PASS (Stage B, V6) |
| SB3-wrapper leakage canary (P1-4) | PASS (Stage A/B, V6b) |
| Disjoint, strictly-later holdout (runtime asserts L460-465) | PASS (V5) |
| Explicit non-zero `cost_bps` in eval | PASS — `cost_bps = 25` logged (V13) |
| Shuffle / permutation sanity check (V8) | N/A this stage — not required to forbid a claim that is already forbidden by the power floor; mandatory if/when a `n_folds ≥ 5` claim is ever attempted |
| Supervised-ranker floor (P1-5 / V9b) | REPORTED — RL ≤ ranker → verdict recommends abandoning RL |
| ≥2-seed agreement (V9) | N/A — single pre-registered seed (seed=100); a claim would require ≥2 seeds |
| Multiplicity + power (P0-1 / V9c) | `M = 1` (no correction owed) BUT `n_folds = 2 < 5` → **advisory-only, NO alpha claim** |

---

## 7. Discrepancies between the plan's expected numbers and the artifact

None material. The artifact numbers match the plan/task expectations to rounding:

- `trained_ppo` mean = **−1.5464%** (task said ≈ −1.546%) ✓
- `supervised_ranker` mean = **−0.1049%** (task said ≈ −0.105%) ✓
- `equal_weight_candidate` mean = **−0.1049%** (task said ≈ −0.105%) ✓
- `no_trade` = **0.000%** ✓
- raw invalid-action rate = **96.875% ≈ 96.9%**, MaskablePPO trigger FIRED, `sb3-contrib` NOT
  installed ✓
- pre-registration `M = 1`, `n_folds = 2`, `advisory_only = true` ✓

**One nuance worth flagging (not a discrepancy, an honest detail):** `supervised_ranker` and
`equal_weight_candidate` returns are **byte-identical** on both folds (−0.08586448598130181 and
−0.12388735420503227). On this thin 3-symbol universe the learned ranker collapsed to the same
top-k selection as naive equal-weighting — which strengthens, not weakens, the "no signal in this
data" reading: a trained model that cannot distinguish itself from equal-weight has found no edge.

---

*Stage E verdict. Doc-only deliverable; the supporting `.omx/` artifacts are intentionally not
committed.*
