# STOM Tick DB 독립 강화학습 실험실 설계 계획서

작성일: 2026-05-22 KST
대상 저장소: `D:\Chanil_Park\Project\Programming\Kronos`
계획 방식: `$ralplan --deliberate` 성격의 설계 문서
핵심 방향: **Kronos를 사용하지 않고**, 현재 존재하는 STOM tick/1초봉 DB를 이용해 독립 강화학습 기능과 웹 대시보드 탭을 구축한다.

---

## 1. 한 줄 결론

가능하다. 다만 첫 목표는 “강화학습으로 바로 수익 보장”이 아니라, **STOM tick DB에서 비용 차감 후 실제로 baseline보다 나은 매매 행동을 학습할 수 있는지 검증하는 독립 실험실**을 만드는 것이다.

추천 구조는 다음과 같다.

> **Gymnasium 호환 STOM 전용 trading environment + RLTrader식 주식 매매 상태/행동/보상 아이디어 + 자체 walk-forward/cost-gate 검증 + 신규 웹 탭**

---

## 2. 배경과 문제 정의

기존 작업에서 STOM 2025년 1초봉 데이터는 Kronos fine-tuning 파이프라인에 연결됐고, 학습/평가/대시보드까지 구축됐다. 그러나 평가 결과는 실전 신호로 바로 사용하기 어렵다.

| 항목 | 현재 상태 |
|---|---|
| Kronos fine-tuning 파이프라인 | 정상 동작 |
| STOM 2025 1초봉 export | 완료 |
| 60초 방향 적중률 | 약 44.79%, random과 유사 |
| 300초 horizon | 상대적으로 유망하지만 cost gate 미통과 |
| 결론 | 가격 경로 예측 모델만으로는 비용 차감 후 수익성이 부족 |

따라서 다음 질문으로 전환한다.

> “미래 가격을 예측하는 모델”이 아니라, **주어진 상태에서 매수/관망/청산 행동을 선택해 비용 차감 후 수익을 높이는 모델**을 만들 수 있는가?

이 질문은 강화학습 또는 contextual bandit 계열의 실험 대상이다.

---

## 3. 참고 오픈소스 검토 요약

### 3.1 Gymnasium

- 저장소: <https://github.com/Farama-Foundation/Gymnasium>
- 문서: <https://gymnasium.farama.org/>
- 역할: 강화학습 환경 API 표준
- 핵심 API: `reset()`, `step()`, `action_space`, `observation_space`

우리 프로젝트 적용 판단:

| 판단 | 내용 |
|---|---|
| 채택 수준 | 핵심 기반으로 채택 권장 |
| 이유 | Stable-Baselines3, RLlib 등과 연결하기 쉬움 |
| 한계 | 주식/체결/수수료/슬리피지는 직접 구현해야 함 |
| 적용 방식 | `StomTickTradingEnv`를 Gymnasium 호환 형태로 설계 |

### 3.2 RLTrader

- 저장소: <https://github.com/quantylab/rltrader>
- 역할: 한국 주식 강화학습 예제/학습 프로젝트
- 장점: 주식 매매의 행동, 포트폴리오, 보상 구조 아이디어가 있음
- 한계: 오래된 의존성, 최신 Gymnasium 표준 아님, STOM 초단위 tick/1초봉 구조와 직접 맞지 않음

우리 프로젝트 적용 판단:

| 판단 | 내용 |
|---|---|
| 채택 수준 | 코드 이식보다 설계 아이디어 참고 |
| 참고할 점 | 매수/매도/관망, 보유 비율, 거래비용, 포트폴리오 상태 |
| 피할 점 | 구버전 학습 루프를 그대로 가져오기 |
| 적용 방식 | Gymnasium API 안에 RLTrader식 상태/행동/보상 아이디어를 흡수 |

---

## 4. RALPLAN-DR 요약

### 4.1 원칙

1. **Kronos와 완전 분리**
   Kronos tokenizer, predictor, fine-tuning loop, checkpoint에 의존하지 않는다.

2. **수익성은 비용 차감 후 판단**
   수수료, 세금, 슬리피지, 과매매 패널티를 반영한 net return을 1급 지표로 둔다.

3. **미래 데이터 누수 금지**
   상태값에는 현재와 과거 정보만 사용한다. 미래 수익률은 보상/평가에만 사용한다.

4. **baseline보다 못하면 실패**
   random, no-trade, buy-and-hold, momentum, mean-reversion보다 나아야 다음 단계로 간다.

5. **재현 가능한 실험 우선**
   seed, config, 데이터 범위, artifact, report를 모두 남긴다.

### 4.2 Top decision drivers

| 순위 | 의사결정 기준 | 이유 |
|---:|---|---|
| 1 | STOM tick/1초봉 DB를 직접 읽는 환경 | Kronos 비의존 목표의 핵심 |
| 2 | 거래비용·슬리피지·체결 제약 반영 | 초단기 데이터에서는 비용이 성과를 크게 좌우 |
| 3 | 웹 대시보드 해석 가능성 | 사용자가 학습/성과/리스크를 직접 확인해야 함 |

### 4.3 선택지 비교

#### Option A. Gymnasium-compatible custom environment

| 항목 | 내용 |
|---|---|
| 설명 | STOM 전용 환경을 Gymnasium 표준 API로 직접 구현 |
| 장점 | 표준 알고리즘 연결 쉬움, 테스트/재현성 좋음, 확장성 높음 |
| 단점 | 주식 체결/비용/보상은 직접 구현 필요 |
| 판단 | 단독으로도 가능하지만 도메인 설계 참고가 필요 |

#### Option B. RLTrader 스타일 자체 루프

| 항목 | 내용 |
|---|---|
| 설명 | RLTrader처럼 주식 매매 전용 학습 루프를 직접 구성 |
| 장점 | 주식 매매 맥락 이해가 쉽고 빠른 프로토타입 가능 |
| 단점 | 최신 RL 생태계와 호환성 낮음, 유지보수 위험 |
| 판단 | 그대로 이식은 비추천 |

#### Option C. 하이브리드: Gymnasium API + RLTrader식 매매 아이디어

| 항목 | 내용 |
|---|---|
| 설명 | 외부 알고리즘 호환은 Gymnasium, 상태/행동/보상은 STOM/RLTrader식으로 설계 |
| 장점 | 표준성과 주식 도메인 적합성 균형 |
| 단점 | 경계와 artifact schema를 명확히 해야 함 |
| 판단 | **추천안** |

---

## 5. ADR: 추천 결정

### Decision

**Option C를 채택한다.**

STOM 강화학습 실험실은 Gymnasium 호환 custom environment로 만들고, RLTrader에서 얻은 주식 매매 상태/행동/포트폴리오 아이디어를 STOM tick/1초봉 데이터 구조에 맞게 재설계한다.

### Drivers

