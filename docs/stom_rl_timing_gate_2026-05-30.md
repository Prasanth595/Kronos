# P1b — baseline-relative de-idealized 타이밍 게이트 결과 (딥RL 최종 go/no-go)

- 작성일: **2026-05-30 KST** / 브랜치: `feature/stom-rl-lab`
- 상위: `docs/stom_rl_predictability_gate_2026-05-30.md`(P1), `docs/stom_rl_deeprl_opening20min_design_2026-05-29.md`(설계)
- 구현: `stom_rl/marketable_fill.py`(순수 마켓에이블 체결) + `stom_rl/timing_gate.py`(P1b 게이트) + 테스트 11개
- 대상: 시초 갭상승 `ts_imb` — **RULE strategy, NOT reinforcement learning.** 수익 주장 아님.

---

## 0. 한 줄 결론 (결정적 NO-GO)

**모델의 마이크로구조 진입-타이밍 선택은, 마켓에이블 체결·paired 비교에서, 룰의 고정 09:00 진입보다 −0.38~−0.46%/trade *더 나쁘다*(full universe N=5,173, CI 음수쪽 0 제외, 전 5경계, DSR=0). P1의 "GO"는 드리프트+idealized 체결 artifact였음이 확정됐다. → 딥RL 진입-타이밍은 만들 가치가 없다.**

P1의 ranking 신호(IC≈0.10)는 통계적으론 실재하나, 그것을 *타이밍*에 쓰면 가치를 *파괴*한다: 모멘텀 종목에서 "예측 net이 높은 초"는 *이미 오른 뒤*라, 늦게 추격 진입 → 남은 상승은 적고 스프레드만 더 문다.

---

## 1. 결과 — full universe (결정론적·권위 수치)

전 종목(`--max-symbols 0`) → 부분집합 의존 없음. **이것이 확정 수치다.**

| 항목 | 값 |
|---|---|
| instances / samples | 5,173 / 532,245 |
| 룰 고정 09:00 de-idealized net | **+0.884%/trade** (마켓에이블 buy@ask/sell@bid에도 idealized +0.9%와 거의 동일 → **룰 엣지는 현실 체결서 유지**) |
| ridge 증분(모델−룰) | **−0.456%/trade**, CI [−0.575, −0.345] (전부 음수), Sharpe −0.172, DSR 0.000 |
| gbm 증분(모델−룰) | **−0.384%/trade**, CI [−0.495, −0.272] (전부 음수), Sharpe −0.148, DSR 0.000 |
| per-boundary 증분 | ridge −0.43~−0.47 / gbm −0.35~−0.41 (전 5경계 음수, 타이트) |
| DSR 설정 | external sharpe_variance=0.0064(SD 0.08), n_trials=40 (보수적) |
| **VERDICT** | **NO-GO** |

> bounded(`--max-symbols 120`)는 `list_stock_tables`가 고르는 120종목 부분집합에 따라 비결정적이라(룰 net +0.12~+0.46%, 증분 −0.56~−1.18%로 흔들림) 권위 수치가 아니다. **결론(전 경계 음수·NO-GO)은 모든 run·full에서 불변.** full이 확정.

---

## 2. 왜 모델이 룰보다 *나쁜가* (단순 무효가 아니라 해로움)

모델은 "예측 진입-net이 가장 높은 초"에 진입한다. 그런데 이 종목들은 갭상승 모멘텀이라, 체결강도·OFI가 강해 보이는 초는 **대개 이미 급등한 직후**다. 거기서 진입하면:
- 남은 상승 여력↓ (TP까지 거리↓), 되돌림 위험↑,
- 마켓에이블 체결로 스프레드를 또 문다.
→ 룰의 **시초(09:00) 진입**(움직임 *전*)이 구조적으로 유리. 모델 타이밍은 full universe서 −0.38~−0.46%/trade 손해.

이것이 P1 "GO"의 정체를 확정한다: P1은 (a) baseline 대비가 아니라 *not-trading* 대비였고(=룰이 이미 먹는 드리프트를 자기 공으로 셈) (b) idealized 체결이었다. 둘을 고치니 신호는 타이밍 우위가 0이 아니라 **음(−)**.

---

## 3. 강건성과 정직성 캐비엇

- **paired 비교라 fill 모델의 가혹함에 sign이 강건**: 룰·모델 둘 다 동일 마켓에이블 체결 → 스프레드를 과대 가정해도 *증분 부호*(모델<룰)는 불변. 전 5경계 음수·CI 0 제외 → 견고.
- **(정정) 룰 de-idealized net은 full universe서 +0.884%/trade** — 마켓에이블 체결(스프레드 2회 교차)에도 idealized +0.9%와 거의 동일. 즉 **룰 엣지는 현실 체결서 유지**된다. 앞서 bounded에서 보였던 +0.12/+0.46%는 소표본 부분집합 노이즈였고, 스프레드가 룰을 잠식한다는 우려는 full에서 **해소**. (단 본 마켓에이블 모델은 항상 풀스프레드 교차 가정이라 보수적; 실제는 더 나을 수 있음.)
- RULE NOT RL. 수익 주장 아님. STOM-trigger 조건부.

---

## 4. 딥RL 탐구 종합 (게이트 사슬 최종)

| 게이트 | 결과 |
|---|---|
| R0 딥리서치(105 에이전트) | 비용차감 OOS 수익 RL 사례 0건; 사전확률 ~8–15% |
| P0 MinTRL | 작은 엣지는 표본서 검출 불가(소표본 게이트) |
| P1 (idealized, non-baseline-relative) | ranking 신호 IC≈0.10 실재 — 단 artifact성 "GO" |
| **P1b (de-idealized, baseline-relative)** | **모델 타이밍이 룰보다 −0.38~−0.46%/trade 열등(full N=5,173) → 결정적 NO-GO** |

**최종: 이 데이터에서 딥RL(진입-타이밍)은 룰을 못 이긴다. 실재하는 ranking 신호조차 현실 체결·baseline-relative에선 타이밍 가치가 음(−).** A2/A3/A4(메타라벨링·표현학습·offline RL)는 **착수 안 함** — P1b가 그 전제(증분 신호 존재)를 기각.

> 단, RL이 "무의미"한 게 아니라 **이 문제·이 데이터에 부적합**하다는 정밀 결론이다. 데이터(L2·대조군)나 문제(execution)가 바뀌면 재검토 대상.

---

## 5. 재현
```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.timing_gate --max-symbols 120   # bounded
py -3.11 -X utf8 -m stom_rl.timing_gate --max-symbols 0     # full
py -3.11 -m pytest tests/test_stom_rl_marketable_fill.py tests/test_stom_rl_timing_gate.py -q  # 11 passed
```
산출: `.omx/artifacts/timing_gate/summary_*.json`.

## 6. 페이지 트랙
| | 상태 |
|---|---|
| R0/R1/R1b/B/C/D / P0+P1 | ✅ |
| **P1b baseline-relative de-idealized 게이트 (full N=5,173)** | ✅ **결정적 NO-GO — 딥RL 진입-타이밍 폐기** |
| A2/A3/A4 RL | ❌ 미착수(전제 기각) |
| 룰 마켓에이블 체결 생존성 | ✅ full서 +0.884%/trade 유지(스프레드 우려 해소) |
