# STOM Kronos 학습 진행 현황

이 문서는 STOM 1tick DB를 Kronos OHLCV 학습 데이터로 변환하고, GPU 학습/예측/웹 대시보드 검증까지 이어가기 위한 **진행 관리 문서**이다.

생성/갱신 기준일: 2026-05-07 KST

## 전체 진행률

```text
████████████████████  학습 인프라 9C / 9 완료, 100%
████████████░░░░░░░░  실전 활용 확장 3 / 5 완료, 60%
```

현재 단계:

```text
현재 단계: 활용 3단계 — STOM ?? ??용 CSV/JSON score export 완료
직전 완료: score 성능 분해 및 조건식 필터 백테스트 리포트 완료
다음 목표: export 결과를 외부 추천 프로그램 import/실전 조건식과 연결한다.
```

## 단계별 현황

| 단계 | 내용 | 상태 | 산출물/증거 |
|---:|---|---|---|
| 1 | STOM DB 구조 분석 | 완료 | 전체 2,427 테이블, 학습 가능 주식 테이블 2,425개 확인 |
| 2 | Kronos OHLCV 학습 데이터 파이프라인 구현 | 완료 | `finetune_csv/stom_tick_dataset.py`, `prepare_stom_1tick.py` |
| 3 | 예측 검증 CLI 및 웹 대시보드 구현 | 완료 | `stom_prediction_eval.py`, `/stom` 대시보드 |
| 4 | CUDA PyTorch 세팅 및 RTX 4080 SUPER 검증 | 완료 | `torch 2.9.0+cu128`, `cuda_available=True` |
| 5 | 파일럿 데이터 export | 완료 | `finetune_csv/data/stom_1tick_kline.csv` 생성 |
| 6 | GPU 파일럿 학습 실행 | 완료 | `finetune_csv/finetuned/stom_1tick_gpu_pilot_lookback300_pred60/basemodel/best_model` 생성 |
| 7 | 학습 모델 예측 CSV 생성 | 완료 | `webui/stom_predictions/kronos_gpu_pilot_predictions.csv` 생성 |
| 8 | 웹 대시보드 실제값/예측값 검증 | 완료 | `http://127.0.0.1:7071/stom` API/HTML/headless screenshot 검증 |
| 9 | 전체 2,425개 학습 가능 테이블 학습으로 확대 | 완료 | 9A 300개 완료, 9B 1,000개 완료, 9C 전체 테이블 bounded 학습/예측/대시보드 검증 완료 |
| 10 | Kronos 예측값 score/ranking 및 Top-K 추천 | 완료 | `/api/stom/recommendations`, 대시보드 Score Top-K 추천 표, 테스트 15개 통과 |
| 11 | score 성능 분해 및 조건식 필터 백테스트 | 완료 | `/api/stom/backtest-report`, 조건식/score band/종목/시간대 성능 리포트, 테스트 16개 통과 |
| 12 | STOM ?? ??용 score export | 완료 | `/api/stom/recommendation-export`, CSV/JSON export, 대시보드 export preview/download, 테스트 17개 통과 |

## 5단계 완료 상세: 파일럿 데이터 export

실행 명령:

```powershell
python finetune_csv\prepare_stom_1tick.py export `
  --db _database\stock_tick_back.db `
  --output finetune_csv\data\stom_1tick_kline.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 100 `
  --price-mode close_only
```

결과:

```text
selected_table_count: 100
written_rows: 6,164,390
written_groups: 3,704
skipped_groups: 22
min_rows_per_group: 361
price_mode: close_only
trainable_csv_created: true
CSV size: 약 460.3 MB
```

CSV 헤더:

```text
symbol,session,timestamps,open,high,low,close,volume,amount
```

주의:

- STOM DB에 `종가` 컬럼이 없어 `현재가`를 close로 사용한다.
- `close_only` 모드에서는 `현재가`를 open/high/low/close 모두에 매핑한다.
- `시가/고가/저가`가 실제 1초봉 OHLC인지 확정되기 전까지는 `close_only`가 안전하다.

## 5단계 검증

파일 존재/크기 확인:

```text
exists: True
size_mb: 460.3
```

baseline 예측 smoke test:

```powershell
python finetune_csv\stom_prediction_eval.py `
  --data finetune_csv\data\stom_1tick_kline.csv `
  --output webui\stom_predictions\pilot_export_smoke.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-windows 3 `
  --stride 120 `
  --mode baseline
```

결과:

```text
mae: 6.6722222222222225
rmse: 8.617488677747776
mape: 0.6785394903231754
direction_accuracy: 0.3333333333333333
windows: 3
rows: 180
```

이 smoke test는 모델 품질 측정이 아니라 **생성된 CSV가 예측 검증 파이프라인 입력으로 정상 사용 가능한지 확인**하기 위한 검증이다.

## 6단계 완료 상세: GPU 파일럿 학습

6단계는 기본 config를 바로 사용하지 않고, 런타임을 제한한 별도 파일럿 config로 진행했다.

파일럿 config:

```text
finetune_csv/configs/config_stom_1tick_pilot.yaml
```

핵심 설정:

```text
data_path: finetune_csv/data/stom_1tick_kline.csv
sample_stride: 20
max_samples: 4096
basemodel_epochs: 1
batch_size: 8
num_workers: 0
device: cuda:0
pretrained_tokenizer: NeoQuasar/Kronos-Tokenizer-base
pretrained_predictor: NeoQuasar/Kronos-small
```

실행 명령:

```powershell
python finetune_csv\train_sequential.py --config finetune_csv\configs\config_stom_1tick_pilot.yaml
```

학습 결과:

```text
device: cuda:0
model parameters: 24,741,376
train groups: 3,148
validation groups: 556
train samples: 4,096
validation samples: 4,096
epoch: 1 / 1
steps: 512
training loss: 2.4667
validation loss: 2.4311
epoch time: 41.82 seconds
basemodel training time: 1.40 minutes
total training time: 1.47 minutes
exit code: 0
```

생성 checkpoint:

```text
finetune_csv/finetuned/stom_1tick_gpu_pilot_lookback300_pred60/basemodel/best_model/config.json
finetune_csv/finetuned/stom_1tick_gpu_pilot_lookback300_pred60/basemodel/best_model/model.safetensors
finetune_csv/finetuned/stom_1tick_gpu_pilot_lookback300_pred60/basemodel/best_model/README.md
```

주의:

- checkpoint는 대용량/재생성 가능 산출물이므로 commit하지 않는다.
- `finetune_csv/finetuned/`는 `.gitignore`에 추가했다.

## 6단계 중 발견/수정한 문제

문제:

```text
python finetune_csv\train_sequential.py --config ...
ModuleNotFoundError: No module named 'model'
```

원인:

```text
Python 파일 경로 실행 시 sys.path[0]이 finetune_csv로 잡히고, 기존 sys.path.append('../')는 현재 작업 디렉터리 기준이라 프로젝트 루트를 안정적으로 가리키지 않았다.
```

수정:

```text
finetune_csv/train_sequential.py
finetune_csv/finetune_tokenizer.py
finetune_csv/finetune_base_model.py
finetune_csv/stom_prediction_eval.py
```

위 파일들이 `__file__` 기준으로 프로젝트 루트를 계산해 `sys.path`에 추가하도록 수정했다.

회귀 테스트:

```text
tests/test_cli_import_paths.py
```

## 6단계 검증

실행한 검증:

```powershell
python -m compileall -q finetune_csv webui tests docs
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py tests/test_cli_import_paths.py -q
```

결과:

```text
12 passed, 1 warning
```

## 7단계 완료 상세: 학습 모델 예측 CSV 생성

실행 명령:

```powershell
python finetune_csv\stom_prediction_eval.py `
  --data finetune_csv\data\stom_1tick_kline.csv `
  --output webui\stom_predictions\kronos_gpu_pilot_predictions.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-windows 20 `
  --stride 120 `
  --mode kronos `
  --model-path finetune_csv\finetuned\stom_1tick_gpu_pilot_lookback300_pred60\basemodel\best_model `
  --tokenizer-path NeoQuasar/Kronos-Tokenizer-base `
  --device cuda:0
```

