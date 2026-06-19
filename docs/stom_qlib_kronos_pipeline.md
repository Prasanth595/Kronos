# STOM Qlib Kronos 파이프라인 개발/사용 문서

작성일: 2026-05-07

## 1. 목적

기존 STOM 파인튜닝은 `finetune_csv`의 grouped CSV 경로로 진행되었다. 이 문서는 STOM `stock_tick_back.db`를 Qlib 연구 흐름에 연결하기 위한 새 pilot-first 파이프라인을 설명한다.

목표 흐름:

```text
STOM SQLite DB
→ Qlib dump-ready CSV
→ Kronos QlibDataset pickle split
→ Kronos predictor fine-tuning
→ Kronos prediction CSV
→ Qlib-style Top-K score backtest
→ 웹 대시보드 시각화
```

참고:

- Qlib 공식 문서는 CSV를 Qlib `.bin` format으로 변환할 때 `scripts/dump_bin.py dump_all`을 사용하며, `date_field_name`, `symbol_field_name`, `include_fields`를 지정할 수 있다고 설명한다.
- Qlib의 기본 목적은 데이터 계층, feature retrieval, dataset, backtest/risk analysis를 표준화하는 것이다.
- 현재 구현은 pyqlib을 강제 dependency로 추가하지 않고, Qlib dump-ready CSV와 Kronos `QlibDataset` pickle split을 먼저 생성한다. pyqlib 설치 후에는 생성된 command로 `.bin` 변환을 이어갈 수 있다.

## 2. 새로 추가된 구성

| 파일 | 역할 |
| --- | --- |
| `finetune/qlib_stom_pipeline.py` | STOM→Qlib export, Qlib-style Top-K score backtest CLI |
| `tests/test_stom_qlib_pipeline.py` | synthetic STOM DB export/backtest 검증 |
| `webui/stom_dashboard.py` | Qlib backtest artifact list/load/chart helper |
| `webui/app.py` | `/api/stom/qlib-backtests` API |
| `webui/templates/stom_dashboard.html` | Qlib Top-K equity curve와 metrics 표시 |
| `.gitignore` | 대용량 Qlib export/backtest 산출물 제외 |

## 3. STOM DB → Qlib pilot export

### 3.1 1초 pilot

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1s_pilot `
  --max-tables 50 `
  --lookback-window 300 `
  --predict-window 60 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 093000 `
  --freq 1s `
  --max-groups 500 `
  --train-ratio 0.70 `
  --val-ratio 0.15 `
  --test-ratio 0.15
```

### 3.1.1 1초 grid + 실제 초 단위 horizon

30초 후/60초 후 예측은 단순히 `30 row 후`, `60 row 후`가 아니라 실제 시간 기준이어야 한다. STOM tick row가 중간에 비어 있을 수 있으므로 1초봉 전체 파인튜닝용 export는 다음 옵션을 사용한다.

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

핵심 옵션:

- `--regularize-1s`: 누락된 초를 1초 grid로 보정한다. 가격은 직전가 forward-fill, 거래량/거래대금은 0으로 채운다.
- `--horizon-seconds`: 1초 grid 기준 실제 N초 후 target을 명시한다.
- `--split-by session`: 같은 거래일이 train/val/test에 섞이지 않도록 날짜/session 기준으로 분리한다.

### 3.2 1분 pilot

1분봉은 Qlib daily/minute 연구 흐름에 더 자연스럽다. 단, `lookback + predict + 1` row를 만족해야 하므로 window를 1분 단위에 맞게 줄여야 한다.

```powershell
python finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1min_pilot `
  --max-tables 50 `
  --lookback-window 20 `
  --predict-window 5 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 093000 `
  --freq 1min `
  --max-groups 500
```

## 4. Export 산출물

예: `finetune\qlib_exports\stom_1s_pilot`

```text
qlib_csv/
  KR000001_20260102.csv
  ...
processed_datasets/
  train_data.pkl
  val_data.pkl
  test_data.pkl
meta/
  calendar_1s.txt
  instruments_all.txt
  qlib_dump_bin_command.txt
stom_qlib_export_report.json
```

### 4.1 Qlib dump-ready CSV

각 CSV는 다음 컬럼을 가진다.

```text
symbol,date,open,high,low,close,volume,amount,money,factor
```

이 구조는 Qlib `dump_bin.py`에 연결하기 위한 전단계다.

### 4.2 Kronos QlibDataset pickle