- Kronos와 독립된 새 기능이어야 한다.
- 장기적으로 DQN/PPO/A2C/RLlib/Stable-Baselines3 계열을 붙일 수 있어야 한다.
- 실전 수익성 판단은 비용 차감 후 walk-forward로 해야 한다.

### Alternatives considered

| 대안 | 기각/보류 이유 |
|---|---|
| FinRL/TensorTrade 전체 도입 | 무겁고 STOM 초단위 구조에 맞추려면 오히려 복잡해질 수 있음 |
| RLTrader 직접 이식 | 오래된 의존성과 비표준 루프 때문에 유지보수 위험 |
| 순수 자체 구현만 사용 | 외부 RL 알고리즘 생태계와 연결성이 떨어짐 |

### Consequences

- 1차 구현은 모델보다 환경/보상/검증을 먼저 만든다.
- 새 의존성 `gymnasium`은 실제 구현 단계에서 도입 후보로 둔다. 단, 초기에는 의존성 추가 없이 Gymnasium식 인터페이스만 맞추는 방식도 가능하다.
- Stable-Baselines3는 바로 필수는 아니다. baseline 검증 이후 도입한다.

---

## 6. 데이터 범위와 계약

### 6.1 원본 데이터

| 항목 | 계획 |
|---|---|
| 원본 | STOM tick DB / 1초봉 DB |
| 읽기 방식 | 원본 DB 수정 금지, read-only |
| 우선 범위 | 2025년 09:00~09:30 1초봉부터 시작 |
| 확장 범위 | 전체 연도, 전체 tick, 여러 시간대 |
| 종목 universe | 매일 달라질 수 있음. 종목 고정 모델이 아니라 날짜-종목 episode로 처리 |

### 6.2 데이터 단위

초기 구현은 다음 단위가 안전하다.

```text
episode = 특정 날짜 + 특정 종목 + 09:00~09:30 1초봉 구간
```

이후 확장:

```text
episode = 특정 날짜 + 거래대금 상위 N개 종목 포트폴리오
```

### 6.3 누수 방지 규칙

| 금지 | 이유 |
|---|---|
| 미래 30/60/300초 수익률을 observation에 포함 | 정답 누수 |
| 하루 전체 거래대금 순위를 현재 시점 feature로 사용 | 미래 체결량 포함 가능 |
| 테스트 기간으로 reward/feature scaler를 fit | 평가 오염 |
| 종목별 전체 기간 통계를 현재 시점에 사용 | 미래 분포 누수 |

### 6.4 STOM 데이터 자원 실측 (Kronos export 기준)

기존 Kronos 파이프라인이 동일 데이터에서 만든 통계를 그대로 강화학습 환경의 episode 자원 추정치로 활용한다. 근거 파일: `finetune/qlib_exports/stom_1s_grid_pred60_2025/stom_qlib_export_report.json`

| 항목 | 값 |
|---|---:|
| 원본 DB | `_database/stock_tick_back.db` (read-only) |
| 적용 구간 | 2025-01-03 ~ 2025-12-30 09:00~09:30 |
| compatible tables | 2,425 / 2,427 |
| 2025 row 보유 tables | 1,638 |
| sessions | 240 (train 168 / validation 36 / test 36) |
| exported group count | 18,750 (episode 단위 후보) |
| exported row count | 33,360,325 |
| train rows | 23,579,043 |
| validation rows | 4,920,437 |
| test rows | 4,860,845 |

함의:

1. **episode pool 규모**: train 13,256 / val 2,764 / test 2,730 group이 그대로 RL episode 후보가 된다. baseline 충돌 없이 1차 실험이 가능한 규모다.
2. **session split 재사용**: Kronos가 사용한 168/36/36 session split을 그대로 사용하면 후속 비교가 쉽다.
3. **read-only 강제**: 학습 코드는 `_database/stock_tick_back.db`를 SQLite `mode=ro` URI 또는 OS read-only 권한으로만 열어야 하며, 단위 테스트로 쓰기 호출 부재를 확인한다.

### 6.5 누수 방지 검증 메커니즘

규칙 명시뿐 아니라 다음 자동화된 검증 단계를 1차 환경 구현에 포함한다.

| 검증 | 도구 | 기대값 |
|---|---|---|
| observation에 미래 timestamp 없음 | unit test (`tests/test_rl_env_no_leakage.py`) | observation t에 t+1 이후 row 0건 |
| feature scaler train fit | pipeline assertion | test set fit 호출 0건 |
| 종목별 통계 cutoff | manifest 검사 | `as_of_ts <= current_step_ts` 100% |
| reward에 사용된 future 가격 별도 분리 | env 내 검사 | observation 텐서와 reward 입력 텐서 dtype/source 다름 |
| read-only DB | DB connect mock | 모든 `sqlite3.connect`가 `mode=ro` 사용 |

---

## 7. 상태 공간 설계

### 7.1 1차 observation 후보

| 그룹 | 변수 예시 | 설명 |
|---|---|---|
| 가격 | open, high, low, close | 1초봉 OHLC |
| 거래 | volume, amount | 거래량/거래대금 |
| 수익률 | ret_1s, ret_5s, ret_30s, ret_60s | 과거 수익률만 사용 |
| 변동성 | rolling_std_30s, high_low_range_30s | 최근 변동성 |
| 거래 강도 | volume_z_30s, amount_z_30s | 최근 평균 대비 강도 |
| 캔들 구조 | body_ratio, upper_shadow, lower_shadow | 순간 매수/매도 압력 proxy |
| 시간 | seconds_from_open, minute_bucket | 장초반 시간 위치 |
| 포지션 | position, entry_price, unrealized_pnl | 현재 보유 상태 |
| 리스크 | drawdown, trade_count, time_in_position | 과매매/손실 관리 |

### 7.2 observation shape

초기 권장:

```text
lookback_window = 60~300초
feature_count = 20~40개
observation = [lookback_window, feature_count]
```

초기에는 300초 lookback이 무겁다면 60초/120초부터 시작하고, 이후 300초로 확장한다.

---

## 8. 행동 공간 설계

### 8.1 1차 단순 행동

```text
0 = 관망 / 유지
1 = 매수 또는 롱 진입
2 = 청산
```

국내 주식 현물 기준에서는 공매도 없이 롱 전용이 현실적이다.

### 8.2 2차 확장 행동

```text
0 = 현금 0%
1 = 보유 25%
2 = 보유 50%
3 = 보유 100%
```

이 방식은 position target 방식이라 PPO/A2C와 연결하기 쉽다.

### 8.3 3차 포트폴리오 행동

여러 종목 동시 선택은 후순위다. 초기에는 단일 종목 episode에서 환경과 보상 검증을 완료한 뒤 확장한다.

---

## 9. 보상 함수 설계

### 9.1 기본 보상

```text
reward_t = realized_or_mark_to_market_return_t
         - transaction_cost_t
         - slippage_t
         - turnover_penalty_t
         - drawdown_penalty_t
         - invalid_action_penalty_t
```

### 9.2 보상 구성 요소

