# 딥러닝/RL 장초 20분 수익모델 — 게이트형 실험설계 (ultracode 연구)

- 작성일: **2026-05-29 KST** / 브랜치: `feature/stom-rl-lab`
- 생성: **13-에이전트 워크플로우** (연구 6각도 fan-out → 적대적 검증 **6/6 survives=False** → 우리 DB 맞춤 설계 종합, ~1.3M 토큰) + **DB 실측 grounding**
- 상위 앵커: `docs/stom_rl_rl_feasibility_research_2026-05-29.md`(R0), `docs/stom_rl_session_progress_2026-05-29.md`
- **RULE strategy, NOT RL**: 기존 룰이 배포 후보(incumbent)이고 RL/ML은 "재판 중(on trial)". 본 문서는 **수익 주장이 아니라, 자기기만 없이 가부를 가리는 설계**다.

> 적대적 검증 결과: 6개 연구각도의 "이건 우리 데이터에서 될 수도 있다" 주장이 **전부 기각**됐다(킬러: DSR 게이트가 도는 tradeable episode 수 부족 + triggered-subset 선택편향). 이것이 아래 사전확률이 낮은 이유다.

---

## DB 실측 grounding (2026-05-29 측정)

| 사실 | 값 | 함의 |
|---|---|---|
| 마이크로구조 피처 | 14종 전부 존재(40/40 종목) — 5단 호가/잔량·초당 매수/매도 금액·수량·체결강도·초당거래대금·회전율·VI | 표현학습 입력 충분 |
| 세션 내부 밀도 | 09:00–09:20에 **median 1067봉**(p10 838·p90 1186) — 약 89% 초마다 기록 | 세션 내부는 sparse 아님; 인스턴스당 ~1000-step 시퀀스 |
| 지도학습 학습쌍(P1) | (상태, 미래수익) **ts_imb ~5M / 전체 ~29M** | 예측 게이트엔 데이터 풍부 |
| **tradeable episode (DSR 게이트 단위)** | ts_imb 전체 **~5,175**(70/30 OOS ~1,900); bounded-120 set은 235/81 | **이것이 진짜 구속** |

**정정/refine (중요):** 아래 §1·§7의 사전확률·필요엣지는 **bounded N=235** 기준이다. **게이트를 full universe(5,175 episode)에서 돌리면** DSR/MinTRL 바가 약 2.2x 낮아져 필요 incremental 엣지가 **≈+0.17~0.35%/trade(OOS)**로 내려가고, **+0.10%/trade도 MinTRL 허용**(5,175 ≫ 288–633). → 정직한 사전확률을 **~8–15%에서 ~12–22%로 소폭 상향**(데이터가 더 많아 통계검정력↑). 단 **selection-bias·23bp 비용 구속은 불변**이고, 게이트-우선·딥RL-후순위 설계는 그대로다.

---

# STOM Within-Window Micro-Timing: Gated Deep-Learning / RL Research Design (RULE-vs-RL)

**Status:** Research DESIGN, not a profit claim. Prior is LOW-to-MODERATE. Everything below is explicitly labeled RULE (the existing pre-registered strategy) vs RL/ML (the candidate being tested). The candidate must beat the RULE *and* a linear baseline net of 23 bp OOS, or it is killed.

---

## 0. Honesty statement (read first)

This document specifies *what would make a deep-learning / RL micro-timing result trustworthy on our existing DB*, and the gates that should kill it cheaply if the edge is not there. It does **not** assert that RL will produce profit. Our own lab has already run the nearest-neighbor experiment (causal exit-timing search) and it **failed the gate** (in-sample-best variant −0.71%/trade OOS, deflated Sharpe 0.931 < 0.95). The realistic expectation is a **documented NULL**, and the value of this program is largely to produce that null rigorously, not to harvest alpha. The RULE remains the deployable strategy throughout; RL is on trial.

---

## 1. Honest prior

