# STOM Portfolio — Story B1 세션바("일봉 proxy") 교차세션 선택신호 검정 (CAVEATED PROXY, NON-ADVISORY)

Feasibility: `docs/stom_rl_story_b_daily_data_feasibility_2026-05-27.md` (B1 경로)
인트라데이 null 대조: `docs/stom_rl_1min_signal_verdict_2026-05-27.md`, 1초 null(동 문서 §7)
Repo: `Kronos` · Branch: `feature/stom-rl-lab` · Baseline: `9741465` · Python `py -3.11` (3.11.9) · Windows
증거 산출물(커밋 안 함 — `.omx/` gitignore): `.omx/artifacts/stom_rl_b1/`
Date: 2026-05-27

---

## 0. 정직성 계약 (먼저, 비협상)

본 검정은 **CAVEATED PROXY**다. 깨끗한 일봉 알파 검정이 **아니다**. 현 DB는 이벤트 트리거형 +
세션당 ~30분(아침)만 기록하므로 두 confound에 묶인다:

1. **선택편향**: (종목, 세션)이 패널에 존재하는 이유 자체가 "그날 기록 조건을 쳤기 때문". 이미 급등/이벤트
   종목들 사이의 선택이라 모집단이 편향돼 일반 시장에 일반화 불가, 거짓양성 위험 큼.
2. **아침-only 수익**: "세션 수익"은 종가-종가 일봉이 아니라 아침 ~30분 구간 수익. 보유=1세션이지만 체결은
   해당 종목의 **차기 가용 세션**(불규칙 gap, 정직히 명시)이다.

따라서 **B1에서는 결과가 양수여도 알파를 주장할 수 없다.** 진짜 알파 판정은 정규 일봉 OHLCV
재현(B2)이 선행 조건이다. NO/null은 (인트라데이 null과 정합적인) 유력하고 타당한 결과다. 검증된
falsifier 게이트(V-NONDEGEN → ranker-vs-baseline → mandatory shuffle, n_folds≥5)를 그대로 재사용해
confound/noise 신호가 알파로 위장하지 못하게 막았고, 어떤 수치도 massage 하지 않았다.

### NON-ADVISORY 판정: **NO.** 교차세션 선택신호에 shuffle-생존 엣지가 없다 (게다가 가장 damning한 방식으로).

`supervised_ranker`는 비용(25bps) 차감 후 REAL에서 `equal_weight`를 **1/5 fold**에서만 이겨 사전등록
strict-majority(3/5)에 **미달**하고, 평균(+2.66%)이 `equal_weight`(+5.23%)·`buy_and_hold`에 **진다**.
결정타: **SHUFFLE(신호 파괴)이 REAL을 압도** — 셔플된 noise가 `equal_weight`를 4/5로 이기고 평균
**+32.60%** 로, REAL(1/5, +2.66%)보다 훨씬 낫다. random noise가 모델을 out-select하면 모델에는 실제
선택정보가 없다. **알파 없음**. (이마저도 알파 주장이 아니라 proxy 신호 부재의 증거다.)

---

## 1. 세션바 resample 접근 + 교차세션 패널 구성

### 1.1 세션바("일봉 proxy") resample — 유일한 net-new 코드

Stage-2 RL resampler(`finetune/qlib_stom_pipeline.py:resample_stom_rl_source_frame`)를 `freq="session"`
모드로 확장. 한 `(symbol, session)`의 **모든 행**을 **1 바**로 붕괴시키되, 1분 경로와 **동일한 LOCKED
per-column 집계**를 쓴다:

| 컬럼군 | 집계 | 근거 (Stage-1 LOCKED) |
|---|---|---|
| OHLC | open=first / high=max / low=min / close=last | 1분 경로와 동일 |
| flow (초당매수/매도수량, volume, amount) | **SUM** | amount=초당거래대금 per-second → SUM |
| order-book / rate / snapshot (총잔량·호가1·등락율·회전율·시가총액·고저평균대비등락율·체결강도) | **LAST** | 세션 마지막 초 스냅샷 |

- 버킷 = 세션 그 자체 → 정확히 **(symbol, session)당 1 바**. 바의 `timestamp` = **세션 날짜(자정)** 로
  지정해, 서로 다른 종목의 세션바가 **공통 세션-날짜 축**에 정렬(교차세션 패널 그리드).
