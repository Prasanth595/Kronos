# STOM Tick DB 기반 Kronos 기본 OHLCV 파인튜닝 연구 문서

작성일: 2026-05-06  
대상 DB: `D:\Chanil_Park\Project\Programming\Kronos\_database\stock_tick_back.db`  
범위: **Kronos 기본 OHLCV 입력만 사용**. STOM의 체결강도, 호가, 잔량, VI 등 확장 컬럼 학습은 이번 문서의 직접 범위가 아니다.

---

## 1. 결론 요약

### 1.1 학습 가능한가?

가능하다.

단, “STOM tick DB를 Kronos에 그대로 직접 넣는다”는 의미는 아니다. Kronos 기본 fine-tuning 코드는 기본적으로 다음 형태의 K-line/OHLCV 시퀀스를 기대한다.

```text
timestamps, open, high, low, close, volume, amount
```

따라서 STOM tick DB의 각 종목 테이블에서 Kronos가 이해할 수 있는 OHLCV만 추출해 **종목/날짜 경계를 유지한 grouped 학습 데이터**로 변환한 뒤 파인튜닝하는 방식이 현실적이다.

### 1.2 모든 주식 테이블을 사용할 수 있는가?

대체로 가능하다.

실제 DB 전체를 읽기 전용으로 검사한 결과는 다음과 같다.

| 항목 | 결과 |
|---|---:|
| 전체 테이블 수 | 2,427 |
| Kronos OHLCV 변환 호환 테이블 | 2,425 |
| 비호환 테이블 | `moneytop`, `stockinfo` |
| 고유 주식 테이블 schema 수 | 1 |
| 전체 주식 rows | 122,522,300 |
| 전체 symbol/session 그룹 수 | 73,968 |
| `lookback=300`, `predict=60` 기준 학습 가능 그룹 | 73,650 |
| 예상 학습 window 수 | 95,946,764 |

즉, `moneytop`, `stockinfo`는 종목 tick 테이블이 아니라 metadata 성격이라 제외하고, 나머지 2,425개 주식 테이블은 같은 스키마로 OHLCV 변환이 가능하다.

### 1.3 파인튜닝은 직접 가능한가?

가능하다. 다만 권장 경로는 다음이다.

```text
STOM SQLite DB
→ read-only inspect
→ OHLCV grouped CSV/Parquet cache 생성
→ Kronos grouped dataset
→ tokenizer는 보통 pretrained 유지
→ predictor/base model fine-tuning
→ holdout 예측 검증
→ 웹 대시보드에서 실제값 vs 예측값 시각화
```

현재 구현 기준으로는 `finetune_csv/prepare_stom_1tick.py`가 DB를 읽어 학습용 CSV를 만들고, `GroupedKlineDataset`이 `symbol + session` 단위로 window를 생성한다.

---

## 2. STOM Tick DB 구조 이해

### 2.1 테이블 구조

DB는 SQLite이며 각 종목 코드가 하나의 테이블이다.

예:

```text
000020
000040
000050
000060
...
066970
...
```

두 개의 비주식/metadata 테이블도 존재한다.

```text
moneytop
stockinfo
```

이 두 테이블은 `현재가` 같은 가격 컬럼이 없어 Kronos OHLCV 학습 대상에서 제외한다.

### 2.2 주식 테이블의 핵심 컬럼

주식 테이블에는 약 54개 컬럼이 존재한다. 그중 Kronos 기본 OHLCV 학습에 필요한 최소 컬럼은 다음이다.

| Kronos 입력 | STOM 컬럼 | 설명 |
|---|---|---|
| `timestamps` | `index` | `YYYYMMDDHHMMSS` 형태의 tick/초 단위 시각 |
| `close` | `현재가` | 현재 체결/마지막 가격. DB에는 `종가` 컬럼이 없음 |
| `open` | `현재가` 또는 `시가` | 기본 권장값은 `현재가` |
| `high` | `현재가` 또는 `고가` | 기본 권장값은 `현재가` |
| `low` | `현재가` 또는 `저가` | 기본 권장값은 `현재가` |
| `volume` | `초당매수수량 + 초당매도수량` | 1초 단위 거래량 proxy |
| `amount` | `초당거래대금` | 1초 단위 거래대금 |

