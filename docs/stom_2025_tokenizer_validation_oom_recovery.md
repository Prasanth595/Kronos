# STOM 2025 full tokenizer validation OOM 실패 분석 및 복구 노하우

작성일: 2026-05-15 KST
대상 run: `stom_1s_grid_pred60_2025_full_small`
대상 데이터: STOM 1초봉 2025 QlibDataset, pred60, full sequential 계열

## 1. 현재 실패 현황

| 항목 | 확인 내용 |
| --- | --- |
| 실패 단계 | tokenizer fine-tuning |
| 실패 시각 | 2026-05-15 00:39:03 KST (`2026-05-14T15:39:03Z`) |
| return code | `1` |
| 마지막 기록 진행률 | tokenizer 99.9847%, 전체 49.9923% |
| 마지막 train step 로그 | `4701000 / 4701721` |
| predictor 단계 | 시작하지 않음 |
| tokenizer checkpoint | 없음 |
| 웹 대시보드 | 실패 확인 시점에 `127.0.0.1:5070` 연결 불가 |

주의: 99.9847%는 마지막으로 파싱된 학습 로그 기준이다. 실제로는 학습 루프가 끝나고 validation 단계로 넘어간 뒤 CUDA OOM으로 실패했으므로, “완료된 모델”이 생성된 것은 아니다.

## 2. 직접 증거

### 2.1 manifest / progress

- `finetune/outputs/stom_1s_grid_pred60_2025_full_small/tokenizer_run_manifest.json`
  - `status: failed`
  - `returncode: 1`
  - `completed_at: 2026-05-14T15:39:03Z`
- `finetune/outputs/stom_1s_grid_pred60_2025_full_small/logs/tokenizer.progress.json`
  - `status: failed`
  - `progress.step: 4701000`
  - `progress.total_steps: 4701721`
  - `stage.percent: 99.9847`
  - `metrics.best_model_path: null`
- `finetune/outputs/stom_1s_grid_pred60_2025_full_small/run_manifest.json`
  - predictor manifest는 `dry_run` 상태로 남아 있었다.
- `finetune/outputs/stom_1s_grid_pred60_2025_full_small/logs/predictor.progress.json`
  - 존재하지 않았다.

### 2.2 stdout traceback

`logs/tokenizer.stdout.log` 마지막 구간에 다음 실패가 기록되었다.

```text
[Rank 0, Epoch 1/1, Step 4701000/4701721] LR 0.000000, Loss: -0.0274
Traceback (most recent call last):
  File "D:\Chanil_Park\Project\Programming\Kronos\finetune\train_tokenizer.py", line 196, in train_model
    zs, _, _, _ = model(ori_batch_x)
torch.AcceleratorError: CUDA error: out of memory
```

실패 지점은 `finetune/train_tokenizer.py`의 validation loop 내부 forward pass이다.

## 3. 원인 분석

### 3.1 1차 원인: validation forward 중 CUDA OOM

학습이 끝난 뒤 아래 validation loop에서 GPU 메모리 할당이 실패했다.

```python
model.eval()
with torch.no_grad():
    for ori_batch_x, _ in val_loader:
        ori_batch_x = ori_batch_x.to(device, non_blocking=True)
        zs, _, _, _ = model(ori_batch_x)
```

이번 run은 tokenizer train batch size가 4였고 validation batch도 같은 값을 사용했다. 장시간 학습 후 validation으로 전환될 때 마지막 train tensor/optimizer gradient/캐시/Windows WDDM 환경의 VRAM 단편화 등이 겹치면 validation 첫 구간 또는 초반 forward에서 OOM이 날 수 있다.

### 3.2 왜 83시간 가까운 학습분이 모델로 남지 않았나

기존 코드에서는 checkpoint 저장이 validation loss 계산 뒤에만 실행되었다.

흐름:

1. train loop
2. validation loop
3. validation loss 계산
4. `checkpoints/best_model` 저장

이번 실패는 2번 validation loop에서 발생했기 때문에 4번까지 도달하지 못했다. 따라서 `best_model_path`는 `null`이고 checkpoint 폴더도 비어 있었다.

### 3.3 predictor 설정은 원인이 아님

predictor 고효율 handoff 설정은 predictor 시작 시점에만 적용된다. 이번 실패는 tokenizer validation 단계에서 발생했고 predictor progress 파일도 없으므로 predictor 설정은 실패 원인이 아니다.

## 4. 개선한 방어 전략