`finetune/dataset.py`의 `QlibDataset`은 다음 pickle을 읽는다.

```text
train_data.pkl
val_data.pkl
test_data.pkl
```

각 pickle은 다음 형태다.

```python
{
    "KR000001_20260102": DataFrame(
        index=datetime,
        columns=["open", "high", "low", "close", "vol", "amt"]
    )
}
```

주의: key를 `symbol + session`으로 만든 이유는 기존 `QlibDataset`이 symbol 단위로 연속 window를 만들기 때문이다. session을 분리하지 않으면 하루 끝 window가 다음날로 넘어가는 누수가 생길 수 있다.

## 5. pyqlib `.bin` 변환

export 후 다음 파일에 command가 저장된다.

```text
meta\qlib_dump_bin_command.txt
```

현재 Qlib upstream `scripts/dump_bin.py` 기준 인자는 `--csv_path`가 아니라 `--data_path`이다. 예:

```powershell
python scripts/dump_bin.py dump_all `
  --data_path finetune/qlib_exports/stom_1min_pilot/qlib_csv `
  --qlib_dir finetune/qlib_exports/stom_1min_pilot/qlib_bin `
  --date_field_name date `
  --symbol_field_name symbol `
  --include_fields open,high,low,close,volume,amount,money,factor `
  --freq 1min
```

pyqlib은 repo 필수 dependency가 아니라 실행 환경 dependency이다. 현재 워크스테이션에서는 `python -m pip install pyqlib`로 `pyqlib 0.9.7` 설치를 완료했고, pip 패키지에는 `dump_bin.py`가 포함되지 않아 Microsoft Qlib source를 `.omx/external/qlib`에 clone하여 `scripts/dump_bin.py`를 사용했다. `.omx`는 실행 보조 산출물이며 commit 대상이 아니다.

### 5.1 Qlib 환경 점검

먼저 현재 Python 환경에 pyqlib과 `dump_bin.py`가 준비되어 있는지 확인한다.

```powershell
python finetune\qlib_stom_pipeline.py qlib-env-check
```

현재 워크스테이션 점검 결과:

```json
{
  "qlib_installed": true,
  "qlib_version": "0.9.7",
  "dump_bin_script_found": true,
  "dump_bin_script": "D:\\Chanil_Park\\Project\\Programming\\Kronos\\.omx\\external\\qlib\\scripts\\dump_bin.py"
}
```

### 5.2 dump_bin 실행

export report에서 Qlib 변환 command를 재생성한다. `--execute`를 빼면 dry-run만 수행한다.

```powershell
python finetune\qlib_stom_pipeline.py dump-bin `
  --export-report finetune\qlib_exports\stom_1min_pilot\stom_qlib_export_report.json `
  --qlib-dir finetune\qlib_exports\stom_1min_pilot\qlib_bin `
  --dump-bin-script .omx\external\qlib\scripts\dump_bin.py `
  --freq 1min `
  --execute