| 항목 | 설명 |
|---|---|
| realized_or_mark_to_market_return | 보유 중 평가손익 또는 청산 손익 |
| transaction_cost | 수수료/세금/기타 비용 |
| slippage | 체결 가격 불리함 |
| turnover_penalty | 너무 잦은 매매 억제 |
| drawdown_penalty | 큰 손실과 급격한 낙폭 억제 |
| invalid_action_penalty | 보유 중 재매수, 미보유 청산 등 이상 행동 억제 |

### 9.3 추천 비용 기본값

초기 문서/실험에서는 보수적으로 여러 비용 시나리오를 병렬 계산한다.

| 시나리오 | 총 비용 가정 |
|---|---:|
| 낙관 | 5bp |
| 중립 | 10~15bp |
| 보수 | 25bp |

기존 Kronos 평가에서 25bp 비용이 성과를 크게 악화시켰으므로, RL에서도 25bp cost gate를 반드시 포함한다.

---

## 10. Baseline 비교군

강화학습 모델은 다음보다 좋아야 한다.

| baseline | 목적 |
|---|---|
| no-trade | 아무것도 하지 않는 기준 |
| random | 모델이 랜덤보다 나은지 확인 |
| buy-and-hold | 장초반 구간 단순 보유 대비 |
| simple momentum | 최근 상승 종목을 따라가는 규칙 |
| mean reversion | 급등/급락 후 되돌림 규칙 |
| volume/amount filter | 거래대금/거래량 조건식 기반 규칙 |

보고서는 반드시 다음을 분리한다.

1. 비용 미차감 gross return
2. 비용 차감 net return
3. 거래 수
4. 승률
5. MDD
6. turnover
7. split별 성과

### 10.1 Kronos checkpoint 결과를 외부 비교군으로 활용

Kronos 의존을 학습 단계에서는 끊되, **비교 기준점**으로는 기존 결과를 그대로 활용한다. 같은 STOM 2025 test split(2025-11-07 ~ 2025-12-30, 36 sessions, 비용 25bp)에서 측정된 수치를 재현 없이 baseline 표에 고정한다.

근거 파일: `webui/qlib_backtests/stom_1s_2025_full_small_horizon_comparison.json`

| horizon | Kronos 방향 적중률 | random 방향 적중률 | Top-K net | 최적 필터 net | rolling net | rolling 방향 | gate |
|---:|---:|---:|---:|---:|---:|---:|---|
| 30초 | 39.21% | 38.77% | -0.2522% | -0.0465% | -0.2398% | 32.08% | 실패 |
| 60초 | 44.79% | 44.93% | -0.2041% | -0.0168% | -0.2043% | 39.39% | 실패 |
| 120초 | 45.67% | 42.73% | -0.1735% | -0.0335% | -0.2903% | 49.35% | 실패 |
| 300초 | 49.19% | 46.26% | -0.1145% | +0.0922% | -0.0052% | 44.29% | 실패 |

RL 모델은 같은 split·비용 조건에서 **300초 horizon Kronos rolling net -0.0052%를 양수로 끌어올리는 것**을 1차 우위 기준으로 둔다. 즉 RL이 Kronos 모델보다 명확히 나은지 보려면 cost gate 통과 + 300초 행 대비 rolling net delta가 양수여야 한다.

---

## 11. 모델 구축 로드맵

### 11.0 reward horizon 우선순위

기존 Kronos 실험에서 30/60/120/300초 중 **300초가 비용 차감 후 손익분기에 가장 가까운 horizon**이었다(섹션 10.1). RL 환경의 mark-to-market 평가도 동일 단위를 1순위로 둔다.

| 우선순위 | reward horizon | 이유 |
|---:|---|---|
| 1 | 300초 청산 또는 mark-to-market | Kronos 비교군에서 cost gate에 가장 근접 |
| 2 | 120초 | 방향 edge +2.94%p 확보 구간 |
| 3 | 60초 | 기존 기본 horizon이지만 random 대비 edge 없음 |
| 후순위 | 30초 | 노이즈가 커 1차 검증에서 제외 가능 |

30초는 환경 단위 시간이 1초이므로 step 단위로는 항상 측정 가능하지만, **보상/평가의 1차 horizon은 300초**로 시작한다.

### 11.1 0단계: 모델 없는 환경 검증

가장 먼저 환경이 맞는지 확인한다.

- `reset()`이 같은 seed에서 같은 episode를 반환하는가?
- `step()`이 포지션/현금/수익률을 정확히 갱신하는가?
- 수수료/슬리피지가 제대로 차감되는가?
- 미래 데이터를 observation에 넣지 않는가?

### 11.2 1단계: 규칙 기반 baseline

강화학습 이전에 규칙 전략으로 시장에 edge가 있는지 확인한다.

### 11.3 2단계: Contextual Bandit

초기 RL 후보로 가장 현실적이다.

| 장점 | 이유 |
|---|---|
| 단순 | 각 시점의 행동 선택 문제로 시작 가능 |
| 과최적화 위험 낮음 | 긴 episode credit assignment 부담이 적음 |
| 대시보드 설명 쉬움 | 어떤 feature에서 어떤 행동을 골랐는지 해석 가능 |

### 11.4 3단계: DQN

행동이 관망/매수/청산처럼 discrete일 때 적합하다.

### 11.5 4단계: PPO/A2C

position target 방식으로 확장할 때 적합하다.

### 11.6 5단계: 다종목 포트폴리오 RL

단일 종목에서 비용 차감 후 baseline 우위를 확인한 뒤 진행한다.

---

## 12. 실험 산출물 schema

각 실험은 최소한 아래 파일을 남긴다.

```text
webui/rl_runs/{run_id}/
  config.json
  data_manifest.json
  train_metrics.jsonl
  eval_summary.json
  walk_forward_splits.json
  trades.csv
  equity_curve.csv
  actions.csv
  risk_report.json
  artifacts_manifest.json
```

### 12.1 핵심 metric

| 지표 | 설명 |
|---|---|
| total_net_return_pct | 비용 차감 총수익률 |
| period_return | 기간 기준 성과 |
| max_drawdown_pct | 최대 낙폭 |
| hit_rate | 거래 승률 |
| avg_trade_return_pct | 거래당 평균 수익률 |
| trade_count | 거래 수 |
| turnover | 회전율 |
| cost_paid_pct | 비용으로 사라진 수익 |
| baseline_delta_pct | 기준 전략 대비 차이 |
| pass_cost_gate | 비용 gate 통과 여부 |
| rolling_overfit_gap_pct | train net - test net. Kronos 60초 실험에서 0.2874% 관측, RL은 0.15% 이내 목표 |
| positive_fold_rate | rolling fold 중 net return 양수 비율. Kronos 60초 실험 0.2857, RL은 0.50 이상 목표 |
| baseline_delta_300s_pct | 동일 split에서 Kronos 300초 rolling net (-0.0052%) 대비 차이 |
| cost_gate_pass_at_25bp | 25bp 비용 시나리오에서 양수 net return 달성 여부 |
| invalid_action_rate | 보유 중 재매수, 미보유 청산 등 무효 행동 비율 (1% 미만 목표) |
| episode_completion_rate | 강제 청산 없이 종료된 episode 비율 |