**Realistic probability that a deep-learning/RL within-window micro-timing model beats the RULE net-of-cost OOS at our deflated-Sharpe > 0.95 gate: ~8–15%.** (Low. Not zero, because we have not literally run a *deep representation over the full per-second sequence* — only entry-bar-feature rankers and a 9-variant causal exit grid. The residual probability lives entirely in "the full intra-window sequence carries causal timing information that point-in-time entry-bar features and 9 hand rules could not encode.")

Why so low, concretely:

1. **The DSR-gate arithmetic is the killer, and it is quantified.** The deflated-Sharpe test runs on *tradeable episodes*, not 1s rows. The realized exit analysis ran at **N≈235 ts_imb episodes, OOS≈81**. From the rule's own dispersion (mean +0.906%/trade, per-trade Sharpe ≈0.303 ⇒ sd ≈3.0%), a *baseline-relative (paired-difference)* series must show, to clear DSR>0.95 at OOS T=81 with a realistic deep-model trial count (n_trials 20–50): **a differential mean of roughly +0.37% to +0.76%/trade of pure timing alpha on top of the rule.** That is a large fraction of — or larger than — the rule's *entire* +0.906%/trade edge. Even at the full N=235, the bar is +0.30% to +0.64%/trade. A within-20-minute entry/exit *re-scheduling* edge of that magnitude, net of 23 bp, is implausible. (Numbers: §7.)
2. **MinTRL says the small edges we could plausibly hope for are statistically inadmissible at our sample size.** A +0.10%/trade incremental edge (sd_diff≈1.0–1.5%) needs **288–633 trades** to be distinguished from zero at 95% — we have ~81 OOS / ~235 total. Only a +0.30%/trade edge with low difference-variance is admissible at N≈81, and an edge that large is not credible from coarse 1s timing.
3. **Adjacent gates already fired NO-GO in-house:** cross-sectional selection alpha absent (shuffle tests, 1s/1min/session); causal exit improvements lose OOS (DSR 0.931); perfect-foresight exit ceiling (capture 17.8%, regret +4.18%/trade) proven to be **non-causal hindsight**; a logistic-regression entry-bar ranker collapsed to equal-weight.
4. **Domain-matched literature predicts deep loses to linear on exactly this market.** Kang 2026 (*The Limits of Complexity*, arXiv:2601.07131): Korean equities, 2020–2024, ICA-Wavelet-LSTM Sharpe ≈0 vs linear momentum Sharpe 1.30. We must clear *both* the rule *and* a linear baseline; the prior is that the linear baseline matches or beats the deep model.
5. **Data physics caps it.** 1s *aggregated*, event-triggered, irregular snapshots; **no L2 queue position, no order-by-order.** The published net-of-cost RL wins (Nevmyvaka–Kearns execution; queue-position alpha) all require microstructure we do not have. Honest fill modeling forces marketable-only fills + de-idealization (already costs −0.045% to −0.140%/trade in-house), eating the headroom.

**Upside scenario (the ~8–15%):** the full per-second OFI / 체결강도 / depth-dynamics *sequence* contains a continuation-vs-reversal separation (Berkman et al. 2012 opening-overshoot mechanism, strong in retail-dominated KR attention stocks) that the entry-bar snapshot and 9 rules genuinely could not encode, and it is large enough to clear the gate. We test for this directly and cheaply before any deep RL.

---

## 2. Problem formulation: what to ATTEMPT vs AVOID (ranked)

Ranked best→worst by expected feasibility *on this data*. We attempt strictly in this order, gated.

