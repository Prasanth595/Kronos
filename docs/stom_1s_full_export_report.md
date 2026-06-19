# STOM 1초봉 전체 QlibDataset export 검증 보고서

작성일: 2026-05-08

## 1. 결론

STOM `stock_tick_back.db`의 전체 SQLite table을 대상으로 `09:00:00~09:30:00` 구간을 1초 grid로 정규화한 뒤, Kronos `QlibDataset`이 직접 읽을 수 있는 `processed_datasets/*.pkl` 산출물을 30초/60초 horizon별로 생성했다.

핵심 판단:

- **실제 stock table 2,425개는 export 성공**했다.
- SQLite 전체 table 2,427개 중 `moneytop`, `stockinfo` 2개는 OHLCV stock table이 아니어서 `close/current price` column 부재로 제외되었다.
- 각 horizon별로 **73,900개 instrument/session group**, **131,470,857 row**가 생성되었다.
- `--split-by session` 결과 train/val/test 사이의 거래일 중복은 없다.
- 이 단계는 **학습 완료가 아니라 학습용 전체 데이터셋 구축 완료**이다. 다음 단계는 이 pickle을 사용한 30초/60초 Kronos 파인튜닝과 baseline 비교이다.

## 2. 실행 명령

### 2.1 30초 horizon

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1s_grid_pred30_full `
  --max-tables 0 `
  --lookback-window 300 `
  --horizon-seconds 30 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 093000 `
  --freq 1s `
  --regularize-1s `
  --split-by session `
  --train-ratio 0.70 `
  --val-ratio 0.15 `
  --test-ratio 0.15
```

### 2.2 60초 horizon

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1s_grid_pred60_full `
  --max-tables 0 `
  --lookback-window 300 `
  --horizon-seconds 60 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 093000 `
  --freq 1s `
  --regularize-1s `
  --split-by session `
  --train-ratio 0.70 `
  --val-ratio 0.15 `
  --test-ratio 0.15
```

## 3. manifest 요약

| 구분 | 30초 horizon | 60초 horizon |
| --- | ---: | ---: |
| effective predict window | 30 | 60 |
| lookback window | 300 | 300 |
| 성공 stock table | 2,425 | 2,425 |
| 제외 table | 2 | 2 |
| export group | 73,900 | 73,900 |
| export row | 131,470,857 | 131,470,857 |
| qlib CSV 파일 | 73,900 | 73,900 |
| 1초 grid 보정 group | 73,900 | 73,900 |
| 1초 grid 삽입 row | 9,063,493 | 9,063,493 |

30초/60초 산출물의 row 수가 같은 이유는 `horizon_seconds`가 데이터 row를 줄이는 옵션이 아니라 **Kronos 학습 target window 길이를 고정하는 metadata/loader 기준**이기 때문이다. 같은 09:00~09:30 원천 구간을 쓰되, 이후 학습에서 `KRONOS_PREDICT_WINDOW=30` 또는 `60`으로 다르게 사용한다.

## 4. train/val/test split 검증

### 4.1 30초 horizon

| split | groups | rows | sessions | pickle |
| --- | ---: | ---: | ---: | ---: |
| train | 51,944 | 92,418,715 | 665 | 4.84 GiB |
| val | 11,240 | 19,984,507 | 143 | 1.05 GiB |
| test | 10,716 | 19,067,635 | 143 | 1.00 GiB |

- session overlap: train/val=0, train/test=0, val/test=0

### 4.2 60초 horizon

| split | groups | rows | sessions | pickle |
| --- | ---: | ---: | ---: | ---: |
| train | 51,944 | 92,418,715 | 665 | 4.84 GiB |
| val | 11,240 | 19,984,507 | 143 | 1.05 GiB |
| test | 10,716 | 19,067,635 | 143 | 1.00 GiB |

- session overlap: train/val=0, train/test=0, val/test=0

## 5. column 해석

현재 STOM tick table은 일반적인 일봉 OHLC column이 아니라 tick/current price 중심 구조이므로, 이번 1초봉 export는 다음 원칙을 사용했다.

- `--price-mode close_only`: `현재가`를 open/high/low/close로 사용한다. 1초 단위로 이미 매우 짧은 구간이므로 tick 가격 기반 close-only OHLC로 고정했다.
- 거래량 column이 직접 없으면 `초당매수수량 + 초당매도수량`을 `volume`으로 사용한다.
- 거래대금은 `초당거래대금`이 있으면 사용하고, 없으면 `close * volume`으로 대체한다.
- 1초 grid에서 빠진 초는 가격을 직전 값으로 forward-fill하고, volume/amount는 0으로 채운다.

## 6. 제외 table

### 6.1 30초 horizon

- `moneytop`: Missing required STOM columns: close/current price
- `stockinfo`: Missing required STOM columns: close/current price

### 6.2 60초 horizon

- `moneytop`: Missing required STOM columns: close/current price
- `stockinfo`: Missing required STOM columns: close/current price

해석: 위 2개는 stock tick OHLCV table이 아니라 metadata/ranking 계열 table이므로, 전체 stock table 학습 데이터 구축 실패로 보지 않는다.

## 7. 다음 단계

1. `processed_datasets`를 `KRONOS_DATASET_PATH`로 지정하여 30초/60초 모델을 각각 파인튜닝한다.
2. 기존 `direction_accuracy=0.40` 모델, persistence baseline, 단순 상승/하락 랜덤 baseline과 동일 holdout에서 비교한다.
3. 학습 후 prediction CSV를 생성하고, 웹 대시보드에서 실제값/예측값·direction hit·Top-K 성과를 시각화한다.
4. 30초/60초 중 실전 적용 가능성이 높은 horizon을 선택해 STOM ?? ?? 연동 설계를 진행한다.
