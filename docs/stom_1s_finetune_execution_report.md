# STOM 1초봉 Kronos 파인튜닝 실행 보고서

작성일: 2026-05-08

## 1. 결론

전체 STOM 1초봉 QlibDataset export 산출물을 사용해 Kronos predictor 파인튜닝 실행 경로를 실제로 검증했다. Windows + RTX 4080 SUPER 워크스테이션에서는 `torchrun`/NCCL 고정 경로가 아니라 **single GPU non-DDP 실행 경로**가 안정적으로 동작했다.

이번 단계에서 확인한 것:

- pred30/pred60 전체 `processed_datasets`가 실제 학습 루프에 로드된다.
- pretrained `NeoQuasar/Kronos-Tokenizer-base`, `NeoQuasar/Kronos-small` fallback이 동작한다.
- `comet_ml` 미설치 상태에서도 `KRONOS_USE_COMET=0`로 학습이 가능하다.
- full export 전체 sample pool에서 budgeted full run을 수행하고 checkpoint를 저장했다.

아직 확인하지 않은 것:

- `direction_accuracy`, Top-K 수익률, 실제값/예측값 시각화는 아직 아니다.
- 이번 metric은 Kronos predictor token loss 기반 `best_val_loss`이며, 매매 성과 정확도와 동일하지 않다.
- 다음 단계에서 생성된 checkpoint로 prediction CSV를 만들고 holdout actual과 비교해야 한다.

## 2. 실행 보강 내용

| 파일 | 내용 |
| --- | --- |
| `finetune/run_stom_1s_finetune.py` | STOM 1초봉 pred30/pred60 학습 launcher 추가 |
| `finetune/train_predictor.py` | single GPU non-DDP, optional Comet, pretrained fallback 지원 |
| `finetune/utils/training_utils.py` | Windows에서 NCCL 고정 대신 backend 자동 선택 및 DDP 비활성 지원 |
| `finetune/config.py` | `KRONOS_NUM_WORKERS`, finetuned model path env override 추가 |
| `.gitignore` | 대용량 `finetune/outputs/` 산출물 제외 |

## 3. 실행 환경

```text
GPU: NVIDIA GeForce RTX 4080 SUPER
VRAM: 16 GiB
Torch: 2.9.0+cu128
CUDA available: True
CUDA version: 12.8
DDP mode: disabled for single GPU
```

Windows 실행에서 필요한 핵심 env:

```text
KRONOS_DISABLE_DDP=1
KRONOS_USE_COMET=0
KRONOS_DDP_BACKEND=gloo
USE_LIBUV=0
WORLD_SIZE=1
LOCAL_RANK=0
```

## 4. 실행 결과

### 4.1 전체 데이터 smoke

| horizon | train possible samples | val possible samples | used train | used val | best val loss | duration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30초 | 75,277,195 | 16,275,307 | 2 | 2 | 2.8061 | 212.86s |
| 60초 | 73,718,875 | 15,938,107 | 2 | 2 | 1.9724 | 211.90s |

### 4.2 stage run

| horizon | used train | used val | batch | steps | best val loss | duration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30초 | 512 | 128 | 4 | 128 | 2.3093 | 223.57s |
| 60초 | 512 | 128 | 4 | 128 | 2.2624 | 221.84s |

### 4.3 budgeted full run

| horizon | used train | used val | batch | steps | best val loss | duration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30초 | 20,000 | 4,000 | 4 | 5,000 | 2.1549 | 550.89s |
| 60초 | 20,000 | 4,000 | 4 | 5,000 | 2.1302 | 549.04s |

생성 checkpoint:

```text
finetune/outputs/stom_1s_grid_pred30_full_budget/finetune_predictor/checkpoints/best_model
finetune/outputs/stom_1s_grid_pred60_full_budget/finetune_predictor/checkpoints/best_model
```

주의: `finetune/outputs/`는 대용량 모델 산출물이므로 git에 commit하지 않는다. 대신 실행 manifest와 요약 결과를 이 문서에 고정한다.

## 5. 재실행 명령

### 5.1 30초 budgeted full run

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 30 `
  --mode full `
  --output-root finetune\outputs `
  --run-name stom_1s_grid_pred30_full_budget
```

### 5.2 60초 budgeted full run

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --output-root finetune\outputs `
  --run-name stom_1s_grid_pred60_full_budget
```

## 6. 현재 해석

이번 결과는 “전체 STOM tick DB로 Kronos 파인튜닝이 가능한가?”에 대해서는 **가능**으로 판단한다. 실제 전체 export pickle을 로드했고, 7천만 개 이상의 가능한 train window pool에서 샘플링해 GPU 학습 및 checkpoint 저장까지 완료했다.

다만 “정확도가 0.4보다 좋아졌는가?”는 아직 답할 수 없다. 현재 `best_val_loss`는 tokenizer token prediction loss이므로 매매 방향 정확도와 직접 비교할 수 없다. 다음 단계는 다음 두 가지를 구현/실행해야 한다.

1. budgeted checkpoint로 test session prediction CSV 생성
2. persistence/random/기존 0.40 모델과 동일 holdout 기준 direction accuracy 및 Top-K 성과 비교