| Rank | Formulation | Verdict | Why |
|---|---|---|---|
| **A1 (DO FIRST)** | **Supervised short-horizon predictability PROBE** — does the full per-second panel predict a noise-robust, cost-relevant within-window target at all? Purged CV + Deflated Sharpe. | **DO — cheap gate** | Answers the only question that matters before any RL. If a supervised head on the full sequence cannot beat a naive baseline OOS, every RL formulation downstream is dead. (§3) |
| **A2** | **Supervised meta-labeling on entry timing**: layered on the RULE, classify "is the next k-second window a better marketable entry than entering now?" using only causal features; trade as a tie-breaker. Linear first, then deep. | **DO if A1 passes** | This is the honest operationalization of the open question. Ablation: (1) RULE, (2) RULE+linear-OFI-timing, (3) RULE+deep-representation-timing. Deep must beat **both** (Kang 2026). |
| **A3** | **Representation-learning state encoder** (CNN/transformer over the sequence) feeding a *fixed* execution policy, scored end-to-end on de-idealized net PnL — NOT on classification F1. | **DO only if A2-deep beats A2-linear** | DeepLOB/TLOB-style encoder repurposed for timing, not tick-direction. Pooled cross-symbol (Sirignano–Cont). Justified only if the deep representation has already shown incremental value at A2. |
| **A4** | **Offline RL, near-behavior, low-capacity**: IQL (advantage-weighted BC) or filtered-BC, cost-embedded sparse baseline-relative reward, seeded from the RULE. | **CONDITIONAL — last resort** | Only after A1–A3 show a supervised edge exists. IQL's benign failure mode (reverts to BC ≈ the rule) makes it the safest RL. Imitation target must be a **state-averaged** edge, never single-trajectory return (avoids cloning luck — Paster et al. 2022). |

**AVOID (do NOT attempt on this data):**

| Formulation | Why avoid |
|---|---|
| **Tick-direction prediction (DeepLOB/TLOB native target)** | Predicted moves are sub-bp to a few bp; crushed by 23 bp. Hopeless. |
| **Decision Transformer / return-conditioned sequence model from scratch** | (a) Return-conditioning fails in stochastic environments (Paster et al. 2022 — confuses luck with skill, near-maximal at 1s); (b) more data-hungry than CQL (Bhargava et al. 2024); (c) ~235 correlated episodes ≪ the millions DT needs; (d) filtered-BC matches/beats DT anyway (Omori et al. 2025). Overfit magnet. |
| **Naive online Q-learning / PPO with OOD action bootstrapping** | Value overestimation under our narrow, selection-biased support is lethal (Kumar et al. 2020). |
| **Per-step dense mark-to-market reward** | Reward-hacking / noise-fitting magnet on irregular 1s bars; agent churns. Use cost-embedded *sparse terminal* reward only. |
| **Queue-position / passive-limit-fill / optimal-placement alpha** | Requires L2/L3 FIFO position we do not have (Moallemi–Yuan; Maglaras–Moallemi–Zheng). Unsimulatable honestly. Off the table without new data. |
| **Distributional RL / CVaR as the learning objective; differential-Sharpe dense reward** | Add objective-design degrees of freedom (atoms, quantiles, α, risk-aversion weight) that fit noise on ~235 episodes. Use CVaR for downstream *sizing*, not as reward. |
| **BC of the perfect-foresight oracle** | The oracle conditions on the future; the lab proved the 17.8% capture is non-causal. Distilling it learns a non-causal target that collapses OOS. Distill from the RULE, never from the oracle. |

---

## 3. CHEAP PRE-CHECKS / GATES before any deep RL

These run in **hours on CPU**, before any GPU/RL spend. If any fails, STOP.

### Gate P0 — MinTRL admissibility (cheapest, run first)
Compute, on the *incremental* (paired RL-minus-RULE) per-trade return series, the Minimum Track Record Length needed to distinguish a plausible incremental Sharpe from zero at 95% (Bailey–López de Prado 2012, skew/kurtosis-adjusted).
- **Metric:** MinTRL(SR_inc, skew, kurt, 0.95).
- **Threshold:** If N_OOS (≈81) and N_total (≈235) are **below MinTRL for the smallest incremental edge worth deploying** (target ≥+0.20%/trade after the +0.906% rule), the result is **statistically inadmissible regardless of backtest**. From §7: a +0.10%/trade edge needs 288–633 trades → inadmissible. A +0.20%/trade edge needs 79–167 trades → admissible *only* if difference-variance is low and we accept ~all of N=235. **GO only if the pre-registered target edge is admissible at our N.** This gate alone likely caps the program.