- 인과 추세 피처(이동평균/변동성/거래대금각도/등락율각도 + amount_delta + 체결강도 trailing 평균)는
  세션바에서 per-session 그룹이 길이-1이 되어 붕괴하므로, `build_stom_rl_feature_frame(trend_group_keys=["symbol"])`
  로 **종목별 세션 시계열을 가로질러**(group by symbol) trailing 계산한다. 여전히 trailing-only(룩어헤드
  없음) — 행 T는 세션 ≤T만 사용. 1s/1min 경로는 기본값(`[symbol, session]`) 유지로 byte-불변.

### 1.2 교차세션 패널 구성 (bounded, NO full-DB scan)

- **유니버스 선택**(bounded probe, `.omx/artifacts/stom_rl_b1/probe.py`): 2,427 테이블 중 6자리 종목
  테이블을 800개까지 bounded 슬라이스, 각 테이블에 **단 1개의 cheap aggregate 쿼리**
  (`DISTINCT substr(ts,1,8)` in 아침 윈도) 로 거래 세션을 집계. 전 행 스캔 없음.
- **선택된 유니버스**: 세션 수 기준 **상위 120 종목**(007660=510세션 … 011790=325세션 등), 이들의
  **≥5 종목 공동거래 세션**만 패널에 사용 → **945 distinct 세션-날짜**, 2022-03-23 ~ 2026-02-27.
- **읽기**(`.omx/artifacts/stom_rl_b1/run_b1.py`): 종목당 **1회 bounded indexed read**(세션-prefix `IN`
  945-세션 화이트리스트, 아침 윈도 09:00–09:30) → 세션 resample → 종목별 세션 시계열 피처 →
  `merge_asof(backward)` 로 세션-날짜 축 정렬(`stom_rl/panel_join.py` 재사용). 전 DB 스캔 아님.
- **후보 생성**: `screen_frame`(rule = `buy_demand_pressure`). T+1 fill 계약이 그리드-불문이라
  per-symbol `shift(-1)` = **차기 세션 바** = 보유 1세션. 마지막 세션은 T+1 없음 → unfillable.

### 1.3 유니버스 / 패널 / 후보 규모

| 항목 | 값 |
|---|---|
| 종목 수 | **120** (probe 상위 세션수) |
| 패널 distinct 세션-날짜 | **945** (≥5 종목 공동거래) |
| 패널 행 (long, 종목×세션바) | **113,400** |
| 후보 | **13,743** (fillable 13,722 · unfillable 21 = 종목별 마지막 세션) |
| distinct 후보 세션 | **945** |
| 윈도 | 09:00:00–09:30:00 (기록된 아침 ~30분) |
| Rule | `buy_demand_pressure` (가장 관대 — ranker에 최대·공정 풀) |
| Freq | **session** (net-new 세션바 resample) |
| Cost | **`cost_bps = 25`** (명시, 1s/1min과 동일) |

### 1.4 per-fold 후보 카운트 (`n_folds=5`, 확장윈도 disjoint·strictly-later 세션 holdout)

945 distinct 세션 → 6 disjoint 세션-세그먼트 → 5 평가 fold. 시간 축 = **세션**.

| Fold | TRAIN 후보 | TEST 후보 | TEST 세션 구간 (disjoint, strictly later) |
|---|---|---|---|
| 0 | 1,691 | 2,233 | 2022-11-10 .. 2023-06-30 |
| 1 | 3,924 | 2,672 | 2023-07-03 .. 2024-02-26 |
| 2 | 6,596 | 2,218 | 2024-02-27 .. 2024-10-24 |
| 3 | 8,814 | 2,526 | 2024-10-25 .. 2025-06-25 |
| 4 | 11,340 | 2,403 | 2025-06-26 .. 2026-02-27 |

---

## 2. 게이트 순서 — feature-integrity 게이트가 알파 판정보다 먼저

constant/zero 피처는 자기 자신으로 셔플돼 shuffle 테스트를 vacuously 통과하므로(거짓 null 제조), 비퇴화를
하드 선행조건으로 둔다.

### V-NONDEGEN (FIRST, 실제 세션 후보 집합) — **PASS**

모든 게이트-네임드 세션-바 피처가 비-제로 분산 + ≥2 distinct. 핵심: **세션 축을 가로지른 4개 추세 피처가
진짜 비퇴화** (종목별 세션 시계열 trailing 계산 정상 동작 증거).

