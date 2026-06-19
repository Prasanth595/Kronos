# STOM Kronos 파인튜닝 올바름 집중 검토 보고서

작성일: 2026-05-07
검토 대상: STOM 1tick SQLite DB → grouped OHLCV CSV → Kronos predictor fine-tuning → 예측 CSV/웹 대시보드 산출물

## 1. 결론 요약

| 판단 항목 | 결론 | 근거 |
| --- | --- | --- |
| DB를 학습 가능한 OHLCV 형태로 변환했는가 | **가능 / 대체로 올바름** | `_database\stock_tick_back.db`에서 2,427개 테이블 중 2,425개 호환, 73,650개 eligible session 확인. `price_mode=close_only` 기준으로 현재가/종가를 OHLC에 매핑. |
| 여러 종목/여러 일자 세션을 학습했는가 | **예** | 그룹 키가 `symbol, session`이며, window가 종목/일자 경계를 넘지 않도록 `GroupedKlineDataset`이 구성됨. |
| GPU 파인튜닝이 실제 완료되었는가 | **예** | CUDA `NVIDIA GeForce RTX 4080 SUPER`, PyTorch `2.9.0+cu128`, 최종 all-table bounded run이 `cuda:0`에서 37,500 step 완료 후 checkpoint 저장. |
| 데이터 누수 위험은 통제되었는가 | **대체로 통제됨** | 학습/검증 split은 group 단위이며, 정규화 기준은 config에서 `normalize_using: lookback`으로 설정되어 미래 구간을 정규화 통계에 쓰지 않음. |
| 최종 모델을 실전 매매에 바로 신뢰해도 되는가 | **아직 아님** | all-table bounded 모델 예측의 방향정확도는 0.40으로 낮음. MAPE는 좋아졌지만 방향성/수익성 검증은 별도 walk-forward + 비용 반영 backtest가 필요. |

**최종 판단:** 파인튜닝 절차 자체는 올바른 방향으로 구현·실행되었습니다. 다만 현재 산출물은 “학습 성공 모델”이지 “실전 종목 추천에 바로 투입 가능한 검증 완료 모델”은 아닙니다. 특히 최종 all-table bounded 모델은 가격 오차(MAPE)는 개선됐지만 방향정확도는 낮아, 점수화/조건식/백테스트 보완 없이는 매매 신호로 단독 사용하면 안 됩니다.

## 2. 검토한 핵심 근거

### 2.1 DB 스캔/학습 가능성

확인 파일: `.omx/specs/stom-ohlcv-finetune-research/all_tables_inspect_close_only.json`

- DB: `_database\stock_tick_back.db`
- DB 크기: 29,727,162,368 bytes
- 전체 테이블: 2,427개
- 호환 테이블: 2,425개
- 비호환 테이블: `moneytop`, `stockinfo`
- 최소 필요 row 수: `lookback 300 + predict 60 + 1 = 361`
- eligible session: 73,650개
- `trainable: true`
- price mode: `close_only`

스케일 추정 파일: `.omx/specs/stom-ohlcv-finetune-research/all_tables_sample_scale_lookback300_predict60.json`

- 호환 주식 테이블: 2,425개
- 전체 그룹: 73,968개
- eligible 그룹: 73,650개
- 주식 그룹 전체 row: 122,522,300
- 이론상 window sample 추정: 95,946,764

해석:

- “여러 종목을 학습했는가?”에 대한 답은 **예**입니다.
- 단, 최종 all-table 학습은 95,946,764개 모든 window를 전부 학습한 것이 아니라, bounded 설정으로 sample 수를 제한한 pilot/scale-up 성격입니다.

### 2.2 STOM tick DB → OHLCV 변환 로직

확인 코드: `finetune_csv/stom_tick_dataset.py`

중요 구현:

- `connect_readonly()`는 SQLite를 `mode=ro`로 열고 `PRAGMA query_only=ON`을 설정합니다.
- `infer_stom_column_mapping()`은 STOM 테이블의 timestamp/현재가/종가/거래량/거래대금 계열 컬럼을 Kronos OHLCV로 매핑합니다.
- `price_mode=close_only`에서는 open/high/low/close를 모두 `종가` 또는 `현재가` 기반 close 컬럼으로 통일합니다.
- `read_stom_table_as_kline()`은 09:00:00~09:30:00 구간을 필터링할 수 있습니다.
- `export_stom_tick_db_to_csv()`는 모든 테이블을 순회하면서 `symbol, session` 그룹별로 학습 가능한 row 수를 만족하는 데이터만 CSV에 기록합니다.

판단:

- DB 원본을 직접 수정하지 않고 읽기 전용으로 사용하므로 안전합니다.
- STOM tick DB가 “진짜 봉 OHLC”가 아니라 tick 단위 현재가 흐름일 가능성이 커서 `close_only`를 쓴 것은 합리적입니다.
- 다만 `close_only`는 OHLC가 모두 같은 값이므로 Kronos가 원래 기대하는 candlestick shape 정보는 줄어듭니다. 이 모델은 “초단위 close path + volume/amount”에 더 가깝게 학습된 것으로 봐야 합니다.

## 3. 데이터 누수/분할 정확성 검토

확인 코드: `finetune_csv/stom_tick_dataset.py`, `finetune_csv/finetune_base_model.py`

### 3.1 종목/일자 경계 누수

`GroupedKlineDataset`은 다음 방식으로 window를 구성합니다.

- 필수 column: `symbol`, `session`, `timestamps`, `open`, `high`, `low`, `close`, `volume`, `amount`
- 정렬: `group_columns + timestamps`
- 그룹: `symbol, session`
- window 길이: `lookback_window + predict_window + 1`
- sample index는 각 그룹 내부에서만 생성

따라서 한 종목의 어느 날짜 window가 다른 종목 또는 다른 날짜로 이어지는 문제는 코드 구조상 방지됩니다.

### 3.2 train/validation split

`GroupedKlineDataset._split_groups()`는 전체 그룹을 `first_timestamp, group_key` 기준으로 정렬한 뒤 group 단위로 train/val/test를 나눕니다.

장점:

- row 중간에서 split하지 않으므로 window가 train/val 경계를 넘지 않습니다.
- 종목/세션 경계가 보존됩니다.

주의점:

- 같은 종목이 다른 날짜 session으로 train과 validation 양쪽에 등장할 수 있습니다.
- 이는 “매일 거래대금 상위 100위가 바뀌는 universe에 대해 일반화”하려는 목적에는 자연스럽지만, “완전한 미등장 종목 holdout 검증”은 아닙니다.
- 일자 기준 엄격한 walk-forward 검증은 아직 별도 보강이 필요합니다.

### 3.3 정규화 누수

중요 설정:

- `config_stom_1tick_all.yaml`: `normalize_using: "lookback"`
- `GroupedKlineDataset.get_numpy()`: `lookback` 설정이면 정규화 평균/표준편차를 예측 대상 미래 구간이 아니라 lookback 구간에서만 계산합니다.

판단:

- 현재 config 기준으로 정규화 미래 누수는 통제되어 있습니다.
- 단, 누군가 `normalize_using: window`로 바꾸면 미래 구간까지 평균/표준편차 계산에 들어가므로 학습/검증 해석이 왜곡될 수 있습니다. 이 설정은 바꾸지 않는 것이 좋습니다.

## 4. 파인튜닝 실행 방식 검토

확인 코드: `finetune_csv/train_sequential.py`, `finetune_csv/finetune_base_model.py`

학습 방식:

- tokenizer: `NeoQuasar/Kronos-Tokenizer-base` 사용, STOM용 tokenizer 재학습은 하지 않음.
- predictor/base model: `NeoQuasar/Kronos-small`에서 시작해 fine-tuning.
- 입력: 정규화된 OHLCV + 시간 feature.
- target: tokenizer가 만든 token sequence를 한 step shift하여 autoregressive next-token loss 계산.
- optimizer: AdamW.
- checkpoint: validation loss가 개선될 때 `best_model` 저장.

판단:

- Kronos 구조에 맞는 “시계열 token next-step 예측” 방식으로 학습되고 있습니다.
- 모델이 단순 회귀 label을 직접 맞추는 것이 아니라, Kronos tokenizer/predictor 구조에 맞춰 tokenized future sequence를 학습합니다.
- 현재 설정은 1 epoch, 작은 learning rate 중심의 적응 학습입니다. 큰 폭의 재학습이 아니라 STOM tick 분포에 맞춘 미세 조정입니다.

## 5. GPU 학습 완료 여부

확인 파일: `.omx/specs/stom-full-training-dashboard/env_check_after_cuda.json`

- PyTorch: `2.9.0+cu128`
- CUDA 사용 가능: `true`
- CUDA version: `12.8`
- GPU: `NVIDIA GeForce RTX 4080 SUPER`
- GPU memory: 15.99 GB

학습 로그/체크포인트:

| 모델/run | data path | device | step | train loss | val loss | 시간 | checkpoint |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `stom_1tick_gpu_pilot_lookback300_pred60` | `finetune_csv/data/stom_1tick_kline.csv` | `cuda:0` | 512 | 2.4667 | 2.4311 | 1.40분 | 있음 |
| `stom_1tick_300_lookback300_pred60` | `finetune_csv/data/stom_1tick_kline_300.csv` | `cuda:0` | 6,250 | 2.3893 | 2.3258 | 9.32분 | 있음 |
| `stom_1tick_1000_lookback300_pred60` | `finetune_csv/data/stom_1tick_kline_1000.csv` | `cuda:0` | 25,000 | 2.3204 | 2.3030 | 35.22분 | 있음 |
| `stom_1tick_all_lookback300_pred60` | `finetune_csv/data/stom_1tick_kline_all_bounded.csv` | `cuda:0` | 37,500 | 2.4891 | 2.3983 | 55.95분 | 있음 |

