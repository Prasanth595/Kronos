# Cost-Aware Policy 실험 (TRACK B 다음 방향, Page 14 후속)

- 작성일: 2026-05-26
- 베이스라인 커밋: `0a9a67e` (Page 16 full-universe 게이트)
- 브랜치: `feature/stom-rl-lab`
- 실행: Python 3.13 (Windows). **주의**: 본 환경에는 `stable_baselines3`/`gymnasium` 미설치 — 이 사실이 라우트 선택을 결정함(아래 §2).
- 비용 가정(명시): **`cost_bps = 25.0`**, `slippage_bps = 0.0`, `initial_cash = 1,000,000 KRW`, 체결 = **T+1** (`stom_rl/accounting.py`, `stom_rl/portfolio_env.py`).
- 가설(Page 14): 손실 원인은 **알파 부재가 아니라 거래 회전(turnover) 비용**. 비용 인지형 정책 — **TRAIN 구간에 fit, disjoint·후행 TEST 구간에서 평가** — 이 `cost_bps=25.0` 후 equal-weight 를 이기는가?

---

## 0. 결론 먼저 (정직)

**판정: MARGINAL / 데이터 의존적 (조건부 Yes).**

- **demand_pressure set (227 candidate, Page 14 와 동일)**: 비용 인지형 정책이 `cost=25bps` 후 equal-weight 를 **+0.0817%p 로 이긴다 (Yes)**. 그러나 이는 **알파가 아니라 회전 비용 회피** 때문이다 — 정책이 TRAIN 에서 "거의 거래하지 않기"를 학습해(min-hold=8, 높은 score 임계값) no_trade(0.0%)에 근접했고, equal-weight 가 매 fold 비용으로 잃는 만큼을 피했을 뿐이다.
- **widev1 set (25 candidate, 더 엄격한 룰)**: equal-weight 자체가 **+0.0758% 흑자**라서, 정책이 TRAIN 에서 매우 높은 임계값을 fit → TEST 에서 **0 거래** → no_trade(0.0%)와 동률, **equal-weight 에 -0.0758%p 패배 (No)**.
- **비용 민감도(demand_pressure)**: gap(cost_aware − equal_weight) 이 **cost=0 에선 음수(-0.0521%p, 패배), cost↑ 할수록 양수로 커진다(+0.082%p @25bps)**. 즉 **이 정책의 우위는 전적으로 회전 비용 회피 효과이며, raw 알파는 없다** — Page 14 가설의 결정적 확증.

**한 줄 요약**: 비용 인지형 reward 는 "churn 을 멈추라"를 정확히 학습시켰고, 그 결과 고빈도 대역(rl_baseline, -3.28%)을 압도하고 비용이 높을수록 equal-weight 도 이긴다. 그러나 종목 선택 알파는 만들지 못했다 — 정책의 최적해가 사실상 "현금 보유"로 수렴하기 때문이다. 이는 정당한 트랙 B 종착점이다.

---

## 1. 라우트 선택: (b) 파라메트릭 비용 인지형 정책 (TRAIN-tuned)

| 후보 | 채택? | 이유 |
|---|:--:|---|
| (a) SB3 학습 (DQN/PPO) | ✗ | 본 환경에 `stable_baselines3`/`gymnasium` **미설치**(import 실패 확인). `sb3_adapter` 는 단일 종목 env 만 래핑하며 portfolio_env 용 Gym 래퍼가 없다. Page 14 §6-4 가 MaskablePPO 도입을 invalid-action 게이트 통과 전까지 보류로 명시. → 무거운 의존성 추가 + 새 래퍼 = scope creep. |
| **(b) 파라메트릭 정책 (채택)** | ✓ | 가설("churn 이 edge 를 먹는다")을 **직접** 검증. rank_score 임계값 + min-hold 두 파라미터를 **TRAIN 구간에서 grid-search** 로 비용 조정 수익 최대화 → freeze → disjoint·후행 TEST 평가. 결정론적·고속·`_fit_policy` seam 에 그대로 삽입, holdout 기계 무변경. |

