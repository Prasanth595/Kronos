# Page 10.5 — Thin-slice 조기 성능 read (비용 반영 알파 go/no-go)

- 작성일: 2026-05-26
- 계획 근거: `.omx/plans/ralplan-stom-rl-portfolio-page7-15.md` §5 (Page 10.5), §6 Page 10.5
- 베이스라인 커밋: `7107d24` (Page 10, env T+1 체결 고정)
- 브랜치: `feature/stom-rl-lab`
- 실행: Python 3.11.9 (Windows), 기존 툴링 재사용 (**프로덕션 코드 변경 없음**)

> **결론 먼저**: 이 thin-slice 구간에서 **RL(현재 결정론 대역 정책)은 비용 반영 후 equal-weight 를 이기지 못한다.** 3개 fold 전부에서 RL 대역은 equal-weight 대비 크게 밑돈다(-3.9% ~ -4.6% vs +0.77% ~ -0.19%). 손실의 대부분은 과도한 거래 회전(턴오버 ~17.9×)에서 나오는 거래비용이다. 이는 **예상 가능한 정상 결과**이며 실패가 아니다. **권고: Page 11(holdout) 으로 진행하되, full 투입 전에 비용 인지형 reward/액션 설계(거래 빈도 억제)를 우선 보강**한다.

---

## 0. 이 read 의 성격과 caveat (읽기 전 필수)

1. **IN-SAMPLE caveat (낙관적/방향성 전용)**: `stom_rl/portfolio_walk_forward.py:61-138` 는 현재 timestamp 를 bin 으로 나눈 뒤 **같은 bin 안에서 평가**한다. 즉 train/test holdout 이 없고 전부 in-sample 이다. holdout 은 Page 11 의 executor 과제(P1-2)다. 따라서 여기서 보이는 알파는 **낙관적이며 방향성(directional) 신호로만** 해석해야 한다.

2. **"RL" 은 아직 학습된 정책이 아니다 (이중 caveat)**: 현 단계 코드베이스에는 학습된 RL 정책이 없다. walk-forward 의 5번째 baseline "RL" 은 `rule_baseline` 정책(`portfolio_walk_forward.py:86-95`)으로 대표되며, 이는 `portfolio_train.py:52-62` 의 결정론 스모크 정책("an RL agent will consume" 한다고 docstring 에 명시된 고정 액션 레이아웃)과 동일한 로직이다. 즉 매 스텝 매수 슬롯이 비면 매수하고 `step % 4 == 3` 마다 매도하는 **고빈도 결정론 대역**이다. 실제 학습 정책은 이보다 나을 수도, 나쁠 수도 있다.

3. **비용 가정**: `cost_bps=25.0`, `slippage_bps=0.0`, `initial_cash=1,000,000 KRW`. 비용은 env 가 체결마다 적용하며 NAV 에 반영된다. 체결가는 T+1(`fill_price`).

4. **결과**: 위 두 caveat 하에서도 비용 반영 신호는 명확하다 — RL 대역은 비용 때문에 진다. 이는 "알파를 짜내려고 RL 을 좋게 보이게 한 것이 아니라" 있는 그대로의 숫자다.

---

## 1. 사용한 candidate set

`python -m stom_rl.candidate_gen` 로 DB 윈도우에서 생성 (풀스캔 아님, 소수 종목·짧은 윈도우만):

| 항목 | 값 |
|---|---|
| DB | `_database/stock_tick_back.db` |
| 종목(tables) | `000100, 000150, 000250` |
| 세션 | `20250709` |
| 윈도우 요청 | 09:00:00 – 10:00:00 |
| 룰 | `stom_rl/rules/buy_demand_pressure.json` |
| **candidate 수** | **227** (전부 fillable, unfillable 0) |
| distinct timestamp | 219 |
| 종목별 분포 | `000250`: 168, `000100`: 59, `000150`: 0 (이 윈도우에서 룰 미발화) |
| 실제 candidate 시간 범위 | 09:00:05 – 09:29:58 (룰이 첫 30분에만 발화) |

스키마 확인: `price`(close@T) + `fill_price`(T+1) 컬럼 모두 존재, T+1 체결 계약 충족. Page 10 의 227 candidate 결과와 일치.

