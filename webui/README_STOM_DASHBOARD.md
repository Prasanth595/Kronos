# STOM Kronos 대시보드 사용법

## 목적

`/stom` 페이지는 STOM tick DB에서 만든 Kronos OHLCV 학습/검증 결과를 확인하는 연구용 대시보드입니다.

확인할 수 있는 것:

- 전체 DB 학습 가능 요약
- 파일럿/전체 학습 진행 명령
- 실제값 vs 예측값 차트
- MAE/RMSE/MAPE/방향정확도
- 예상등락률 Top-K 검증
- Qlib-style Top-K backtest artifact/equity curve

## 1. 대시보드 의존성 설치

기존 webui requirements를 사용합니다.

```powershell
python -m pip install -r webui/requirements.txt
```

## 2. 파일럿 데이터 생성

```powershell
python finetune_csv/prepare_stom_1tick.py export `
  --db _database/stock_tick_back.db `
  --output finetune_csv/data/stom_1tick_kline_pilot.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 100 `
  --price-mode close_only
```

## 3. 예측 검증 파일 생성

모델이 아직 없으면 baseline으로 먼저 대시보드를 확인합니다.

```powershell
python finetune_csv/stom_prediction_eval.py `
  --data finetune_csv/data/stom_1tick_kline_pilot.csv `
  --output webui/stom_predictions/pilot_predictions.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-windows 20 `
  --mode baseline
```

학습 모델이 있으면:

```powershell
python finetune_csv/stom_prediction_eval.py `
  --data finetune_csv/data/stom_1tick_kline_pilot.csv `
  --output webui/stom_predictions/kronos_predictions.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-windows 20 `
  --mode kronos `
  --model-path finetune_csv/finetuned/stom_1tick_lookback300_pred60/basemodel/best_model `
  --tokenizer-path NeoQuasar/Kronos-Tokenizer-base `
  --device cuda:0
```

## 4. 실행

```powershell
python webui/run.py
```

접속:

```text
http://localhost:7070/stom
```

## 5. Qlib-style Top-K backtest 표시

Kronos 예측 CSV가 있으면 Qlib-style score backtest artifact를 생성할 수 있습니다.

```powershell
python finetune\qlib_stom_pipeline.py score-backtest `
  --prediction-csv webui\stom_predictions\kronos_all_predictions.csv `
  --output-dir webui\qlib_backtests `
  --top-k 10 `
  --cost-bps 15 `
  --slippage-bps 10
```

생성된 `webui/qlib_backtests/*.json`은 `/stom` 페이지의 **Qlib Top-K 백테스트** 영역에서 선택해 equity curve와 성과 metrics를 확인할 수 있습니다.

## 6. Qlib 실행 환경 점검

Qlib `.bin` 변환/provider 검증 단계로 넘어가기 전:

```powershell
python finetune\qlib_stom_pipeline.py qlib-env-check
```

현재 워크스테이션에서는 `pyqlib 0.9.7` 설치와 `.omx/external/qlib/scripts/dump_bin.py` 확보가 확인되었습니다. export report가 있으면 dump command를 dry-run으로 확인합니다.

```powershell
python finetune\qlib_stom_pipeline.py dump-bin `
  --export-report finetune\qlib_exports\stom_1min_pilot\stom_qlib_export_report.json `
  --qlib-dir finetune\qlib_exports\stom_1min_pilot\qlib_bin `
  --dump-bin-script .omx\external\qlib\scripts\dump_bin.py `
  --freq 1min
```

실제 변환은 `--execute`를 붙입니다.

```powershell
python finetune\qlib_stom_pipeline.py dump-bin `
  --export-report finetune\qlib_exports\stom_1min_pilot\stom_qlib_export_report.json `
  --qlib-dir finetune\qlib_exports\stom_1min_pilot\qlib_bin `
  --dump-bin-script .omx\external\qlib\scripts\dump_bin.py `
  --freq 1min `
  --execute
```

provider smoke:

```powershell
python finetune\qlib_stom_pipeline.py provider-smoke `
  --provider-uri finetune\qlib_exports\stom_1min_pilot\qlib_bin `
  --region cn `
  --freq 1min
```

주의: 1초봉(`--freq 1s`)은 dump_bin 변환은 가능하지만 pyqlib provider의 `D.calendar(freq="1s")`가 지원하지 않습니다. 1초봉 학습은 Qlib provider보다 `processed_datasets/*.pkl`을 통한 Kronos fine-tuning 경로를 사용하세요.

## 주의

- `webui/stom_predictions/*.csv`는 생성 결과이므로 기본 커밋 대상이 아닙니다.
- `webui/qlib_backtests/*`도 생성 결과이므로 기본 커밋 대상이 아닙니다.
- baseline 결과는 모델 성능이 아니라 대시보드 smoke test용입니다.
- 실제 학습 모델 검증은 `--mode kronos`로 생성한 prediction CSV를 사용해야 합니다.