체크포인트 파일:

- 각 run마다 `basemodel/best_model/model.safetensors` 존재.
- 각 model.safetensors 크기: 약 98,980,656 bytes.

중요 주의:

- `stom_1tick_all_lookback300_pred60` 로그에는 2026-05-06 22:08의 이전 all CSV 시작 기록과 2026-05-07 06:27의 bounded CSV 완료 기록이 같은 log 파일에 함께 남아 있습니다.
- 완료된 segment는 `stom_1tick_kline_all_bounded.csv`를 사용했고, 37,500 step/55.95분으로 정상 종료되었습니다.
- 따라서 “절전 모드 때문에 학습이 안 됐는가?” 관점에서는, 최종 bounded run은 완료 및 checkpoint 저장 근거가 있습니다. 다만 이전 unbounded 시작 segment는 완료 기록이 없으므로 성공 run으로 보지 않아야 합니다.

## 6. 예측 성과 검토

확인 파일: `webui/stom_predictions/*.metrics.json`

| 예측 파일 | windows | rows | MAPE | 방향정확도 | 평균 예측 등락률 | 평균 실제 등락률 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `pilot_predictions` | 5 | 300 | 0.7366 | 0.20 | 0.0000 | 0.4960 |
| `kronos_gpu_pilot_predictions` | 20 | 1,200 | 0.8289 | 0.50 | -0.2807 | 0.1523 |
| `kronos_300_predictions` | 100 | 6,000 | 0.6687 | 0.58 | -0.1967 | 0.0202 |
| `kronos_1000_predictions` | 200 | 12,000 | 0.5583 | 0.49 | -0.1879 | -0.0481 |
| `kronos_all_predictions` | 300 | 18,000 | 0.2720 | 0.40 | -0.0751 | 0.0094 |

해석:

- 가격 오차 관점에서는 all-table bounded 예측의 MAPE가 가장 낮습니다.
- 하지만 방향정확도는 all-table bounded가 0.40으로 낮습니다.
- `kronos_300`은 방향정확도 0.58로 가장 좋아 보이지만 windows 100개 수준이므로 과대평가 가능성이 있습니다.
- 평균 예측 등락률이 전반적으로 음수 쪽으로 치우쳐 있어 보수적/하방 bias가 있습니다.

결론:

- “모델이 예측 CSV를 생성하고 실제값/예측값 비교를 할 수 있는가?”는 **예**입니다.
- “예측이 매매에 충분한가?”는 **아직 아니오**입니다.
- 현재는 raw Kronos 예측값을 그대로 매수/매도 조건으로 쓰기보다, 점수화와 필터링을 거친 후보 feature로 활용해야 합니다.

## 7. 웹 대시보드 검증 관점

기존 개발 산출물 기준으로 다음 경로가 확인됩니다.

- 예측 산출물: `webui/stom_predictions/*.csv`
- metrics: `webui/stom_predictions/*.metrics.json`
- dashboard helper 테스트: `tests/test_stom_dashboard_helpers.py`
- 예측 평가 테스트: `tests/test_stom_prediction_eval.py`

판단:

- 학습 후 생성된 예측 CSV/metrics를 웹 UI에서 실제값과 예측값 비교 용도로 사용할 수 있는 구조는 만들어져 있습니다.
- 단, 웹 대시보드 표시가 “모델 품질 검증 완료”를 의미하지는 않습니다. 대시보드는 관찰/검토 도구이고, 실전 투입 판단은 backtest와 live paper-trading 검증이 별도로 필요합니다.

## 8. 현재 파인튜닝의 가장 중요한 한계

1. **최종 all-table 모델은 bounded 학습이다.**
   모든 호환 테이블 universe를 대상으로 했지만, 모든 가능한 95,946,764 window를 전부 학습한 것은 아닙니다. config상 `max_samples: 300000`, `sample_stride: 10`으로 제한된 학습입니다.

2. **1 epoch만 학습했다.**
   실행 검증과 pilot scale-up에는 적절하지만, 최종 성능 수렴을 단정할 수 없습니다.

3. **방향정확도가 안정적이지 않다.**
   all-table bounded 예측은 MAPE가 낮아도 방향정확도 0.40입니다. 가격 경로가 평균적으로 가까워도 종가매매/단타 의사결정의 승률로 바로 연결되지 않습니다.