---

## 2. 비용 반영 5-baseline vs RL 비교 (per-fold)

`python -m stom_rl.portfolio_walk_forward --candidate-csv <csv> --output-dir .omx/artifacts/page10_5_earlyread/ --n-folds 3 --max-steps-per-fold 200`

Fold 구간 (in-sample, 같은 세션 내 시간 bin):

| fold | 구간 | candidate 수 |
|---|---|---|
| 0 | 09:00:05 – 09:13:54 | 76 |
| 1 | 09:13:55 – 09:21:44 | 78 |
| 2 | 09:21:55 – 09:29:58 | 73 |

각 fold 73 step 실행. **비용(KRW)·턴오버는 env 의 trade log 에서 직접 합산**한 값이다(report JSON 은 비용 컬럼을 노출하지 않으므로 trade log 로 명시 산출).

### Fold 0 (09:00:05 – 09:13:54)

| 정책 | 거래수 | 턴오버(×) | 비용(KRW) | MDD% | **수익률%(비용 후)** |
|---|---:|---:|---:|---:|---:|
| no_trade (무거래 바닥) | 0 | 0.00 | 0 | 0.00 | **0.0000** |
| equal_weight_candidate | 2 | 0.50 | 1,250 | -0.13 | **+0.7710** |
| buy_and_hold | 2 | 0.50 | 1,250 | -0.13 | **+0.7710** |
| rule_baseline | 73 | 17.91 | 44,763 | -3.91 | **-3.9125** |
| **RL (= 결정론 대역 = rule_baseline)** | 73 | 17.91 | 44,763 | -3.91 | **-3.9125** |

### Fold 1 (09:13:55 – 09:21:44)

| 정책 | 거래수 | 턴오버(×) | 비용(KRW) | MDD% | **수익률%(비용 후)** |
|---|---:|---:|---:|---:|---:|
| no_trade | 0 | 0.00 | 0 | 0.00 | **0.0000** |
| equal_weight_candidate | 2 | 0.50 | 1,249 | -0.25 | **-0.1861** |
| buy_and_hold | 2 | 0.50 | 1,249 | -0.25 | **-0.1861** |
| rule_baseline | 73 | 17.85 | 44,621 | -4.58 | **-4.5826** |
| **RL (= 결정론 대역)** | 73 | 17.85 | 44,621 | -4.58 | **-4.5826** |

### Fold 2 (09:21:55 – 09:29:58)

| 정책 | 거래수 | 턴오버(×) | 비용(KRW) | MDD% | **수익률%(비용 후)** |
|---|---:|---:|---:|---:|---:|
| no_trade | 0 | 0.00 | 0 | 0.00 | **0.0000** |
| equal_weight_candidate | 2 | 0.50 | 1,249 | -0.19 | **-0.1479** |
| buy_and_hold | 2 | 0.50 | 1,249 | -0.19 | **-0.1479** |
| rule_baseline | 73 | 17.84 | 44,591 | -4.57 | **-4.5651** |
| **RL (= 결정론 대역)** | 73 | 17.84 | 44,591 | -4.57 | **-4.5651** |

### 핵심 관측

- `equal_weight_candidate` 와 `buy_and_hold` 는 이 데이터에서 동일한 거래·결과(둘 다 첫 매수 가능 슬롯 1개를 잡고 보유). best policy by return = `equal_weight_candidate`.
- RL 대역의 손실은 **거의 전부 비용 발생**: 73회 거래 × ~17.9× 턴오버 → fold 당 ~44,600 KRW 비용. 같은 구간 equal-weight 의 비용은 ~1,250 KRW (35배 차이). 즉 알파 부재라기보다 **비용 누수**가 RL 대역을 침몰시킨다.
- `no_trade` 가 모든 RL 대역 fold 를 이긴다(0% > -3.9%~-4.6%). 거래할수록 손해라는 신호.

---

## 3. go/no-go 판정

**질문: RL 이 비용 후 equal-weight 를 이기는가? → 아니오 (명확한 No).**