### Gate P1 — Supervised predictability probe (the core cheap gate)
Train a **linear/logistic** model and a **shallow gradient-boosted** model on the **full per-second panel** (all §4 features, with the full sequence summarized into causal aggregates — see below) to predict a **noise-robust within-window target**:
- **Target (noise-robust, NOT single-trajectory return):** for each (symbol,session), the *state-conditioned average* net-of-23bp forward return over the next k∈{5s,15s,30s,60s} marketable entry windows, binned and cross-validated, so the label reflects the conditional edge of similar states rather than one lucky path (ESPER-style cluster target — Paster et al. 2022).
- **Validation:** Purged & embargoed CV at **(symbol,session)** granularity (never split a session; embargo by trading DAY; purge by SYMBOL so the model cannot memorize per-ticker behavior). López de Prado AFML Ch.7.
- **Gate metric & threshold (exact):**
  1. **OOS rank-IC / AUC vs naive baseline:** the model's OOS predictive score must exceed the naive baseline (predict the unconditional within-window mean) by a margin whose **stationary-bootstrap (block = (symbol,session)) 95% CI excludes zero**.
  2. **Translated to PnL:** a simple threshold policy on the probe's signal, scored net of 23 bp on the RULE-eligible population, must produce a per-trade mean whose **Deflated Sharpe > 0.95** charging **every probe trial** (feature sets × horizons × model families) to n_trials.
- **STOP rule:** If the probe cannot beat the naive baseline OOS with CI excluding zero, **STOP — do not build any deep representation or RL.** The edge is not in this data. (This is the gate the literature and our priors say will most likely fire NO-GO.)

### Gate P2 — Linear-beats-deep pre-registration
Before training any deep model, freeze the **linear-OFI-timing baseline** result from P1. The deep model is only worth building if it is *pre-registered to beat the linear baseline by a margin admissible at our N*. (Kang 2026 predicts it will not.)

---

## 4. State / feature design (from OUR columns)

All features are **strictly causal** (point-in-time, no look-ahead). Built from the per-second sequence up to decision time t.

**Price/return state**
- 등락율, 고저평균대비등락율, 저가대비고가등락율; first-bar return sign as a weak within-day prior; time-in-window (seconds since 09:00, the single most informative scalar for a 20-min decision).

**Order-flow imbalance dynamics (strongest theoretical basis — Cont–Kukanov–Stoikov 2014; Kolm–Turiel–Westray 2023)**
- Per-second signed flow: 초당매수수량−초당매도수량, 초당매수금액−초당매도금액 (and ratios); 거래대금증감.
- **Generalized OFI** from 5-level depth deltas: Δ(매수잔량1-5) vs Δ(매도잔량1-5) across consecutive 1s snapshots, depth-weighted. Label this explicitly as *approximate* OFI (inferred from 1s deltas, not true book events) — noisier than message-level OFI.
- Rolling OFI over trailing windows {3s,5s,10s,30s} (the documented ~seconds horizon), plus OFI *acceleration* (the sequence carries this; the entry-bar snapshot does not — this is the candidate causal signal the rule cannot encode).

**Trade-strength / pressure**
- 체결강도 level and its trailing slope; 초당거래대금, 당일거래대금; 회전율; 전일동시간비 (relative-volume regime).

**Book shape (5-level)**
- Best-level imbalance 매수잔량1/(매수잔량1+매도잔량1); total-depth imbalance 매수총잔량/매도총잔량; spread = 매도호가1−매수호가1 (and in ticks via 호가단위); depth slope across levels 1→5; microprice = depth-weighted mid.

**VI state (KR-specific — JRFM 2022; handle as hazard)**
- Binary in-VI flag, time-since-VI-release, time-to-VI (causal only). **Never use 해제시간 forward** (look-ahead). VI bars are non-executable → mask for fills.

**Regime / context (for pooled cross-symbol training — Sirignano–Cont 2019)**
- 시가총액 bucket, KOSPI-vs-KOSDAQ flag (split — KOSDAQ is more retail/biotech with different dynamics).

**Normalization:** per-(symbol,session) z-scoring of flow/depth using only trailing in-window data (causal); cross-symbol pooling with regime one-hots.