주의할 점은 STOM의 `시가`, `고가`, `저가`가 “해당 1초봉 자체의 open/high/low”인지, 아니면 “당일 누적 시가/고가/저가”인지 확인이 필요하다는 점이다. 실제 샘플상 누적 일중 값일 가능성이 있으므로, Kronos 기본 OHLCV 학습에서는 `--price-mode close_only`가 더 안전하다.

`close_only` 모드는 다음처럼 매핑한다.

```text
open  = 현재가
high  = 현재가
low   = 현재가
close = 현재가
```

이 방식은 진짜 1초봉 OHLC 폭은 잃지만, “가격 시퀀스 + 거래량/거래대금”을 누수 없이 안정적으로 학습하기 좋다.

---

## 3. 왜 단순 CSV 합치기는 안 되는가?

여러 종목을 단순히 하나의 CSV로 이어붙이면 안 된다.

잘못된 예:

```text
000020 마지막 tick
000040 첫 tick
```

이런 식으로 연결되면 학습 window가 종목 경계를 넘어가며, 모델은 존재하지 않는 가격 연속성을 학습한다.

올바른 방식은 다음처럼 `symbol`, `session` 경계를 유지하는 것이다.

```text
symbol, session, timestamps, open, high, low, close, volume, amount
000020, 20221212, 2022-12-12 09:00:05, ...
000020, 20221212, 2022-12-12 09:00:06, ...
000040, 20230906, 2023-09-06 09:02:25, ...
```

그리고 Dataset은 반드시 다음 단위 안에서만 window를 만든다.

```text
symbol + session
```

현재 구현된 `GroupedKlineDataset`은 이 경계를 지킨다. 따라서 여러 종목을 하나의 파일로 담더라도 “단순 연결 CSV”가 아니라 “grouped CSV”로 동작한다.

---

## 4. 전체 테이블 기준 학습 가능성 판단

### 4.1 검사 조건

검사 조건:

```text
lookback_window = 300
predict_window  = 60
필요 최소 rows  = 300 + 60 + 1 = 361
price_mode      = close_only
```

즉, 한 종목의 하루 session에 최소 361개 row가 있어야 하나의 학습 window가 만들어진다.

### 4.2 전체 검사 결과

읽기 전용 검사 결과:

```text
전체 테이블: 2,427
호환 주식 테이블: 2,425
비호환 테이블: 2
전체 주식 rows: 122,522,300
전체 symbol/session 그룹: 73,968
학습 가능 그룹: 73,650
예상 학습 window: 95,946,764
```

비호환 테이블:

```text
moneytop
stockinfo
```

두 테이블은 가격 시계열 테이블이 아니므로 학습 대상에서 제외하는 것이 맞다.

### 4.3 “모든 주식 테이블 사용”의 정확한 의미

이 문서에서 “모든 주식 테이블 사용”은 다음을 의미한다.

```text
전체 2,427개 테이블
→ metadata 2개 제외
→ 주식 tick 테이블 2,425개 사용
→ 단, session rows가 window보다 짧은 날짜 그룹은 자동 제외
```

따라서 2,425개 주식 테이블을 대상으로 export를 걸 수 있고, 실제 학습 sample은 window 생성이 가능한 symbol/session에서 만들어진다.

---

## 5. 실제 준비/학습 절차

### 5.1 1단계: 전체 DB 검사

```powershell
python finetune_csv/prepare_stom_1tick.py inspect `
  --db _database/stock_tick_back.db `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 0 `
  --price-mode close_only `
  --json-output finetune_csv/data/stom_1tick_all_inspect.json
```

설명:

- `--max-tables 0`: 전체 테이블 검사
- `--price-mode close_only`: `현재가`를 OHLC 모두에 사용
- 결과 JSON에서 학습 가능 테이블/그룹/경고 확인

### 5.2 2단계: 파일럿 CSV 생성

처음부터 전체 122M rows를 변환하지 말고 일부 테이블로 smoke test를 먼저 한다.

```powershell
python finetune_csv/prepare_stom_1tick.py export `
  --db _database/stock_tick_back.db `
  --output finetune_csv/data/stom_1tick_kline_pilot.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 100 `
  --price-mode close_only `
  --json-output finetune_csv/data/stom_1tick_export_pilot.json
```

### 5.3 3단계: 전체 주식 테이블 CSV 생성

파일럿이 정상이라면 전체 주식 테이블을 대상으로 export한다.

