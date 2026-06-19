# Page 14 — 성능 최적화 (TRACK B, 결과 문서화로 완료)

- 작성일: 2026-05-26
- 계획 근거: `.omx/plans/ralplan-stom-rl-portfolio-page7-15.md` §5 (Page 14), §0 트랙 B
- 베이스라인 커밋: `95ff7f8` (Page 13, 대시보드 연결까지 완료)
- 브랜치: `feature/stom-rl-lab`
- 실행: Python 3.11.9 (Windows), **기존 CLI 플래그만 사용 — 프로덕션 코드 변경 없음**
- 비용 가정(명시): **`cost_bps = 25.0`**, `slippage_bps = 0.0`, `initial_cash = 1,000,000 KRW`, 체결 = **T+1** (출처 `stom_rl/accounting.py:70`, `stom_rl/baselines.py:55`; walk-forward config 에 노출)

---

## 0. 결론 먼저

**판정: 어떤 변형도 비용(`cost_bps=25.0`) 반영 후 equal-weight 를 이기지 못한다 (No). → 트랙 B = "문서화된 성능 격차 + 다음 연구 방향"으로 완료.**

핵심 원인은 다시 한 번 확인되었다: **알파 부재가 아니라 거래 회전(turnover) 비용**이다. 비용을 0 으로 두면 현재 결정론 대역 정책("RL")이 equal-weight 를 아주 근소하게(+0.07%p) 이기지만, **break-even 비용은 약 0.54 bps**에 불과하다. 즉 현실적 비용(5~25 bps) 어디에서도 정책이 가진 미세한 raw edge 는 회전 비용에 전부 잡아먹힌다.

가장 효과적인 레버는 **거래 빈도를 직접 줄이는 것**이었다:
- **포지션 슬롯 축소(top_k/max_positions↓)는 효과 없음** — 대역 정책이 슬롯 수와 무관하게 매 사이클 사고팔기 때문에 회전이 그대로다.
- **더 엄격한 룰(`buy_widev1`, candidate 227→25)** 은 거래 기회 자체를 줄여 격차를 **-3.17%p → -0.29%p 로 10배 이상 축소**했다(여전히 패배지만 방향성 입증).

**다음 연구 방향: 턴오버 패널티를 reward 에 명시적으로 넣은 비용 인지형 RL 정책을 학습**한다. 평가 인프라(holdout walk-forward + leakage canary + 대시보드)는 이미 갖춰져 있으므로, 학습 정책을 `_fit_policy` seam 에 끼우면 즉시 같은 비교표로 검증 가능하다.

---

## 1. 이 페이지의 caveat (읽기 전 필수)

1. **"RL"은 아직 학습된 정책이 아니다.** 코드베이스에 학습된 RL 모델이 없다. walk-forward 의 `rl_baseline` 은 `_fit_policy` 가 no-op 인 결정론 대역(`portfolio_walk_forward.py:181-191` / `portfolio_train.py` 스모크 정책)으로, 매 스텝 매수 슬롯이 비면 매수하고 `step % 4 == 3` 마다 매도하는 **고빈도 정책**이다. 본 문서의 "RL" 수치는 이 대역의 거동이며 학습 정책의 상한/하한이 아니다. 이는 계획 §5 Page 10.5 caveat 와 동일하다.

2. **holdout(out-of-sample) 평가.** Page 11 의 expanding-window holdout 을 사용한다 — fold N 은 segment `0..N` 으로 fit(대역은 no-op), **disjoint 하고 더 나중인** segment `N+1` 에서 평가. 따라서 Page 10.5 의 in-sample read 보다 보수적이다(같은 데이터에서 V0 가 -3.28% 로 Page 10.5 의 -4.0% 대비 fold 구간이 다름).

3. **비용은 정직하게 명시.** 모든 비용/턴오버/거래수는 walk-forward fold report(`portfolio_walk_forward_folds.csv`)의 `total_cost`, `turnover`, `trade_count`, `cost_bps` 컬럼에서 직접 읽었다(Page 11 이 이 컬럼들을 노출). 정책을 좋게 보이게 가공하지 않았다.

---

## 2. 사용한 candidate set (풀스캔 아님)

`python -m stom_rl.candidate_gen` 로 동일 DB 윈도우(소수 종목·30분 발화 구간)에서 두 룰로 생성:

| set | 룰 | candidate 수 | distinct ts | 종목 분포 |
|---|---|---:|---:|---|
| demand_pressure (V0/V1/V3) | `buy_demand_pressure.json` | **227** | 219 | 000250:168, 000100:59, 000150:0 |
| widev1 (V2) | `buy_widev1.json` | **25** | 25 | 000100:13, 000250:12 |

공통 윈도우: DB `_database/stock_tick_back.db`, tables `000100,000150,000250`, session `20250709`, 09:00:00–10:00:00. (demand_pressure 227 set 은 Page 10.5 와 동일 — 비교 가능성 확보.)

생성 커맨드:
```bash
# demand_pressure set (V0/V1/V3 입력)
py -3.11 -m stom_rl.candidate_gen \
  --db _database/stock_tick_back.db \
  --tables 000100,000150,000250 --session 20250709 \
  --time-start 090000 --time-end 100000 \
  --rules stom_rl/rules/buy_demand_pressure.json \
  --output .omx/artifacts/page14_opt/cand_demand_pressure.csv \
  --topk-report .omx/artifacts/page14_opt/topk_demand_pressure.json --top-k 3

# widev1 set (V2 입력, 더 엄격한 룰)
py -3.11 -m stom_rl.candidate_gen \
  --db _database/stock_tick_back.db \
  --tables 000100,000150,000250 --session 20250709 \
  --time-start 090000 --time-end 100000 \
  --rules stom_rl/rules/buy_widev1.json \
  --output .omx/artifacts/page14_opt/cand_widev1.csv \
  --topk-report .omx/artifacts/page14_opt/topk_widev1.json --top-k 3
```

---

## 3. 변형(variation)과 정확한 커맨드

모든 변형은 **기존 walk-forward CLI 플래그만** 사용한다(새 학습 알고리즘·새 코드 없음). 식별된 회전 비용 문제를 직접 겨냥한다.

| 변형 | 레버 | 커맨드 플래그 |
|---|---|---|
| **V0 baseline** | 없음(Page 10.5 재현, holdout) | `--top-k-candidates 3 --max-positions 2 --cost-bps 25.0` |
| **V1 fewer_pos** | 포지션 슬롯 축소(churn 억제 시도) | `--top-k-candidates 1 --max-positions 1 --cost-bps 25.0` |
| **V2 widev1** | 더 엄격한 룰(candidate 227→25) | (입력 CSV = widev1) `--top-k-candidates 3 --max-positions 2 --cost-bps 25.0` |
| **V3 cost sweep** | 비용 민감도(break-even 탐색) | `--cost-bps {0, 5, 10}` (+ V0 의 25) |

공통: `--n-folds 3 --max-steps-per-fold 200 --seed 100`. 예:

```bash
# V0 baseline (canonical, holdout)
py -3.11 -m stom_rl.portfolio_walk_forward \
  --candidate-csv .omx/artifacts/page14_opt/cand_demand_pressure.csv \
  --output-dir .omx/artifacts/page14_opt/v0_baseline \
  --n-folds 3 --max-steps-per-fold 200 --top-k-candidates 3 --max-positions 2 --cost-bps 25.0 --seed 100

# V1 fewer positions
py -3.11 -m stom_rl.portfolio_walk_forward \
  --candidate-csv .omx/artifacts/page14_opt/cand_demand_pressure.csv \
  --output-dir .omx/artifacts/page14_opt/v1_fewer_pos \
  --n-folds 3 --max-steps-per-fold 200 --top-k-candidates 1 --max-positions 1 --cost-bps 25.0 --seed 100

# V2 stricter rule (widev1 candidates)
py -3.11 -m stom_rl.portfolio_walk_forward \
  --candidate-csv .omx/artifacts/page14_opt/cand_widev1.csv \
  --output-dir .omx/artifacts/page14_opt/v2_widev1 \
  --n-folds 3 --max-steps-per-fold 200 --top-k-candidates 3 --max-positions 2 --cost-bps 25.0 --seed 100

# V3 cost sweep (break-even)
for C in 0.0 5.0 10.0; do
  py -3.11 -m stom_rl.portfolio_walk_forward \
    --candidate-csv .omx/artifacts/page14_opt/cand_demand_pressure.csv \
    --output-dir .omx/artifacts/page14_opt/v3_cost${C%%.*} \
    --n-folds 3 --max-steps-per-fold 200 --top-k-candidates 3 --max-positions 2 --cost-bps $C --seed 100
done
```