### 1.1 정책 정의 (`_CostAwarePolicy`)

두 개의 학습 파라미터:
- **`score_threshold`** (절대 rank_score): 후보의 `rank_score ≥ threshold` 일 때만 매수. TRAIN rank_score 분포의 quantile {0.0, 0.5, 0.75, 0.9} 에서 유도(저확신 진입 억제).
- **`min_hold_steps`** ∈ {1, 2, 4, 8}: 매수 후 N 바 동안 매도 금지(churn 직접 억제).

매 스텝: ① min-hold 충족한 보유분만 매도 → ② 임계값 통과한 최상위 fillable 후보 매수 → ③ 아니면 HOLD. 동률 시 더 선택적/긴 보유(저회전) 쪽으로 결정론적 tie-break.

---

## 2. 비용 인지형 reward 정식화 (additive, opt-in)

`stom_rl/portfolio_env.py`, `PortfolioEnvConfig.turnover_penalty_lambda: float = 0.0`:

```
reward = Δnav_pct − λ · (execution_cost_this_step / nav_before)
```

- `Δnav_pct = (nav_after − nav_before) / nav_before` (기존 reward, 무변경).
- `execution_cost_this_step` = 이번 스텝 체결(fill)에 이미 계상된 브로커 비용(T+1 fill 의 `cost`), `nav_before` 로 정규화 → λ 는 무차원.
- **HOLD/무체결 스텝은 패널티 0** (거래하지 않으면 비용 없음).
- **`λ = 0.0` (기본) ⇒ 엄격한 no-op** — 레거시 NAV-변화 reward 와 비트 동일, 기존 테스트 전부 불변.

### 2.1 fit/eval 시 λ 분리 (정직성 핵심)

- **TRAIN 튜닝 시에만** `COST_AWARE_TRAIN_LAMBDA = 1.0` 적용 (`replace(config, turnover_penalty_lambda=1.0)`) → 튜너가 저회전 파라미터를 선호하도록 유도.
- **held-out TEST 평가는 항상 λ=0 의 무가공 비용 반영 수익** 으로 측정 → 다른 baseline 과 동일 척도로 정직하게 비교(정책을 유리하게 가공하지 않음).

---

## 3. fit-on-train / eval-on-test 프로토콜 + 누수 안전성

기존 Page 11 expanding-window holdout 을 **무변경**으로 재사용 (`portfolio_walk_forward.py`):

- fold N 은 segment `0..N` 으로 fit, **disjoint 하고 strictly-later** 인 segment `N+1` 에서 평가.
- `_fit_cost_aware_policy(train_frame, ...)` 는 **오직 `train_frame`** 만 받아 grid-search → 동결.
- 런타임 하드 가드: train/test 타임스탬프 교집합 = ∅, `min(test) > max(train)` (`run_portfolio_walk_forward` 의 `AssertionError`).

### 3.1 누수 방지 증거 (테스트)

- `test_cost_aware_fit_uses_only_train_segment_no_test_leakage`: TEST 구간(미래) 의 rank_score/price 를 +1000/×3 으로 교란해도 **earliest fold 의 동결 파라미터가 비트 동일** → fitter 가 TEST 를 엿보지 않음 입증.
- 기존 leakage canary 2종(forward-looking column 무시 / 가격 교란 탐지)은 cost_aware 포함 상태로 **여전히 통과**.

### 3.2 fold 별 동결 파라미터 (demand_pressure, cost=25bps)

| fold | TRAIN 범위 (KST) | TEST 범위 (KST) | fitted threshold | fitted min-hold | TEST return% | trade |
|---:|---|---|---:|---:|---:|---:|
| 0 | 09:00:05–09:12:44 | 09:12:45–09:16:03 | 107.90 | 8 | -0.0945 | 2 |
| 1 | 09:00:05–09:16:03 | 09:16:05–09:23:08 | 134.36 | 8 | 0.0000 | 0 |
| 2 | 09:00:05–09:23:08 | 09:23:43–09:29:58 | 127.03 | 8 | 0.0000 | 0 |