```powershell
python finetune_csv/prepare_stom_1tick.py export `
  --db _database/stock_tick_back.db `
  --output finetune_csv/data/stom_1tick_kline_all.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 0 `
  --price-mode close_only `
  --json-output finetune_csv/data/stom_1tick_export_all.json
```

주의:

- 전체 rows가 `122,522,300`개 수준이므로 CSV 파일이 매우 커질 수 있다.
- 운영 단계에서는 CSV보다 Parquet/Arrow cache가 더 적합하다.
- 현재 구현은 CSV 중심이므로, 첫 실험은 `--max-tables 100~300`으로 시작하는 것을 권장한다.

### 5.4 4단계: config 설정

기본 템플릿:

```text
finetune_csv/configs/config_stom_1tick.yaml
```

핵심 설정:

```yaml
data:
  data_path: "finetune_csv/data/stom_1tick_kline_all.csv"
  dataset_type: "stom_tick"
  group_columns: ["symbol", "session"]
  lookback_window: 300
  predict_window: 60
  normalize_using: "lookback"
  sample_stride: 1
  max_samples: null

experiment:
  train_tokenizer: false
  train_basemodel: true
  pre_trained_tokenizer: true
  pre_trained_predictor: true
```

중요:

- `normalize_using: "lookback"`은 미래 예측 구간을 정규화 통계에 포함하지 않기 위해 필요하다.
- `sample_stride`를 2, 5, 10으로 키우면 학습 샘플 수와 시간이 줄어든다.
- `max_samples`를 지정하면 파일럿 학습이 쉬워진다.

예:

```yaml
sample_stride: 5
max_samples: 1000000
```

### 5.5 5단계: 학습 실행

```powershell
python finetune_csv/train_sequential.py --config finetune_csv/configs/config_stom_1tick.yaml
```

RTX 4080 Super 16GB 기준 권장 시작값:

```yaml
training:
  basemodel_epochs: 1
  batch_size: 16
  num_workers: 4

data:
  max_samples: 200000
  sample_stride: 5
```

처음에는 다음만 확인하면 된다.

1. DataLoader가 정상 생성되는가?
2. GPU 메모리가 터지지 않는가?
3. train loss / validation loss가 계산되는가?
4. 저장 경로에 best model이 생성되는가?

그 후 점진적으로:

```text
max_samples 20만
→ 100만
→ 500만
→ 전체 또는 stride 기반 전체
```

순서로 확대하는 것이 안전하다.

---

## 6. 파인튜닝 모델 사용 방법

### 6.1 입력 window

`lookback_window=300`, `predict_window=60`이면 모델 사용 시점마다 최근 300초를 입력으로 넣고, 다음 60초 구간을 예측한다.

입력 예:

```text
09:05:00 ~ 09:09:59 실제 OHLCV
→ 09:10:00 ~ 09:10:59 예측
```

### 6.2 예측값을 점수화하는 방법

Kronos 예측 sequence에서 가장 단순한 점수는 예상 등락률이다.

```text
현재가 = 입력 마지막 close
예측가 = 예측 horizon 마지막 close
예상등락률 = (예측가 / 현재가 - 1) * 100
```

추가로 다음을 계산할 수 있다.

| 지표 | 설명 |
|---|---|
| `pred_return_60s` | 60초 후 예상 등락률 |
| `pred_max_return_60s` | 예측 60초 안의 최고 예상 수익률 |
| `pred_min_return_60s` | 예측 60초 안의 최저 예상 수익률 |
| `pred_volatility_60s` | 예측 경로 변동성 |
| `confidence_proxy` | 예측 경로의 방향 일관성 또는 변동 대비 기대수익 |

예:

```text
score = pred_return_60s / max(pred_volatility_60s, epsilon)
```

다만 이것은 모델 확률이 아니라 예측 경로 기반 proxy 점수다. 실전 조건식과 결합하려면 별도 검증이 필요하다.

---

## 7. 학습 후 실제값 vs 예측값 검증

### 7.1 Offline validation

가장 먼저 해야 할 것은 과거 holdout 데이터에서 예측값과 실제값을 비교하는 것이다.

절차:

```text
1. validation symbol/session 선택
2. 각 시점 t에서 최근 lookback_window 입력
3. 모델로 t+predict_window까지 예측
4. 실제 t+predict_window 가격과 비교
5. 예측 row를 저장
6. MAE/RMSE/방향정확도/수익률 hit ratio 계산
```