모든 6개 run 은 exit 0 으로 완주하고 실 fold 메트릭을 산출했다(`portfolio_walk_forward_folds.csv` per variation).

---

## 4. 비용 반영 비교표 (fold 평균, `cost_bps=25.0` 기본)

각 변형마다 `rl_baseline`(=대역 정책) 을 두 핵심 baseline(`equal_weight_candidate`, `no_trade`)과 비교. 수치는 3개 holdout fold 평균.

### V0 — baseline (demand_pressure, top_k=3/max_pos=2, **cost=25 bps**)

| 정책 | 평균 수익률%(비용 후) | 평균 턴오버 | 평균 거래수 | 평균 비용(KRW) | 평균 MDD% |
|---|---:|---:|---:|---:|---:|
| no_trade | **0.0000** | 0 | 0 | 0 | 0.00 |
| equal_weight_candidate | **-0.1132** | 499,895 | 2.0 | 1,250 | -0.17 |
| **rl_baseline (대역)** | **-3.2816** | 13,453,032 | 54.7 | 33,633 | -3.28 |

→ rl 이 equal-weight 대비 **-3.17%p** 열세. 턴오버가 **27배**, 비용이 **27배**.

### V1 — fewer positions (demand_pressure, top_k=1/max_pos=1, cost=25 bps)

| 정책 | 평균 수익률%(비용 후) | 평균 턴오버 | 평균 거래수 | 평균 비용(KRW) |
|---|---:|---:|---:|---:|
| no_trade | **0.0000** | 0 | 0 | 0 |
| equal_weight_candidate | **-0.0266** | 250,000 | 1.0 | 625 |
| **rl_baseline (대역)** | **-3.2816** | 13,453,885 | 54.7 | 33,635 |

→ **포지션 슬롯 축소는 효과 없음**. rl 거래수가 54.7 로 V0 와 동일 — 대역 정책은 슬롯 수와 무관하게 매 사이클 매수·매도하므로 회전이 줄지 않는다. **회전 문제는 포지션 한도가 아니라 정책의 거래 빈도에서 온다**는 음성(negative) 결과. (gap **-3.26%p**.)

### V2 — 더 엄격한 룰 (widev1, candidate 227→25, cost=25 bps) — 가장 효과적 레버

| 정책 | 평균 수익률%(비용 후) | 평균 턴오버 | 평균 거래수 | 평균 비용(KRW) |
|---|---:|---:|---:|---:|
| no_trade | **0.0000** | 0 | 0 | 0 |
| equal_weight_candidate | **+0.0758** | 499,895 | 2.0 | 1,250 |
| **rl_baseline (대역)** | **-0.2103** | 1,500,405 | 6.0 | 3,751 |

→ candidate 가 227→25 로 줄자 rl 거래수가 54.7→**6.0**, 비용이 33,633→**3,751 KRW**. gap 이 **-3.17%p → -0.29%p 로 10배 이상 축소**. 여전히 equal-weight 에 미달하지만 **거래 기회를 줄이는 것이 가장 직접적인 레버**임을 입증.

### V3 — 비용 민감도 sweep (demand_pressure, top_k=3/max_pos=2) — break-even 분석

| cost_bps | rl_baseline 수익률% | equal_weight 수익률% | **gap (rl − ew)** | rl이 ew를 이기나 |
|---:|---:|---:|---:|:--:|
| **0.0** | +0.0824 | +0.0117 | **+0.0706** | ✅ Yes |
| 5.0 | -0.5993 | -0.0133 | -0.5860 | No |
| 10.0 | -1.2765 | -0.0383 | -1.2382 | No |
| **25.0** (canonical) | -3.2816 | -0.1132 | -3.1683 | No |

→ **break-even 비용 ≈ 0.54 bps** (0 과 5 bps 사이 선형보간). 비용 0 에서만 대역 정책의 미세한 raw edge(+0.07%p)가 보이고, 현실적 비용(5 bps 이상) 전 구간에서 회전 비용이 그 edge 를 전부 소진한다. **알파가 없는 게 아니라(0 cost 에선 근소 우위) 그 알파가 회전 비용을 못 견딘다**는 결정적 증거.

---

