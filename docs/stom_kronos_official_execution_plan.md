# STOM tick Kronos 공식 준수 실행 계획

작성일: 2026-05-09

## 1. 반드시 기억할 최종 원칙

Kronos 공식 README 기준의 fine-tuning 순서는 다음이다.

```text
Config 설정
-> Qlib/STOM 데이터 준비
-> Tokenizer fine-tuning
-> Predictor fine-tuning
-> Backtesting / evaluation / visualization
```

따라서 지금부터의 공식 준수 작업은 `pretrained tokenizer + predictor만 fine-tuning`이 아니라,
**STOM 데이터로 tokenizer를 먼저 fine-tuning하고 그 tokenizer checkpoint로 predictor를 fine-tuning**하는 흐름이다.

## 2. 1~8 단계

| 단계 | 목적 | 현재 상태 |
| --- | --- | --- |
| 1 | tokenizer 학습 경로 안정화 | 완료/커밋 대기 |
| 2 | tokenizer 20k benchmark로 시간 계수 측정 | 예정 |
| 3 | pred60 tokenizer expand_200k 실행 | 예정 |
| 4 | pred60 predictor expand_200k 실행 | 예정 |
| 5 | holdout 실제값 vs 예측값 그래프 생성 | 예정 |
| 6 | 성과 보고서 작성 | 예정 |
| 7 | pred30 진행 여부 판단 | 예정 |
| 8 | 1M/5M/full-window 확대 안내 | 예정 |

## 3. pred 길이 결정

우선순위는 `pred60`이다.

```text
lookback_window = 300
predict_window = 60
```

`pred30`은 학습 목표가 다른 별도 모델이므로 pred60 official pilot 결과를 보고 반복 여부를 판단한다.

## 4. full-window의 정확한 의미

기존 dataset 기본 동작은 전체 possible window에서 무작위 샘플링하는 방식이다. “전체 window를 학습했다”고 말하려면 `full_sequential` 방식이 필요하다.

인정 기준:

```text
visited_window_count == total_available_windows
unique_visited_window_count == total_available_windows
duplicate_count == 0
missing_count == 0
```

이번 1단계에서 `sample_random`과 `full_sequential` mode를 코드에서 분리했다.

## 5. 대형 실행 확대 기준

200k official pilot은 공식 절차와 그래프 확인 목적이다. 수익성 승인 단계가 아니다.

1M/5M/full-window 성과 목적 확대에는 다음 중 하나가 필요하다.

```text
1. target 25bp cost_sensitivity_gate 통과
2. 사용자가 수익성 근거 없이도 공식 준수 대형 실행을 하겠다고 명시적으로 override
```

## 6. 현재 예상 시간

| 범위 | pred60 예상 |
| --- | ---: |
| tokenizer 20k benchmark | 약 7~15분 |
| pred60 tokenizer 200k | 약 1.2~3시간 |
| pred60 predictor 200k | 약 1.5~2시간 |
| pred60 200k 예측/그래프 검증 | 약 40~60분 |
| pred60 official 200k 전체 | 약 3~5시간 |
| pred60 official full-window | 약 40~75시간 |

시간은 기존 predictor 20k 실측 549초를 기준으로 한 추정이며, tokenizer는 20k benchmark 후 재계산한다.

## 7. 1단계 검증 근거

- `KRONOS_DATASET_SAMPLE_MODE=sample_random|full_sequential` 지원 추가.
- tokenizer/predictor 학습 runner에 `--train-stage tokenizer|predictor|both` 추가.
- `both` 실행 시 tokenizer checkpoint를 predictor 학습에 자동 전달.
- Windows 단일 GPU/단일 프로세스에서도 tokenizer 학습 스크립트 실행 가능하도록 DDP 필수 조건 완화.
- 테스트: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1; C:\Python\64\Python3119\python.exe -m pytest tests\test_stom_1s_finetune_runner.py -q` → 6 passed.
- 컴파일: `C:\Python\64\Python3119\python.exe -m compileall finetune\config.py finetune\dataset.py finetune\run_stom_1s_finetune.py finetune\train_predictor.py finetune\train_tokenizer.py tests\test_stom_1s_finetune_runner.py` → 성공.
- dry-run: pred60 `--train-stage both --sample-stage budget_20k --dataset-sample-mode full_sequential` → tokenizer/predictor manifest 생성 및 handoff 확인.

주의: 기본 pytest 플러그인 자동 로딩 상태에서는 Windows PyTorch DLL 초기화 오류가 발생했다. 실제 Python 프로세스의 `import torch`와 플러그인 비활성화 테스트는 정상이다.

## 8. 2단계 tokenizer 20k benchmark 실측 결과

실행 명령:

```powershell
C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage tokenizer `
  --sample-stage budget_20k `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets `
  --output-root finetune\outputs `
  --run-name stom_1s_grid_pred60_official_tokenizer_20k `
  --dataset-sample-mode full_sequential `
  --batch-size 4 `
  --num-workers 0 `
  --log-interval 100