→ 모든 fold 에서 **min-hold=8(그리드 최대)** 선택 = 회전 최대 억제. fold 1·2 는 임계값이 높아 TEST 에서 0 거래(현금 보유).

---

## 4. 비용 반영 비교표 (3 holdout fold 평균, `cost_bps=25.0`)

### 4.1 demand_pressure set (227 candidate, Page 14 와 동일 윈도우)

| 정책 | 평균 수익률%(비용 후) | 평균 턴오버 | 평균 거래수 | 평균 비용(KRW) |
|---|---:|---:|---:|---:|
| no_trade | **0.0000** | 0 | 0.00 | 0 |
| equal_weight_candidate | **-0.1132** | 499,895 | 2.00 | 1,250 |
| buy_and_hold | -0.1132 | 499,895 | 2.00 | 1,250 |
| rule_baseline | -3.2816 | 13,453,032 | 54.67 | 33,633 |
| rl_baseline (대역) | -3.2816 | 13,453,032 | 54.67 | 33,633 |
| **cost_aware (TRAIN-fit)** | **-0.0315** | **166,769** | **0.67** | **417** |

→ cost_aware 가 equal-weight 를 **+0.0817%p** 이김. 턴오버 13.45M→167K(**80배↓**), 거래수 54.7→0.67, 비용 33,633→417 KRW. **단, no_trade(0.0%)에는 -0.0315%p 미달** — 우위는 "거의 안 거래"에서 나온다.

### 4.2 widev1 set (25 candidate, 더 엄격한 룰)

| 정책 | 평균 수익률%(비용 후) | 평균 턴오버 | 평균 거래수 | 평균 비용(KRW) |
|---|---:|---:|---:|---:|
| no_trade | **0.0000** | 0 | 0.00 | 0 |
| equal_weight_candidate | **+0.0758** | 499,895 | 2.00 | 1,250 |
| rl_baseline (대역) | -0.2103 | 1,500,405 | 6.00 | 3,751 |
| **cost_aware (TRAIN-fit)** | **0.0000** | 0 | 0.00 | 0 |

→ equal-weight 가 흑자(+0.0758%)인데, 정책이 TRAIN 에서 임계값을 너무 높게 fit(192–312) → TEST 0 거래 → no_trade 동률, **equal-weight 에 -0.0758%p 패배**. 정직한 음성 결과.

### 4.3 비용 민감도 sweep (demand_pressure) — 우위의 출처 규명

| cost_bps | cost_aware% | equal_weight% | no_trade% | gap(ca−ew) | ca>ew? |
|---:|---:|---:|---:|---:|:--:|
| 0.0 | -0.0404 | +0.0117 | 0.0000 | **-0.0521** | ✗ No |
| 5.0 | +0.0019 | -0.0133 | 0.0000 | +0.0151 | ✅ Yes |
| 10.0 | -0.0065 | -0.0383 | 0.0000 | +0.0318 | ✅ Yes |
| 25.0 | -0.0315 | -0.1132 | 0.0000 | **+0.0817** | ✅ Yes |

→ **결정적 증거**: gap 이 cost=0 에선 음수(정책 우위 없음), 비용↑ 할수록 단조 증가. **정책의 우위 = 100% 회전 비용 회피이지 알파가 아니다.** Page 14 의 "알파 부재가 아니라 회전 비용" 가설을 학습 정책으로 재확증.

---

## 5. 판정

| 질문 | 답 |
|---|---|
| 비용 인지형 정책이 `cost=25bps` 후 equal-weight 를 이기는가? | **MARGINAL / 조건부**: demand_pressure 에선 Yes(+0.082%p), widev1 에선 No(-0.076%p) |
| 우위의 출처는? | **회전 비용 회피** (cost=0 에선 우위 소멸, cost↑ 단조 증가). 종목 선택 알파 아님 |
| 정책이 학습한 최적 행동은? | **거의 거래하지 않기** (min-hold=8, 높은 임계값) → no_trade 에 수렴 |
| 고빈도 대역(rl_baseline)은 이기는가? | **압도적 Yes** (-3.28% vs -0.03%, 비용 80배↓) |
| 누수 있는가? | **없음** — fit 은 train_frame 만, TEST 교란이 동결 파라미터 불변(테스트 입증) |