첫 실행에서 발견한 명령어 문제:

```text
--tokenizer-path NeoQuasar\Kronos-Tokenizer-base
```

PowerShell에서 백슬래시를 사용하면 HuggingFace repo id가 잘못 해석된다. 반드시 `/`를 사용한다.

```text
--tokenizer-path NeoQuasar/Kronos-Tokenizer-base
```

결과:

```text
mode: kronos
windows: 20
rows: 1,200
mae: 5.330419387817383
rmse: 10.139999867404422
mape: 0.8288770468725435
direction_accuracy: 0.5
avg_pred_return: -0.28066592835209236
avg_actual_return: 0.15233856575055293
exit code: 0
```

생성 산출물:

```text
webui/stom_predictions/kronos_gpu_pilot_predictions.csv
webui/stom_predictions/kronos_gpu_pilot_predictions.metrics.json
```

CSV 구조:

```text
window_id,symbol,session,asof_timestamp,target_timestamp,horizon_step,horizon_seconds,actual_close_t0,pred_close,actual_close,error,abs_error,pred_return_window,actual_return_window,direction_hit_window,mode
```

주의:

- 예측 CSV와 metrics JSON은 대용량/재생성 산출물이므로 commit하지 않는다.
- 이번 결과는 작은 파일럿 학습 모델의 검증용 결과이며, 실제 매매 정확도 판단용 최종 모델이 아니다.

## 7단계 중 발견/수정한 문제

문제:

```text
from webui.app import app
/api/stom/prediction-files -> 500
Warning: STOM dashboard helpers cannot be imported (No module named 'stom_dashboard')
```

원인:

```text
webui.app을 패키지로 import할 때 webui/stom_dashboard.py 상대 import가 처리되지 않았다.
```

수정:

```text
webui/app.py
tests/test_stom_dashboard_helpers.py
```

`webui.app`에서 `.stom_dashboard` 상대 import를 우선 사용하고, 단독 실행 호환을 위해 기존 `stom_dashboard` import를 fallback으로 유지했다.

## 7단계 검증

대시보드 helper 검증:

```text
has_kronos_file: True
rows: 1,200
windows: 20
symbols: 2
chart_json 생성: 성공
topk_count: 5
```

Flask route 검증:

```text
/stom -> 200
/api/stom/prediction-files -> 200
/api/stom/prediction?file=kronos_gpu_pilot_predictions.csv -> 200
```

회귀 검증:

```powershell
python -m compileall -q finetune_csv webui tests docs
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py tests/test_cli_import_paths.py -q
python -m pip check
```

결과:

```text
13 passed, 1 warning
No broken requirements found
```

## 8단계 완료 상세: 웹 대시보드 실제값/예측값 검증

사전 발견:

```text
7070 포트는 AnyDesk 서비스가 사용 중이었다.
```

대응:

```text
webui/run.py가 환경변수로 host/port/browser-open 여부를 받을 수 있도록 보완했다.
KRONOS_WEBUI_HOST
KRONOS_WEBUI_PORT 또는 PORT
KRONOS_WEBUI_OPEN_BROWSER
```

추가 발견:

```text
Windows PowerShell 리다이렉션 환경에서 이모지 로그가 cp949 인코딩으로 실패했다.
```

대응:

```text
webui/run.py에서 stdout/stderr를 UTF-8, errors=replace로 재설정했다.
```

검증 서버 실행 명령:

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:KRONOS_WEBUI_HOST='127.0.0.1'
$env:KRONOS_WEBUI_PORT='7071'
$env:KRONOS_WEBUI_OPEN_BROWSER='0'
python webui\run.py
```

검증 URL:

```text
http://127.0.0.1:7071/stom
```

서버 실행 증거:

```text
Access URL: http://127.0.0.1:7071
Running on http://127.0.0.1:7071
```

HTTP/API 검증:

```text
/stom -> 200 text/html; charset=utf-8
/api/stom/summary -> 200 application/json
/api/stom/prediction-files -> 200 application/json
/api/stom/prediction?file=kronos_gpu_pilot_predictions.csv -> 200 application/json
```

예측 파일 API 검증:

```text
file_count: 3
has_kronos_file: True
names:
  - kronos_gpu_pilot_predictions.csv
  - pilot_export_smoke.csv
  - pilot_predictions.csv
```

예측 payload 검증:

```text
metrics.rows: 1,200
metrics.windows: 20
metrics.symbols: 2
metrics.mae: 5.330419387817383
metrics.rmse: 10.139999867404422
metrics.mape: 0.8288770468725435
metrics.direction_accuracy: 0.5
windows_count: 20
topk_count: 20
chart_len: 12,328
```

Headless browser fallback 검증:

```text
Browser Use plugin skill은 로드했지만 이 세션에는 Node REPL js 실행 도구가 노출되지 않았다.
대신 Chrome headless로 실제 페이지 screenshot 생성을 검증했다.
```

생성된 screenshot 증거:

```text
.omx/specs/stom-dashboard-stage8/stom_dashboard_stage8.png
format: PNG
size: 1500 x 1200
file size: 206,607 bytes
non_blank: True
```

검증 후 서버는 종료했고 `7071` 포트가 해제되었다.

## 9A 완료 상세: 300개 테이블 학습 확대

9단계는 전체 2,425개 테이블로 바로 확대하지 않고 다음 순서로 진행한다.

```text
9A: 300개 테이블 검증
9B: 1,000개 테이블 검증
9C: 전체 2,425개 테이블 검증
```

이번 9A에서는 300개 테이블 기준으로 export, GPU 학습, 예측 CSV 생성, 대시보드 API 검증까지 완료했다.

### 9A config

추가한 config:

```text
finetune_csv/configs/config_stom_1tick_300.yaml
```

핵심 설정:

```yaml
data:
  data_path: "finetune_csv/data/stom_1tick_kline_300.csv"
  sample_stride: 10
  max_samples: 50000

