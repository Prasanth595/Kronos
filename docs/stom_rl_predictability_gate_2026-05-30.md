# P0+P1 예측 게이트 결과 — 딥RL go/no-go (조건부)

- 작성일: **2026-05-30 KST** / 브랜치: `feature/stom-rl-lab`
- 상위: `docs/stom_rl_deeprl_opening20min_design_2026-05-29.md`(설계), `docs/stom_rl_session_progress_2026-05-29.md`
- 구현: `stom_rl/microstructure_features.py`(순수 인과피처) + `stom_rl/predictability_probe.py`(P0 MinTRL + P1 walk-forward 프로브) + 테스트 16개
- 대상: 시초 갭상승 `ts_imb` — **RULE strategy, NOT reinforcement learning.** 수익 주장 아님.

---

## 0. 한 줄 결론 (정직)

**대표본(full universe)에서 마이크로구조가 60초 forward return을 OOS·미학습종목·전 기간에서 일관되게 예측하는 *modest하지만 robust한 ranking 신호(IC≈0.10)*가 처음으로 드러났다. 그러나 "GO" 판정은 (1) 정책 net이 baseline-relative가 아니고 (2) idealized 체결을 쓰며 (3) DSR이 하드 파라미터에 따라 뒤집히는 세 가지 이유로 과대평가돼 있다. 정직한 상태는 "신호는 실재, 룰 대비 증분·현실 체결 후 수익성은 미입증".**

---

## 1. 결과: bounded vs full

| 지표 | bounded(120종목, N=235) | **full universe(N=5,173, 569k 샘플)** |
|---|---:|---:|
| rank-IC ridge / gbm | +0.027 / +0.060 | **+0.075 / +0.104** |
| IC 95% CI 0 제외 | ridge✗ / gbm✓ | **둘 다 ✓** |
| per-boundary IC 안정성 | gbm +0.04~0.07 | ridge +0.074~0.079 / **gbm +0.099~0.105 (5경계 안정)** |
| **symbol-disjoint IC(미학습 종목)** | — | **ridge 0.067 / gbm 0.106** |
| 임계정책 net/trade | +0.18% (Sharpe 0.06) | **+0.44%/+0.38% (Sharpe ~0.15, N≈1,700)** |
| DSR | ≈0 → NO-GO | 1.000 → GO |

→ bounded NO-GO는 **검정력 부족**(N=235)이었다. 대표본에서 ranking 신호가 실재함이 분명해졌고, **미학습 종목에서도 유지**(0.067~0.106)되어 ticker 암기가 아니다. per-boundary 안정성으로 단일기간 우연도 아니다. **이 랩 최초의 hard-to-dismiss 양성 신호.**

---

## 2. ⚠️ "GO"가 과대평가된 3가지 이유

### (1) 정책 net이 baseline-relative가 아님 — 가장 중요
대상 종목은 전부 갭상승 모멘텀(등락율≥2·체결강도≥100·호가 imbalance≥0.5)이라, forward 60s return은 **무조건부로 양(+) 드리프트**를 가진다. 임계정책 +0.4%는 모델의 *선택력*이 아니라 **룰이 이미 harvest하는 그 드리프트**를 대부분 반영한다. 설계가 명시한 **baseline-relative(룰/항상진입 대비)** 를 프로브가 생략 → **룰 대비 *증분* 가치는 미입증.** IC(랭킹)는 실재하지만, 랭킹이 *증분 net*으로 이어지는지는 별개다.

### (2) idealized 체결
라벨 = 현재가 forward return − 평탄 23bp. **마켓에이블 체결(매수=매도호가1, 매도=매수호가1) + 스프레드·시장충격 미반영.** 60초 스캘프는 스프레드를 두 번 건너고 회전이 높아, 실제 net은 +0.4%보다 **상당히 낮을 가능성**이 크다. 설계는 idealized 의존 결과를 폐기 대상으로 명시.

### (3) DSR=1.000은 파라미터 artifact
DSR의 `sharpe_variance`를 프로브 내 10개 config(같은 전략의 중첩 경계, 상호 상관)에서 유도 → 0.0002로 과소 → expected-max-Sharpe 바가 trivially 낮아 어떤 양수 Sharpe도 통과. 반대로 하드코딩 0.25는 바를 0.79로 만들어 NO-GO. **즉 verdict가 하드 파라미터로 뒤집히므로 DSR은 여기서 신뢰 불가.** 믿을 것은 raw 유의성: 정책 Sharpe 0.15·N≈1,700 → t≈6.7(다중검정 보정 후에도 raw로는 유의), IC CI 매우 타이트. **단 (1)·(2) 때문에 이 유의성이 "증분·현실 net"의 유의성은 아니다.**

---

## 3. 정직한 판정

**조건부 — "신호 실재, 증분·현실 수익성 미입증".** bounded NO-GO도 full GO도 부분 artifact이고 진실은 그 사이다:
- ✅ 마이크로구조의 60초 ranking 예측력은 **실재·robust**(IC≈0.10, OOS·미학습종목·전기간). 딥(gbm 0.10) > 선형(ridge 0.075) → 깊이가 약간 기여.
- ❓ 그 신호가 **룰의 고정진입을 마켓에이블 체결 후에 이기는지**(baseline-relative + de-idealized)는 미검정.

---

## 4. 결정적 다음 게이트 (이게 통과해야 RL로 감)

**baseline-relative + de-idealized 재검정**:
1. 라벨/정책을 **마켓에이블 체결**로: 진입=매도호가1, 청산=매수호가1(또는 보수적 슬리피지), 23bp 위에 스프레드·충격 반영.
2. **baseline-relative**: 모델 타이밍/선택의 net을 **룰의 고정 09:00 진입 net과 paired-difference**로 비교. 증분이 양수인지.
3. **proper deflation**: 외부 합리적 sharpe_variance(per-trade 스케일 SD~0.05~0.1) + 랩 전체 trial 원장 기반 Harvey-Liu haircut.
4. linear-vs-deep 사전등록(설계 P2).
- **통과 시에만** RL 형식(A2 메타라벨링 → A3 표현학습 → A4 offline IQL)으로. 미통과면 신호는 룰이 이미 먹는 드리프트로 귀결.

---

## 5. 재현
```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.predictability_probe --max-symbols 0   # full
py -3.11 -X utf8 -m stom_rl.predictability_probe --max-symbols 120 # bounded
py -3.11 -m pytest tests/test_stom_rl_microstructure_features.py tests/test_stom_rl_predictability_probe.py -q  # 16 passed
```
산출: `.omx/artifacts/predictability/summary_full.json`. 코드리뷰 APPROVE(누설 없음 구조적 확인; 본 문서의 3개 한계는 프로브 설계상의 알려진 caveat).

---

## 6. 페이지 트랙
| | 상태 |
|---|---|
| R0 딥리서치 / R1·R1b(청산RL 폐기) / B / C / D | ✅ |
| **P0+P1 예측 게이트** | ✅ **조건부 — robust ranking 신호 발견, 증분·현실 수익성 미입증** |
| **P1b baseline-relative + de-idealized 게이트** | ⬜ **다음 — 결정적** |
| A2/A3/A4 RL | 🔒 P1b 통과 시에만 |

> 정직성: RULE NOT RL. 이 결과는 사전확률을 **상향**(실재 신호)하되 "RL이 돈 번다"는 아니다. 증분·현실 체결 게이트가 진짜 시험이다.
