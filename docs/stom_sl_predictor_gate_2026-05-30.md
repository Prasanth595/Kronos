# 실험 ③ — SL예측 선행 분류기 (싼 디리스커 게이트)

- 작성일: **2026-05-30 KST** (full-universe run 완료 2026-05-31) / 브랜치: `feature/stom-rl-lab`
- 상위: `docs/stom_data_layer_assessment_2026-05-30.md`(실험 목록 §4)
- 구현: `stom_rl/sl_predictor.py`(순수함수+DB추출기+CLI) + 테스트 `tests/test_stom_rl_sl_predictor.py`(8개) / 산출물 `.omx/artifacts/sl_predictor/summary.json`
- 대상: 시초 갭상승 `ts_imb` 룰(TP5/SL1/09:25) — **RULE strategy, NOT reinforcement learning.** 수익 검정 아님, "조건 걸 게 있나" 측정.

> 수치는 모두 결정론적 산출물 `.omx/artifacts/sl_predictor/summary.json` 실측값. (초안에 추정치를 적었다가 full-run 실측으로 §3·§4 전면 정정함.)

---

## 0. 한 줄 결론 (GO — 단, "리스크 예측"이지 "알파"가 아님)

**진입·첫 30초 마이크로구조로 "이 트레이드가 결국 SL로 끝날지"는 *예측 가능*하다(full N=5,173, entry AUC 0.60·path30 AUC 0.66–0.68, symbol-disjoint 0.61–0.67, 4개 모델 전부 사전등록 바 통과). → 사전등록대로 GO: 실험 ①(skip-gate)·④(상태조건 청산)의 전제(조건 걸 신호 존재)가 *기각되지 않았다*.**

**중요한 해석 한 줄: 이건 *방향성 알파*가 아니라 *리스크(변동성) 예측*이다.** "−1% 먼저 칠지(SL)"는 하방 변동성 문제이고, microstructure가 *방향*은 못 맞춰도(P1b NO-GO·shuffle 무알파) *변동성/리스크*는 맞춘다는 건 문헌·데이터레이어 평가(1초봉=리스크 레이어)와 정확히 정합. **돈이 되는지는 별개** — 그건 ①이 직접 검정한다.

> 이번 게이트는 이 전체 RL/ML 조사에서 **처음 나온 비-음성 결과**다. 과대해석 금물: entry AUC 0.60은 "동전보다 조금 나음"이고, path30 0.68도 modest다. SL 예측이 곧 수익은 아니다.

---

## 1. 무엇을 검정했나

ts_imb 룰 트레이드를 결과로 라벨링: **결국 SL 청산 = 1, 아니면(TP/시간) = 0** (`rule_exit_reason`, TP5/SL1/09:25, 동점 시 SL 우선·보수적). base rate **SL 59.4%** (N=5,173 중 3,074). SL이 −1%·TP가 +5%라 SL 배리어가 훨씬 가까워 SL률이 높음 → 즉 "SL 예측 ≈ *상방 5% 전에 하방 1%를 칠* 단기 하방변동성 예측".

두 사전등록 스냅샷:

| 스냅샷 | 피처 시점 | 관련 실험 | survival 조건 |
|---|---|---|---|
| **entry** | 진입봉~첫 5초 | ① skip-gate("진입 시 스킵?") | 없음(전 5,173, SL률 59.4%) |
| **path30** | 첫 30초 | ④ 상태청산("30초 보유 중, SL로 끝날까?") | 30초 시점 *미청산*만(4,218, SL률 57.4%) |

피처 = 기존 29개 인과 microstructure 벡터(`causal_feature_vector`: 추세/실현변동성/signed-flow/체결강도 slope/호가 imbalance/microprice/근사 OFI). 누수 없음 — 피처는 t시점(≤5s 또는 ≤30s)까지만, 라벨은 그 이후 결과. 검증 = purged walk-forward(이전 세션 train→이후 세션 test, logit+GBM) + 세션 부트스트랩 AUC CI + symbol-disjoint AUC(미관측 종목).

---

## 2. 사전등록 판정 기준 (결과 *전* 고정)

스냅샷이 **PREDICTABLE**이려면 어떤 모델이든 셋 다 충족:
1. walk-forward test AUC의 세션-부트스트랩 95% CI **하한 > 0.5** (통계적으로 chance 초과)
2. point AUC **≥ 0.55** (실용적 의미 최소선)
3. symbol-disjoint AUC **≥ 0.53** (per-ticker 암기에 강건)

하나라도 PREDICTABLE이면 ①④ GO, 아니면 STOP. **positive control**(심은 신호 AUC 0.92→PREDICTABLE)·**negative control**(노이즈→AT-CHANCE) 단위테스트로 게이트 검출력 검증 완료(8 passed).

---

## 3. 결과 (full universe, N=5,173 instances, 결정론적)

| 스냅샷 | 모델 | AUC | CI95 | symbol-disjoint AUC | 판정 |
|---|---|---:|---|---:|---|
| entry (n=5,173) | logit | **0.603** | [0.577, 0.629] | 0.607 | PREDICTABLE |
| entry | gbm | 0.600 | [0.574, 0.627] | 0.614 | PREDICTABLE |
| path30 (n=4,218) | logit | 0.661 | [0.634, 0.687] | 0.656 | PREDICTABLE |
| path30 | gbm | **0.677** | [0.650, 0.703] | 0.669 | **PREDICTABLE** |

(walk-forward 분할: entry train 3,230 / test 1,938; path30 train 2,633 / test 1,582. boundary 0.7.)

