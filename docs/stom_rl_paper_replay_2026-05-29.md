# Page D — 동결정책 paper replay (forward proxy)

- 작성일: **2026-05-29 KST**
- 브랜치: `feature/stom-rl-lab`
- 상위 앵커: `docs/stom_rl_session_progress_2026-05-29.md`, `docs/stom_rl_liquidity_slippage_2026-05-29.md`(Page C)
- 구현: `stom_rl/paper_sim.py`(순수함수+CLI) / 테스트 `tests/test_stom_rl_paper_sim.py`(9개) / 산출물 `.omx/artifacts/paper_sim/summary*.json`
- 대상: **시초 갭상승 `ts_imb` 룰 + Page A 사이징 — RULE strategy, NOT reinforcement learning.**

> 이 환경엔 **실시간 피드가 없어 진짜 forward/paper는 불가능**하다. 본 페이지는 동결된 전체 정책(룰+사이징)을 과거 DB의 최근 구간에 **그대로 재생(replay)**한 *근사*다. Page A 사이징(지금까지 정적 공식)이 실제 거래 *시퀀스*에 처음 적용된다.

---

## 0. 한 줄 결론

**동결 정책이 끝까지 정상 작동하고, full·최근holdout 모두·낙관/비관 체결 모두에서 계좌가 양수이며 낙폭이 Page A 봉투(약 −2~−3%) 안에 머문다. 단 헤드라인 수익률(+396~612% full)은 복리×idealized의 낙관적 replay 수치이지 미래 기대치가 아니다.** 가장 큰 실질 성과는 **이 replay가 정책의 deadlock 결함을 드러내고 고쳤다는 것**이다.

---

## 1. ⚠️ replay가 드러낸 정책 결함 (Page D의 진짜 가치)

처음 replay에서 FULL이 5175 신호 중 **73개만 taken** + halt로 2610개 skip → 비정상. 원인:
- Page A의 "**7연패 → f=0 (진입 중단)**" 룰을 문자 그대로 적용하면, **중단 중엔 거래가 없어 승리로 streak를 리셋할 수 없다 → 계좌가 영구 동결(deadlock).**
- 수정: 7연패 도달을 **서킷브레이커**로 — 그날 쉬고 **streak 리셋(쿨다운)** → 다음날 재개. (표준 circuit-breaker 설계; `paper_sim`에 국한, Page A 티어/테스트 불변.)
- 수정 후: 정상(아래). **테스트로 deadlock 없음을 고정**(`test_streak_halt_is_a_recoverable_circuit_breaker_not_a_deadlock`).

이것이 "사이징을 실제 시퀀스에 적용"하는 Page D의 핵심 효용 — 정적 공식만으론 안 보이던 운영 결함 발견.

---

## 2. replay 결과 (체결 양 끝, 복리, 초기 1억)

| 구간 | 체결 | 수익률 | maxDD | taken/signals |
|---|---|---:|---:|---:|
| FULL (2022-03~2026-02) | idealized(낙관) | +612.0% | −1.8% | 2606/5175 |
| FULL | **sl_gap_stress(최악)** | **+396.4%** | **−3.1%** | 2606/5175 |
| HOLDOUT (2025-09~2026-02) | idealized | +45.4% | −0.7% | 325/760 |
| HOLDOUT | **sl_gap_stress(최악)** | **+39.3%** | **−0.9%** | 325/760 |

운영 통계: skip(cap/halt) full 2492/77, holdout 429/6. **일손실한도 발동 0일**(예상대로 −3%는 거의 안 닿음). taken은 신호의 ~50%(주로 K=3 동시보유 cap 때문, halt는 드묾).

해석(정직):
- **두 체결 가정 모두, 두 구간 모두 양수 + 한 자릿수% 낙폭** → 정책이 안전하게 작동하고 fill 가정에 robust.
- 최악체결도 full +396%/holdout +39% → 양수 유지.

---

## 3. ⚠️ 헤드라인 수익률을 곧이곧대로 읽으면 안 되는 이유

1. **복리 × 수천 거래**: 2606 거래 복리는 작은 per-trade 엣지도 큰 헤드라인으로 부풀린다. +612%를 "6배 번다"로 읽으면 안 됨.
2. **replay ≠ live**: 같은 과거 DB 재생이지 미래/실시간 검증이 아니다. **과거 곡선 ≠ 미래.**
3. **triggered-subset 편향**: DB는 특정 조건 걸린 세션만 기록 → 전체 기회집합 아님. 실제 신호 가용성/체결은 다를 수 있음.
4. **체결 frictions 미반영**: idealized/stress는 TP/SL 체결 모델일 뿐, 지연·부분체결·실주문 거부 등은 미모델(데이터 한계). Page C 슬리피지(<3bp)는 작지만 별도.
5. **순서/동시성 근사**: 동시 진입(09:00)을 신호강도순 처리로 근사.

→ 따라서 본 결과의 의미는 **"정책이 안전하게·일관되게 굴러간다"는 질적 확인**이지, **수익률 예측이 아니다.**

---

## 4. 재현 명령

```powershell
$env:PYTHONIOENCODING='utf-8'
# 낙관(idealized) replay
py -3.11 -X utf8 -m stom_rl.paper_sim --holdout-start 20250901
# 최악(stress) replay
py -3.11 -X utf8 -m stom_rl.paper_sim --instances .omx/artifacts/gap_up_full_stress/instances.json --holdout-start 20250901 --json-out .omx/artifacts/paper_sim/summary_stress.json
# 테스트
py -3.11 -m pytest tests/test_stom_rl_paper_sim.py -q   # 9 passed
```

---

## 5. 정직성 캐비엇 (유지)

- 실시간 피드 없음 → 진짜 forward 아님. 본 페이지는 **replay 근사**.
- 여전히 triggered-subset DB, idealized/stress 체결모델, 복리 헤드라인.
- 서킷브레이커 리셋은 합리적 표준 설계지만 "쉬고 즉시 풀사이즈 복귀"라 다소 관대 — 더 보수적으로 "복귀 시 probe 사이즈" 변형 가능(후속).

---

## 6. 페이지 트랙 갱신 + 다음

| 페이지 | 상태 |
|---|---|
| A 사이징 / R0·R1·R1b / B full universe / C 유동성·꼬리 | ✅ 완료 |
| **D 동결정책 replay (forward proxy)** | ✅ **완료** — 정책 정상·저낙폭, deadlock 결함 발견·수정 |
| **진짜 forward/paper (실시간 피드)** | ⬜ **다음 — 환경 밖**(실시간 데이터 연동 필요) |
| E broker/order 연동 | 🔒 명시 승인 전 금지 |

**위치**: 백테스트·검증·운영정책 replay까지 완료. 남은 건 **실시간 피드를 붙인 진짜 forward 관찰**(이 환경 밖) → 그 후에만 E(실주문) 검토.

검증: paper_sim 테스트 9 passed(복구/deadlock 방지 포함). code-reviewer 검증 예정.
