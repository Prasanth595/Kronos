# STOM 1초봉 Kronos tokenizer 99.98% 정체 복구 기록

작성일: 2026-05-21 KST
대상 run: `stom_1s_grid_pred60_2025_full_small`

## 결론

`tokenizer` 학습은 실패로 끝난 것이 아니라, 학습 루프가 거의 끝난 뒤 `latest_train_model` 사전 검증 체크포인트를 저장한 상태에서 대규모 validation 단계로 들어가 멈춘 것처럼 보인 상황이다. 기존 자동 handoff는 validation 완료 후 생성되는 `best_model`만 predictor 입력으로 사용했기 때문에, validation이 장시간 진행되거나 정체되면 predictor 단계가 시작되지 못했다.

## 확인 증거

| 항목 | 확인값 |
| --- | --- |
| tokenizer progress | `293800 / 293858`, stage `99.9803%`, overall `49.9901%` |
| 마지막 로그 | `Tokenizer checkpoint saved ... latest_train_model (pre-validation epoch 1)` |
| validation 규모 | `3,925,397` steps, 기존 `tokenizer-val-batch-size=1` |
| predictor progress | `predictor.progress.json` 미생성 상태 |
| 사용 가능한 checkpoint | `finetune_tokenizer/checkpoints/latest_train_model/model.safetensors` 존재 |
| 기존 handoff 문제 | `--train-stage both` predictor가 `best_model` 경로만 사용 |

## 원인

1. full STOM run은 tokenizer validation OOM을 피하려고 validation batch size를 1로 낮췄다.
2. 이 설정에서 validation step 수가 약 392만 개가 되어, 학습보다 긴 validation 병목이 생길 수 있다.
3. 기존 `train_tokenizer.py`는 validation 루프 내부 progress 로그를 남기지 않아 대시보드가 마지막 train step인 99.98%에서 멈춘 것처럼 보였다.
4. 기존 `run_stom_1s_finetune.py`는 `best_model`만 predictor handoff로 사용했다. validation이 끝나지 않으면 `best_model`이 없어서 predictor로 넘어갈 수 없다.

## 적용한 복구/개선

| 변경 | 목적 |
| --- | --- |
| `--start-stage predictor` 추가 | `--train-stage both`의 2단계 진행률을 유지하면서 predictor 단계만 재개 |
| `--tokenizer-checkpoint-policy best_then_latest` 추가 | `best_model`이 있으면 공식 best를 쓰고, 없으면 `latest_train_model`로 안전하게 fallback |
| tokenizer validation progress 로그 추가 | 다음 장기 run에서 validation 단계가 숨지 않도록 `validation_step`, `validation_fraction` 기록 |
| progress sidecar validation 필드 추가 | 웹 대시보드/API에서 validation 상태를 표현 가능하게 함 |
| 웹 monitor stage 요약에 validation 필드 추가 | `/api/training/status`가 validation phase/step 정보를 전달 |
| UI done status에 `ok/recovered` 반영 | 복구된 tokenizer checkpoint를 완료/복구 단계로 표시 가능하게 함 |

## 복구 실행 원칙

이번 run은 `latest_train_model`이 이미 저장되어 있으므로, 오래 멈춘 tokenizer process를 정리한 뒤 predictor를 다음 명령으로 재개한다.

```powershell
python finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage both `
  --start-stage predictor `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets `
  --output-root finetune\outputs `
  --run-name stom_1s_grid_pred60_2025_full_small `
  --dataset-sample-mode full_sequential `
  --n-train-iter 18806883 `
  --n-val-iter 3925397 `
  --predictor-batch-size 16 `
  --predictor-num-workers 2 `
  --epochs 1 `
  --num-workers 12 `
  --persistent-workers `
  --prefetch-factor 6
```

`best_then_latest`가 기본값이므로 위 명령은 `best_model`이 없을 때 자동으로 `latest_train_model`을 predictor tokenizer로 사용한다.

## 주의사항

- 이 복구는 “validation loss 기준 best tokenizer”가 아니라 “학습 완료 직전 checkpoint”를 사용하는 방식이다.
- 목적은 장시간 validation 병목 때문에 전체 pipeline이 영구 정지되는 것을 막고 predictor 학습 성과를 먼저 확보하는 것이다.
- 최종 연구/검증에서는 별도 validation-only 또는 validation max-step/cap 전략으로 tokenizer 품질을 다시 측정해야 한다.

## 실제 복구 실행 결과 (2026-05-21 07:32 KST)

| 항목 | 결과 |
| --- | --- |
| 기존 tokenizer process | `81208`, `82888` 종료 |
| tokenizer progress 상태 | `recovered`, stage `100%`, overall `50%`로 복구 표시 |
| predictor launcher PID | `107684` |
| predictor child PID | `96764` |
| predictor handoff source | `latest_train_model` |
| predictor 시작 확인 | `train_predictor.py` 실행, `Step 500/1175431` 이후 진행 확인 |
| GPU 확인 | RTX 4080 SUPER, 학습 중 약 95% 사용 / VRAM 약 6.4GB 사용 확인 |

이제 장기 학습 감시는 `http://127.0.0.1:5070/training` 또는 `/api/training/status`에서 predictor 단계 기준으로 보면 된다.