| 세션바 피처 | variance(ddof=0) | distinct | 비퇴화? |
|---|---|---|---|
| `rank_score` | 591.29 | 2,113 | yes |
| `trade_strength` | 1,253.36 | 1,771 | yes |
| `bid_ask_imbalance` | 0.01032 | 2,106 | yes |
| `change_rate` | 29.84 | 1,033 | yes |
| `moving_average_n` (이동평균) | 5.36e9 | 2,066 | yes |
| `volatility_n` (변동성) | 4.4267 | 2,104 | yes |
| `amount_slope_n` (거래대금각도) | 3.769e7 | 2,103 | yes |
| `change_rate_slope_n` (등락율각도) | 3.6937 | 2,079 | yes |

(전체 24개 feature_*/rank_score 컬럼 모두 PASS — `.omx/artifacts/stom_rl_b1/v_nondegen_full.json`.)

### V-COVERAGE — **PASS** (945 distinct 세션 ≥ 6; 120 종목 전원 후보 생성)

V-NONDEGEN + V-COVERAGE PASS → 아래 shuffle/majority 게이트에 teeth가 있다.

---

## 3. 사전등록 (M=1, post-hoc 튜닝 없음)

| 항목 | LOCKED 값 |
|---|---|
| freq | **session** (1 바/세션) |
| Trailing window `N` | **10** 세션 바 (종목별 세션 시계열) |
| 변동성 ddof | **0** |
| `cost_bps` | **25.0** |
| `M` (config 수) | **1** |
| Primary policy | **`supervised_ranker`** (`trained_ppo` **DEFERRED**) |
| `top_k` / `max_positions` | **10 / 10** |
| `n_folds` / majority | **5** / **⌈6/2⌉ = 3 of 5** |
| 보유 / 체결 | **1 세션**; 체결 = **차기 가용 세션**(불규칙 gap) |
| 셔플 시드 | **0** (paired real-vs-shuffle) |
| `max_steps_per_fold` | **0** (truncation 없음 — 각 fold 전체 TEST 평가) |

`M=1` ⇒ 다중성 보정 불요. `n_folds=5 ≥ 5` ⇒ **NON-ADVISORY**.

---

## 4. 수치 (REAL, 비용차감 `return_pct`, `cost_bps=25`, `n_folds=5`, seed 100)

### 4.1 per-fold 비용차감 return %

| Policy | f0 | f1 | f2 | f3 | f4 | **mean** | vs `no_trade` |
|---|---|---|---|---|---|---|---|
| `no_trade` | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | **0.0000** | — |
| `equal_weight_candidate` | −9.5912 | 8.6361 | 12.7852 | 17.0869 | −2.7624 | **5.2309** | wins |
| `buy_and_hold` | −9.5912 | 8.6361 | 12.7852 | 17.0869 | −2.7624 | **5.2309** | wins |
| `rule_baseline` | −9.9174 | −21.0360 | 0.1110 | −4.1263 | 11.0788 | **−4.7780** | loses |
| **`supervised_ranker`** | −0.0163 | 8.2243 | 3.7517 | 14.6804 | −13.3265 | **2.6627** | wins(약) |

### 4.2 `supervised_ranker` vs `equal_weight` per-fold

| Fold | ranker % | equal_weight % | diff | result |
|---|---|---|---|---|
| 0 | −0.0163 | −9.5912 | +9.5749 | WIN |
| 1 | 8.2243 | 8.6361 | −0.4118 | lose |
| 2 | 3.7517 | 12.7852 | −9.0335 | lose |
| 3 | 14.6804 | 17.0869 | −2.4065 | lose |
| 4 | −13.3265 | −2.7624 | −10.5640 | lose |

**REAL majority over `equal_weight`: 1/5** → 3/5 **미달**. ranker 평균(+2.66%)은 `equal_weight`(+5.23%)에
**진다**. (`no_trade`는 평균으로 이기지만 — 아래 §5에서 보듯 selection-bias pop의 confound 효과이고,
shuffle이 그것을 더 잘 먹는다.)

### 4.3 worst-fold MDD / 평균 turnover / 평균 trades (REAL)

| Policy | worst-fold MDD % | 평균 turnover | 평균 trades |
|---|---|---|---|
| `no_trade` | 0.000 | 0 | 0.0 |
| `equal_weight_candidate` | −18.525 | 997,506 | 4.2 |
| **`supervised_ranker`** | −16.225 | 997,506 | 4.4 |

수익 크기가 ±10~17%로 비현실적으로 큰 것 자체가 **아침-only + selection-bias confound의 가시적 증거**다
(종가-종가 일봉이라면 불가능한 규모). 이는 신호가 아니라 confound다.

---

## 5. Mandatory shuffle / permutation 검정 (LOCKED shuffle-seed 0) — 결정타