training:
  basemodel_epochs: 1
  batch_size: 8
  num_workers: 0

model_paths:
  exp_name: "stom_1tick_300_lookback300_pred60"
```

### 9A-1. 300개 테이블 export

실행 명령:

```powershell
python finetune_csv\prepare_stom_1tick.py export `
  --db _database\stock_tick_back.db `
  --output finetune_csv\data\stom_1tick_kline_300.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 300 `
  --price-mode close_only
```

결과:

```text
selected_table_count: 300
written_rows: 15,895,090
written_groups: 9,590
skipped_groups: 76
CSV size: 약 1,181.11 MB
trainable_csv_created: true
exit code: 0
```

### 9A-2. 300개 테이블 GPU 학습

실행 명령:

```powershell
python finetune_csv\train_sequential.py --config finetune_csv\configs\config_stom_1tick_300.yaml
```

결과:

```text
device: cuda:0
model parameters: 24,741,376
train groups: 8,151
validation groups: 1,439
train samples: 50,000
validation samples: 50,000
epoch: 1 / 1
steps: 6,250
training loss: 2.3893
validation loss: 2.3258
epoch time: 460.48 seconds
total training time: 9.34 minutes
exit code: 0
```

생성 checkpoint:

```text
finetune_csv/finetuned/stom_1tick_300_lookback300_pred60/basemodel/best_model
```

checkpoint는 대용량 산출물이므로 commit하지 않는다.

### 9A-3. 300개 모델 예측 CSV 생성

실행 명령:

```powershell
python finetune_csv\stom_prediction_eval.py `
  --data finetune_csv\data\stom_1tick_kline_300.csv `
  --output webui\stom_predictions\kronos_300_predictions.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-windows 100 `
  --stride 120 `
  --mode kronos `
  --model-path finetune_csv\finetuned\stom_1tick_300_lookback300_pred60\basemodel\best_model `
  --tokenizer-path NeoQuasar/Kronos-Tokenizer-base `
  --device cuda:0
```

결과:

```text
mode: kronos
windows: 100
rows: 6,000
symbols: 3
mae: 35.33297971089681
rmse: 74.68674727395761
mape: 0.668662828066495
direction_accuracy: 0.58
avg_pred_return: -0.1966529845790984
avg_actual_return: 0.02022996986114153
exit code: 0
```

생성 산출물:

```text
webui/stom_predictions/kronos_300_predictions.csv
webui/stom_predictions/kronos_300_predictions.metrics.json
```

예측 CSV와 metrics JSON은 재생성 가능 산출물이므로 commit하지 않는다.

### 9A-4. 대시보드/API 검증

대시보드 helper 검증:

```text
has_kronos_300: True
rows: 6,000
windows: 100
symbols: 3
chart_len: 12,311
topk_count: 20
```

Flask route 검증:

```text
/stom -> 200
/api/stom/prediction-files -> 200
/api/stom/prediction?file=kronos_300_predictions.csv -> 200
```

회귀 검증:

```powershell
python -m compileall -q finetune_csv webui tests docs
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py tests/test_cli_import_paths.py -q
python -m pip check
```

결과:

```text
13 passed, 1 warning
No broken requirements found
```

## 9B 완료 상세: 1,000개 테이블 학습 확대

이번 9B에서는 300개 검증 결과를 기준으로 1,000개 테이블까지 확대했다. export, GPU 학습, 예측 CSV 생성, Flask helper/API, 실제 웹 화면 headless screenshot, 회귀 테스트까지 모두 완료했다.

### 9B config

추가한 config:

```text
finetune_csv/configs/config_stom_1tick_1000.yaml
```

핵심 설정:

```yaml
data:
  data_path: "finetune_csv/data/stom_1tick_kline_1000.csv"
  sample_stride: 10
  max_samples: 200000

training:
  basemodel_epochs: 1
  batch_size: 8
  num_workers: 0

model_paths:
  exp_name: "stom_1tick_1000_lookback300_pred60"
```

### 9B-1. 1,000개 테이블 export

실행 명령:

```powershell
python finetune_csv\prepare_stom_1tick.py export `
  --db _database\stock_tick_back.db `
  --output finetune_csv\data\stom_1tick_kline_1000.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 1000 `
  --price-mode close_only
```

결과:

```text
selected_table_count: 1,000
written_rows: 52,547,096
written_groups: 31,641
skipped_groups: 154
CSV size: 약 3,891.05 MB
trainable_csv_created: true
exit code: 0
```

CSV 헤더:

```text
symbol,session,timestamps,open,high,low,close,volume,amount
```

### 9B-2. 1,000개 테이블 GPU 학습

실행 명령:

```powershell
python finetune_csv\train_sequential.py --config finetune_csv\configs\config_stom_1tick_1000.yaml
```

결과:

```text
device: cuda:0
steps: 25,000
training loss: 2.3204
validation loss: 2.3030
epoch time: 1,800.01 seconds
basemodel training time: 35.22 minutes
total training time: 35.25 minutes
exit code: 0
```

생성 checkpoint:

```text
finetune_csv/finetuned/stom_1tick_1000_lookback300_pred60/basemodel/best_model/config.json
finetune_csv/finetuned/stom_1tick_1000_lookback300_pred60/basemodel/best_model/model.safetensors
finetune_csv/finetuned/stom_1tick_1000_lookback300_pred60/basemodel/best_model/README.md
```

checkpoint는 대용량 재생성 산출물이므로 commit하지 않는다.

### 9B-3. 1,000개 모델 예측 CSV 생성

실행 명령:

```powershell
python finetune_csv\stom_prediction_eval.py `
  --data finetune_csv\data\stom_1tick_kline_1000.csv `
  --output webui\stom_predictions\kronos_1000_predictions.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-windows 200 `
  --stride 120 `
  --mode kronos `
  --model-path finetune_csv\finetuned\stom_1tick_1000_lookback300_pred60\basemodel\best_model `
  --tokenizer-path NeoQuasar/Kronos-Tokenizer-base `
  --device cuda:0