이번 개선의 목적은 “OOM을 절대 낼 수 없게 한다”가 아니라, 긴 학습 이후 validation OOM이 발생해도 학습 결과를 잃지 않고 원인을 추적할 수 있게 만드는 것이다.

### 4.1 validation 전 checkpoint 저장

새 설정:

- `KRONOS_TOKENIZER_SAVE_PRE_VAL_CHECKPOINT=1`
- `KRONOS_TOKENIZER_PRE_VAL_CHECKPOINT_NAME=latest_train_model`

각 epoch 학습 loop가 끝난 직후, validation 시작 전에 다음 경로에 checkpoint를 저장한다.

```text
<save_path>/finetune_tokenizer/checkpoints/latest_train_model
```

validation이 실패해도 이 checkpoint는 남는다.

### 4.2 tokenizer validation batch size 분리

새 설정:

- `KRONOS_TOKENIZER_VAL_BATCH_SIZE`

기존에는 train batch size와 validation batch size가 동일했다. 이제 tokenizer validation만 별도 batch size를 사용할 수 있다.

STOM full mode runner 기본값:

```text
train batch size = 4
validation batch size = 1
```

즉, full run에서는 validation 속도를 일부 희생해서 VRAM 안정성을 우선한다.

### 4.3 validation 전 CUDA 메모리 정리

새 설정:

- `KRONOS_TOKENIZER_EMPTY_CACHE_BEFORE_VAL=1`

validation 전에 다음을 수행한다.

- 마지막 train tensor 참조 삭제
- optimizer gradient를 `set_to_none=True`로 정리
- `torch.cuda.empty_cache()` 호출
- validation은 `torch.inference_mode()`로 수행

### 4.4 validation OOM 실패 artifact 기록

validation에서 CUDA OOM이 다시 발생하면 다음 파일을 기록한다.

```text
<save_path>/finetune_tokenizer/validation_failure.json
```

기록 내용:

- 실패 stage
- epoch
- error type
- error message
- CUDA OOM 여부
- pre-validation checkpoint 경로

이 파일은 다음 복구 판단에 사용한다.

## 5. 재실행 권장 명령

이번 실패 run과 같은 pred60 2025 full small 목적을 유지하되 validation batch를 안전하게 1로 둔 실행 예시는 다음과 같다.

```powershell
python finetune/run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage both `
  --sample-stage full_window `
  --dataset-dir D:\Chanil_Park\Project\Programming\Kronos\finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets `
  --output-root D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs `
  --run-name stom_1s_grid_pred60_2025_full_small_retry_safe `
  --dataset-sample-mode full_sequential `
  --tokenizer-batch-size 4 `
  --tokenizer-val-batch-size 1 `
  --predictor-batch-size 16 `
  --predictor-num-workers 2
```

주의: 현재 실패 run에는 usable tokenizer checkpoint가 없으므로 기존 run을 이어서 predictor로 넘어가는 것은 불가능하다. 새 안전 설정으로 tokenizer부터 다시 수행해야 한다.

## 6. 운영 노하우

1. 장시간 full 학습에서는 validation 전에 checkpoint가 반드시 필요하다.
2. train batch가 가능하다고 validation batch도 가능한 것은 아니다.
3. progress가 99% 이상이어도 checkpoint가 없으면 실사용 모델은 없는 상태다.
4. predictor 최적화는 tokenizer checkpoint가 생성된 뒤에만 의미가 있다.
5. full validation은 속도보다 안정성을 우선해야 한다. 4080 SUPER 16GB에서는 tokenizer validation batch size 1이 가장 보수적인 선택이다.
6. 다시 실패하면 `validation_failure.json`, `tokenizer.stdout.log`, `tokenizer.progress.json`, checkpoint 폴더를 함께 확인한다.

## 7. 이번 코드 개선 파일

- `finetune/config.py`
  - tokenizer validation batch size 및 pre-validation checkpoint 옵션 추가
- `finetune/train_tokenizer.py`
  - validation 전 checkpoint 저장
  - validation batch size 분리
  - validation 전 CUDA 캐시/참조 정리
  - validation OOM artifact 기록
- `finetune/tokenizer_safety.py`
  - torch import 없이 검증 가능한 checkpoint/OOM 기록 helper 분리
- `finetune/run_stom_1s_finetune.py`
  - `--tokenizer-val-batch-size` CLI 추가
  - full mode tokenizer validation batch 기본값 1 적용
- `tests/test_stom_1s_finetune_runner.py`
  - runner env 생성 검증
- `tests/test_train_tokenizer_safety.py`
  - safety helper 단위 테스트 추가