---

## 13. 웹 대시보드 신규 탭 설계

탭 이름 후보:

```text
강화학습 실험실
```

내부 컴포넌트명 후보:

```text
IndependentRLLabTab.svelte
```

### 13.1 화면 구성

| 섹션 | 내용 |
|---|---|
| 실험 개요 | run id, 데이터 범위, 종목 수, row 수, 모델 종류 |
| 데이터 계약 | 사용 feature, lookback, episode 정의, 누수 체크 결과 |
| 학습 진행 | episode, step, reward, loss, ETA, GPU/CPU 상태 |
| 성과 요약 | net return, MDD, 승률, 거래 수, baseline 대비 |
| 그래프 | reward curve, equity curve, drawdown curve |
| 거래 위치 | 실제 가격 차트 위 매수/청산 마커 |
| baseline 비교 | no-trade/random/momentum/mean-reversion 대비 |
| cost gate | 5/10/15/25bp 비용 시나리오 결과 |
| artifact | config/report/trades/actions 다운로드 또는 링크 |
| 경고 | overfit, high turnover, low trade count, leakage risk |

### 13.2 API 후보

| endpoint | 역할 |
|---|---|
| `GET /api/rl/runs` | 실험 목록 |
| `GET /api/rl/runs/{run_id}` | 실험 상세 |
| `GET /api/rl/runs/{run_id}/metrics` | 학습 곡선 |
| `GET /api/rl/runs/{run_id}/equity` | 수익곡선 |
| `GET /api/rl/runs/{run_id}/trades` | 거래 내역 |
| `GET /api/rl/runs/{run_id}/baseline-comparison` | baseline 비교 |
| `GET /api/rl/runs/{run_id}/cost-gate` | 비용 gate |

---

## 14. 성공 기준

### 14.1 1차 성공 기준: 플랫폼 구축

| 기준 | 통과 조건 |
|---|---|
| DB read-only loader | 원본 DB 수정 없이 episode 생성 |
| 환경 reset/step | deterministic test 통과 |
| 보상 계산 | 수수료/슬리피지/포지션 갱신 test 통과 |
| baseline runner | 최소 4개 baseline 실행 |
| artifact 생성 | config, metrics, trades, equity 저장 |
| 대시보드 | 새 탭에서 run 결과 확인 |

### 14.2 2차 성공 기준: 모델 유효성

| 기준 | 통과 조건 |
|---|---|
| walk-forward | train/val/test 시간 분리 |
| leakage check | 미래 데이터 누수 없음 |
| net return | 비용 차감 후 baseline 2개 이상 대비 우위 |
| MDD | 허용 기준 이하 |
| turnover | 과매매 경고 기준 이하 |
| stability | split별 성과가 한 구간에만 몰리지 않음 |

### 14.3 3차 성공 기준: 확장 승인

다음 조건을 모두 만족할 때만 전체 연도/전체 tick/포트폴리오 RL로 확장한다.

1. 25bp 비용 기준에서 rolling net return이 양수
2. random/no-trade/momentum 대비 유의미한 우위
3. trade count가 너무 적지 않음
4. 과최적화 gap이 과도하지 않음
5. 대시보드에서 사용자가 거래 위치와 손익을 확인 가능

---

## 15. 구현 페이지별 단계

| 페이지 | 단계 | 목표 | 완료 기준 |
|---:|---|---|---|
| 1 | 설계/문서 | 상태·행동·보상·검증 기준 고정 | 본 문서 커밋 |
| 2 | DB loader | STOM tick/1초봉 episode manifest 생성 | row/session/symbol 통계 report |
| 3 | Env | `StomTickTradingEnv` reset/step 구현 | unit test 통과 |
| 4 | Baseline | no-trade/random/momentum/mean-reversion 실행 | baseline report 생성 |
| 5 | Reward/cost gate | 비용/슬리피지/turnover/MDD 계산 | cost gate report 생성 |
| 6 | 1차 모델 | contextual bandit 또는 DQN prototype | walk-forward eval report |
| 7 | Backend API | RL run artifact API | pytest/API smoke 통과 |
| 8 | Web tab | `강화학습 실험실` 탭 | build + browser smoke 통과 |
| 9 | Review | 성과/위험/확장 판단 | 확장/보류 결정 문서화 |

현재 이 문서는 **페이지 1 완료**에 해당한다.

---

## 16. 예상 리스크와 완화책

| 리스크 | 설명 | 완화책 |
|---|---|---|
| 강화학습 과최적화 | 과거 데이터에서만 수익 | strict walk-forward, unseen date 검증 |
| 거래비용 압박 | 초단기 수익이 비용에 잠식 | 25bp gate, 거래 횟수 penalty |
| 데이터 누수 | 미래 통계가 feature에 섞임 | feature builder 테스트, scaler split 분리 |
| 종목 universe 변화 | 매일 종목이 달라짐 | episode를 날짜-종목 단위로 분리 |
| 모델 해석 어려움 | 왜 매수했는지 알기 어려움 | action attribution, feature snapshot 저장 |
| 속도 문제 | tick 전체 학습 시간이 김 | 1초봉/2025 subset → 전체 확장 |

---

## 17. 다음 권장 OMX 명령어

### 17.1 구현 전 확정 검토

```text
$ralplan --deliberate STOM 독립 강화학습 실험실 1차 구현 범위를 확정한다. 범위는 DB loader, Gymnasium 호환 StomTickTradingEnv, baseline runner, cost gate report, 웹 대시보드 탭 skeleton까지로 제한한다.
```

### 17.2 바로 구현 진행

```text
$ralph feature/stom-rl-lab 브랜치에서 STOM tick DB 기반 독립 강화학습 실험실 1차 구현을 진행하세요. 1차 범위는 DB loader, Gymnasium 호환 인터페이스의 StomTickTradingEnv, no-trade/random/momentum/mean-reversion baseline, cost-gate report, 웹 대시보드 '강화학습 실험실' 탭 skeleton, 테스트와 문서 업데이트입니다.
```

### 17.3 병렬 구현이 필요할 때

```text
$team STOM 독립 강화학습 실험실을 병렬 구현하세요. Lane A는 DB loader/env/test, Lane B는 baseline/cost-gate/evaluator, Lane C는 backend API/dashboard tab, Leader는 통합 검증과 문서/커밋 관리를 담당합니다.
```

---

## 18. 이번 문서의 stop condition

이 문서는 구현이 아니라 방향 고정 문서다. 완료 조건은 다음이다.