## 5. 판정 (게이트 = 루프 실행 + 문서화)

| 질문 | 답 |
|---|---|
| 변형 중 하나라도 `cost_bps=25.0` 후 equal-weight 를 이기는가? | **아니오** (V0/V1/V2/V3-cost5/10/25 전부 패배) |
| 비용을 0 으로 두면? | rl 이 equal-weight 를 +0.07%p 로 근소하게 이김 (V3-cost0) |
| break-even 비용은? | **≈ 0.54 bps** — 현실적 비용 대비 매우 낮음 |
| 손실의 원인은? | **회전 비용** (alpha 부재 아님). 턴오버 27×, 비용 27× |
| 가장 효과적인 레버는? | **거래 기회 축소**(더 엄격한 룰). 포지션 슬롯 축소는 무효 |

**트랙 B 완료 형태 = (b) 문서화된 성능 격차 + 다음 연구 방향** (계획 §0 트랙 B, §1 User Sign-off #2 에 부합). 알파를 짜내거나 정책을 좋게 보이게 가공하지 않았다.

---

## 6. 다음 연구 방향 (구체적)

1. **비용 인지형 RL 정책 학습 (최우선)**: reward 에 **턴오버/거래비용 패널티**를 명시적으로 추가해 정책이 "거래할 가치가 있을 때만" 거래하도록 학습시킨다. 현재 대역 정책의 break-even 0.54 bps 는 "매 사이클 churn" 때문이며, 패널티 항이 이를 직접 억제하는 학습 신호다. 평가 인프라(holdout walk-forward, leakage canary, 대시보드)는 이미 자리잡았으므로, 학습 정책을 `portfolio_walk_forward.py:_fit_policy` seam 에 끼우면 **같은 비교표로 즉시 재평가** 가능하다(holdout 기계는 그대로).

2. **룰 단계 게이팅 결합**: V2 가 보여주듯 candidate 발화를 엄격하게 하면 회전이 급감한다. 학습 정책 + 엄격한 룰(또는 rank_score 임계값)을 결합하면 비용 인지형 reward 와 상호 보완.

3. **데이터 폭 확대(Page 16 게이트)**: 본 read 는 단일 세션·2~3종목·30분 발화 구간이다. 신호 안정성은 더 많은 fold/세션에서 봐야 하며, full-universe 는 Page 16 별도 게이트로 추적한다(open-ended background 금지).

4. **(보류) MaskablePPO**: 계획 §5 Page 10 의 invalid-action 비율 수치 게이트(>20% / 50k) 통과 전에는 도입하지 않는다(의존성 creep 회피).

**대안 종착점(정직)**: 비용 인지형 reward 보강 후에도 holdout 에서 학습 정책이 equal-weight 를 못 이기면, 그 자체가 정당한 트랙 B 종착점("이 데이터/비용에서 이 candidate 셋은 저회전 equal-weight 가 강한 baseline")이며 추가 격차 문서화로 닫는다.

---

## 7. 산출물 (커밋 안 함, `.omx/` gitignore)

`.omx/artifacts/page14_opt/`:
- `cand_demand_pressure.csv`, `topk_demand_pressure.json` (227 candidate set)
- `cand_widev1.csv`, `topk_widev1.json` (25 candidate set)
- `v0_baseline/`, `v1_fewer_pos/`, `v2_widev1/`, `v3_cost00/`, `v3_cost05/`, `v3_cost10/` — 각 `portfolio_walk_forward_report.json` + `portfolio_walk_forward_folds.csv`
- `comparison.csv`, `comparison.json` — 전체 변형 fold 평균 + 변형별 verdict (집계는 fold CSV read-only 분석)

---

## 8. 메모 (정직성)

- **프로덕션 코드 변경 없음** — 기존 `candidate_gen` / `portfolio_walk_forward` CLI 플래그만 실행. 집계 스크립트는 fold CSV 를 읽어 평균/판정만 계산하는 read-only 분석(코드 수정 아님).
- 비용 가정(`cost_bps=25.0`)을 전면에 명시했고, 0 cost 에서의 근소 우위를 숨기지 않고 break-even(0.54 bps)으로 정량화했다.
- DB 풀스캔 없음(소수 종목·30분 윈도우). `eval/exec/__` 미사용. 숫자를 RL 에 유리하게 가공하지 않았다.