```

2026-05-07 파일럿 검증 결과:

| 구분 | 결과 |
| --- | --- |
| 1초봉 export | 성공: 4개 instrument/session, 4,792 rows |
| 1초봉 dump_bin | 성공: `--freq 1s` bin 생성 |
| 1초봉 pyqlib provider smoke | 실패/제약 확인: pyqlib `D.calendar(freq="1s")`는 초봉 freq를 지원하지 않음 |
| 1분봉 export | 성공: 4개 instrument/session, 112 rows |
| 1분봉 dump_bin | 성공: `--freq 1min` bin 생성 |
| 1분봉 pyqlib provider smoke | 성공: calendar 112개 로드 |

따라서 **Qlib provider/전략 연구는 1분봉 이상을 우선 사용**하고, **1초봉은 Kronos fine-tuning용 `processed_datasets/*.pkl` 경로를 우선 사용**한다.

### 5.3 Qlib provider smoke test

`.bin` 변환이 완료되면 provider를 초기화하고 calendar를 읽어본다.

```powershell
python finetune\qlib_stom_pipeline.py provider-smoke `
  --provider-uri finetune\qlib_exports\stom_1min_pilot\qlib_bin `
  --region cn `
  --freq 1min
```

성공 예:

```json
{
  "mode": "qlib_provider_smoke",
  "freq": "1min",
  "calendar_count": 112,
  "calendar_sample": [
    "2022-12-12 09:00:00",
    "2022-12-12 09:01:00"
  ]
}
```

주의: `dump_bin.py`는 `--freq 1s` 변환 자체는 수행하지만, pyqlib provider의 `Freq` parser는 `1s`를 공식 지원하지 않는다. `provider-smoke --freq 1s`는 의도적으로 명확한 오류를 반환하게 했다.

## 6. Kronos predictor 학습 연결

export된 pickle을 기존 `finetune/dataset.py`가 읽게 하려면 환경변수를 지정한다.

```powershell
$env:KRONOS_DATASET_PATH="D:\Chanil_Park\Project\Programming\Kronos\finetune\qlib_exports\stom_1s_pilot\processed_datasets"
$env:KRONOS_LOOKBACK_WINDOW="300"
$env:KRONOS_PREDICT_WINDOW="60"
$env:KRONOS_EPOCHS="1"
$env:KRONOS_BATCH_SIZE="8"
$env:KRONOS_N_TRAIN_ITER="2000"
$env:KRONOS_N_VAL_ITER="400"
$env:KRONOS_USE_COMET="0"
$env:KRONOS_PRETRAINED_TOKENIZER_PATH="NeoQuasar/Kronos-Tokenizer-base"
$env:KRONOS_PRETRAINED_PREDICTOR_PATH="NeoQuasar/Kronos-small"
```

그 다음 기존 Qlib predictor fine-tune entry를 사용한다.

```powershell
python finetune\train_predictor.py
```

주의:

- 이 script는 DDP/CUDA 전제를 포함한다.
- 실전 장시간 학습 전에는 작은 pilot pickle로 loader smoke test를 먼저 수행한다.
- 현재 `finetune_csv/train_sequential.py` 경로가 이미 검증되어 있으므로, Qlib 경로는 pilot부터 단계적으로 확대한다.

## 7. Kronos prediction CSV → Qlib-style Top-K backtest

기존 예측 CSV를 score로 사용한다.

```powershell
python finetune\qlib_stom_pipeline.py score-backtest `
  --prediction-csv webui\stom_predictions\kronos_all_predictions.csv `
  --output-dir webui\qlib_backtests `
  --top-k 10 `
  --cost-bps 15 `
  --slippage-bps 10
```

산출물:

```text
webui/qlib_backtests/*.json
webui/qlib_backtests/*.curve.csv
webui/qlib_backtests/*.trades.csv
```

실제 실행 예시 결과:

```text
period_count: 300
trade_count: 300
avg_gross_return_pct: 0.0094
avg_net_return_pct: -0.2406
hit_rate: 0.4567
direction_hit_rate: 0.4
cumulative_return_pct: -51.77
max_drawdown_pct: -52.11
```

중요 해석:

- 기존 `kronos_all_predictions.csv`는 각 window의 `asof_timestamp`가 대부분 달라 진짜 cross-sectional Top-K가 아니다.
- 그래서 평균 선택 수가 Top-K보다 작으면 artifact에 warning을 남긴다.
- 진짜 Qlib Top-K를 하려면 같은 `asof_timestamp`에서 여러 종목 score를 생성하는 prediction export가 필요하다.

## 8. 웹 대시보드

실행:

```powershell
python webui\run.py
```

접속:

```text
http://localhost:7070/stom
```

추가된 기능:

- Qlib Top-K backtest artifact 선택
- period/trade/top-k metrics
- gross/net return
- cumulative return / MDD
- hit / direction / Sharpe
- equity curve
- top trades table

API:

```text
GET /api/stom/qlib-backtests
GET /api/stom/qlib-backtests?file=<artifact.json>
```

## 9. 전체 DB로 확대하는 순서

1. `--max-tables 50`, `--max-groups 500` pilot
2. 변환 report 확인
3. `QlibDataset` loader smoke test
4. predictor 1 epoch smoke 학습
5. prediction CSV 생성
6. score-backtest와 dashboard 확인
7. `--max-tables 300`
8. `--max-tables 1000`
9. 제한 해제 또는 날짜 구간별 batch export

## 10. 아직 남은 중요한 과제

1. 동일 asof timestamp의 cross-sectional prediction 생성기
2. Qlib `TopkDropoutStrategy` 직접 연결
3. 1초 데이터는 pyqlib provider 공식 freq 제약 때문에 Kronos pickle 경로와 분리 운영
4. 비용/슬리피지 모델 정교화
5. 최근 날짜 완전 holdout 기준 학습/평가
6. 전체 DB 장시간 export/train의 재개/로그/대시보드 상태 표시

## 11. 최종 판단

이번 구현은 Qlib 적용의 실제 실행 게이트까지 통과했다.

```text
완료: STOM DB → Qlib dump-ready CSV/pickle split → dump_bin 실제 변환 → 1분봉 pyqlib provider smoke → Qlib-style score backtest → dashboard
제약: 1초봉 dump_bin 변환은 가능하지만 pyqlib provider freq는 1s를 지원하지 않아 Kronos pickle 학습 경로를 우선 사용
미완료: Qlib TopkDropoutStrategy 실연동, cross-sectional prediction 생성, 전체 DB 장시간 학습
```

따라서 이제는 “Qlib을 써야 하나?”를 논의하는 단계에서 벗어나, 1분봉 이상 STOM 데이터를 Qlib 연구 체계로 넣어 검증할 수 있는 기반이 생겼다.

## 12. 2026-05-08 1초봉 전체 export 완료

1초봉은 pyqlib provider의 `1s` freq 제약 때문에 `.bin` provider 학습 경로가 아니라 Kronos `QlibDataset` pickle 경로를 우선한다. 이번 단계에서 전체 `stock_tick_back.db`를 대상으로 30초/60초 horizon 학습용 pickle을 생성했다.

- 30초 output: `finetune/qlib_exports/stom_1s_grid_pred30_full/processed_datasets`
- 60초 output: `finetune/qlib_exports/stom_1s_grid_pred60_full/processed_datasets`
- 각 horizon: 73,900 groups, 131,470,857 rows
- 성공 stock table: 2,425
- 제외 table: `moneytop`, `stockinfo` (OHLCV stock table 아님)
- split: session 기준, train/val/test 거래일 overlap 0

따라서 이후 단계는 `dump_bin/provider-smoke`가 아니라 `KRONOS_DATASET_PATH`를 위 `processed_datasets`로 지정한 `finetune/train_predictor.py` 실행이다.

## 13. 2026-05-08 1초봉 budgeted 파인튜닝 완료

`finetune/run_stom_1s_finetune.py` launcher로 pred30/pred60 전체 QlibDataset pickle을 실제 Kronos predictor 학습 루프에 연결했다.

핵심 실행 결과:

- pred30 possible train window: 75,277,195
- pred60 possible train window: 73,718,875
- 각 horizon budgeted run: train 20,000 sample, val 4,000 sample, batch 4, 5,000 train step
- pred30 best val loss: 2.1549
- pred60 best val loss: 2.1302
- checkpoint 저장 완료:
  - `finetune/outputs/stom_1s_grid_pred30_full_budget/finetune_predictor/checkpoints/best_model`
  - `finetune/outputs/stom_1s_grid_pred60_full_budget/finetune_predictor/checkpoints/best_model`

이 결과는 “STOM 1초봉 전체 데이터로 Kronos 파인튜닝 실행이 가능한가?”에 대한 실행 증거다. 단, 아직 “매매 정확도 개선” 증거는 아니므로 다음 단계에서 checkpoint prediction CSV와 holdout actual을 비교해야 한다.

## 14. 2026-05-08 checkpoint 예측 CSV와 baseline 비교

`finetune/evaluate_stom_1s_checkpoint.py`로 budgeted checkpoint의 holdout prediction CSV를 생성했다. CSV는 `webui/stom_predictions`에 저장되며 기존 `/stom` 대시보드에서 실제값/예측값 차트로 확인할 수 있다.

생성된 주요 파일:

- `stom_1s_pred30_budget_holdout_eval_kronos.csv`
- `stom_1s_pred30_budget_holdout_eval_persistence.csv`
- `stom_1s_pred30_budget_holdout_eval_random.csv`
- `stom_1s_pred60_budget_holdout_eval_kronos.csv`
- `stom_1s_pred60_budget_holdout_eval_persistence.csv`
- `stom_1s_pred60_budget_holdout_eval_random.csv`

제한 샘플 평가 결과:

- 30초 Kronos direction accuracy: 0.3704
- 60초 Kronos direction accuracy: 0.4444
- 60초는 0.40을 넘었지만, Qlib-style Top-K net return은 음수다.

따라서 다음 단계는 단순 정확도 확인이 아니라 walk-forward 표본 확대, 필터 조건식 보완, Top-K net return 개선 여부 검증이다.

## 15. 2026-05-08 pred60 walk-forward와 조건식 필터 검증

`finetune/evaluate_stom_1s_checkpoint.py`는 checkpoint 예측 CSV에 예측 시점 feature를 추가로 기록한다. 이 feature는 미래 실제값을 쓰지 않으므로 조건식 또는 종가/단기 추천 점수화에 사용할 수 있다.

추가된 주요 feature:

- `pred_path_consistency`: 예측 경로가 기준가 대비 상승/하락 방향을 얼마나 일관되게 유지했는지
- `pred_range_pct`: 예측 경로의 가격 폭
- `history_volatility_pct`: lookback 구간 변동성
- `history_mean_amount`: lookback 구간 평균 거래대금

조건식 탐색은 `finetune/search_stom_1s_filters.py`로 수행한다.

```powershell
python finetune\search_stom_1s_filters.py `
  --prediction-csv webui\stom_predictions\stom_1s_pred60_walkforward30x3_eval_kronos.csv `
  --output-dir webui\qlib_backtests `
  --top-k 5 `
  --cost-bps 15 `
  --slippage-bps 10 `
  --min-trades 30 `
  --min-periods 30 `
  --min-coverage 0.5
```

현재 best robust 조건은 다음과 같다.

```text
pred_return_window >= 0.05
history_volatility_pct <= 0.2
```

더 좁힌 opportunistic 조건은 다음과 같다.

```text
pred_return_window >= 0.05
pred_range_pct <= 0.1
history_volatility_pct <= 0.2
```

하지만 25bp 비용 가정에서는 opportunistic 조건도 평균 net -0.0089%로 아직 양수 전환하지 못했다. 그러므로 이 조건식은 실전 매수 승인 규칙이 아니라 다음 확대 검증의 후보 규칙으로만 취급한다.

대시보드는 Qlib Top-K JSON과 filter-search JSON을 같은 폴더에서 보게 되므로, `metrics`가 있는 Qlib Top-K artifact만 backtest 목록에 노출하도록 안전 처리했다. filter-search JSON은 현재 문서와 파일 artifact로 확인하며, 다음 단계에서 별도 패널로 승격할 수 있다.

## 16. 2026-05-08 rolling filter validation과 대시보드 패널

조건식 과최적화를 확인하기 위해 `finetune/search_stom_1s_filters.py`에 rolling validation 모드를 추가했다.

```powershell
python finetune\search_stom_1s_filters.py `
  --prediction-csv webui\stom_predictions\stom_1s_pred60_walkforward30x3_eval_kronos.csv `
  --output-dir webui\qlib_backtests `
  --prefix stom_1s_pred60_walkforward30x3_eval_kronos_rolling30x30 `
  --top-k 5 `
  --cost-bps 15 `
  --slippage-bps 10 `
  --min-trades 10 `
  --min-periods 10 `
  --min-coverage 0.25 `
  --rolling-validate `
  --rolling-train-periods 30 `
  --rolling-test-periods 30 `
  --rolling-step-periods 30
```

이번 결과:

- avg train net: +0.0519%
- avg test net: -0.0351%
- avg test baseline net: -0.2438%
- baseline 대비 test 개선폭: +0.2087%p
- weighted test direction hit: 0.4615
- positive test fold rate: 0.5

해석:

```text
조건식은 baseline 대비 손실을 줄이는 효과가 rolling test에서도 유지된다.
그러나 25bp 비용 후 평균 test net이 아직 음수이므로 실전 승인 조건은 아니다.
```

대시보드 추가:

- `GET /api/stom/filter-reports`
- filter-search JSON 목록/상세 표시
- rolling validation JSON 목록/상세 표시
- fold별 train net, test net, baseline net, 개선폭 표시

다음 대형 평가 규모는 `max_sessions 100`, `max_asofs 5`, `max_symbols 50`이며 예상 최대 window는 25,000개, horizon 60초 기준 mode당 row는 1,500,000개다. GPU 추론 시간이 길 수 있어 별도 장시간 실행 단계로 진행한다.

## 17. 2026-05-09 staged full-training launcher

전체 STOM tick dataset은 이미 학습 루프에 연결되어 있지만, 현재 실제 fine-tuning은 20,000 train sample budget으로 수행되었다. 전량 학습을 단계적으로 확대하기 위해 `finetune/run_stom_1s_finetune.py`에 `--sample-stage` 옵션을 추가했다.

지원 stage:

| stage | train samples | val samples |
| --- | ---: | ---: |
| `budget_20k` | 20,000 | 4,000 |
| `expand_200k` | 200,000 | 40,000 |
| `expand_1m` | 1,000,000 | 100,000 |
| `expand_5m` | 5,000,000 | 250,000 |
| `full_window` | horizon별 전체 possible train | horizon별 전체 possible val |

예시:

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --sample-stage expand_200k `
  --output-root finetune\outputs `
  --dry-run
```

주의: `full_window`는 pred60 기준 73,718,875 train samples이므로 즉시 실행 대상이 아니다. 먼저 대형 walk-forward와 rolling validation에서 비용 후 성과가 개선되는지 확인한 뒤 `expand_200k`부터 실행한다.

## 18. 2026-05-09 pred60 대형 walk-forward 게이트 결과

상세 보고서: `docs/stom_1s_large_walkforward_gate_report.md`

이번 단계에서는 `expand_200k` 실제 학습으로 넘어가기 전에, 기존 pred60 `budget_20k` checkpoint를 더 큰 holdout walk-forward 표본으로 검증했다.

핵심 수치:

| 항목 | 값 |
| --- | ---: |
| selected windows | 3,080 |
| rebalance periods | 500 |
| rows per mode | 184,800 |
| Kronos direction accuracy | 0.4312 |
| random direction accuracy | 0.4084 |
| persistence direction accuracy | 0.1487 |
| Qlib Top-K avg net return | -0.1953% |
| best robust filter avg net return | -0.1266% |
| rolling avg test net return | -0.1766% |
| rolling positive test fold rate | 0.25 |

판단:

```text
expand_200k 실제 학습은 이번 단계에서 실행하지 않는다.
방향성 신호는 random보다 높지만, 비용 후 수익성과 rolling 안정성이 아직 기준 미달이다.
```

따라서 다음 단계는 학습량 확대가 아니라 score/filter 구조 개선, 비용 민감도 분석, pred30/pred60 ensemble 후보 검증이다. rolling 평균 test net이 0 이상으로 올라오고 여러 fold에서 반복 개선이 확인될 때만 `--sample-stage expand_200k` 학습으로 넘어간다.

현재 판단:

```text
Page 1 DB 구조 분석                       [█████] 100%
Page 2 STOM tick OHLCV/QlibDataset 구축    [█████] 100%
Page 3 bounded/pilot 학습 검증             [████░] 70%
Page 4 1초봉 전체 학습 루프 연결           [█████] 100%
Page 5 30초/60초 20k 파인튜닝              [█████] 100%
Page 6 대형 walk-forward/rolling 검증      [█████] 95%
Page 7 웹 대시보드/검증 산출물 확인        [████░] 82%
Page 8 staged full-training 계획           [████░] 88%
Page 9 expand/full-window 실제 확대 학습   [░░░░░] 0%
전체 진행률                                [█████░] 91%
```

주의: 여기서 전체 진행률은 “파이프라인 구축과 검증 체계” 기준이다. STOM tick의 모든 possible window를 실제로 끝까지 학습한 것은 아니며, 확대 학습은 게이트 미충족으로 보류한다.

## 19. 2026-05-09 cost sensitivity gate 자동화

상세 보고서: `docs/stom_1s_cost_gate_analysis_report.md`

`finetune/search_stom_1s_filters.py`에 `--gate-analysis` 모드를 추가했다. 이 모드는 기존 filter-search와 rolling-validation JSON을 재사용해 비용 민감도와 확대 학습 승인 여부를 계산한다.

생성 artifact:

```text
*.cost_gate.json
*.cost_gate_rolling_sensitivity.csv
```

대시보드 artifact 유형도 다음처럼 확장했다.

```text
filter_search
rolling_filter_validation
cost_sensitivity_gate
```

현재 대형 pred60 결과에서는 5bp 비용 가정만 통과하고, target 25bp 기준은 실패했다.

| total cost | rolling avg test net | positive fold rate | gate |
| ---: | ---: | ---: | --- |
| 5bp | +0.0234% | 0.500 | PASS |
| 10bp | -0.0266% | 0.375 | FAIL |
| 15bp | -0.0766% | 0.375 | FAIL |
| 25bp | -0.1766% | 0.250 | FAIL |

따라서 pipeline의 안전 순서는 다음과 같다.

```text
prediction CSV
-> Qlib Top-K/filter-search
-> rolling validation
-> cost_sensitivity_gate
-> target 25bp gate 통과 시에만 expand_200k fine-tuning
```
