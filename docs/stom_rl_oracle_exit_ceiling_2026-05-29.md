# Oracle-exit 천장 테스트 결과 (Page R1)

- 작성일: **2026-05-29 KST**
- 브랜치: `feature/stom-rl-lab`
- 상위 앵커: `docs/stom_rl_rl_feasibility_research_2026-05-29.md`(R0 딥리서치), `docs/stom_rl_resume_commit_2026-05-29.md`
- 구현: `stom_rl/exit_oracle.py` (순수함수 + CLI) / 테스트 `tests/test_stom_rl_exit_oracle.py` (15개) / 산출물 `.omx/artifacts/oracle_exit/summary.json`(gitignored)
- 대상: **시초 갭상승 `ts_imb` 룰 — RULE strategy, NOT reinforcement learning.**

> 가드레일: 이 문서는 RL이 수익난다고 말하지 않는다. "RL 청산을 만들 가치가 있는가"를 **완전예지 상한(oracle)**으로 판정하는 게이트일 뿐이다.

---

## 0. 한 줄 결론

**완전예지 청산 대비 룰의 capture는 17.8%뿐이라 "여지"는 분명히 크지만, 이는 RL을 시작할 *필요조건*일 뿐 *충분조건*이 아니다.** 완전예지 regret은 변동성 있는 어떤 종목에서도 크게 나오기 때문이다. 따라서 R1의 정직한 판정은 "RL을 만들어라"가 아니라 **"인과적 청산 개선(트레일링/SL 조정)이 OOS에서 룰을 이기는지 값싸게 먼저 검정하라(R1b)"**이며, regret의 55%가 손절(SL) 청산에서 나온다는 점이 가장 강한 단서다.

---

## 1. 결과 수치 (ts_imb, N=235, realized 체결, 비용 23bp)

> regret은 비용 불변(oracle·rule 둘 다 1회 왕복비용 차감 → 상쇄). 아래는 검증 corpus와 동일한 bounded universe(`--max-symbols 120`).

| 지표 | 값 | 의미 |
|---|---:|---|
| rule_mean_net | **+0.906%/trade** | 룰의 realized 기대값(핸드오프 realized 수치와 일치 → 모듈 정합성 확인) |
| oracle_mean_net | **+5.089%/trade** | 완전예지 최선 청산(상한) |
| regret 평균 | **+4.182%** | trade당 남긴 청산 가치(상한 대비) |
| regret 중앙값 | +2.842% | |
| regret p90 | +10.384% | |
| regret 최대 | +24.467% | |
| **capture_ratio** | **17.8%** | 룰이 완전예지의 17.8%만 포착 |
| frac_rule_optimal | 1.7% | 룰이 진짜 고점에 청산한 비율(거의 없음 — 당연) |

### 1.1 청산 사유별 regret (가장 중요한 단서)

| 룰 청산사유 | 비중 | 평균 regret |
|---|---:|---:|
| TP (익절) | 31% | +4.296% |
| **SL (손절)** | **55%** | **+4.678%** |
| TIME (시간청산) | 14% | +1.982% |

→ **trade의 55%가 손절로 끝나고, 그 손절들이 평균 +4.68%/trade의 가장 큰 regret을 남긴다.** "−1% 손절이 이후 회복할 종목을 잘라낸다"는 가설과 정합. 이것이 다음 실험의 1순위 타깃이다.

---

## 2. 정직한 해석 — 왜 "RL 즉시 착수"가 아닌가

1. **완전예지 상한은 약한 신호다.** 20분 창에서 가격 경로의 최대값은 인과적으로 도달 불가능한 hindsight다. 변동성 있는 어떤 자산도 완전예지 regret은 크게 나온다. 따라서 capture 17.8%는 "여지 있음"의 *필요조건*만 충족한다(만약 완전예지조차 룰을 못 이겼다면 RL은 확실히 불가 → 그 경우만 즉시 기각).
2. **R0 딥리서치(105 에이전트 검증)와 합치면**: 문헌상 청산 RL조차 비용차감 OOS 우위 입증이 0건이다. 즉 "여지(R1)"는 있으나 "인과적 포착 가능성"은 미입증.
3. 그러므로 R1의 출력은 **RL greenlight가 아니라, 더 값싼 인과 baseline(R1b) greenlight**다.

---

## 3. 다음 단계 권고 — R1b: 인과적 청산 baseline (RL 아님)

**목적**: 완전예지가 아니라 *인과적으로 실행 가능한* 단순 규칙이 고정 TP5/SL1/09:25를 OOS에서 이기는지 검정. 이기면 → 여지가 인과적으로 포착 가능 → R3(청산 RL) 정당화. 못 이기면 → 여지는 순수 hindsight → RL 만들지 않음.

| 실험 | 내용 |
|---|---|
| SL 폭 sweep | −1% → −1.5/−2/−3% (손절이 regret의 55%이므로 1순위) |
| 트레일링 스톱 | 고점 대비 −X% 추적청산 |
| 시간청산 sweep | 09:25 → 09:20/09:30 등 |
| 부분청산 | TP 도달 시 50% 청산 + 잔량 트레일 |

**검증 하드닝 필수**(R0 결론): purged walk-forward + **Deflated Sharpe**(시도 횟수 입력) + PBO/CSCV + 다중시드. 단일 best-run 샤프 금지.

산출(예정): `stom_rl/exit_baselines.py`(순수함수) + 테스트 + `docs/stom_rl_exit_baseline_<date>.md`.

> R1b가 OOS에서 고정 룰을 **유의하게** 못 이기면, 청산 RL(R3)은 폐기하고 운영 트랙(B/C/D)으로 복귀한다.

---

## 4. 재현 명령

```powershell
# 천장 테스트(realized, ts_imb, bounded). UTF-8 강제(cp949 콘솔 대비).
$env:PYTHONIOENCODING='utf-8'
py -3.11 -X utf8 -m stom_rl.exit_oracle --max-symbols 120 --cost-bps 23 --filter ts_imb
# 결과 -> .omx/artifacts/oracle_exit/summary.json
```

```powershell
# 테스트(15개)
py -3.11 -m pytest tests/test_stom_rl_exit_oracle.py -q
```

핵심 출력(2026-05-29):
```text
N=235  rule_mean=+0.906%  oracle_mean=+5.089%
regret: mean=+4.182%  median=+2.842%  p90=+10.384%  max=+24.467%
capture_ratio=17.8%  frac_rule_optimal=1.7%
  tp   n=72  share=31% regret_mean=+4.296%
  sl   n=130 share=55% regret_mean=+4.678%
  time n=33  share=14% regret_mean=+1.982%
```

---

## 5. 페이지 트랙 갱신

| 페이지 | 상태 |
|---|---|
| R0 RL 타당성 딥리서치 | ✅ 완료 |
| **R1 oracle-exit 천장 테스트** | ✅ **완료(이 문서)** — 여지 있음(필요조건 충족), 단 RL 직행 아님 |
| **R1b 인과적 청산 baseline** | ⬜ **다음 권고** (SL/트레일링/시간 sweep + walk-forward·Deflated Sharpe) |
| R2 메타라벨링(진입 필터) | ⬜ 대안 |
| R3 offline RL(CQL) 청산 | 🔒 R1b가 인과 우위 입증 시에만 |

검증: 전체 게이트 테스트 116 passed, R1 코드리뷰 APPROVE(regret≥0를 2M 랜덤경로로 증명).
