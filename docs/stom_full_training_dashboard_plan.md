# STOM OHLCV Kronos 전체 구축 계획과 실행 가이드

이 문서는 STOM tick DB를 Kronos 기본 OHLCV로 학습하고, 학습 후 실제값/예측값을 웹 대시보드에서 검증하기 위한 전체 1~5 단계 계획이다.

## 전체 목표

```text
1. 환경 점검
2. STOM DB → Kronos OHLCV 학습 데이터 준비
3. Kronos 파일럿 파인튜닝
4. 예측 검증 결과 생성
5. 웹 대시보드에서 실제값/예측값 시각화
```

전체 DB 기준 규모:

- 전체 테이블: `2,427`
- 주식 OHLCV 테이블: `2,425`
- 제외: `moneytop`, `stockinfo`
- `lookback=300`, `predict=60` 기준 학습 가능 그룹: `73,650`
- 예상 학습 window: `95,946,764`

## Page 1. 환경 점검

목표는 “학습을 시작해도 되는 상태인지”를 먼저 확인하는 것이다.

명령:

```powershell
python finetune_csv/stom_ohlcv_pipeline.py env-check
```

확인 항목:

- Python 실행 경로
- torch 설치 여부
- CUDA 사용 가능 여부
- Flask/Plotly dashboard dependency
- STOM DB 존재 여부
- `config_stom_1tick.yaml` 설정 요약

CUDA가 false이면 전체 학습을 바로 강행하지 않는다. 먼저 CUDA PyTorch를 설치하거나 CPU pilot만 수행한다.

## Page 2. DB 분석/학습 데이터 준비

전체 검사:

```powershell
python finetune_csv/prepare_stom_1tick.py inspect `
  --db _database/stock_tick_back.db `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 0 `
  --price-mode close_only
```

파일럿 export:

```powershell
python finetune_csv/prepare_stom_1tick.py export `
  --db _database/stock_tick_back.db `
  --output finetune_csv/data/stom_1tick_kline_pilot.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 100 `
  --price-mode close_only
```

`close_only`는 `현재가`를 OHLC 모두에 사용하는 안전 모드다. STOM `시가/고가/저가`가 실제 1초봉 OHLC가 아니라 일중 누적 시고저일 수 있기 때문에 기본값으로 권장한다.

## Page 3. 파일럿 학습

처음부터 전체 `95,946,764` windows를 사용하지 않는다.

권장 파일럿 설정:

```yaml
data:
  max_samples: 200000
  sample_stride: 5

training:
  basemodel_epochs: 1
  batch_size: 16
```

학습 명령:

```powershell
python finetune_csv/train_sequential.py --config finetune_csv/configs/config_stom_1tick.yaml
```

목표:

- DataLoader 정상 생성
- GPU/CPU memory 확인
- train/validation loss 계산
- best model 저장

## Page 4. 예측 검증 결과 생성

대시보드가 실제값/예측값을 표시하려면 prediction CSV가 필요하다.

모델이 아직 없을 때 baseline smoke:

```powershell
python finetune_csv/stom_prediction_eval.py `
  --data finetune_csv/data/stom_1tick_kline_pilot.csv `
  --output webui/stom_predictions/pilot_predictions.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-windows 20 `
  --mode baseline
```

학습 모델이 준비된 뒤 real Kronos 검증:

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

저장되는 주요 컬럼:

- `symbol`
- `session`
- `asof_timestamp`
- `target_timestamp`
- `pred_close`
- `actual_close`
- `error`
- `abs_error`
- `pred_return_window`
- `actual_return_window`
- `direction_hit_window`

## Page 5. 웹 대시보드

실행:

```powershell
python webui/run.py
```

접속:

```text
http://localhost:7070/stom
```

표시 내용:

- 전체 DB 학습 가능 요약
- 진행 단계별 명령
- prediction CSV 선택
- 실제 close vs 예측 close 차트
- MAE/RMSE/MAPE/방향정확도
- 예상등락률 Top-K 검증 표

## Commit 운영 원칙

커밋에 포함:

- 코드
- 테스트
- 문서
- 설정 템플릿

커밋 제외:

- `_database/`
- 대용량 CSV
- 모델 checkpoint
- 일회성 prediction 결과 대용량 파일

## 현재 구현 상태

- 환경 점검 CLI: `finetune_csv/stom_ohlcv_pipeline.py`
- 예측 검증 CLI: `finetune_csv/stom_prediction_eval.py`
- 웹 대시보드: `webui/templates/stom_dashboard.html`, `/stom`
- 대시보드 API:
  - `/api/stom/summary`
  - `/api/stom/prediction-files`
  - `/api/stom/prediction`

## 목표 달성 기준

다음이 모두 통과하면 구축 목표를 달성한 것으로 본다.

```powershell
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py -q
python -m compileall -q finetune_csv webui tests docs
python finetune_csv/stom_ohlcv_pipeline.py env-check
python finetune_csv/stom_prediction_eval.py --help
```
