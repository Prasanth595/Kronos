# 8단계 안내: STOM Kronos 1M/5M/full-window 확대 계획

작성일: 2026-05-09
기준 모델: `stom_1s_grid_pred60_official_200k`

## 1. 현재 상태

1~7단계는 완료됐다.

| 단계 | 상태 | commit |
| --- | --- | --- |
| 1. tokenizer 학습 경로 안정화 | 완료 | `2153f9f` |
| 2. tokenizer 20k benchmark | 완료 | `9ef5207` |
| 3. pred60 tokenizer 200k | 완료 | `66dd204` |
| 4. pred60 predictor 200k | 완료 | `6fc9bf2` |
| 5. holdout 실제값/예측값 그래프 | 완료 | `79c5e6c` |
| 6. 성과 보고서 | 완료 | `60dc759` |
| 7. pred30 판단 | 완료 | `eb3f9ba` |

핵심 결론:

```text
공식 학습 절차와 대시보드 시각화는 성공.
하지만 25bp cost gate는 실패.
따라서 수익성 목적의 1M/5M/full-window 확대는 보류.
```

## 2. 8단계에서 먼저 선택해야 하는 목적

| 목적 | 권장 여부 | 설명 |
| --- | --- | --- |
| 대시보드/연구용 더 큰 공식 모델 | 가능 | 1M부터 실행 가능. 단, 수익성 보장은 없음 |
| 수익성 목적 확대 | 비권장 | 현재 25bp gate 실패. 먼저 비용/조건식/score 개선 필요 |
| 전체 window exact 학습 증명 | 가능하지만 매우 장시간 | pred60 full-window는 약 31일 이상 예상 |
| pred30 공식 비교 | 보류 | pred60 gate 실패 후 20k pilot부터 재검토 |

## 3. 실측 기반 시간 계산

실측:

| 작업 | train/val samples | 시간 |
| --- | ---: | ---: |
| tokenizer 200k | 200k / 40k | 3,211초, 약 53.5분 |
| predictor 200k | 200k / 40k | 4,129초, 약 68.8분 |
| holdout 예측/그래프 | 3,080 windows | 1,136초, 약 18.9분 |
| filter search | 3,080 windows | 약 109초 |
| rolling validation | 3,080 windows | 약 255초 |

단순 선형 환산:

| 확대 범위 | tokenizer | predictor | 학습 합계 |
| --- | ---: | ---: | ---: |
| 1M | 약 4.46시간 | 약 5.74시간 | 약 10.20시간 |
| 5M | 약 22.30시간 | 약 28.68시간 | 약 50.98시간, 약 2.12일 |
| pred60 full-window 73,718,875 | 약 328.78시간 | 약 422.80시간 | 약 751.58시간, 약 31.32일 |

주의:

- 위 시간은 현재 3990X + RTX 4080 SUPER + batch_size 4 기준이다.
- full-window는 장시간 중단/절전/오류 리스크가 크므로 checkpoint resume 설계 없이는 권장하지 않는다.
- 1M/5M도 장시간이므로 절전 방지, 로그 저장, 중간 산출물 확인이 필요하다.

## 4. 1M/5M 실행 시 sample mode 선택

### A. 대표성/성과 실험 목적

권장:

```text
KRONOS_DATASET_SAMPLE_MODE=sample_random
```

이유:

- 1M/5M은 전체 73,718,875 window 중 일부만 보는 stage다.
- `full_sequential`로 일부만 돌리면 데이터 앞부분에 편중될 수 있다.
- 성과 실험은 전체 종목/날짜 pool에서 random sampling 하는 것이 더 대표성이 좋다.

### B. 전체 window exact 증명 목적

권장:

```text
KRONOS_DATASET_SAMPLE_MODE=full_sequential
--sample-stage full_window
```

이유:

- 모든 window를 중복/누락 없이 1회 방문했다는 claim은 sequential mode에서만 가능하다.
- 단, pred60 기준 학습만 약 31일 이상 예상된다.

## 5. 1M 연구용 공식 확대 명령어

### 5.1 tokenizer 1M

```powershell
C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage tokenizer `
  --sample-stage expand_1m `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets `
  --output-root finetune\outputs `
  --run-name stom_1s_grid_pred60_official_1m `
  --dataset-sample-mode sample_random `
  --batch-size 4 `
  --num-workers 0 `
  --log-interval 5000
```

### 5.2 predictor 1M

```powershell
C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage predictor `
  --sample-stage expand_1m `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets `
  --output-root finetune\outputs `
  --run-name stom_1s_grid_pred60_official_1m `
  --dataset-sample-mode sample_random `
  --finetuned-tokenizer-path finetune\outputs\stom_1s_grid_pred60_official_1m\finetune_tokenizer\checkpoints\best_model `
  --batch-size 4 `
  --num-workers 0 `
  --log-interval 5000
```

### 5.3 1M 평가/그래프

```powershell
C:\Python\64\Python3119\python.exe finetune\evaluate_stom_1s_checkpoint.py `
  --dataset-path finetune\qlib_exports\stom_1s_grid_pred60_full\processed_datasets `
  --model-path finetune\outputs\stom_1s_grid_pred60_official_1m\finetune_predictor\checkpoints\best_model `
  --tokenizer-path finetune\outputs\stom_1s_grid_pred60_official_1m\finetune_tokenizer\checkpoints\best_model `
  --output-dir webui\stom_predictions `
  --prefix stom_1s_pred60_official1m_walkforward100x5x50_eval `
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

## 6. 5M/full-window 안내

5M은 1M 결과가 다음 조건을 만족할 때만 권장한다.

```text
1. 25bp cost gate 개선
2. 또는 비용을 낮춘 5~10bp 환경에서 양수 net return 확인
3. 또는 사용자가 수익성 목적이 아니라 연구/공식 전체 학습 목적이라고 명시
```

full-window는 다음 조건을 만족할 때만 권장한다.

```text
1. 최소 31일 이상 워크스테이션을 안정적으로 점유 가능
2. 절전/재부팅 방지 가능
3. checkpoint resume 또는 중간 저장 실패 대응 가능
4. 사용자가 full exact coverage 자체가 목적이라고 명시
```

## 7. 다음 권장 OMX 명령어

현재 evidence 기준 추천은 “바로 1M 실행”이 아니라 “대시보드 확인 후 목적 선택”이다.

```text
$ralph official 200k 결과를 웹 대시보드에서 확인하고, 1M 연구용 확대 또는 cost-gate 개선 중 하나를 선택해 다음 실행 계획을 세워주세요.
```

수익성 개선을 먼저 하려면:

```text
$ralph pred60 official 200k 예측 CSV 기반으로 score/filter/비용 민감도 개선안을 개발하고 25bp cost gate 재검증까지 진행해주세요.
```

수익성과 무관하게 1M 연구용 학습을 진행하려면:

```text
$ralph pred60 official 1M을 sample_random으로 tokenizer부터 predictor, holdout 그래프, cost gate까지 진행해주세요. 각 단계별 commit 해주세요.
```