```

실측 결과:

| 항목 | 값 |
| --- | ---: |
| train possible windows | 73,718,875 |
| val possible windows | 15,938,107 |
| 실제 train samples | 20,000 |
| 실제 val samples | 4,000 |
| train steps | 5,000 |
| val steps | 1,000 |
| duration_seconds | 567.944628초 |
| 총 경과 | 약 9분 28초 |
| best tokenizer val_loss | 0.004013419676455669 |
| checkpoint | `finetune/outputs/stom_1s_grid_pred60_official_tokenizer_20k/finetune_tokenizer/checkpoints/best_model` |

이 실측을 단순 선형 환산하면 tokenizer 학습 예상 시간은 다음이다.

| tokenizer 범위 | 단순 환산 시간 |
| --- | ---: |
| 200k | 약 1.58시간 |
| 1M | 약 7.89시간 |
| 5M | 약 39.44시간 |
| pred60 train full-window 73,718,875 | 약 581.5시간, 약 24.2일 |

주의: full-window 환산은 train sample 기준의 보수적 단순 환산이며, 전체 validation을 같이 full로 돌리면 더 길어진다. 따라서 8단계 대형 확대는 반드시 목적을 분리해야 한다.

## 9. 3단계 pred60 tokenizer 200k 실행 결과

실행 명령:

```powershell
C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage tokenizer `
  --sample-stage expand_200k `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets `
  --output-root finetune\outputs `
  --run-name stom_1s_grid_pred60_official_200k `
  --dataset-sample-mode full_sequential `
  --batch-size 4 `
  --num-workers 0 `
  --log-interval 1000
```

실측 결과:

| 항목 | 값 |
| --- | ---: |
| train possible windows | 73,718,875 |
| val possible windows | 15,938,107 |
| 실제 train samples | 200,000 |
| 실제 val samples | 40,000 |
| train steps | 50,000 |
| val steps | 10,000 |
| duration_seconds | 3,211.134006초 |
| 총 경과 | 약 53분 31초 |
| best tokenizer val_loss | 0.002904271284851711 |
| checkpoint | `finetune/outputs/stom_1s_grid_pred60_official_200k/finetune_tokenizer/checkpoints/best_model` |

20k 대비 val_loss는 0.004013 → 0.002904로 개선되었다. 다음 단계는 이 tokenizer checkpoint를 `KRONOS_FINETUNED_TOKENIZER_PATH`로 predictor 200k 학습에 전달하는 것이다.

## 10. 4단계 pred60 predictor 200k 실행 결과

실행 명령:

```powershell
C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage predictor `
  --sample-stage expand_200k `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets `
  --output-root finetune\outputs `
  --run-name stom_1s_grid_pred60_official_200k `
  --dataset-sample-mode full_sequential `
  --finetuned-tokenizer-path finetune\outputs\stom_1s_grid_pred60_official_200k\finetune_tokenizer\checkpoints\best_model `
  --batch-size 4 `
  --num-workers 0 `
  --log-interval 1000
```

실측 결과:

| 항목 | 값 |
| --- | ---: |
| train samples | 200,000 |
| val samples | 40,000 |
| train steps | 50,000 |
| duration_seconds | 4,129.433555초 |
| 총 경과 | 약 1시간 8분 49초 |
| best predictor val_loss | 2.131037336307764 |
| tokenizer source | `finetune/outputs/stom_1s_grid_pred60_official_200k/finetune_tokenizer/checkpoints/best_model` |
| predictor checkpoint | `finetune/outputs/stom_1s_grid_pred60_official_200k/finetune_predictor/checkpoints/best_model` |

이 단계로 공식 순서의 핵심인 `STOM tokenizer fine-tuning -> STOM predictor fine-tuning` 흐름은 실제 checkpoint 기준으로 완료되었다. 다음 단계는 이 모델을 holdout/walk-forward 데이터에 적용하여 실제값과 예측값을 그래프 및 성과 지표로 비교하는 것이다.

## 11. 5단계 holdout 실제값 vs 예측값 시각화 산출물

실행 명령:

```powershell
C:\Python\64\Python3119\python.exe finetune\evaluate_stom_1s_checkpoint.py `
  --dataset-path finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets `
  --model-path finetune\outputs\stom_1s_grid_pred60_official_200k\finetune_predictor\checkpoints\best_model `
  --tokenizer-path finetune\outputs\stom_1s_grid_pred60_official_200k\finetune_tokenizer\checkpoints\best_model `
  --output-dir webui\stom_predictions `
  --prefix stom_1s_pred60_official200k_walkforward100x5x50_eval `
  --lookback-window 300 `
  --predict-window 60 `
  --max-symbols 50 `
  --max-asofs 5 `
  --max-sessions 100 `
  --stride 300 `
  --batch-size 4 `
  --top-k 5 `
  --device cuda:0
```

