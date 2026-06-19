# 인과적 청산 baseline 결과 (Page R1b) — 청산 RL 게이트 종결

- 작성일: **2026-05-29 KST**
- 브랜치: `feature/stom-rl-lab`
- 상위 앵커: `docs/stom_rl_oracle_exit_ceiling_2026-05-29.md`(R1), `docs/stom_rl_rl_feasibility_research_2026-05-29.md`(R0)
- 구현: `stom_rl/exit_baselines.py`(순수함수+CLI) / 테스트 `tests/test_stom_rl_exit_baselines.py`(22개) / 산출물 `.omx/artifacts/exit_baselines/summary.json`
- 대상: **시초 갭상승 `ts_imb` 룰 — RULE strategy, NOT reinforcement learning.**

---

## 0. 한 줄 결론 (결정적)

**어떤 인과적 청산 변형(SL 확대·트레일링)도 고정 TP5/SL1을 이기지 못했고, 인-샘플 최적 변형은 OOS에서 오히려 −0.71%/trade 더 나빴다(DSR 0.931<0.95). 따라서 R1의 큰 천장은 인과적으로 포착 불가능한 hindsight이며 → 청산 RL(R3)은 만들지 않는다. 운영 트랙(Page B)으로 복귀한다.**

이는 R0 딥리서치(문헌상 청산 RL의 비용차감 OOS 우위 0건)와 정확히 합치한다. 게이트-우선 방식으로 두 번의 bounded 분석만으로 "청산 RL 해야 하나?"를 **데이터로 닫았다.**

---

## 1. 전 표본 후보 비교 (ts_imb, N=235, realized, 23bp)

| 후보 | 평균 net | 승률 | per-trade Sharpe |
|---|---:|---:|---:|
| **fixed_tp5_sl1 (현행)** | **+0.906%** | 42% | **+0.303** |
| fixed_tp5_sl1.5 | +0.850% | 46% | +0.267 |
| fixed_tp5_sl2 | +0.797% | 49% | +0.234 |
| fixed_tp5_sl3 | +0.876% | 54% | +0.238 |
| trail_1 | +0.532% | 49% | +0.283 |
| trail_2 | +0.800% | 51% | +0.252 |
| trail_3 | +0.750% | 48% | +0.200 |
| trail_2_tp5 | +0.737% | 51% | +0.277 |
| trail_3_tp5 | +0.764% | 49% | +0.238 |

→ **현행 고정 TP5/SL1이 9개 후보 중 평균 net·Sharpe 모두 최고.** SL을 넓히면 승률은 오르지만 기대값·Sharpe는 떨어지고, 트레일링은 일찍 털려 기대값이 낮아진다. 청산 변형은 전부 edge를 깎는다.

## 2. Walk-forward (인-샘플 선택 → OOS 보고, 누설 없음)

| 항목 | 값 |
|---|---:|
| 경계일 / N(IS/OOS) | 20250410 / 154·81 |
| 인-샘플 최적 선택 | **trail_1** (현행 아님) |
| 선택 변형 OOS net | +0.373% |
| 현행 baseline OOS net | **+1.086%** |
| **OOS 개선** | **−0.713%** (선택 변형이 더 나쁨) |
| Deflated Sharpe Ratio | **0.931** (< 0.95) |

→ 교과서적 과적합: 인-샘플에서 가장 좋아 보인 trail_1이 OOS에서 현행보다 **0.71%p/trade 열등**. 9개 시도를 보정한 DSR도 0.931로 유의 기준(0.95) 미달.

---

## 3. 사전 등록 판정 규칙 적용 (둘 다 FAIL)

| 게이트 | 기준 | 결과 |
|---|---|---|
| ① OOS net이 현행을 이김 | 개선 > 0 | ❌ −0.713% |
| ② DSR > 0.95 | 다중검정 보정 유의 | ❌ 0.931 |

**둘 다 실패 → 청산 헤드룸은 hindsight → 청산 RL(R3) 폐기, 운영 트랙 복귀.**

부수 확인: 현행 룰의 OOS net(+1.086%)이 전표본(+0.906%)보다 높다 → **최근 구간(2025-04 이후)에서 룰이 잘 버텼다**(룰 강건성 긍정 신호).

---

## 4. 의미

1. **고정 TP5/SL1은 이미 인과적 청산 프런티어 근처다.** R1의 capture 17.8%·regret +4.18%는 "완전예지로만" 도달 가능한 hindsight였고, 실행 가능한 단순 규칙으로는 1mm도 못 가져온다.
2. **RL은 이 격차를 더 못 메운다**(RL ≤ 가능한 최선 인과정책; 단순 인과정책조차 현행을 못 이김). R0 문헌 결론과 동일.
3. 따라서 **AI/RL 청산 트랙은 여기서 종결**한다. 검증된 수익원은 변함없이 **룰 전략 + Page A 사이징**이다.

---

## 5. 재현 명령

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.exit_baselines --max-symbols 120 --cost-bps 23 --filter ts_imb
py -3.11 -m pytest tests/test_stom_rl_exit_baselines.py -q   # 22 passed
```

핵심 출력(2026-05-29):
```text
fixed_tp5_sl1  mean_net=+0.906% win=42% sharpe=+0.303   <- 전 후보 중 최고
walk-forward: selected=trail_1  OOS_net=+0.373%  baseline_OOS_net=+1.086%
OOS_improvement=-0.713%  deflated_sharpe_ratio=0.931
```

---

## 6. 페이지 트랙 갱신 — RL 트랙 종결, 운영 트랙 복귀

| 페이지 | 상태 |
|---|---|
| R0 RL 타당성 딥리서치 | ✅ 완료 |
| R1 oracle-exit 천장 | ✅ 완료 (여지=hindsight 가능성) |
| **R1b 인과적 청산 baseline** | ✅ **완료 — 청산 RL 폐기 판정** |
| R2 메타라벨링(진입 필터) | ⬜ 선택(낮은 우선순위; 진입 알파 부재 이미 검증) |
| R3 offline RL 청산 | ❌ **폐기**(R1b 게이트 실패) |
| **B full universe 재검증** | ⬜ **다음 권고**(운영 본선) |
| C 유동성/꼬리 → D paper → E broker | 이후 |

검증: R1b 코드리뷰 APPROVE(DSR 수식 Bailey-LdP 정확 일치), 테스트 22 passed.