메커니즘(`stom_rl/portfolio_walk_forward.py:shuffle_candidate_signal`): 각 timestamp(세션) 내에서
`rank_score` + 모든 `feature_*` 값을 독립 순열로 **OVERWRITE**, `price`/`fill_price`/`symbol`/`fillable`은
불변 → 체결·비용 회계는 byte-동일, 선택 신호만 파괴.

### REAL vs SHUFFLE — `supervised_ranker`

| Run | ranker wins vs EW | ranker mean % | EW mean % | ranker beats `no_trade`? |
|---|---|---|---|---|
| REAL, seed 100 | **1/5** | +2.6627 | +5.2309 | yes(약) |
| SHUFFLE, seed 0 | **4/5** | **+32.6012** | +11.7243 | yes |

### SHUFFLE per-fold (ranker vs EW)

| Fold | ranker % | EW % | diff | result |
|---|---|---|---|---|
| 0 | 47.2625 | 10.2404 | +37.02 | WIN |
| 1 | 25.9462 | 19.9396 | +6.01 | WIN |
| 2 | 20.7473 | −10.8118 | +31.56 | WIN |
| 3 | 59.2110 | 16.9607 | +42.25 | WIN |
| 4 | 9.8388 | 22.2927 | −12.45 | lose |

**해석(결정적):** 파괴된-신호 SHUFFLE이 REAL을 **압도** — 4/5 majority(REAL 1/5), 평균 +32.60%(REAL
+2.66%). random noise가 모델을 큰 폭으로 out-select하면, 모델에 **실제 선택정보가 전혀 없다**. shuffle이
"재현하지 못할" positive 엣지가 애초에 없다. 더구나 selection-biased 풀에서는 이미 트리거(상승)한 종목
사이의 random 선택이 survivorship pop을 더 잘 타므로, "real" ranker가 그 풀 안에서 random보다 **더 나쁘게**
고른다는 것까지 드러난다 — confound가 신호로 위장하지 못하도록 게이트가 정확히 작동했다.

---

## 6. NON-ADVISORY 판정 + 알파 게이트 (CAVEATED)

| 알파-게이트 절 | 결과 |
|---|---|
| ranker가 `equal_weight`를 strict majority(≥3/5)로 이김 — REAL | **FAIL** (1/5) |
| ranker 평균이 `equal_weight`를 이김 — REAL | **FAIL** (+2.66% < +5.23%) |
| shuffle 생존 (real majority 유지 AND shuffle이 재현 못함) | **FAIL** (shuffle 4/5 ≫ real 1/5, +32.6% ≫ +2.66%) |
| 다중성 + power (M=1, n_folds=5≥5, 사전등록 준수) | clean |

> ### 판정: 본 유니버스/피처/세션-proxy에서 교차세션 선택 엣지는 **없다**.
> ### 설령 양수였더라도 정직성 계약상 알파 주장 금지였다 — 그런데 결과는 깨끗한 NO다.
> ### `trained_ppo`(MaskablePPO)는 **DEFERRED 유지**. cheap falsifier가 아무것도 못 찾았으므로 RL 컴퓨트 낭비 금지.

**CAVEATED 결론 한 줄:** 이 NO는 인트라데이 null과 정합적이며, 동시에 **proxy 자체의 한계**(선택편향 +
아침-only)에 의해 어차피 해석이 묶여 있었다. 진짜 일봉 알파 유무는 **B2(정규 일봉 OHLCV 재현)** 없이는
판정 불가다. 본 B1의 가치는 "값싼 탐색에서도 신호가 없다 + 인프라(세션바 resample) 재사용 가능"을 확인한
것이지, 알파의 존부를 결론낸 것이 아니다.

---

## 7. 인트라데이 null과의 대조 — horizon을 1초→1분→세션으로 넓히면 바뀌었나?

**아니다 — 오히려 더 강한 NO.** 동일 하니스·동일 25bps·동일 cheap ranker·동일 mandatory shuffle.