산출물:

| 파일 | 목적 |
| --- | --- |
| `webui/stom_predictions/stom_1s_pred60_official200k_walkforward100x5x50_eval_kronos.csv` | Kronos 실제값/예측값 행 단위 비교 |
| `webui/stom_predictions/stom_1s_pred60_official200k_walkforward100x5x50_eval_persistence.csv` | persistence baseline 비교 |
| `webui/stom_predictions/stom_1s_pred60_official200k_walkforward100x5x50_eval_random.csv` | random baseline 비교 |
| `webui/stom_predictions/stom_1s_pred60_official200k_walkforward100x5x50_eval_comparison.json` | 모델별 요약 metric |

평가 결과:

| 항목 | Kronos official 200k |
| --- | ---: |
| rows | 184,800 |
| windows | 3,080 |
| symbols | 334 |
| periods/asof | 500 |
| MAE | 173.0052 |
| RMSE | 441.4880 |
| MAPE | 0.3382% |
| 방향 정확도 | 0.4188 |
| Top-K hit rate | 0.4146 |
| avg pred return | -0.0073% |
| avg actual return | 0.0504% |

웹 대시보드 검증:

```text
GET /api/stom/prediction?file=stom_1s_pred60_official200k_walkforward100x5x50_eval_kronos.csv&window_id=0
status=200
metrics.windows=3080
chart JSON length=12391
```

즉, `/stom` 대시보드에서 위 CSV를 선택하면 실제 close와 예측 close 그래프를 확인할 수 있다.

추가로 filter search가 반복 groupby 때문에 10분 이상 지연되어, 동일 의미를 유지하면서 `sort_values(...).groupby(...).head(top_k)` 방식으로 최적화했다. 최적화 후 filter search는 약 109초, rolling validation은 약 255초에 완료됐다.

## 12. 6단계 성과 보고서

상세 보고서는 다음 파일에 작성했다.

```text
docs/stom_kronos_official_200k_result_report.md
```

핵심 결론:

- 공식 학습 절차와 대시보드 시각화는 성공.
- 방향 정확도 0.4188로 random 0.4084보다 약간 높지만 실전 edge로 보기 어렵다.
- 25bp 비용 반영 Top-K net return은 -0.1989%로 음수.
- 조건식/필터 최적화 후에도 best filter net return은 -0.1739%로 음수.
- rolling cost gate 결과는 `hold_expand_200k`, `expand_training_allowed=false`.

## 13. 7단계 pred30 진행 여부 판단

결론: **지금 즉시 pred30 200k/full-window 학습으로 확대하지 않는다.**

이유:

1. pred60 official 200k가 25bp cost gate를 통과하지 못했다.
2. 공식 200k pred60의 방향 정확도 0.4188은 random 0.4084 대비 약한 개선에 그쳤다.
3. Top-K net return은 25bp 비용 반영 후 -0.1989%로 음수다.
4. pred30은 별도 tokenizer/predictor 모델이 필요하므로 최소 2~3시간 이상의 추가 학습/평가 시간이 든다.
5. pred30이 더 짧은 horizon이라 비용 대비 기대수익폭이 더 작아질 가능성이 있다.

단, pred30을 완전히 버리는 것은 아니다. 다음 조건 중 하나가 있으면 pred30으로 진행한다.

| 조건 | 권장 실행 |
| --- | --- |
| 사용자가 연구 목적으로 pred30도 비교하겠다고 명시 | pred30 tokenizer 20k → predictor 20k → quick holdout |
| pred60에서 비용을 낮춘 환경, 예: 5bp 이하, 에서 gate 통과 | pred30 200k 비교 가능 |
| 종가/분봉/더 긴 horizon에서 edge가 확인됨 | pred30은 후순위 실험으로 유지 |
| 전체 데이터 공식 학습 자체가 목적이며 수익성 gate를 무시한다고 명시 | pred30도 full-window 장시간 계획에 포함 가능 |

현재 권장 순서:

```text
1. pred60 official 200k 결과를 대시보드에서 눈으로 확인
2. 8단계에서 1M/5M/full-window 확대 여부를 목적별로 결정
3. 수익성 목적이면 pred30보다 먼저 비용 구조, 거래 horizon, score filter 개선
4. 연구 목적이면 pred30은 20k benchmark부터 작게 비교
```

## 14. 8단계 안내 문서

8단계 확대 안내는 다음 파일에 작성했다.

```text
docs/stom_kronos_stage8_expansion_guide.md
```

핵심:

- 수익성 목적이면 현재는 확대 보류.
- 연구 목적이면 1M부터 `sample_random`으로 대표성 있게 재시작 권장.
- 전체 window exact 목적이면 `full_sequential + full_window`가 필요하지만 pred60 기준 약 31일 이상 예상.