추천 저장 schema:

```text
prediction_id
model_version
symbol
session
asof_timestamp
horizon_seconds
actual_close_t0
pred_close_t_horizon
actual_close_t_horizon
pred_return
actual_return
error
abs_error
direction_hit
created_at
```

### 7.2 주요 검증 지표

| 지표 | 의미 |
|---|---|
| MAE | 예측 가격 평균 절대 오차 |
| RMSE | 큰 오차에 더 민감한 가격 오차 |
| MAPE | 가격 대비 오차율 |
| Directional Accuracy | 상승/하락 방향 적중률 |
| Top-K Hit Ratio | 예측 점수 상위 종목의 실제 상승 비율 |
| Return IC | 예측 등락률과 실제 등락률의 상관 |

단순 가격 예측 MAE보다 실제 매매에는 다음이 더 중요하다.

```text
예측 등락률 순위가 실제 등락률 순위와 관련이 있는가?
상위 점수 종목이 평균적으로 유리한가?
예측값이 기존 STOM 조건식과 결합될 때 성능이 개선되는가?
```

---

## 8. 웹 대시보드 설계

### 8.1 목적

웹 대시보드는 “모델이 맞았는지”를 눈으로 검증하기 위한 도구다.

핵심 질문:

```text
특정 종목/특정 시각에서
모델이 예측한 1분 뒤 가격 경로가
실제 1분 뒤 움직임과 얼마나 비슷했는가?
```

### 8.2 권장 화면 구성

#### 화면 1: 모델/데이터 개요

표시 항목:

- model path
- tokenizer path
- 학습 데이터 기간
- 사용 종목 수
- validation session 수
- lookback/predict window
- MAE/RMSE/방향정확도

#### 화면 2: 종목별 실제값 vs 예측값 차트

필터:

- `symbol`
- `session`
- `asof_timestamp`
- horizon: 30초/60초/180초 등

차트:

```text
실제 close line
예측 close line
입력 lookback 구간
예측 horizon 구간
```

시각적 표현:

- 입력 구간: 회색 배경
- 예측 구간: 파란색 배경
- 실제값: 검정 선
- 예측값: 빨간 선
- asof 시점: 세로선

#### 화면 3: 오차 분석

차트:

- 시간대별 error
- symbol별 평균 error
- 예측 등락률 bin별 실제 평균 수익률
- predicted return vs actual return scatter

#### 화면 4: Top-K 후보 검증

예:

```text
09:10:00 기준 예측 점수 상위 20개
→ 60초 후 실제 상승률
→ hit/miss 표시
```

테이블 컬럼:

```text
rank
symbol
asof_timestamp
pred_return
actual_return
direction_hit
score
```

#### 화면 5: 실시간 모니터링

실시간 모드에서는 다음 흐름이 필요하다.

```text
STOM 실시간 tick 수신
→ 최근 300초 OHLCV buffer 구성
→ Kronos 예측
→ prediction DB 저장
→ 대시보드 갱신
→ 60초 후 실제값 도착 시 정답 채움
```

이때 처음에는 1초마다 모든 종목을 예측하지 말고, 후보 종목만 예측하는 것이 현실적이다.

예:

```text
거래대금 상위 100개
조건식 통과 종목
관심종목
```

### 8.3 대시보드 기술 선택

#### Option A: Streamlit

장점:

- 빠르게 만들 수 있음
- 연구/검증용에 적합
- Plotly 차트 연동 쉬움

단점:

- 실시간 고빈도 운영 UI로는 한계

#### Option B: FastAPI + React/Plotly

장점:

- 운영형 대시보드에 적합
- 실시간 WebSocket 구성 가능
- 기존 프로그램과 API 연결 쉬움

단점:

- 구현량 증가

#### Option C: 기존 `webui/` 확장

장점:

- Kronos repo 내부 구조 활용

단점:

- 현재 webui가 STOM DB/학습 결과 검증용으로 바로 맞춰져 있는지 추가 분석 필요

권장:

```text
1차: Streamlit으로 빠르게 검증용 대시보드
2차: 검증 지표가 의미 있으면 FastAPI + React로 운영형 전환
```

---

## 9. 실제 운영 파이프라인 제안

### 9.1 연구 단계