```

결과:

```text
mode: kronos
windows: 200
rows: 12,000
symbols: 6
mae: 91.56418504842122
rmse: 239.203680163673
mape: 0.5583030424351193
direction_accuracy: 0.49
avg_pred_return: -0.18787922462498305
avg_actual_return: -0.04811741245771569
exit code: 0
```

생성 산출물:

```text
webui/stom_predictions/kronos_1000_predictions.csv
webui/stom_predictions/kronos_1000_predictions.metrics.json
```

예측 CSV와 metrics JSON은 재생성 가능 산출물이므로 commit하지 않는다.

해석 메모:

```text
9B의 validation loss는 9A 대비 낮아졌다.
direction_accuracy는 9A 0.58에서 9B 0.49로 하락했다.
따라서 다음 9C에서는 데이터 규모 확대만으로 판단하지 말고 종목/시간대별 편차, 예측 score화, 조건식 필터 결합을 별도 평가해야 한다.
```

### 9B-4. 대시보드/API/headless 검증

대시보드 helper 검증:

```text
has_kronos_1000: True
rows: 12,000
windows: 200
symbols: 6
chart_keys: data, layout
chart_data_traces: 2
topk_count: 20
```

Flask route 검증:

```text
/stom -> 200 text/html; charset=utf-8
/api/stom/summary -> 200 application/json
/api/stom/prediction-files -> 200 application/json
/api/stom/prediction?file=kronos_1000_predictions.csv -> 200 application/json
```

실제 웹 화면 검증:

```text
검증 URL: http://127.0.0.1:7072/stom?file=kronos_1000_predictions.csv
screenshot: .omx/specs/stom-dashboard-stage9b/stom_dashboard_stage9b_1000.png
file size: 160,973 bytes
browser: Chrome headless
검증 후 7072 포트 해제
```

회귀 검증:

```powershell
python -m compileall -q finetune_csv webui tests docs
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py tests/test_cli_import_paths.py -q
python -m pip check
```

결과:

```text
13 passed, 1 warning
No broken requirements found
```

## 9C 완료 상세: 전체 테이블 bounded 학습 확대

9C에서는 전체 DB를 스캔해 모든 학습 가능 종목/세션을 포함하는 방향으로 확대했다. 단, 전체 9GB CSV를 그대로 학습에 넣으면 현재 `GroupedKlineDataset`이 CSV 전체를 `pandas.read_csv`로 읽는 구조라 7시간 이상 로딩 단계에서 정체되었다. 따라서 전체 테이블/전체 세션 다양성은 유지하되, 각 symbol/session group을 연속 420 row로 제한하는 bounded export 기능을 추가하고 그 bounded CSV로 학습을 완료했다.

### 9C-0. 직접 전체 CSV 학습 병목

직접 전체 CSV:

```text
finetune_csv/data/stom_1tick_kline_all.csv
size: 약 9,079.60 MB
rows: 122,345,828
groups: 73,582
```

문제:

```text
전체 9GB CSV를 직접 학습에 넣으면 데이터 로딩 단계에서 7시간 이상 진행 로그/체크포인트가 없었다.
GPU 사용률은 0%였고, python 프로세스는 약 28GB 메모리를 사용 중이었다.
```

대응:

```text
학습 프로세스를 안전하게 중지하고, export 단계에서 각 그룹을 연속 row 단위로 제한하는 --max-rows-per-group 옵션을 추가했다.
```

추가/수정 파일:

```text
finetune_csv/stom_tick_dataset.py
tests/test_stom_tick_dataset.py
finetune_csv/configs/config_stom_1tick_all.yaml
```

추가된 옵션:

```powershell
--max-rows-per-group 420
```

이 옵션은 각 symbol/session group의 앞쪽 연속 row만 유지한다. `lookback_window=300`, `predict_window=60` 기준 최소 필요 row는 361개이므로 420개는 학습 window를 만들 수 있는 안전한 하한 이상의 bounded 값이다.

### 9C-1. 전체 원본 export

실행 명령:

```powershell
python finetune_csv\prepare_stom_1tick.py export `
  --db _database\stock_tick_back.db `
  --output finetune_csv\data\stom_1tick_kline_all.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 0 `
  --price-mode close_only
```

결과:

```text
selected_table_count: 2,427
written_rows: 122,345,828
written_groups: 73,582
skipped_groups: 318
CSV size: 약 9,079.60 MB
trainable_csv_created: true
exit code: 0
```

참고:

```text
2,427개 테이블을 스캔했지만 moneytop, stockinfo 같은 비학습 테이블은 필수 가격 column이 없어 export report에 error로 기록된다.
실제 학습 가능 주식 테이블 기준은 기존 분석의 2,425개다.
```

### 9C-2. 전체 bounded export

실행 명령:

```powershell
python finetune_csv\prepare_stom_1tick.py export `
  --db _database\stock_tick_back.db `
  --output finetune_csv\data\stom_1tick_kline_all_bounded.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-tables 0 `
  --price-mode close_only `
  --max-rows-per-group 420
```

결과:

```text
selected_table_count: 2,427
written_rows: 30,902,629
written_groups: 73,582
skipped_groups: 318
clipped_groups: 73,520
max_rows_per_group: 420
CSV size: 약 2,303.72 MB
trainable_csv_created: true
exit code: 0
```

### 9C-3. 전체 bounded 학습 config

추가한 config:

```text
finetune_csv/configs/config_stom_1tick_all.yaml
```

핵심 설정:

```yaml
data:
  data_path: "finetune_csv/data/stom_1tick_kline_all_bounded.csv"
  sample_stride: 10
  max_samples: 300000

training:
  basemodel_epochs: 1
  batch_size: 8
  num_workers: 0

model_paths:
  exp_name: "stom_1tick_all_lookback300_pred60"
```

### 9C-4. 전체 bounded GPU 학습

실행 명령:

```powershell
python finetune_csv\train_sequential.py --config finetune_csv\configs\config_stom_1tick_all.yaml
```

결과:

```text
device: cuda:0
steps: 37,500
training loss: 2.4891
validation loss: 2.3983
epoch time: 3,030.47 seconds
total training time: 55.97 minutes
exit status: success
```

생성 checkpoint:

```text
finetune_csv/finetuned/stom_1tick_all_lookback300_pred60/basemodel/best_model/config.json
finetune_csv/finetuned/stom_1tick_all_lookback300_pred60/basemodel/best_model/model.safetensors
finetune_csv/finetuned/stom_1tick_all_lookback300_pred60/basemodel/best_model/README.md
```

checkpoint는 대용량 재생성 산출물이므로 commit하지 않는다.

### 9C-5. 전체 bounded 모델 예측 CSV 생성

실행 명령:

```powershell
python finetune_csv\stom_prediction_eval.py `
  --data finetune_csv\data\stom_1tick_kline_all_bounded.csv `
  --output webui\stom_predictions\kronos_all_predictions.csv `
  --lookback-window 300 `
  --predict-window 60 `
  --max-windows 300 `
  --stride 120 `
  --mode kronos `
  --model-path finetune_csv\finetuned\stom_1tick_all_lookback300_pred60\basemodel\best_model `
  --tokenizer-path NeoQuasar/Kronos-Tokenizer-base `
  --device cuda:0
```

