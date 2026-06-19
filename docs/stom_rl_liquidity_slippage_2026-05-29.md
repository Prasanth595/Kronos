# Page C — 유동성/슬리피지 & gap-through 꼬리

- 작성일: **2026-05-29 KST**
- 브랜치: `feature/stom-rl-lab`
- 상위 앵커: `docs/stom_rl_session_progress_2026-05-29.md`, `docs/stom_rl_gap_up_full_universe_2026-05-29.md`(Page B)
- 구현: `stom_rl/liquidity_model.py`(순수함수+CLI) / 테스트 `tests/test_stom_rl_liquidity_model.py`(15개) / 산출물 `.omx/artifacts/liquidity/summary.json`
- 대상: **시초 갭상승 `ts_imb` 룰 — RULE strategy, NOT reinforcement learning.**

---

## 0. 한 줄 결론

**유동성: PASS.** 계좌 1천만~1억(f=10% → 주문 100만~1000만원)에서 주문은 진입봉 1초 거래대금의 **0.2~1.6%(median)**에 불과하고 **100% 트레이드가 feasible(≤1x)**, 슬리피지는 비관적 coef(20bp/√)에서도 **<3bp**라 slip-adjusted 기대값이 **+0.72~0.75% 유지**(breakeven ~75bp 여유 대비 무시 가능). **gap-through 꼬리: PASS.** full-universe 최악체결(sl_gap_stress)에서도 ts_imb 전 연도 양수(**2022 +0.603 포함**, bounded 음수 해소), breakeven OOS 81bp(비용 3.5배), 슬리피지 43bp서도 +0.445%.

---

## 1. ⚠️ 단위 발견 (중요 — 잘못된 결론을 막은 sanity check)

초기 분석은 `초당거래대금`(entry_sec_amount)을 raw 원으로 가정 → median participation 1606x, "0% feasible"라는 **불가능한 결과**가 나옴(622원/초는 1주 값도 안 됨). 점검 결과:

- 같은 DB 행에서 **`초당매수금액 2,072,136원 / 초당매수수량 3,102주 = 668 = 현재가`** → 초당매수/매도금액은 **raw 원**.
- **`초당거래대금` = `당일거래대금`(누적, 백만원)의 초당 증분 = (초당매수금액+초당매도금액)/1e6** (예: 5.8M원→6, 41.8M원→42, 2.27M원→2). ✅
- 결론: **`초당거래대금`은 백만원 단위.** 로더에서 ×1,000,000로 원 환산.

median 622 = **6.22억원/초** 거래대금. 보정 후 결과가 물리적으로 타당.

---

## 2. 유동성 feasibility (보정 후, ts_imb N=5175, full universe)

f=10%, base 23bp, gross 0.98%(full OOS). 슬리피지 = coef·√(participation), coef는 **무보정 가정**(L2 없음) → sweep.

| 계좌 | 1회 주문 | median participation | feasible(≤1x) | strict(≤0.1x) | slip-adj exp (coef 5/10/20bp) |
|---|---:|---:|---:|---:|---:|
| 1,000만 | 100만 | **0.2%** | 100% | 100% | +0.748 / +0.746 / +0.742 |
| 5,000만 | 500만 | **0.8%** | 100% | 97% | +0.746 / +0.741 / +0.732 |
| 1억 | 1,000만 | **1.6%** | 100% | 93% | +0.744 / +0.737 / +0.725 |

- 세 계좌 모두 **median 슬리피지 <3bp** → +0.75% 엣지를 거의 깎지 않음(breakeven 여유 ~75bp 대비 무시 가능).
- 1개 entry-second는 거래대금 0(유동성 공백)이라 drop. 나머지 전 트레이드 feasible.

### 2.1 스케일 한도 (어디서 유동성이 binding?)
- median 초당거래대금 6.22억원 → 주문 ≤ 1x(한 초 거래대금)이려면 **median 기준 계좌 ~62억원**까지 여유.
- p10 = 1.46억원(얇은 트레이드) → 그 구간은 **계좌 ~14.6억원**부터 1x 접근.
- 즉 **1억 계좌는 매우 여유**, 수억~수십억까지 대부분 feasible. 본 전략은 상당한 계좌 규모까지 유동성 확장 가능.

---