```text
1. 전체 DB inspect
2. 100개 테이블 export
3. max_samples 20만으로 학습 smoke
4. validation 예측값 저장
5. Streamlit 대시보드로 실제값/예측값 확인
```

### 9.2 파일럿 단계

```text
1. 300~500개 테이블 export
2. sample_stride 5 또는 10
3. 1~3 epochs 학습
4. Top-K 예측 점수 검증
5. 기존 조건식과 결합 검증
```

### 9.3 전체 학습 단계

```text
1. 전체 2,425개 주식 테이블 export
2. Parquet cache 또는 shard CSV 구성
3. symbol/session 단위 train/validation split
4. GPU fine-tuning
5. dashboard 기반 holdout 검증
```

---

## 10. 현재 한계와 주의점

### 10.1 모든 STOM 컬럼을 쓰는 것이 아니다

이번 방식은 Kronos 기본 OHLCV만 사용한다.

사용하지 않는 예:

- 체결강도
- 등락율
- 거래대금증감
- 회전율
- 시가총액
- 호가/잔량
- VI 정보
- 관심종목

이 컬럼들을 쓰려면 Kronos tokenizer 입력 차원을 바꾸거나, 별도 조건식/점수화 모델과 결합해야 한다.

### 10.2 `시가/고가/저가` 해석 문제

현재 안전한 기본값은 `close_only`다.

만약 STOM DB의 `시가/고가/저가`가 진짜 1초봉 OHLC로 확정되면 다음 모드를 사용할 수 있다.

```powershell
--price-mode db_ohlc
```

하지만 누적 일중 시고저라면 모델 입력에 왜곡이 생길 수 있다.

### 10.3 전체 학습 규모가 크다

예상 window 수가 `95,946,764`개다.

처음부터 전체 학습을 시도하면:

- CSV 파일 크기 증가
- DataLoader 시간 증가
- 학습 시간 증가
- validation 반복 시간 증가

문제가 발생할 수 있다.

따라서 반드시 pilot → staged scale-up 순서가 필요하다.

### 10.4 현재 환경의 GPU 확인 필요

이전 환경 확인에서는 Python의 torch가 CPU build로 보였다.

```text
torch 2.9.0+cpu
cuda_available=False
```

RTX 4080 Super를 실제로 쓰려면 CUDA 지원 PyTorch 설치가 필요하다.

---

## 11. 권장 다음 작업

### 11.1 바로 실행 가능한 다음 단계

1. 전체 export 전 pilot export:

```powershell
python finetune_csv/prepare_stom_1tick.py export `
  --db _database/stock_tick_back.db `
  --output finetune_csv/data/stom_1tick_kline_pilot.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 100 `
  --price-mode close_only
```

2. config의 `data_path`를 pilot CSV로 변경
3. `max_samples: 200000`, `sample_stride: 5`로 smoke training
4. validation 예측 저장 스크립트 작성
5. Streamlit dashboard 작성

### 11.2 이후 구현하면 좋은 기능

- Parquet export 지원
- export resume/checkpoint
- validation prediction writer
- Streamlit dashboard
- 실시간 prediction log DB
- 조건식 + Kronos score 결합 리포트

---

## 12. 최종 판단

Kronos 기본 OHLCV만 사용한다는 조건에서는 STOM tick DB 기반 파인튜닝은 가능하다.

정확한 표현은 다음과 같다.

```text
STOM DB의 모든 주식 테이블을 읽어
index/현재가/초당매수수량/초당매도수량/초당거래대금 기반 OHLCV로 변환하고,
symbol + session 경계를 유지한 grouped dataset으로 Kronos predictor를 파인튜닝할 수 있다.
```

다만:

```text
원본 SQLite DB를 Kronos에 그대로 직접 넣는 방식은 아니다.
모든 STOM 컬럼을 사용하는 것도 아니다.
metadata 테이블 moneytop/stockinfo는 제외한다.
session 길이가 부족한 그룹은 window 생성에서 제외된다.
```

따라서 현재 가장 현실적인 진행 방향은:

```text
close_only OHLCV 변환
→ grouped CSV/Parquet cache
→ pretrained tokenizer 유지
→ Kronos-small/base predictor fine-tuning
→ holdout 예측 로그 생성
→ 웹 대시보드에서 실제값/예측값 비교
```

이다.