- Kronos 비의존 강화학습 방향이 명확함
- Gymnasium과 RLTrader의 역할이 구분됨
- 상태/행동/보상/비용/검증 기준이 문서화됨
- 새 웹 탭과 artifact/API 구조가 제안됨
- 다음 구현 명령어가 명확함

따라서 다음 단계는 **페이지 2: DB loader + episode manifest** 또는 **페이지 3: `StomTickTradingEnv` skeleton** 구현이다.

---

## 19. 2026-05-22 보완 업데이트 기록

최초 작성(commit 8188284) 이후 동일 일자에 진행한 상세 검토에서 다음 항목이 보완되었다. 본문 내 해당 섹션은 모두 업데이트 완료 상태이며, 이 섹션은 변경 사항을 한 곳에서 추적하기 위한 색인이다.

### 19.1 추가/보강된 섹션

| 위치 | 변경 | 출처/근거 |
|---|---|---|
| 6.4 | STOM 데이터 자원 실측치(18,750 group / 33.36M row / 168·36·36 session) 추가 | `finetune/qlib_exports/stom_1s_grid_pred60_2025/stom_qlib_export_report.json` |
| 6.5 | 누수 방지의 자동화 검증 메커니즘(5종 unit test) 추가 | 기존 Kronos 실험에서 rolling overfit gap 0.2874% 관측에 따른 강화 |
| 10.1 | Kronos checkpoint horizon별 결과를 외부 비교군으로 고정 | `webui/qlib_backtests/stom_1s_2025_full_small_horizon_comparison.json` |
| 11.0 | reward horizon 우선순위(300→120→60→30) 및 근거 추가 | 동일 horizon 비교표 |
| 12.1 | `rolling_overfit_gap_pct`, `positive_fold_rate`, `baseline_delta_300s_pct`, `cost_gate_pass_at_25bp`, `invalid_action_rate`, `episode_completion_rate` 신규 metric 6종 추가 | Kronos 60초 rolling 실험치 0.2874%/0.2857 등 |

### 19.2 보완 후에도 남는 후속 결정

다음 항목은 구현 단계(페이지 2 이후)에서 결정한다. 본 문서에서는 의도적으로 결론을 내리지 않는다.

1. **단위 시간 선택**: 1초봉 step을 그대로 쓰는지 또는 5초/10초 down-sampling을 쓰는지. 환경 검증 0단계 결과로 결정.
2. **invalid action 처리**: penalty만 줄지, 행동을 강제 보정할지. baseline runner 단계에서 비교.
3. **slippage 모델**: 고정 bp / 거래대금 비율 / 호가 기반 중 어떤 모델을 1차로 쓸지. 페이지 5 cost gate 단계에서 결정.
4. **종목 universe 결정 규칙**: 거래대금 상위 N의 N과 컷오프 시각. 종목 universe 변화 리스크(섹션 16)와 함께 페이지 2에서 결정.

### 19.3 본문에서 손대지 않은 영역

다음은 검토했지만 문서 변경이 필요 없다고 판단한 항목이다.

- 섹션 5 ADR 의사결정 자체: Option C(Gymnasium API + RLTrader식 매매 아이디어) 채택은 유지.
- 섹션 13 웹 대시보드 탭 명칭(`강화학습 실험실`)과 컴포넌트명(`IndependentRLLabTab.svelte`): 변경 사유 없음.
- 섹션 17 다음 권장 명령어 3종: 구현 단계로 진입할 때 그대로 사용 가능.

### 19.4 검증

문서 변경은 markdown 구조 무결성과 한글 인코딩 보존을 기준으로 확인한다.

| 검증 | 결과 |
|---|---|
| UTF-8 한글 보존 (물음표 손상 부재) | OK |
| 신규 섹션 헤더 레벨 일관성 | OK (`###` 하위, `##` 최상위 유지) |
| 표 컬럼 정렬 문법 | OK |
| 기존 섹션 번호 유지 | OK (18까지 동일, 19 신규 추가) |

---

## 20. 2026-05-22 페이지 2 구현 착수 기록

장기 goal을 활성화하고 페이지 2를 구현 범위로 확정했다.

### 20.1 페이지 2 범위

| 항목 | 결정 |
|---|---|
| 목적 | 모델 학습 전 episode 계약 고정 |
| 원본 DB | `_database/stock_tick_back.db` read-only |
| episode 기준 | 기존 2025 1초봉 Qlib CSV group |
| split 기준 | 기존 Kronos export의 train/val/test session split 재사용 |
| reward horizon | 300초 우선 |
| 산출물 | episode manifest JSON/CSV, summary JSON |

### 20.2 구현 파일

| 파일 | 역할 |
|---|---|
| `stom_rl/episode_manifest.py` | read-only DB 검증과 episode manifest 생성 |
| `tests/test_stom_rl_episode_manifest.py` | read-only, split overlap, manifest artifact 테스트 |
| `docs/stom_rl_lab_goal_pages_2026-05-22.md` | 장기 goal 페이지별 구현 계획 |

### 20.3 완료 기준

페이지 2는 다음을 모두 만족해야 완료로 본다.

1. `sqlite3` 연결이 `mode=ro`와 `PRAGMA query_only=ON`을 사용한다.
2. 쓰기 probe가 실패하여 원본 DB 보호가 증명된다.
3. train/validation/test session overlap이 0이다.
4. manifest episode 수가 기존 export report의 group 수와 일치한다.
5. 테스트와 실제 manifest smoke 실행이 통과한다.

### 20.4 완료 결과

페이지 2 구현 후 실제 smoke 실행에서 다음 결과를 확인했다.

| 지표 | 결과 |
|---|---:|
| episode_count | 18,750 |
| symbol_count | 1,638 |
| session_count | 240 |
| train episodes | 13,256 |
| validation episodes | 2,764 |
| test episodes | 2,730 |
| manifest delta vs export report | 0 |
| split overlap | 0 |
| unknown split episodes | 0 |

생성 산출물은 `webui/rl_runs/stom_1s_2025_episode_manifest/` 아래에 기록된다. 해당 디렉터리는 런타임 대용량 산출물이므로 `.gitignore`에 추가하고 커밋 대상에서 제외한다.

---

## 21. 2026-05-22 페이지 3 환경 구현 기록

페이지 3에서는 실제 강화학습 모델이 상호작용할 수 있는 환경 skeleton을 추가했다. 이 단계도 아직 수익 모델 학습이 아니라, **행동-보상-상태 전이 계약을 검증하는 기반 작업**이다.

### 21.1 구현 범위

| 항목 | 결정 |
|---|---|
| 환경 클래스 | `stom_rl.trading_env.StomTickTradingEnv` |
| 입력 | 페이지 2 episode manifest |
| API | Gymnasium 호환 `reset(seed, options)`, `step(action)` |
| 행동 | `hold`, `buy`, `sell` |
| 포지션 | long-only, 단일 포지션 |
| 기본 reward horizon | 300초 |
| observation | 과거 `lookback_window` row만 사용 |
| 누수 방지 | observation 마지막 timestamp가 action timestamp보다 항상 이전 |
| invalid action | penalty와 count로 기록 |