## 3. 슬리피지 해석 (정직)

- √-impact는 표준 형태지만 **coef는 L2 없이 보정 불가 → 가정**. 그래서 5/10/20bp sweep으로 제시.
- 핵심: 이 작은 participation(≤1.6%)에서는 어떤 coef를 써도 슬리피지가 <3bp라 **결론(엣지 유지)이 coef에 둔감**. 이것이 유동성 PASS의 강건성.

---

## 4. gap-through 꼬리 (체결 de-idealization)

R1에서 손절이 regret의 55%였고, sl_gap_stress(손절 gap-through 최악체결)가 실제 꼬리를 잡는다.

- **bounded(120) 확정**(핸드오프 §5.4–5.5, 23bp): idealized +0.952 / realized +0.906 / **sl_gap_stress +0.811%/trade**. 최악 스트레스에도 양수.
  - 연도별 sl_gap_stress: 2022 −0.05 / 2023 +1.32 / 2024 +0.96 / 2025 +0.85 / 2026 +0.76 (2022만 소폭 음수, 소표본).
- **full-universe sl_gap_stress: PASS** (2026-05-29 완료, `.omx/artifacts/gap_up_full_stress/`). ts_imb N=5175, 최악 손절 gap-through 체결에서도:

| 지표 | 값 |
|---|---:|
| 연도별 @23bp | 2022 **+0.603** / 2023 +0.757 / 2024 +0.674 / 2025 +0.578 / 2026 +0.577 (전 연도 양수) |
| breakeven IS/OOS | +91.3 / +81.3bp (비용 23bp의 ~3.5배) |
| OOS multi-boundary | +0.583 ~ +0.650 (전 경계 양수) |
| 슬리피지 23→43bp | +0.645 → +0.445 |

→ **bounded sl_gap_stress의 2022 −0.05가 대표본에서 +0.603으로 해소**(Page B idealized와 동일한 소표본 노이즈 패턴). 최악 체결 가정·전 종목·전 연도에서 양수 유지. idealized(+0.75) 대비 ~0.15%p 깎이지만 robust.

---

## 5. 정직성 캐비엇

1. `초당거래대금`은 진입봉 1초값 **PROXY**. 첫 세션바가 09:00 누적값일 수 있어 분모가 부풀면 participation/슬리피지가 **실제보다 낙관적**일 수 있음 → feasibility 여유는 상한으로 해석.
2. 슬리피지 coef는 **가정**(L2 없음). 단 결론은 coef에 둔감(§3).
3. 여전히 triggered-subset DB. 시장 전체 일반화 미입증.
4. 이 분석은 주문 **크기** 유동성 검증이지 완전한 체결 realism(큐포지션·부분체결)이 아님 — 그건 데이터 한계로 불가.

---

## 6. 재현 명령

```powershell
$env:PYTHONIOENCODING='utf-8'
# 유동성 분석 (full-universe instances.json 사용)
py -3.11 -X utf8 -m stom_rl.liquidity_model
# gap-through 꼬리(full)
py -3.11 -X utf8 stom_rl/gap_up_backtest.py --max-symbols 0 --fill-mode sl_gap_stress --regime-analysis --regime-cost-bps 23 --artifacts-dir .omx/artifacts/gap_up_full_stress
# 테스트
py -3.11 -m pytest tests/test_stom_rl_liquidity_model.py -q   # 15 passed
```

핵심 출력(2026-05-29): ts_imb N=5175, 1억 계좌 median participation 1.6%, 100% feasible, slip<3bp, slip-adj +0.73~0.74%.

---

## 7. 페이지 트랙 갱신

| 페이지 | 상태 |
|---|---|
| A 사이징 / R0·R1·R1b(RL 청산 폐기) / B full universe | ✅ 완료 |
| **C 유동성/슬리피지** | ✅ **완료 — 유동성 PASS + gap-through PASS** (최악체결 전 연도 양수) |
| **D read-only paper/forward** | ⬜ **다음 권고** (≥20거래일 신호 관찰) |
| E broker/order 연동 | 🔒 승인 전 금지 |

검증: liquidity_model 테스트 15 passed, code-reviewer APPROVE(단위 보정 실데이터 재확인). 단위 버그는 sanity check로 출시 전 차단.