- 3개 fold 전부에서 RL 대역(-3.9% / -4.6% / -4.6%)이 equal-weight(+0.77% / -0.19% / -0.15%)에 크게 밑돈다.
- 이는 §0 의 두 caveat(① in-sample 낙관, ② 학습 정책 아님 = 고빈도 결정론 대역) 때문에 **방향성 신호**로만 해석한다. "학습된 RL 이 알파가 없다"는 결론이 아니라, **현재 대역 정책의 거래 빈도/비용 설계가 비용을 못 이긴다**는 신호다.

이 페이지는 **게이트가 아니라 의식적 체크포인트**다(계획 §5 명시). 따라서 판정은 "중단"이 아니라 **조건부 진행**이다.

---

## 4. Page 11 권고

**권고: Page 11(holdout walk-forward) 으로 진행하되, full 투입 전에 아래를 우선 반영한다.**

1. **비용 인지형 설계 우선** (가장 큰 레버):
   - reward 에 거래비용/턴오버 패널티를 강화하거나, 액션 공간에서 매 스텝 매도(`step % 4 == 3` 강제 매도) 같은 고빈도 churn 을 억제. 현재 RL 대역이 진 원인은 알파 부재가 아니라 ~17.9× 턴오버 비용이다.
   - equal-weight 가 0.5× 턴오버로 비슷하거나 더 나은 성과를 내므로, **낮은 회전이 이 데이터의 강한 baseline** 임을 학습 목표에 반영.

2. **holdout 필수 (P1-2)**: Page 11 은 in-sample 격하가 아니라 expanding-window holdout(fold N 학습 → disjoint·later fold N+1 평가)로 가야 한다. 그래야 여기서 본 낙관적 알파가 과적합인지 검증된다. holdout 제거는 §1 User Sign-off 또는 architect 승인 시에만 허용.

3. **누수 canary**: Page 11 의 미래 컬럼 주입 시 성능 붕괴 단언 테스트를 함께 켠다.

4. **데이터 폭 확대 검토**: 이 read 는 단일 세션·2종목·30분(룰 발화 구간)에 불과하다. Page 11 에서는 더 많은 fold/세션으로 신호 안정성을 본다. 단, full-universe 는 Page 16 게이트.

**대안 시나리오(재고)**: 만약 비용 인지형 reward 보강 후에도 holdout 에서 RL 이 equal-weight 를 못 이기면, 계획 §1-2(Page 14 = 격차 문서화로 트랙 B 완료) 경로로 "성능 격차 + 다음 연구 방향" 을 문서화하는 것이 정당한 종착점이다.

---

## 5. 재현 커맨드

```bash
# 1) candidate 생성
py -3.11 -m stom_rl.candidate_gen \
  --db _database/stock_tick_back.db \
  --tables 000100,000150,000250 --session 20250709 \
  --time-start 090000 --time-end 100000 \
  --rules stom_rl/rules/buy_demand_pressure.json \
  --output .omx/artifacts/page10_5_earlyread/candidates.csv \
  --topk-report .omx/artifacts/page10_5_earlyread/topk.json --top-k 3

# 2) walk-forward (4 결정론 baseline; RL = rule_baseline 대역)
py -3.11 -m stom_rl.portfolio_walk_forward \
  --candidate-csv .omx/artifacts/page10_5_earlyread/candidates.csv \
  --output-dir .omx/artifacts/page10_5_earlyread/ \
  --n-folds 3 --max-steps-per-fold 200
```

아티팩트(커밋 안 함, `.omx/`): `candidates.csv`, `topk.json`, `portfolio_walk_forward_report.json`, `portfolio_walk_forward_folds.csv`.

---

## 6. 메모 (정직성)

- **프로덕션 코드 변경 없음** — 기존 CLI 만 실행. 비용/턴오버/MDD 는 report JSON 이 노출하지 않아 env trade log/NAV path 로 직접 산출(read-only 분석, 코드 수정 아님).
- 숫자를 RL 에 유리하게 가공하지 않았다. 비용은 명시적으로 보고했고(거래 빈도가 손실의 주원인), in-sample 및 "학습 정책 아님" caveat 를 전면에 명시했다.