### 21.2 기본 observation feature

| feature | 설명 |
|---|---|
| open/high/low/close | 1초봉 가격 |
| volume/amount | 거래량/거래대금 |
| position | 현재 보유 여부 |
| unrealized_return | 미실현 수익률 |
| time_in_position | 포지션 유지 step 수 |

### 21.3 검증 결과

| 검증 | 결과 |
|---|---|
| reset/step shape | OK |
| 300초 horizon timestamp | OK |
| no future observation | OK |
| invalid buy/sell 처리 | OK |
| deterministic replay | OK |
| 실제 manifest smoke | OK |

페이지 3 완료 후 다음 단계는 **페이지 4: baseline runner** 이다. baseline runner는 이 환경을 사용하여 no-trade, random, buy-and-hold, momentum, mean-reversion, volume/amount filter를 같은 episode 계약에서 비교해야 한다.

---

## 22. 2026-05-22 페이지 4 baseline runner 구현 기록

페이지 4에서는 강화학습 모델이 비교해야 할 모델 없는 기준선을 구현했다. 이 단계는 수익 모델 학습이 아니라, **향후 RL 모델이 반드시 넘어야 하는 기준표와 산출물 계약을 고정하는 작업**이다.

### 22.1 구현 범위

| 항목 | 결정 |
|---|---|
| 구현 모듈 | `stom_rl.baselines` |
| 기반 환경 | `StomTickTradingEnv` |
| 기본 split | `test` |
| 기본 비용 | 25bp |
| 기본 reward horizon | 300초 |
| 기본 산출 위치 | `webui/rl_runs/stom_1s_2025_baselines*` |
| 커밋 대상 여부 | 런타임 산출물은 제외, 코드/테스트/문서만 커밋 |

### 22.2 구현 baseline

| 정책 | 목적 |
|---|---|
| `no_trade` | 아무것도 하지 않는 무위험 기준 |
| `random` | 모델이 랜덤 매매보다 나은지 확인 |
| `buy_and_hold` | 장초반 구간 단순 보유 기준 |
| `momentum` | 최근 수익률 추종 기준 |
| `mean_reversion` | 최근 하락 후 반등 가정 기준 |
| `volume_filter` | 거래대금 강도 조건식 기준 |

### 22.3 산출물

각 정책은 다음 artifact를 생성한다.

| 파일 | 설명 |
|---|---|
| `actions.csv` | step별 action, env reward, mark equity |
| `trades.csv` | 체결 단위 진입/청산/순수익/강제청산 여부 |
| `equity.csv` | 시간별 mark-to-market equity |
| `episodes.csv` | episode별 최종 equity, 거래 수, forced exit |
| `baseline_summary.json` | 전체 baseline 비교 summary |
| `baseline_summary.csv` | 대시보드/분석용 summary table |

### 22.4 실제 smoke 결과

실제 2025 STOM test split에서 3개 episode만 사용해 경로를 검증했다. 이 결과는 성능 확정이 아니라 smoke 기준이다.

| 정책 | episode | 거래 수 | 평균 episode net | hit rate | MDD |
|---|---:|---:|---:|---:|---:|
| `no_trade` | 3 | 0 | 0.0000% | 0.0000 | 0.0000% |
| `random` | 3 | 885 | -77.2541% | 0.0124 | -98.8246% |
| `buy_and_hold` | 3 | 3 | +3.3240% | 1.0000 | 0.0000% |
| `momentum` | 3 | 214 | -34.1359% | 0.0421 | -71.5770% |
| `mean_reversion` | 3 | 195 | -22.5387% | 0.0359 | -53.5298% |
| `volume_filter` | 3 | 224 | -31.2288% | 0.0045 | -67.6145% |

### 22.5 검증

| 검증 | 결과 |
|---|---|
| baseline unit test | `10 passed` |
| env/manifest 회귀 | 통과 |
| 실제 manifest smoke | `baseline_summary.json/csv` 및 정책별 artifact 생성 |
| `py_compile` | 통과 |

다음 단계는 **페이지 5: reward / cost gate**다. 페이지 5에서는 smoke가 아니라 전체 test split 또는 제한된 검증 범위를 명시하고 5/10/15/25bp 비용별로 baseline을 비교해 “비용 차감 후 살아남는 전략이 있는가?”를 판단한다.

---

## 23. 2026-05-22 페이지 5 reward / cost gate 구현 기록

페이지 5에서는 baseline runner 위에 비용·슬리피지·회전율·MDD·rolling validation gate를 추가했다. 이 단계는 RL 모델의 성과를 좋게 보이게 만드는 작업이 아니라, **향후 모델이 통과해야 할 현실 비용 기준을 먼저 고정하는 작업**이다.

### 23.1 구현 범위

| 항목 | 결정 |
|---|---|
| 구현 모듈 | `stom_rl.cost_gate` |
| 기반 모듈 | `stom_rl.baselines` |
| 기본 split | `test` |
| 기본 비용 시나리오 | 5bp, 10bp, 15bp, 25bp |
| 기본 target gate | 25bp |
| rolling validation | session chunk 단위 fold |
| 산출 위치 | `webui/rl_runs/stom_1s_2025_cost_gate*` |

### 23.2 gate 판정 기준

| 기준 | 기본값 | 의미 |
|---|---:|---|
| `min_avg_episode_net_pct` | 0.0% | 비용 차감 평균 episode 수익률이 양수여야 함 |
| `max_drawdown_pct` | 20.0% | MDD가 -20%보다 나쁘면 실패 |
| `max_trades_per_episode` | 50.0 | 과도한 초단타/비용 민감 전략 실패 |
| `min_trade_count` | 1 | no-trade는 비교 기준일 뿐 gate 통과 전략이 아님 |
| `min_positive_fold_rate` | 0.5 | rolling fold 절반 이상에서 양수여야 함 |

### 23.3 산출물

| 파일 | 설명 |
|---|---|
| `cost_gate_report.json` | 전체 설정, 비용 scenario, rolling, 최종 gate summary |
| `scenario_summary.csv` | cost/slippage/policy별 요약 |
| `rolling_folds.csv` | fold별 policy 성과 |
| `gate_summary.csv` | target 25bp 기준 최종 통과 여부 |

### 23.4 실제 smoke 결과

실제 2025 STOM test split에서 3개 episode, 2개 rolling fold만 사용해 검증 경로를 확인했다.

| 정책 | 25bp 평균 episode net | 거래/episode | hit rate | MDD | positive fold rate | gate |
|---|---:|---:|---:|---:|---:|---|
| `buy_and_hold` | +3.3240% | 1.00 | 1.0000 | 0.0000% | 0.5000 | 통과 |
| `no_trade` | 0.0000% | 0.00 | 0.0000 | 0.0000% | 0.0000 | 실패 |
| `mean_reversion` | -22.5387% | 65.00 | 0.0359 | -53.5298% | 0.0000 | 실패 |
| `volume_filter` | -31.2288% | 74.67 | 0.0045 | -67.6145% | 0.0000 | 실패 |
| `momentum` | -34.1359% | 71.33 | 0.0421 | -71.5770% | 0.0000 | 실패 |
| `random` | -77.2541% | 295.00 | 0.0124 | -98.8246% | 0.0000 | 실패 |