**트랙 B 종착점 (정직)**: Page 14 §6 "대안 종착점"에 정확히 부합 — 비용 인지형 reward 보강 후에도 학습 정책이 종목 선택 알파를 만들지 못했고, 그 최적해는 "저회전(≈현금 보유)"이다. **이 데이터/비용에서 이 candidate 셋은 저회전 equal-weight/no_trade 가 강한 baseline**이라는 것이 정당한 결론. 알파를 짜내거나 수치를 가공하지 않았다.

---

## 6. 다음 연구 방향

1. **알파 신호 자체 강화 (최우선)**: 회전 억제는 한계 효용에 도달(현금 보유로 수렴). 이제 필요한 건 **종목 선택 우위** — candidate 의 rank_score 가 미래 수익과 상관이 있는지부터 검증해야 한다. 상관이 없으면 어떤 정책도 no_trade 를 의미 있게 못 넘는다.
2. **데이터 폭 확대**: 단일 세션·2~3종목·30분. fold 1·2 가 0 거래로 끝나 신호가 빈약. 더 많은 세션/종목(Page 16 게이트)에서 cost_aware 가 거래를 하는 구간을 확보해야 진짜 비교가 됨.
3. **min-hold 그리드 상향 검토**: 모든 fold 가 min-hold=8(최대) 선택 → 더 긴 hold 가 더 나을 수 있음(그리드 경계 효과). 단 데이터 폭 확대가 선행되어야 의미.
4. **(보류) SB3 MaskablePPO**: gymnasium/SB3 설치 + portfolio_env Gym 래퍼 필요. 본 파라메트릭 결과가 "회전 억제로는 알파가 안 나온다"를 보였으므로, RL 도입 전 (1) 신호 검증이 우선.

---

## 7. follow-up B (T+1 sell price 대칭) — **스킵** (정직한 사유)

- 현 env 의 sell 경로는 보유 종목이 **현재 후보일 때 이미 T+1 `fill_price` 사용** (`_fill_price_for(symbol, _candidate_row_for(...))`); 비후보 보유분만 mark(`prices_before`) fallback.
- 본 소규모 universe(2~3종목)에선 보유 종목이 거의 항상 현재 후보 ⇒ follow-up B 는 **사실상 no-op**.
- 비후보 보유분에 panel T+1 을 주려면 **panel 전체를 env 에 주입**해야 함(env 는 현재 candidates 만 보유) = 작은 additive 변경이 아님 → 결정론·scope 위험.
- 과제 가이드("작은 additive 변경이면, 아니면 skip 후 note")에 따라 **스킵**. 데이터 폭 확대 시 재검토.

---

## 8. 산출물 (커밋 안 함, `.omx/` gitignore)

`.omx/artifacts/cost_aware_policy/`:
- `cand_demand_pressure.csv` (227), `cand_widev1.csv` (25) + topk JSON
- `demand_pressure/`, `widev1/`, `dp_cost{0,5,10,25}/`, `dp_determinism_rerun/` — 각 `portfolio_walk_forward_report.json` + `_folds.csv`
- `comparison.csv`, `comparison.json` — 전체 fold 평균 비교 + 비용 sweep (fold CSV read-only 집계)

## 9. 메모 (정직성)

- 기본 동작 무변경(`λ=0`) — 기존 stom_rl 회귀 테스트 비-감소 확인(+4 신규 테스트, 0 회귀; 사전 존재하던 gymnasium 미설치 실패 1건은 본 작업과 무관).
- TEST 평가는 λ=0 무가공 비용 반영 수익. TRAIN 튜닝만 λ=1 사용(분리 명시).
- DB 풀스캔 없음(2~3종목·30분·219 ts). `eval/exec/__` 미사용. cost=0 에서 우위 소멸을 숨기지 않고 비용 sweep 으로 정량화.