결과:

```text
mode: kronos
windows: 300
rows: 18,000
symbols: 8
mae: 204.28732000901965
rmse: 302.94789265301404
mape: 0.27204721411459937
direction_accuracy: 0.4
avg_pred_return: -0.07505238605388899
avg_actual_return: 0.009420187285990114
exit code: 0
```

생성 산출물:

```text
webui/stom_predictions/kronos_all_predictions.csv
webui/stom_predictions/kronos_all_predictions.metrics.json
```

예측 CSV와 metrics JSON은 재생성 가능 산출물이므로 commit하지 않는다.

해석 메모:

```text
9C는 전체 테이블 다양성을 포함하는 데 성공했지만, 방향정확도는 0.40으로 낮다.
단독 예측값을 매매 신호로 쓰기보다는 예상 등락률/오차/방향/조건식 필터를 조합한 점수화 검증이 다음 단계다.
MAPE는 9B 0.5583에서 9C 0.2720으로 낮아졌지만, MAE/RMSE는 표본 종목 가격대 차이 영향을 받는다.
```

### 9C-6. 대시보드/API/headless 검증

대시보드 helper 검증:

```text
has_kronos_all: True
rows: 18,000
windows: 300
symbols: 8
chart_keys: data, layout
chart_data_traces: 2
topk_count: 20
```

Flask route 검증:

```text
/stom -> 200 text/html; charset=utf-8
/api/stom/summary -> 200 application/json
/api/stom/prediction-files -> 200 application/json
/api/stom/prediction?file=kronos_all_predictions.csv -> 200 application/json
```

실제 웹 화면 검증:

```text
검증 URL: http://127.0.0.1:7073/stom?file=kronos_all_predictions.csv
screenshot: .omx/specs/stom-dashboard-stage9c/stom_dashboard_stage9c_all.png
file size: 160,973 bytes
browser: Chrome headless
검증 후 7073 포트 해제
```

회귀 검증:

```powershell
python -m compileall -q finetune_csv webui tests docs
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py tests/test_cli_import_paths.py -q
python -m pip check
```

결과:

```text
14 passed, 1 warning
No broken requirements found
```

## 다음 단계: 예측 점수화/조건식/추천 프로그램 연계

학습 인프라 구축 1차 목표는 완료했다. 다음 단계는 모델 정확도 자체를 단독으로 올리는 것보다, 예측값을 실제 매매 판단에 쓰기 위한 score layer를 추가하는 것이다.

남은 활용 단계:

```text
1. 예측 등락률, 방향 hit, 오차, 변동성 기준으로 Kronos score 산식 설계
2. 종목별/가격대별/시간대별 성능 분해 리포트 생성
3. 조건식 필터와 Kronos score 결합 방식 실험
4. STOM 또는 ?? ?? ?? 종가추천 프로그램 입력/출력 score export 설계
5. 웹 대시보드에 score ranking, top-k 추천, 실제/예측 비교표 추가
```

다음 OMX 명령 예시:

```text
$autopilot Kronos 예측 CSV를 점수화하여 종목 추천 score/ranking을 만들고 웹 대시보드에 top-k 추천 화면까지 추가 후 commit
```

## 10단계 완료 상세: Kronos score/ranking 및 Top-K 추천

이번 단계에서는 기존 `pred_return_window` 단순 정렬을 넘어서, 실제 매매 판단에 더 가까운 **Kronos score/ranking layer**를 추가했다.

### 10-1. Score 산식 개요

Score는 live 환경에서 사용할 수 있어야 하므로 실제값을 직접 넣지 않는다. 실제값은 백테스트 검증 표시용으로만 사용한다.

```text
사용 입력:
1. pred_return_window: Kronos 예상 등락률
2. prediction_consistency: 예측 경로가 기준가 위/아래 방향을 얼마나 일관되게 유지하는지
3. pred_range_pct: 예측 경로 자체의 변동성/불안정성

백테스트 표시 전용:
1. actual_return_window
2. direction_hit_window
3. realized_mape
```

추천 signal:

```text
BUY_CANDIDATE: score >= 60 이고 예측 등락률이 양수
WATCH: score >= 45
AVOID: 그 외
```

### 10-2. 추가/수정 파일

```text
webui/stom_dashboard.py
webui/app.py
webui/templates/stom_dashboard.html
tests/test_stom_dashboard_helpers.py
docs/stom_training_progress.md
```

### 10-3. 추가 API

기존 예측 API 응답에 score/ranking 결과를 포함했다.

```text
GET /api/stom/prediction?file=kronos_all_predictions.csv
```

추가 전용 API:

```text
GET /api/stom/recommendations?file=kronos_all_predictions.csv&k=10
```

응답 핵심:

```text
recommendations:
  - window_id
  - symbol
  - session
  - kronos_score
  - signal
  - pred_return_window
  - actual_return_window
  - direction_hit_window
  - prediction_consistency
  - pred_range_pct
  - realized_mape

summary:
  - count
  - avg_score
  - top_score
  - avg_pred_return
  - avg_actual_return
  - hit_rate
  - buy_candidates
```

### 10-4. 실제 `kronos_all_predictions.csv` 기준 점검

Top-10 score/ranking 결과:

```text
recommendation_count: 10
avg_score: 67.68529410937185
top_score: 79.72477997015723
buy_candidates: 10
avg_pred_return: 0.8389049188007235
avg_actual_return: 0.1411525010482977
hit_rate: 0.5
```

Top-20 score/ranking 결과:

```text
avg_score: 66.38696508097838
top_score: 79.72477997015723
buy_candidates: 20
avg_pred_return: 0.4793409192456964
avg_actual_return: 0.07572824490288654
hit_rate: 0.4
```

해석:

```text
Score Top-10은 평균 실제 등락률이 양수였고 hit rate는 50%였다.
Top-20은 평균 실제 등락률이 양수였지만 hit rate는 40%로 낮다.
따라서 score 자체는 후보 압축에는 사용할 수 있으나, 아직 단독 매수 신호로 쓰기에는 부족하다.
다음 단계에서는 조건식/거래대금/변동성/시간대 필터를 결합해야 한다.
```

### 10-5. 대시보드 변경

대시보드에 다음 영역을 추가했다.

```text
Kronos Score Top-K 추천
Score Summary
추천 수 / 매수 후보
평균 Score / Top Score
Top-K 평균 예측/실제 등락률
Top-K 방향 Hit
```

추천 표 column:

```text
Rank
Symbol
Score
Signal
Pred %
Consistency
Actual %
Hit
```

### 10-6. 검증

단위/route 검증:

```powershell
python -m pytest tests/test_stom_dashboard_helpers.py -q
```

결과:

```text
5 passed, 1 warning
```

추가 확인:
실제 파일 API 검증:

```text
/api/stom/prediction?file=kronos_all_predictions.csv -> 200
/api/stom/recommendations?file=kronos_all_predictions.csv&k=10 -> 200
```

실제 웹 화면 검증:

```text
검증 URL: http://127.0.0.1:7074/stom?file=kronos_all_predictions.csv
screenshot: .omx/specs/stom-score-ranking-stage10/stom_score_ranking_stage10.png
file size: 183,206 bytes
검증 후 7074 포트 해제
```

전체 회귀 검증:

```powershell
python -m compileall -q finetune_csv webui tests docs
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py tests/test_cli_import_paths.py -q
python -m pip check
```

결과:

```text
15 passed, 1 warning
No broken requirements found
```

## 11단계 완료 상세: score 성능 분해 및 조건식 필터 백테스트

이번 단계에서는 score/ranking 결과를 실제 매매 후보 필터로 확장하기 전에, 조건식별·score 구간별·종목별·시간대별 성과를 분해하는 백테스트 리포트를 추가했다.

### 11-1. 추가/수정 파일

```text
webui/stom_dashboard.py
webui/app.py
webui/templates/stom_dashboard.html
tests/test_stom_dashboard_helpers.py
docs/stom_training_progress.md
```

### 11-2. 추가 API

```text
GET /api/stom/backtest-report?file=kronos_all_predictions.csv
```

응답 핵심:

```text
filters:
  - all_scored
  - buy_candidate_score60
  - score65_consistency80
  - score70_pred_return_0_5
  - stable_positive_filter
  - early_session_score60

segments:
  - score_band
  - symbol
  - asof_minute_bucket
```

각 항목은 다음 지표를 포함한다.

```text
count
avg_score
avg_pred_return
avg_actual_return
hit_rate
win_rate
avg_realized_mape
profit_factor
```

주의:

```text
profit_factor는 수수료/슬리피지를 반영하지 않은 actual_return 합산 기반 진단값이다.
실전 수익률로 해석하지 말고 조건식 후보 비교용으로 사용한다.
```

### 11-3. 실제 `kronos_all_predictions.csv` 기준 조건식 리포트

전체 score window:

```text
window_count: 300
scored_count: 300
avg_actual_return: 0.009420187285990119
hit_rate: 0.4
win_rate: 0.45666666666666667
profit_factor: 1.0515874052804386
```

주요 조건식:

```text
buy_candidate_score60:
  count: 61
  avg_score: 63.95274509784309
  avg_pred_return: 0.24310991685402727
  avg_actual_return: 0.032525486174057365
  hit_rate: 0.3770491803278688
  win_rate: 0.3770491803278688
  profit_factor: 1.263161159235278

score65_consistency80:
  count: 17
  avg_score: 66.64469616447495
  avg_pred_return: 0.5307497687798453
  avg_actual_return: 0.06817071944519162
  hit_rate: 0.4117647058823529
  win_rate: 0.4117647058823529
  profit_factor: 1.4871745581504239

stable_positive_filter:
  count: 7
  avg_score: 65.45998227102734
  avg_pred_return: 0.677440695032279
  avg_actual_return: 0.004440193675991562
  hit_rate: 0.5714285714285714
  win_rate: 0.5714285714285714
  profit_factor: 1.024478527562666
```

score band 성과:

```text
70+:
  count: 1
  avg_actual_return: 2.898550724637681
  hit_rate: 1.0
  win_rate: 1.0

60-70:
  count: 147
  avg_actual_return: 0.06514489156519303
  hit_rate: 0.36054421768707484
  win_rate: 0.46938775510204084

45-60:
  count: 130
  avg_actual_return: -0.01803253875671562
  hit_rate: 0.4076923076923077
  win_rate: 0.43846153846153846
```

해석:

```text
score 60 이상 구간은 평균 실제 등락률이 양수였지만 방향 hit는 아직 낮다.
score65_consistency80 조건은 표본은 작지만 profit_factor와 평균 실제 등락률이 더 좋다.
stable_positive_filter는 hit/win이 높아졌지만 평균 실제 등락률 개선은 약하다.
따라서 다음 단계에서는 거래대금/거래량/변동성/가격대 조건을 추가해야 한다.
```

### 11-4. 대시보드 변경

대시보드에 다음 영역을 추가했다.

```text
조건식 필터 백테스트 리포트
조건식 필터별 성과
Score 구간별 성과
종목/시간대 상위 성과
```

### 11-5. 검증

단위/route 검증:

```powershell
python -m pytest tests/test_stom_dashboard_helpers.py -q
```

결과:

```text
6 passed, 1 warning
```

추가 확인:

```text
알 수 없는 asof_timestamp는 unknown 시간대 bucket으로 분류하고 early_session_score60 조건에서 제외한다.
```

실제 파일 API 검증:

```text
/api/stom/backtest-report?file=kronos_all_predictions.csv -> 200
/api/stom/prediction?file=kronos_all_predictions.csv -> 200
```

전체 회귀 검증:

```powershell
python -m compileall -q finetune_csv webui tests docs
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py tests/test_cli_import_paths.py -q
python -m pip check
```

결과:

```text
16 passed, 1 warning
No broken requirements found.
```

웹 화면 검증:

```text
검증 URL: http://127.0.0.1:7075/stom?file=kronos_all_predictions.csv
screenshot: .omx/specs/stom-score-backtest-stage11/stom_score_backtest_stage11.png
file size: 212,694 bytes
검증 후 7075 포트 해제
```

## 12단계 완료 상세: STOM ?? ??용 CSV/JSON score export

이번 단계에서는 Kronos score/ranking 결과를 다른 종목 추천 프로그램에서 바로 읽을 수 있도록 **score export**를 추가했다. 이 기능은 대시보드 표시용 내부 자료구조를 외부 연동용 CSV/JSON schema로 고정하는 단계이다.

### 12-1. 추가/수정 파일

```text
webui/stom_dashboard.py
webui/app.py
webui/templates/stom_dashboard.html
tests/test_stom_dashboard_helpers.py
docs/stom_training_progress.md
```

### 12-2. 추가 API

```text
GET /api/stom/recommendation-export?file=kronos_all_predictions.csv&format=json&limit=20&filter=buy_candidate_score60
GET /api/stom/recommendation-export?file=kronos_all_predictions.csv&format=csv&limit=20&filter=buy_candidate_score60
```

지원 query:

```text
file: prediction CSV 파일명
format: json 또는 csv
limit: export 개수, 기본 20
filter: all_scored, buy_candidate_score60, score65_consistency80, score70_pred_return_0_5, stable_positive_filter, early_session_score60
min_score: 선택 입력
long_only: 1/0, 기본 1
```

### 12-3. Export schema

CSV/JSON record는 다음 필드를 고정해서 제공한다.

