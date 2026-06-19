# STOM 1tick DB로 Kronos 학습 준비

이 문서는 `D:\Chanil_Park\Project\Programming\Kronos\_database\stock_tick_back.db`
같은 STOM SQLite 1tick/1초 데이터를 Kronos 학습 CSV로 변환하고 학습하는 절차입니다.

## 핵심 판단

- 가능합니다. 단, Kronos는 원본 체결/호가 전체를 직접 학습하는 모델이 아니라
  `timestamps, open, high, low, close, volume, amount` 형태의 K-line/OHLCV 시퀀스를 학습합니다.
- STOM DB는 종목별 SQLite 테이블 구조이므로, 변환 후에도 `symbol`, `session` 컬럼을 유지해야 합니다.
- 새 `GroupedKlineDataset`은 `symbol + session` 단위로 윈도우를 만들기 때문에
  여러 종목을 학습해도 한 학습 샘플이 다른 종목/다른 날짜로 넘어가지 않습니다.
- 정규화는 기본값 `normalize_using: lookback`입니다. 예측 구간까지 포함해 평균/표준편차를 계산하는
  기존 단일 CSV 방식보다 실전 예측 누수를 줄입니다.

## 1. DB 분석

```powershell
python finetune_csv/prepare_stom_1tick.py inspect `
  --db _database/stock_tick_back.db `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 20 `
  --json-output finetune_csv/data/stom_1tick_inspect.json
```

- `lookback-window 300`: 최근 5분(1초봉 300개)
- `predict-window 60`: 다음 1분(60개)
- 필요한 최소 행 수는 `300 + 60 + 1 = 361`개입니다.
- 빠른 확인은 `--max-tables 20`, 전체 검사/변환은 `--max-tables 0`을 사용합니다.

## 2. 학습 CSV 생성

```powershell
python finetune_csv/prepare_stom_1tick.py export `
  --db _database/stock_tick_back.db `
  --output finetune_csv/data/stom_1tick_kline.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 100 `
  --price-mode close_only `
  --json-output finetune_csv/data/stom_1tick_export.json
```

생성 CSV 컬럼:

```text
symbol, session, timestamps, open, high, low, close, volume, amount
```

가격 모드:

- `--price-mode close_only`: `현재가/종가`를 `open/high/low/close` 모두에 넣습니다.
- `--price-mode db_ohlc`: DB의 `시가/고가/저가`와 `현재가 또는 종가`를 사용합니다.
  STOM의 `시가/고가/저가`가 “해당 1초봉 OHLC”가 아니라 “당일 누적 시고저”라면 `close_only`가 더 안전합니다.

거래량/거래대금:

- `volume`: `거래량/초당거래량`이 있으면 사용, 없으면 `초당매수수량 + 초당매도수량`
- `amount`: `초당거래대금` 우선, 없으면 `close * volume`

## 3. 학습 실행

기본 템플릿:

```powershell
python finetune_csv/train_sequential.py --config finetune_csv/configs/config_stom_1tick.yaml
```

기본 설정은:

- pretrained tokenizer 유지
- `NeoQuasar/Kronos-small` predictor만 파인튜닝
- `lookback=300`, `predict=60`
- `symbol/session` 그룹 단위 split

RTX 4080 Super 16GB에서는 먼저 `Kronos-small`, `batch_size 16~32`, `basemodel_epochs 1~3`으로
파일/속도/손실 감소를 확인한 뒤 전체 종목으로 늘리는 것을 권장합니다.

## 4. 추천 실험 순서

1. `--max-tables 20`으로 CSV 생성
2. `basemodel_epochs: 1`, `max_samples: 50000`으로 smoke test
3. 손실이 정상적으로 감소하면 `--max-tables 100~300`
4. 최종적으로 `--max-tables 0` 전체 종목/일자 학습
5. 별도 검증 스크립트에서 예측 등락률, 분위수 점수, 기존 조건식을 결합해 종목 점수화

## 주의

- `_database` 원본 DB는 읽기 전용으로만 사용합니다.
- DB가 매일 거래대금 100위 중심이라 종목 구성이 바뀌어도 문제 없습니다.
  모델은 “특정 종목 전용”이 아니라 여러 종목/날짜 패턴을 함께 학습합니다.
- 다만 종목별 고유 특성까지 강하게 반영하려면 추후 `symbol embedding` 같은 구조 변경이 필요합니다.
  현재 구현은 Kronos 입력 형식에 맞춰 가격/거래량 시퀀스와 시간 특징을 학습합니다.