이 smoke 결과는 전체 test split에 대한 결론이 아니다. 다만 다음 사실은 확인했다.

1. 비용이 올라갈수록 random/momentum/volume 계열의 과매매 전략이 빠르게 붕괴한다.
2. 회전율 gate가 없으면 5bp에서 일시적으로 좋아 보이는 mean-reversion도 통과로 오판할 수 있다.
3. 25bp target gate에서는 거래 수가 낮고 수익이 큰 buy-and-hold만 smoke에서 통과했다.
4. 따라서 1차 RL 모델은 단순히 거래를 많이 하는 방향이 아니라 **낮은 회전율 + 선택적 진입 + 300초 horizon 수익**을 목표로 해야 한다.

### 23.5 검증

| 검증 | 결과 |
|---|---|
| cost gate unit test | 통과 |
| baseline/env/manifest 회귀 | 통과 |
| 실제 manifest smoke | `cost_gate_report.json/csv` 산출물 생성 |
| `py_compile` | 통과 |

다음 단계는 **페이지 6: 1차 RL 모델**이다. 추천 출발점은 300초 reward horizon, 25bp target gate 기준으로 contextual bandit 또는 단순 DQN prototype을 만든 뒤, Page 5의 `gate_summary.csv`와 동일 기준으로 모델 결과를 비교하는 것이다.

---

## 24. 2026-05-22 페이지 6 1차 RL 모델 구현 기록

페이지 6에서는 Kronos와 완전히 분리된 첫 학습 모델을 추가했다. 이 단계의 목적은 최종 수익 모델을 확정하는 것이 아니라, **STOM episode에서 학습 → 모델 저장 → 모델 로드/사용 → 평가 artifact 생성**이 가능한 최소 학습 루프를 실제 데이터로 증명하는 것이다.

### 24.1 구현 범위

| 항목 | 결정 |
|---|---|
| 구현 모듈 | `stom_rl.contextual_bandit` |
| 모델 | ridge regression 기반 contextual bandit |
| 의존성 | 신규 의존성 없음, NumPy/Pandas만 사용 |
| action | `buy` 또는 `hold` |
| reward target | 300초 fixed-horizon round-trip net return |
| 비용 | 25bp 기본 |
| 평가 | Page 5와 같은 net return, trade count, hit rate, MDD, cost gate |
| 산출 위치 | `webui/rl_runs/stom_1s_2025_contextual_bandit*` |

### 24.2 사용 feature

feature는 현재와 과거 정보만 사용한다. 미래 가격은 label/reward 계산에만 사용된다.

| feature 그룹 | 예시 |
|---|---|
| 과거 수익률 | `ret_1s`, `ret_5s`, `ret_30s`, `ret_60s`, `ret_120s`, `ret_300s` |
| 변동성/range | `range_30s`, `range_120s` |
| 추세 이격 | `close_vs_ma_30s`, `close_vs_ma_120s` |
| 거래 강도 | `volume_ratio_30s`, `amount_ratio_30s` |
| 시간 위치 | `seconds_from_episode_start` |

### 24.3 산출물

| 파일 | 설명 |
|---|---|
| `config.json` | 학습/평가 설정 |
| `model.json` | feature mean/std, weights, intercept, train summary |
| `train_metrics.jsonl` | train sample/target/오차 기록 |
| `eval_summary.json` | 평가 요약과 artifact 경로 |
| `actions.csv` | 각 의사결정 시점의 예측 점수와 action |
| `trades.csv` | 실제 진입/청산과 net return |
| `equity_curve.csv` | 평가 equity 흐름 |
| `episodes.csv` | episode별 최종 성과 |

### 24.4 실제 smoke 결과

실제 2025 STOM train 5 episode로 학습하고 test 3 episode로 평가했다.

| 항목 | 값 |
|---|---:|
| train episode | 5 |
| train sample | 299 |
| train target mean | -0.6087% |
| train target positive rate | 27.42% |
| train RMSE | 1.3035% |
| predicted positive rate | 11.04% |
| eval episode | 3 |
| eval trade count | 11 |
| trades / episode | 3.67 |
| avg episode net | +1.8960% |
| compounded return | +5.7773% |
| avg trade net | +0.5240% |
| hit rate | 63.64% |
| MDD | -2.6211% |
| 25bp cost gate | 통과 |

해석:

1. 모델은 실제 STOM episode에서 학습되고 `model.json`으로 저장된다.
2. 저장된 모델은 다시 로드해 예측 점수를 계산할 수 있다.
3. 3개 episode smoke에서는 25bp 비용 후에도 양수 성과를 냈다.
4. 그러나 같은 smoke 구간에서 단순 `buy_and_hold`가 +3.3240%였으므로, 아직 “baseline 우위”가 증명된 것은 아니다.
5. 다음 단계에서는 이 artifact를 backend/API와 웹 대시보드에서 확인할 수 있게 연결해야 한다.

### 24.5 검증

| 검증 | 결과 |
|---|---|
| contextual bandit unit test | 통과 |
| model save/load test | 통과 |
| cost gate/baseline/env/manifest 회귀 | 통과 |
| 실제 manifest smoke | `model.json`, `eval_summary.json`, `trades.csv`, `equity_curve.csv` 생성 |
| `py_compile` | 통과 |

다음 단계는 **페이지 7: backend API**다. API는 `webui/rl_runs` 아래의 baseline, cost gate, contextual bandit 산출물을 읽어 웹 대시보드에서 사용자가 강화학습 진행과 성과를 확인할 수 있게 해야 한다.

---

## 25. 2026-05-22 페이지 7 backend API 구현 기록

페이지 7에서는 독립 강화학습 실험실의 런타임 산출물을 웹에서 조회할 수 있는 read-only API를 추가했다. 이 API는 학습을 시작하거나 원본 DB를 수정하지 않고, `webui/rl_runs` 아래의 재생성 가능한 artifact만 읽는다.

### 25.1 구현 범위

| 항목 | 결정 |
|---|---|
| 구현 helper | `webui.rl_dashboard` |
| Flask 연결 | `webui.app` |
| API prefix | `/api/rl` |
| 대상 artifact | episode manifest, baseline, cost gate, contextual bandit |
| 보안 원칙 | run/policy path traversal 차단, direct child만 허용 |
| table limit | 기본 500 row, 최대 5,000 row |

### 25.2 API 목록