---

## 5. Architecture + offline-RL method + reward

**Encoder (only if Gate P1 passes and A2-deep is justified):**
- **Causal Temporal Convolutional Network (TCN) or small causal transformer** over the variable-length, irregular 1s sequence, with **time-gap embeddings** (Δt between event-triggered bars) so irregular spacing is modeled rather than assumed-regular. Transformer attention handles irregular spacing better than fixed-grid CNN; but **cap capacity hard** (≤2 layers, small width) — ~235 episodes cannot support DeepLOB-scale models. **Pool across all symbols** (per-symbol counts are tiny).
- Input tokens = per-second feature vector (§4). 5-level depth (vs DeepLOB's 10) loses some signal — accept it.

**RL method (A4, last resort): IQL (Kostrikov et al. 2021) or TD3+BC (Fujimoto–Gu 2021).**
- **Why IQL/filtered-BC, not CQL/DT:** IQL never queries Q on OOD actions, sidestepping the overestimation lethal under our narrow selection-biased support; its advantage-weighted-BC extraction degrades *gracefully toward BC* (≈the rule) when signal is weak — the benign failure mode we want. CQL's pessimism would clamp back to behavior anyway given degenerate coverage; DT confuses luck with skill in our near-maximally-stochastic 1s environment and is more data-hungry.
- **Action space:** discrete, minimal — {enter now, wait 1 more bar (up to a cap), exit now, hold} within 09:00–09:20, marketable orders only. No passive/limit actions (unsimulatable).

**Reward (cost-embedded, sparse-terminal, baseline-relative):**
```
r_episode = NetPnL_agent(entry,exit | full 23bp deducted at every position change, marketable+slippage)
            − NetPnL_RULE(same symbol-session)         # paired baseline subtraction
r_step    = 0  for all non-terminal bars               # sparse: suppress 1s noise & churn
```
- **Why:** Cost in-reward (not post-hoc filter) is the single most important anti-hacking choice (Amodei et al. 2016; Moody–Saffell 2001). Baseline subtraction is a potential-style constant shift per episode — it does **not** change the optimal policy (Ng–Harada–Russell 1999) but slashes reward variance and centers learning on the marginal timing edge, while making "just replicate the RULE" the zero-skill floor.
- **Risk term:** **none in the reward** (avoids objective-design DoF on a tiny sample). Apply CVaR / downside cap *downstream as a position-sizing / deployment guard*, not as the learning objective.
- **De-idealization (mandatory):** marketable-with-slippage only; add conservative size-aware slippage on top of 23 bp; SL gap-through modeled (already −0.045% to −0.140%/trade in-house); skip a bar after signal to avoid bid-ask-bounce capture (Heston–Korajczyk–Sadka 2010 — sub-hour "signal" is largely bounce/liquidity noise). Any result depending on passive fills is discarded as unverifiable.

---

## 6. Data pipeline: the per-second SEQUENCE extractor (NEW — required)

**Problem:** current artifacts store only **entry-bar features** per instance. Every formulation here needs the **full causal per-second multi-feature sequence** per (symbol,session). This extractor is the prerequisite build.

**Extractor outline (implementable on the existing DB):**
1. **Iterate (symbol,session) keys** in the triggered subset (~29,139 gap≥2% instances; ts_imb subset ~5,175). For each, pull all 1s rows in [09:00:00, 09:30:00] ordered by timestamp.
2. **Build the causal feature panel** per row (§4): keep raw columns + compute trailing-window OFI/체결강도 slopes/microprice/depth-imbalance using **only rows ≤ t** (assert no forward reference in code; unit-test with a shuffled-future canary that must NOT change features).
3. **Handle irregular/sparse bars:** store actual timestamps + Δt gaps as features; do **not** forward-fill across VI halts (mask instead). Record an `is_VI`/`executable` flag per bar.
4. **Define the marketable-fill price series** per bar (현재가/호가-based) for honest PnL replay; precompute the RULE's per-episode net PnL (TP5/SL1/09:25) for the baseline-relative reward.
5. **Persist** as ragged sequences (e.g., Parquet with a `(symbol,session)` group key + ordered arrays, or `.npz` per episode) with a manifest mapping each episode to year / KOSPI-KOSDAQ / 시가총액 bucket for stratified CV and pooling.
6. **Leakage assertions in the pipeline itself:** purge/embargo keys are emitted at extraction time (session boundaries, symbol id, trading-day) so downstream CV cannot accidentally split a session.

**Cost/scale:** ~29k episodes × ≤1,800 bars × ~40 features is modest (low-GB); fits in memory in shards. No new data is collected — this is pure re-extraction from the existing DB.

---

## 7. Validation protocol (concrete)

**Resampling unit = (symbol,session) episode. NEVER the 1s bar.** Within-session bars are strongly autocorrelated; episodes across distinct (symbol,session) are near-independent.

1. **Purged & embargoed walk-forward** (López de Prado AFML Ch.7): train on earlier years, test on held-out *later* years AND a held-out *symbol* slice; purge any training episode whose label horizon overlaps a test session; **embargo by trading day**; **purge by symbol** so per-ticker memorization cannot leak.
2. **CPCV** (Combinatorial Purged CV, AFML Ch.12; skfolio `CombinatorialPurgedCV`): blocks cut at (symbol,session) level → yields a *distribution* of OOS Sharpes from one dataset (essential at our small N).
3. **PBO via CSCV** (Bailey–Borwein–López de Prado–Zhu 2016): config×time-block matrix over all architectures/seeds/hyperparameters. **Threshold: PBO < 0.5** (and report the value); this directly answers "did we pick a fluke config."
4. **Deflated Sharpe Ratio** (Bailey–López de Prado 2014): on the **baseline-relative incremental** per-trade series, charging **the complete trial ledger** to n_trials. **Threshold: DSR > 0.95.** Scope every claim as "*conditional on STOM-trigger + rule-eligibility*" — DSR here tests SR>0 *within the triggered population*, not unconditional gap alpha.
5. **Harvey–Liu haircut Sharpe** (2015) with a **complete trial ledger that includes all prior lab negatives** (1s/1min/session selection, 9-variant exit grid) — the family is already large; the incremental deep signal must clear a high bar.
6. **Multi-seed interval estimates** (rliable, Agarwal et al. 2021): report **IQM + stratified-bootstrap 95% CI + Probability-of-Improvement** over the RULE, stratified by **year** and **KOSPI/KOSDAQ**. **If the IQM CI of the incremental net-of-cost return crosses zero → no defensible improvement.** rliable handles seed variance only — necessary, not sufficient; combine with DSR/PBO.
7. **Dependence-aware CIs:** stationary/block bootstrap (Politis–Romano 1994) with block = (symbol,session), additionally block by **day** for cross-sectional (macro) dependence; powers a White Reality-Check / Hansen SPA across deep-RL configs.

**Quantified bar (from §0 computation, so reviewers see the target before results):** to clear DSR>0.95 on the paired-difference series, the **required incremental edge is ≈+0.37% to +0.76%/trade at OOS N=81** (n_trials 20–50), or **≈+0.30% to +0.64%/trade at full N=235**. MinTRL: a +0.10%/trade edge is inadmissible (needs 288–633 trades); +0.20%/trade is borderline (79–167); only ≥+0.30%/trade with low difference-variance is comfortably admissible. **Pre-register the target edge and verify admissibility at P0 before spending GPU.**

---

## 8. Go/No-Go gates and falsification at each stage

| Stage | Gate | GO if | FALSIFIED / STOP if |
|---|---|---|---|
| **S0 Extractor** | Leakage canary | Shuffled-future canary leaves features unchanged; RULE PnL reproduces the known +0.6–0.95%/trade | Any forward leakage detected → fix before proceeding |
| **S1 MinTRL (P0)** | Admissibility | Pre-registered target edge (≥+0.20%/trade) is admissible at N≈235 | Target edge needs > N trades → **STOP; inadmissible** |
| **S2 Supervised probe (P1)** | OOS predictability | Probe beats naive baseline OOS, bootstrap CI excludes zero, threshold-policy DSR>0.95 charging all probe trials | Probe ≤ baseline OOS → **STOP; edge not in data.** Kills all RL. |
| **S3 Linear timing (A2-linear)** | Beats RULE | RULE+linear-OFI-timing beats RULE OOS, incremental DSR>0.95, PBO<0.5 | ≤ RULE OOS → **STOP** (rule already optimal among simple signals) |
| **S4 Deep timing (A2/A3-deep)** | Beats RULE *and* linear | Deep beats **both** baselines, incremental DSR>0.95, PBO<0.5, rliable PoI CI excludes zero | Deep ≤ linear (Kang-2026 prediction) → **STOP; depth buys nothing.** Deep ≤ RULE → **FALSIFIED.** |
| **S5 Offline RL (A4)** | Beats RULE | IQL/filtered-BC incremental DSR>0.95 on paired reward, multi-seed IQM CI excludes zero | IQL reverts to BC≈RULE (expected) → **documented NULL.** RL < RULE → **FALSIFIED.** |

**Single overriding falsifier:** if the incremental (RL-minus-RULE) net-of-23bp per-trade series has an IQM 95% CI that includes zero after purged CV + DSR + PBO at the honest trial count, **the approach is falsified on this data** — exactly as the analogous causal-exit search was (DSR 0.931). We stop and publish the null.

---

## 9. Honesty statement (restated, for the record)

- This is an **experimental DESIGN with a LOW-to-MODERATE prior (~8–15%)**, not a profit claim and not a prediction of success.
- Every comparison is labeled **RULE** (the existing pre-registered, deployed, net-positive strategy) vs **RL/ML** (the candidate on trial). The RULE is the incumbent; RL must *beat* it net-of-cost OOS through the gates above, or it is rejected.
- **Reward design cannot create an edge the data does not contain.** The cost-embedded baseline-relative sparse reward is chosen to *avoid false positives*, not to manufacture profit.
- Claims are valid **only conditional on STOM-trigger + rule-eligibility**; no extrapolation to general opening gaps (no recorded control group exists to de-bias).
- The most likely honest outcome, given our priors and the DSR/MinTRL arithmetic, is a **rigorously documented NULL** at S1/S2. That is a legitimate and valuable result, and the program is designed to reach it cheaply (CPU-only pre-checks) before any deep/RL spend.

---

**Key sources cited (all real, in the bundle):** Cont–Kukanov–Stoikov 2014 (arXiv:1011.6402); Kolm–Turiel–Westray 2023 (SSRN 3900141); Sirignano–Cont 2019 (arXiv:1803.06917); Zhang–Zohren–Roberts 2019 DeepLOB (arXiv:1808.03668); Berti–Kasneci 2025 TLOB (arXiv:2502.15757); Kang 2026 (arXiv:2601.07131); Berkman et al. 2012 (SSRN 1625495); Heston–Korajczyk–Sadka 2010 (arXiv:1005.3535); Nevmyvaka–Feng–Kearns 2006 (ICML); Fang et al. 2021 OPD (arXiv:2103.10860); Kostrikov et al. 2021 IQL (arXiv:2110.06169); Fujimoto–Gu 2021 TD3+BC (arXiv:2106.06860); Kumar et al. 2020 CQL (arXiv:2006.04779); Paster et al. 2022 (arXiv:2205.15967); Omori et al. 2025 (arXiv:2507.10174); Bailey–López de Prado 2014 DSR (SSRN 2460551), 2012 PSR/MinTRL (SSRN 1821643); Bailey et al. 2016 PBO/CSCV (SSRN 2326253); Harvey–Liu 2015 (SSRN 2345489); López de Prado AFML 2018 Ch.7/12; Agarwal et al. 2021 rliable (NeurIPS); Politis–Romano 1994 (JASA); Ng–Harada–Russell 1999 (ICML); Moody–Saffell 2001 (IEEE TNN); Amodei et al. 2016 (arXiv:1606.06565).