4. **검증 split이 실전 walk-forward와 동일하지 않다.**
   group 단위 split은 누수 방지에는 좋지만, “최근 날짜를 완전히 holdout”하는 실전 검증과는 다릅니다.

5. **`close_only`는 안전하지만 정보량이 제한된다.**
   STOM tick DB의 OHLC 의미가 누적 장중 값일 수 있어 `close_only`가 합리적이지만, 결과적으로 봉의 고저/시가 구조는 학습하지 않습니다.

6. **비용/슬리피지/체결 가능성 검증이 아직 없다.**
   방향정확도와 MAPE만으로 실제 수익성을 판단할 수 없습니다.

## 9. 올바르게 활용하는 방법

현재 Kronos fine-tuned 모델은 단독 매수 신호가 아니라 다음과 같은 feature/score로 쓰는 것이 안전합니다.

### 9.1 실시간 1분/1초 예측 점수

추천 점수 구성 예:

```text
kronos_return_score = 예상 등락률 z-score
kronos_direction_score = 예측 종가 > 현재가 여부
kronos_confidence_score = 여러 sample 예측의 분산 역수
volume_score = 거래량/거래대금 급증 점수
trend_score = 최근 n초 또는 n분 추세 점수
risk_penalty = spread, 급락, VI, 과열, 거래정지/관리종목 등 제외 패널티
final_score = 0.35*kronos_return_score
            + 0.20*kronos_direction_score
            + 0.20*volume_score
            + 0.15*trend_score
            - 0.10*risk_penalty
```

현재 방향정확도만 보면 Kronos 비중을 너무 크게 두면 위험합니다. 초기에는 Kronos 비중을 20~35% 이하로 두고, 거래대금/체결강도/추세/호가 조건으로 보완하는 것이 좋습니다.

### 9.2 종가매매 활용

일봉용으로도 같은 구조는 가능합니다. 다만 현재 검토한 모델은 09:00~09:30 1tick/1초 흐름에 맞춘 STOM 파인튜닝이므로, 일봉 종가매매에 그대로 쓰면 데이터 분포가 다릅니다.

종가매매에는 별도 daily OHLCV CSV를 만들고 다음을 해야 합니다.

- lookback: 예: 60일~240일
- predict: 예: 1일~5일
- split: 최근 기간 holdout walk-forward
- metric: 다음날/다음 n일 수익률, hit ratio, MDD, turnover, 비용 차감 수익
- score: Kronos 예상 등락률 + 수급/거래대금/변동성/시장상태 필터

## 10. 권장 다음 단계

우선순위 1 — 검증 강화:

- 최근 날짜 holdout walk-forward 평가 추가.
- persistence baseline과 동일 window 비교.
- 거래 비용/슬리피지 반영 backtest 추가.
- 방향정확도뿐 아니라 top-k 추천 수익률, MDD, turnover, hit ratio 기록.

우선순위 2 — 재현성 강화:

- checkpoint마다 config hash, data file hash/size, log segment id를 manifest로 저장.
- 같은 log 파일에 이전 중단 run과 완료 run이 섞이지 않도록 run id별 로그 파일 분리.

우선순위 3 — 모델 개선:

- all-table bounded 학습을 2~3 epoch로 늘려 검증 loss와 방향정확도 변화를 확인.
- `max_samples`를 늘리되 memory/time을 기록.
- STOM tick의 시가/고가/저가 컬럼 의미가 “해당 tick 구간 OHLC”인지 “장중 누적 OHLC”인지 확정되면 `db_ohlc` 모드와 비교 실험.

우선순위 4 — 실전 사용:

- Kronos 예측을 단독 신호가 아닌 추천 점수의 일부로 편입.
- 임계값 기반 paper trading 로그를 최소 2~4주 수집.
- 실제 주문 전에는 STOM 실시간 DB 지연, 장중 재학습/재예측 주기, 실패 시 fallback 정책을 정해야 합니다.

## 11. 집중 검토 최종 판정

- **파인튜닝 실행 자체:** 정상 완료.
- **GPU 사용:** 정상.
- **DB 전체 universe 활용:** 호환 가능한 모든 주식 테이블 기반 all-table bounded CSV를 사용한 완료 run 확인.
- **여러 종목 학습:** 정상.
- **종목/세션 경계 누수:** 현재 구조상 방지.
- **정규화 미래 누수:** 현재 `lookback` 설정 기준 방지.
- **checkpoint 사용 가능성:** 가능.
- **실전 예측 신뢰도:** 아직 부족. 특히 방향정확도와 수익성 검증이 부족.

따라서 현재 상태는 **“STOM tick DB로 Kronos를 파인튜닝하는 기술 경로는 성공했고, 모델 산출물도 생성되었으나, 매매 전략으로 채택하려면 검증/점수화/백테스트 단계가 추가로 필요”**로 판단합니다.