- **4개 모델 전부** point AUC≥0.55·CI 하한>0.5·symbol-disjoint≥0.53 통과. symbol-disjoint(미관측 종목)서도 0.61–0.67 유지 → per-ticker 암기 아닌 **일반화되는 리스크 신호**.
- **path30(0.66–0.68) > entry(0.60).** 첫 30초 경로가 진입 시점보다 SL을 *유의하게 더* 잘 예측한다(0.60 → 0.68). 즉 "보유 중 추가정보"가 실재 → ④(상태청산)의 조건변수가 비어있지 않음. (entry는 logit≈gbm, path30은 gbm이 약간 우수 — 경로에 약한 비선형 존재.)
- **FINAL: GO.**

---

## 4. 함의 (정직하게)

1. **① skip-gate: 살아남음 → 빌드 정당화.** 진입 microstructure가 SL(하방변동성)을 AUC 0.60·강건하게 가른다면, "예측-최악 슬라이스를 스킵해 트레이드당 net을 올린다"는 ①의 전제가 *기각되지 않았다*. 데이터레이어 평가가 ①에 매긴 ~20–30% 사전확률이 **상향**된다.
2. **④ 상태청산: 살아남음(생각보다 강).** 30초 경로가 SL을 0.66–0.68로 예측(진입 0.60보다 +0.06–0.08) → "보유 중 들어오는 경로 정보"가 진짜 있다. 데이터레이어 §4가 ④에 매긴 ~20%는 이 path30 lift 때문에 소폭 **상향**될 여지. 단 갭상승 평균회귀라는 구조적 반대(SL 종목을 더 들면 −1%가 −3% 될 위험)는 그대로 → ① 다음 후순위 유지.
3. **그러나 "예측 가능 ≠ 수익".** 핵심 함정(데이터레이어 평가가 P1을 GO→NO-GO로 태운 **드리프트 트랩**): forward 드리프트가 대체로 양수라, SL로 끝나는 트레이드조차 *비용차감 net이 음수가 아닐* 수 있다. AUC 0.60–0.68 SL예측은 "SL 많은 슬라이스를 식별"할 뿐, 그 슬라이스를 스킵해 **돈이 남는지**는 ①이 직접 검정해야 함. SL 트레이드도 일부는 −1% 손절 전 +α 먹고 시간청산됐을 수 있음(라벨은 *최종* 이유라 net 부호와 1:1 아님).
4. **방향성 알파 아님(재확인).** 선택(shuffle 무알파)·타이밍(P1b NO-GO)은 여전히 음성. SL=리스크 예측만 양성. 즉 **1초봉은 방향이 아니라 리스크를 안다** — 데이터레이어 평가 결론(1초봉=비용/리스크 진실레이어)의 *직접 증거*.

---

## 5. 정직성 캐비엇

1. entry AUC 0.60은 **modest**(완벽 1.0·동전 0.5 사이 하단), path30 0.68도 강하지 않다. 통계적으론 견고(CI·symbol-disjoint·4모델 일치)하나 실거래 분리력은 중간 — "강한 예측"이 아니라 "0이 아닌 예측".
2. SL 라벨은 *최종 청산 이유*. net 손익과 1:1 대응 아님(시간청산 SL-미달도 음수 가능, SL도 도중 +α 후 반전 가능). 따라서 ③의 GO는 "리스크 식별 가능"이지 "수익 식별 가능"이 아님 — ①에서 *비용차감 net 부호*로 재검정 필수.
3. path30은 30초 *미청산* 트레이드만(survivorship 조건). ④에 정확한 모집단이나, entry와 직접 비교 시 모집단이 다름(4,218 vs 5,173)을 유의.
4. ts_imb 트리거 모집단 한정·L2 없음. positive/negative control이 게이트 검출력 보증.
5. 사전등록 0.55 바는 임의성 최소화 선택. 결과는 그 바를 명확히 통과(0.600–0.677)하므로 바 민감도 낮음.
6. RULE not RL. 본 실험은 수익 산출이 아니라 "조건 걸 신호 존재" 측정. 모든 후속 양수치는 in-sample/triggered-subset/라이브 없음.

---

## 6. 재현

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.sl_predictor            # full universe entry+path30 게이트(추출 ~88분)
py -3.11 -m pytest tests/test_stom_rl_sl_predictor.py -q   # 8 passed (planted->PREDICTABLE, noise->AT-CHANCE)
```
산출: `.omx/artifacts/sl_predictor/summary.json`. 핵심(2026-05-31): N=5,173, SL률 59.4%, open_at_30s=4,218, entry AUC 0.600–0.603(sd 0.607–0.614)·path30 AUC 0.661–0.677(sd 0.656–0.669), 4모델 PREDICTABLE, FINAL GO.

---

## 7. 실험 트랙 갱신 (데이터 레이어 평가 §4)

| # | 실험 | 상태 |
|---|---|---|
| ② 초당흐름 재구성 (용량 정직화) | ✅ 완료 — 용량 −98% 정정, 조건부 PASS |
| **③ SL예측 선행 분류기** | ✅ **완료 — PREDICTABLE(entry 0.60·path30 0.66–0.68, 강건), FINAL GO** |
| **① skip-gate** | ⬜ **다음 — ③가 전제 통과, 빌드 정당화(드리프트 트랩 가드 사전등록 필수)** |
| ④ 상태조건 청산 | ⬜ ① 이후(path30 lift로 사전확률 소폭↑, 단 평균회귀 반대 그대로) |

→ **③의 GO로 ①(skip-gate)이 처음으로 "지을 가치"를 얻었다.** 단 이는 *리스크 예측*의 통과이지 *수익*의 통과가 아니며, ①은 비용차감 baseline-relative net으로 드리프트 트랩을 정면 검정해야 한다.