```text
rank
source_file
window_id
symbol
session
asof_timestamp
score export_action
signal
kronos_score
score_band
pred_return_pct
prediction_consistency
pred_range_pct
asof_minute_bucket
filter_labels
diagnostic_actual_return_pct
diagnostic_direction_hit
diagnostic_realized_mape
```

중요 원칙:

```text
score export_action, filter_labels, kronos_score, pred_return_pct, prediction_consistency, pred_range_pct는 live 사용 가능한 예측 기반 필드이다.
diagnostic_* 필드는 실제값 기반 검증용이므로 live 조건식/실전 필터에는 사용하지 않는다.
```

### 12-4. 실제 파일 API 검증

`kronos_all_predictions.csv` 기준:

```text
/api/stom/recommendation-export?file=kronos_all_predictions.csv&format=json&limit=5 -> 200
record_count: 5
first_symbol: 000040

/api/stom/recommendation-export?file=kronos_all_predictions.csv&format=csv&limit=5 -> 200
mimetype: text/csv
header: rank,source_file,window_id,symbol,session,asof_timestamp,score export_action,...
```

### 12-5. 대시보드 변경

좌측 패널에 다음 export 영역을 추가했다.

```text
Kronos Score Export
조건식 필터 선택
Export limit 입력
Min score 선택 입력
CSV 다운로드
JSON 새 창 열기
JSON preview
```

사용 흐름:

```text
1. /stom 접속
2. 예측 파일 선택
3. 조건식 필터 선택
4. CSV 다운로드 또는 JSON 열기
5. 외부 추천 프로그램에서 symbol, score, action, asof_timestamp 기준으로 후보를 읽는다.
```

### 12-6. 검증

단위/route 검증:

```powershell
python -m pytest tests/test_stom_dashboard_helpers.py -q
```

결과:

```text
7 passed, 1 warning
```

전체 회귀 검증:

```powershell
python -m compileall -q finetune_csv webui tests docs
python -m pytest tests/test_stom_tick_dataset.py tests/test_stom_training_cli.py tests/test_stom_prediction_eval.py tests/test_stom_dashboard_helpers.py tests/test_cli_import_paths.py -q
python -m pip check
```

결과:

```text
17 passed, 1 warning
No broken requirements found.
```

## 다음 단계: 외부 추천 프로그램 import 및 실전 조건식 강화

남은 활용 단계:

```text
1. ?? ?? ?? 또는 다른 종가종목 추천 프로그램에서 score export CSV/JSON을 읽는 import 예시 추가
2. 거래대금/거래량/변동성/가격대 조건식 추가
3. 수수료/슬리피지 반영 백테스트 지표 추가
4. 실제 장중/종가 후보 추천 워크플로우 연결
```

다음 OMX 명령 예시:

```text
$autopilot D:\Chanil_Park\Project\Programming\?? ?? ?? 프로그램에서 Kronos score export CSV/JSON을 읽어 종목 추천 점수에 반영하는 import 예시와 검증 코드를 추가하고 commit
```

### 대시보드 실행

```powershell
python webui\run.py
```

7070 충돌 시:

```powershell
$env:KRONOS_WEBUI_PORT='7071'
python webui\run.py
```

접속:

```text
http://localhost:7070/stom
또는
http://localhost:7071/stom
```

9단계 완료 확인 항목:

```text
1. export row/group 수가 예상 범위인지: 완료
2. GPU 학습 시간이 감당 가능한지: bounded 기준 약 56분으로 완료
3. OOM 없이 checkpoint가 저장되는지: 완료
4. 예측 CSV의 MAE/RMSE/MAPE/방향정확도가 파일럿 대비 개선/악화되는지: 완료, 다음 단계에서 score화 필요
5. 대시보드에서 신규 prediction 파일을 정상 표시하는지: 완료
```

## OMX 사용 기록

이번 단계에서는 다음 OMX 흐름을 사용했다.

```text
1. autopilot 성격의 자율 진행: 단계 산출물 생성, 검증, 문서화, commit까지 연결
2. note 성격의 진행 기록을 .omx/notepad.md에 보존
3. code-review 성격의 diff 자체 점검: 변경 범위가 config/문서 중심인지 확인
4. explore 시도: Windows POSIX 래퍼 미지원으로 실패
5. sparkshell 시도: 현재 세션에서 program not found로 실패
6. 일반 PowerShell fallback으로 export/train/predict/dashboard/test 검증 지속
7. 전체 9GB CSV 직접 학습 병목 발견 후 bounded export 기능으로 복구
```

## Commit 관리 원칙

각 단계 완료 시 다음을 commit한다.

```text
1. 코드 변경
2. 테스트/검증 결과가 반영된 문서
3. 현재 단계/다음 단계/남은 단계 진행표
4. 실행 명령과 산출물 위치
```

대용량 산출물은 commit하지 않는다.

```text
_database/
finetune_csv/data/stom_*.csv
finetune_csv/finetuned/
webui/stom_predictions/*.csv
webui/stom_predictions/*.json
모델 checkpoint
```

## 2026-05-09 pred60 대형 walk-forward 게이트 중간 점검

상세 보고서: `docs/stom_1s_large_walkforward_gate_report.md`

이번 단계에서 `expand_200k` 학습을 바로 실행하지 않고, 먼저 pred60 `budget_20k` checkpoint를 대형 walk-forward와 rolling validation으로 검증했다.

결과 요약:

| 항목 | 값 |
| --- | ---: |
| selected windows | 3,080 |
| periods | 500 |
| Kronos direction accuracy | 0.4312 |
| random direction accuracy | 0.4084 |
| Qlib Top-K avg net return | -0.1953% |
| robust filter avg net return | -0.1266% |
| rolling avg test net return | -0.1766% |
| rolling positive fold rate | 0.25 |

결론은 `expand_200k` 실제 학습 보류다. 현재 모델은 random보다 방향성 신호가 조금 높지만, 비용 후 수익성과 rolling 안정성이 부족하다. 따라서 다음 단계는 학습량 확대가 아니라 score/filter 리디자인과 비용 민감도 분석이다.

```text
전체 데이터셋 구축                      [█████] 100%
학습 루프 연결                          [█████] 100%
20k budgeted 학습                       [█████] 100%
대형 walk-forward 게이트 검증            [█████] 95%
200k 확대 학습 실행                     [░░░░░] 0%  게이트 미충족으로 보류
전체 진행률                              [█████░] 91%
```

## 2026-05-09 cost sensitivity gate 자동화

상세 보고서: `docs/stom_1s_cost_gate_analysis_report.md`

이번 단계에서 기존 filter-search와 rolling-validation 결과를 재사용해 비용 민감도와 확대 학습 승인 여부를 자동 계산하는 gate를 추가했다.

실행 명령:

```powershell
python finetune\search_stom_1s_filters.py `
  --gate-analysis `
  --filter-report webui\qlib_backtests\stom_1s_pred60_walkforward100x5x50_eval_kronos.filter_search.json `
  --rolling-report webui\qlib_backtests\stom_1s_pred60_walkforward100x5x50_eval_kronos_rolling100x50.rolling_filter_validation.json `
  --total-cost-bps-grid 5,10,15,25 `
  --target-total-cost-bps 25
```

결과:

| total cost | rolling avg test net | positive fold rate | gate |
| ---: | ---: | ---: | --- |
| 5bp | +0.0234% | 0.500 | PASS |
| 10bp | -0.0266% | 0.375 | FAIL |
| 15bp | -0.0766% | 0.375 | FAIL |
| 25bp | -0.1766% | 0.250 | FAIL |

핵심 판단:

```text
target 25bp gate: FAIL
expand_200k: 보류
다음 단계: score/filter 리디자인 또는 pred30/pred60 ensemble 후보 검증
```

진행률:

```text
전체 데이터셋 구축                      [█████] 100%
학습 루프 연결                          [█████] 100%
20k budgeted 학습                       [█████] 100%
대형 walk-forward/rolling/gate 검증      [█████] 96%
웹 대시보드 gate artifact 표시           [████░] 88%
200k 확대 학습 실행                     [░░░░░] 0%  target gate 미충족
전체 진행률                              [█████░] 93%
```

## 2026-05-12 STOM 2025 full training live checkpoint 08

상세 보고서: `docs/stom_2025_full_training_progress_checkpoint_08.md`

이번 단계는 자동 새로고침 대시보드 구현 이후, 실제 long-running full training이 계속 살아 있는지 검증하는 중간 점검이다.

핵심 결과:

- `tokenizer` 단계 running
- step `920000 / 4701721`
- tokenizer 진행률 `19.5673%`
- 전체 both-stage 진행률 `9.7837%`
- 70초 간격으로 `918000 -> 919000` step 증가 확인
- checkpoint/model weight는 아직 없음
- predictor 전환 전
- `/training?refresh_interval=10`, `/?refresh_interval=10`, `/stom?refresh_interval=10` HTTP 응답 및 자동 갱신 UI 확인

진행률:

```text
데이터/실행 준비                          [████████████████████] 100%
웹 대시보드 자동 갱신 통합                [████████████████████] 100%
tokenizer 학습                            [████░░░░░░░░░░░░░░░░] 19.57%
전체 both-stage 학습                       [██░░░░░░░░░░░░░░░░░░] 9.78%
predictor 학습                             [░░░░░░░░░░░░░░░░░░░░] 0.00%
예측 CSV/실제값 비교 대시보드 성과 검증    [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 2026-05-12 STOM 2025 full training live checkpoint 09

상세 보고서: `docs/stom_2025_full_training_progress_checkpoint_09.md`

이번 단계는 checkpoint 08 이후 long-running 학습이 계속 진행되는지 다시 검증한 중간 점검이다.

핵심 결과:

- `tokenizer` 단계 running
- step `1,020,000 / 4,701,721`
- tokenizer 진행률 `21.6942%`
- 전체 both-stage 진행률 `10.8471%`
- checkpoint 08 대비 `+98,000 step` 증가
- 75초 간격으로 `1,019,000 -> 1,020,000` step 증가 확인
- checkpoint/model weight는 아직 없음
- predictor 전환 전
- `/training?refresh_interval=10`, `/?refresh_interval=10`, `/stom?refresh_interval=10` HTTP 응답 및 자동 갱신 UI 확인

진행률:

```text
데이터/실행 준비                          [████████████████████] 100%
웹 대시보드 자동 갱신 통합                [████████████████████] 100%
tokenizer 학습                            [████░░░░░░░░░░░░░░░░] 21.69%
전체 both-stage 학습                       [██░░░░░░░░░░░░░░░░░░] 10.85%
predictor 학습                             [░░░░░░░░░░░░░░░░░░░░] 0.00%
예측 CSV/실제값 비교 대시보드 성과 검증    [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 2026-05-12 STOM 2025 full training live checkpoint 10

상세 보고서: `docs/stom_2025_full_training_progress_checkpoint_10.md`

이번 단계는 checkpoint 09 이후 long-running 학습이 계속 진행되는지 다시 검증한 중간 점검이다.

핵심 결과:

- `tokenizer` 단계 running
- step `1,079,000 / 4,701,721`
- tokenizer 진행률 `22.9490%`
- 전체 both-stage 진행률 `11.4745%`
- checkpoint 09 대비 `+59,000 step` 증가
- 75초 간격으로 `1,078,000 -> 1,079,000` step 증가 확인
- checkpoint/model weight는 아직 없음
- predictor 전환 전
- `/training?refresh_interval=10`, `/?refresh_interval=10`, `/stom?refresh_interval=10` HTTP 응답 및 자동 갱신 UI 확인

진행률:

```text
데이터/실행 준비                          [████████████████████] 100%
웹 대시보드 자동 갱신 통합                [████████████████████] 100%
tokenizer 학습                            [█████░░░░░░░░░░░░░░░] 22.95%
전체 both-stage 학습                       [██░░░░░░░░░░░░░░░░░░] 11.47%
predictor 학습                             [░░░░░░░░░░░░░░░░░░░░] 0.00%
예측 CSV/실제값 비교 대시보드 성과 검증    [░░░░░░░░░░░░░░░░░░░░] 0.00%
```

## 2026-05-12 STOM 2025 full training live checkpoint 11

상세 보고서: `docs/stom_2025_full_training_progress_checkpoint_11.md`

이번 단계는 checkpoint 10 이후 long-running 학습이 계속 진행되는지 다시 검증한 중간 점검이다.

핵심 결과:

- `tokenizer` 단계 running
- step `1,136,000 / 4,701,721`
- tokenizer 진행률 `24.1614%`
- 전체 both-stage 진행률 `12.0807%`
- checkpoint 10 대비 `+57,000 step` 증가
- 75초 간격으로 `1,134,000 -> 1,136,000` step 증가 확인
- checkpoint/model weight는 아직 없음
- predictor 전환 전
- `/training?refresh_interval=10`, `/?refresh_interval=10`, `/stom?refresh_interval=10` HTTP 응답 및 자동 갱신 UI 확인

진행률:

```text
데이터/실행 준비                          [████████████████████] 100%
웹 대시보드 자동 갱신 통합                [████████████████████] 100%
tokenizer 학습                            [█████░░░░░░░░░░░░░░░] 24.16%
전체 both-stage 학습                       [██░░░░░░░░░░░░░░░░░░] 12.08%
predictor 학습                             [░░░░░░░░░░░░░░░░░░░░] 0.00%
예측 CSV/실제값 비교 대시보드 성과 검증    [░░░░░░░░░░░░░░░░░░░░] 0.00%
```