| 차원 | 1초 (proven null) | 1분 (proven null) | **세션-proxy (B1, 본 문서)** |
|---|---|---|---|
| 시간 축 | 세션 내 1초 (~1,800바) | 세션 내 1분 (~31바) | **세션 (945 distinct 세션-날짜)** |
| 유니버스 | 111 공동거래(1세션) | 111 공동거래(1세션) | **120 종목 × 945 세션 (교차세션)** |
| 보유 | 1바(1초) | 1바(1분) | **1 세션 (차기 가용 세션 체결)** |
| ranker beats EW (REAL) | 3/5 (틀 +0.0001% mirage) | 2/5 | **1/5** |
| ranker 평균 vs EW | — | loses | **loses (+2.66% < +5.23%)** |
| shuffle 결과 | real 3/5 → shuffle 1–2/5 (얇은 엣지) | real 2/5 ≤ shuffle 3/5 | **real 1/5 ≪ shuffle 4/5 (+2.66% ≪ +32.6%)** |
| 비용 후 `no_trade` 상회? | NO | NO | NO (평균은 약간 위지만 confound·shuffle이 더 큼) |
| 판정 | NON-ADVISORY NO | NON-ADVISORY NO | **NON-ADVISORY NO (CAVEATED proxy)** |

1초→1분에서 real이 shuffle을 겨우 이기다(3/5 vs 1–2/5) 1분에 역전(2/5 ≤ 3/5)됐고, **세션-proxy에서는
real이 shuffle에 압도(1/5 ≪ 4/5)**된다. horizon을 세션까지 넓히고 비용 비중을 줄여도 selection-bias가
만든 거대한 noise 수익을 random이 더 잘 먹을 뿐, 실제 선택정보는 나타나지 않았다. 다음 정보가 되는
실험은 **B2(정규 일봉 OHLCV)** 또는 외부/단면 신호이지, 더 많은 인트라데이/세션-proxy RL이 아니다.

---

## 8. anti-false-alpha 가드 상태

| 가드 | 상태 |
|---|---|
| V-NONDEGEN (세션바 피처 비-제로 분산 — 알파 게이트 BEFORE) | **PASS** (4개 추세 포함, 세션축 trailing) |
| V-COVERAGE (≥6 distinct 세션) | **PASS** (945) |
| disjoint·strictly-later 세션 holdout (런타임 assert, `portfolio_walk_forward.py` L691-696) | **PASS** (REAL/SHUFFLE 모두 exit 0, AssertionError 없음) |
| 명시 비-제로 `cost_bps` | **PASS** (`cost_bps=25` 모든 fold) |
| Mandatory shuffle (LOCKED seed 0) | **RUN** — real 1/5 ≪ shuffle 4/5 (엣지 미생존) |
| supervised-ranker floor | **REPORTED** — floor가 EW/`no_trade` 대비 엣지 없음; RL 정당화 안 됨 |
| 다중성 + power (M=1, n_folds=5≥5) | M=1 (보정 불요) + `n_folds=5≥5` → **NON-ADVISORY** |
| 사전등록 준수 (post-hoc 튜닝 없음) | **YES** — §3 상수 verbatim |
| **알파 주장 금지 (caveated proxy)** | **준수** — 선택편향 + 아침-only 명시, B2 없이는 알파 판정 불가로 봉인 |

---

## 9. 재현

모든 명령 `py -3.11`, repo 루트, `PYTHONUTF8=1`. 산출물 `.omx/artifacts/stom_rl_b1/`(gitignore).
읽기는 bounded(probe = 테이블당 1 aggregate 쿼리; 본 실행 = 종목당 1 indexed read, 세션-prefix IN
화이트리스트) — 전 DB 스캔 아님.

```bash
# (1) bounded probe — 거래 세션 집계로 유니버스 후보 산출
py -3.11 .omx/artifacts/stom_rl_b1/probe.py 800
py -3.11 .omx/artifacts/stom_rl_b1/select_universe.py   # 상위 120 종목 × 945 세션

# (2) 세션-proxy 후보 + V-NONDEGEN + walk-forward(REAL+SHUFFLE), n_folds=5, cost_bps=25
py -3.11 .omx/artifacts/stom_rl_b1/run_b1.py full

# (3) 표 추출
py -3.11 .omx/artifacts/stom_rl_b1/analyze.py full
```

핵심 코드(커밋): `finetune/qlib_stom_pipeline.py`(`freq="session"` resample + `trend_group_keys`),
`stom_rl/panel_join.py`(session freq → `trend_group_keys=["symbol"]`), `stom_rl/candidate_gen.py`
(`--freq session`), `tests/test_stom_rl_feature_expansion.py`(세션바 unit test 4종).

---

*Story B1 NON-ADVISORY CAVEATED-PROXY 검정. Doc-only 산출물; `.omx/` 증거는 의도적으로 커밋 안 함.
M=1 사전등록 준수 — post-hoc 튜닝 없음. 알파 주장 금지(선택편향 + 아침-only) — 진짜 일봉 알파는 B2
정규 데이터 재현이 선행조건.*