| endpoint | 설명 |
|---|---|
| `GET /api/rl/runs` | RL run artifact 목록 |
| `GET /api/rl/runs/<run>` | run 상세, summary, artifact 목록, 모델 요약 |
| `GET /api/rl/runs/<run>/actions` | action table |
| `GET /api/rl/runs/<run>/trades` | trade table |
| `GET /api/rl/runs/<run>/equity` | equity curve table |
| `GET /api/rl/runs/<run>/episodes` | episode summary table |
| `GET /api/rl/runs/<run>/table/<table>` | generic table 조회 |
| `GET /api/rl/runs/<run>/cost-gate` | cost gate compact payload |

baseline run은 정책별 subdirectory에 table이 있으므로 `?policy=buy_and_hold` 같은 query를 지원한다. policy를 생략하면 가능한 policy table을 limit 범위 안에서 합쳐 반환한다.

### 25.3 실제 smoke 결과

실제 런타임 산출물 기준으로 Flask test client smoke를 수행했다.

| endpoint | 결과 |
|---|---|
| `/api/rl/runs?limit=10` | 200, 4개 RL run 탐지 |
| `/api/rl/runs/stom_1s_2025_contextual_bandit_smoke` | 200, contextual bandit summary 반환 |
| `/api/rl/runs/stom_1s_2025_contextual_bandit_smoke/trades?limit=3` | 200, trade rows 반환, truncated=true |
| `/api/rl/runs/stom_1s_2025_contextual_bandit_smoke/equity?limit=3` | 200, equity rows 반환, truncated=true |
| `/api/rl/runs/stom_1s_2025_cost_gate_smoke/cost-gate?limit=3` | 200, passing policy `buy_and_hold` 반환 |

### 25.4 검증

| 검증 | 결과 |
|---|---|
| helper list/detail/table test | 통과 |
| Flask `/api/rl/*` route smoke | 통과 |
| path traversal 거부 test | 통과 |
| contextual bandit/cost gate/baseline/env/manifest 회귀 | 통과 |
| 실제 runtime artifact smoke | 통과 |

다음 단계는 **페이지 8: 웹 대시보드**다. 이제 프론트엔드에서 `/api/rl/runs`, `/api/rl/runs/<run>`, `/api/rl/runs/<run>/trades`, `/api/rl/runs/<run>/equity`, `/api/rl/runs/<run>/cost-gate`를 사용해 “강화학습 실험실” 탭을 만들 수 있다.


---

## 26. 2026-05-23 페이지 8 웹 대시보드 구현 기록

페이지 8에서는 강화학습 산출물을 사용자가 직접 확인할 수 있도록 v2 대시보드에 RL 실험실 탭을 연결했다. 이 단계는 Kronos 예측/파인튜닝 화면과 별개로 독립 RL 모델 산출물, 비용 관문, 거래 위치, STOM DB 기반 episode 정보를 해석하는 화면이다.

### 26.1 구현 파일

| 파일 | 역할 |
|---|---|
| `webui/v2_src/src/tabs/RLLabTab.svelte` | 강화학습 실험실 화면, 차트/표/해석 UI |
| `webui/v2_src/src/lib/api.ts` | RL API 호출용 fetch wrapper 추가 |
| `webui/v2_src/src/App.svelte` | `rl-lab` 탭 등록 |
| `webui/v2_src/src/layout/Sidebar.svelte` | 좌측 메뉴에 `강화학습 실험실` 추가 |
| `webui/v2_src/src/layout/Header.svelte` | 현재 위치 breadcrumb 표시 보강 |
| `tests/test_stom_rl_dashboard_tab.py` | 프론트 탭/API/dist marker 회귀 테스트 |
| `webui/static/v2/dist/*` | 빌드된 v2 정적 파일 갱신 |

### 26.2 화면 구성

| 영역 | 표시 내용 |
|---|---|
| KPI 카드 | run 수, 평균 순수익률, 거래 수, cost gate 통과 정책 수 |
| Run selector | contextual bandit, cost gate, baseline, episode manifest 산출물 선택 |
| Model usage flow | `model.json`을 어디에 넣고 어떤 feature로 추론하는지 안내 |
| Cost gate chart/table | 25bp 기준 비용 반영 후 baseline/policy 통과 여부 |
| Equity curve | 선택 run의 누적 성과 흐름 |
| Trade chart/table | 진입/청산 위치와 gross net/cost net 차이 |
| Artifact table | 생성된 파일과 크기 확인 |

### 26.3 검증 결과

| 검증 | 결과 |
|---|---|
| Svelte check | 0 errors, 기존 DocsTab/Forecast 경고 4개만 유지 |
| Vite build | 통과 |
| Pytest | `tests/test_stom_rl_dashboard_tab.py tests/test_stom_rl_dashboard_api.py tests/test_v2_route.py` 총 8 passed |
| Browser smoke | Playwright headless Chromium으로 `/` 접속 후 `rl-lab` 탭 확인 |
| Smoke screenshot | `.omx/tmp/rl-lab-page8-smoke.png` |

### 26.4 해석 주의

현재 웹에 표시되는 contextual bandit 결과는 smoke 성과다. 이 수치는 플랫폼 연결과 모델 사용 흐름을 증명하기 위한 것이며 실거래 성과를 보장하지 않는다. 최종 QA에서는 full test split, baseline 대비 우위, cost gate 안정성, 자동 매매 보류 판단을 명확히 구분해야 한다.

### 26.5 다음 단계

다음 페이지는 **페이지 9: 통합 QA / 리뷰**다. 권장 실행 명령은 다음과 같다.

```powershell
omx ultragoal complete-goals
```

페이지 9에서는 전체 Python 테스트, v2 build, browser smoke를 다시 확인하고, `ai-slop-cleaner`와 code review 기준으로 구현 품질을 검토한 뒤 자동 매매 보류 또는 확장 판단을 문서화한다.


---

## 27. 2026-05-23 페이지 9 통합 QA / 리뷰 기록

페이지 9에서는 STOM 독립 강화학습 실험실을 최종 검증 대상으로 닫았다. 상세 보고서는 `docs/stom_rl_lab_final_qa_report_2026-05-23.md`에 남겼다.

### 27.1 검증 요약

| 검증 | 결과 |
|---|---|
| 전체 pytest | 92 passed, 2 skipped, 2 warnings |
| npm build | 통과, Svelte error 0 |
| Python compile | 통과 |
| Browser smoke | 통과 |
| API smoke | 통과 |
| path traversal probe | 400으로 차단 |
| Code review | APPROVE / CLEAR |

### 27.2 최종 판단

구현 목표는 달성했다. 독립 RL 플랫폼, 데이터 manifest, trading env, baseline, cost gate, 첫 모델, API, 웹 대시보드, 최종 QA 흐름이 모두 존재한다.

단, 현재 1차 contextual bandit은 smoke 모델이므로 실거래 자동화에는 아직 충분하지 않다. 다음 확장에서는 full test split 기준으로 baseline과 RL 모델을 비교하고 비용 반영 후에도 반복적으로 우위가 유지되는지 검증해야 한다.
