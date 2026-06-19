# STOM 2025 predictor 최대 효율 전환 준비

작성일: 2026-05-13 KST

## 목표

현재 실행 중인 `stom_1s_grid_pred60_2025_full_small` tokenizer 학습은 중단하지 않는다. tokenizer checkpoint가 생성된 뒤 predictor 단계는 가능한 한 GPU를 더 잘 쓰는 설정으로 실행할 수 있게 준비한다.

## 핵심 제약

- 현재 실행 중인 부모 프로세스는 이미 다음 인자로 시작됐다.
  - `--train-stage both`
  - `--batch-size 4`
  - `--num-workers 0`
- 이 프로세스는 메모리에 로드된 기존 Python 코드/인자를 사용하므로, 이번 코드 변경이 현재 살아 있는 부모 프로세스의 자동 predictor 실행에는 소급 적용되지 않는다.
- 따라서 현재 run에서 predictor를 고효율로 실행하려면 tokenizer checkpoint 확인 후 predictor-only를 별도로 시작하는 제어 전환이 필요하다.

## 이번 준비 변경

`finetune/run_stom_1s_finetune.py`에 stage별 효율 옵션을 추가했다.

- 공통 기존 옵션
  - `--batch-size`
  - `--num-workers`
- 신규 stage별 옵션
  - `--tokenizer-batch-size`
  - `--predictor-batch-size`
  - `--tokenizer-num-workers`
  - `--predictor-num-workers`

미래의 `--train-stage both` 실행에서는 tokenizer는 안정 설정, predictor는 고효율 설정처럼 분리할 수 있다.

예시:

```powershell
C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage both `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets `
  --run-name stom_1s_grid_pred60_2025_full_small `
  --dataset-sample-mode full_sequential `
  --batch-size 4 `
  --num-workers 0 `
  --predictor-batch-size 16 `
  --predictor-num-workers 2 `
  --n-train-iter 18806883 `
  --n-val-iter 3925397 `
  --log-interval 1000
```

## 현재 진행 중인 run의 안전 전환 절차

1. tokenizer 100% 도달을 기다린다.
2. 아래 checkpoint가 실제 생성됐는지 확인한다.

```text
finetune\outputs\stom_1s_grid_pred60_2025_full_small\finetune_tokenizer\checkpoints\best_model
```

3. checkpoint 확인 전에는 PC 재부팅, 학습 프로세스 종료, 절전 진입을 피한다.
4. checkpoint 확인 후 자동 predictor가 기존 `batch_size=4`, `num_workers=0`으로 시작되면 즉시 상태를 기록하고 predictor-only 고효율 run으로 전환한다.
5. 전환 시 원본 tokenizer checkpoint는 그대로 사용한다.

## predictor 고효율 벤치마크 후보

먼저 짧은 budget으로 2~4개 후보를 비교한다. 핵심 지표는 `samples/sec`, GPU 사용률, VRAM, RAM, validation loss다.

| 후보 | batch size | workers | 목적 |
|---|---:|---:|---|
| 안전 | 8 | 0 | 현재와 가장 유사하지만 batch 증가 |
| 1차 추천 | 16 | 0 | Windows worker 복제 리스크 없이 GPU 사용 증가 |
| 2차 추천 | 16 | 2 | 데이터 공급 병목 완화 |
| 공격적 | 24 또는 32 | 2 | VRAM 여유 활용, 안정성 확인 필요 |

## predictor-only 벤치마크 명령 예시

```powershell
$tok = "D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\finetune_tokenizer\checkpoints\best_model"

C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage predictor `
  --sample-stage budget_20k `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets `
  --run-name stom_1s_grid_pred60_2025_predictor_bench_bs16_w2 `
  --dataset-sample-mode full_sequential `
  --batch-size 16 `
  --num-workers 2 `
  --finetuned-tokenizer-path $tok `
  --log-interval 1000
```

## predictor 본학습 추천 시작 명령

벤치마크에서 문제가 없으면 아래 설정을 1차 본학습 후보로 사용한다.

```powershell
$tok = "D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\finetune_tokenizer\checkpoints\best_model"

C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage predictor `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets `
  --run-name stom_1s_grid_pred60_2025_full_small_predictor_opt_bs16_w2 `
  --dataset-sample-mode full_sequential `
  --batch-size 16 `
  --num-workers 2 `
  --n-train-iter 18806883 `
  --n-val-iter 3925397 `
  --finetuned-tokenizer-path $tok `
  --log-interval 1000
```

## 예상 완료 시간 영향

현재 측정 기준에서 predictor를 기존 설정 그대로 돌리면 전체 완료는 대략 2026-05-18~19 KST다. predictor 전에 최적화하면 대략 다음 범위를 기대한다.

| predictor 개선 | 전체 완료 예상 |
|---:|---|
| 1.4x | 2026-05-17 밤 ~ 2026-05-18 |
| 1.8x | 2026-05-17 새벽~오전 |
| 2.2x | 2026-05-16 밤 ~ 2026-05-17 |

## 중단 조건

- tokenizer checkpoint가 없으면 predictor 최적화 전환을 실행하지 않는다.
- `batch_size=16, workers=2`에서 OOM, RAM 급증, DataLoader 정지, samples/sec 저하가 보이면 `workers=0` 또는 `batch_size=8`로 낮춘다.
- validation loss가 기존 설정 대비 명확히 악화되면 속도보다 안정 설정을 우선한다.
