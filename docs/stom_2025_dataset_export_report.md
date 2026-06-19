# 2025년 STOM tick pred60 processed dataset export 보고서

작성일: 2026-05-11 KST  
목적: 2025년 STOM tick 전체 데이터를 Kronos-small 공식 학습에 사용할 수 있는 `processed_datasets` 형식으로 생성하고 검증한다.  
상위 목표: 2025년 전체 학습 → 실제값/예측값 대시보드 검증 → 성과 개선 시 Kronos-base/전체 연도 확대 판단

## 1. 이번 단계의 위치

이 단계는 **본 학습이 아니라 본 학습 직전 데이터셋 생성 단계**다.

```text
전체 진행률: ██████████████████░░ 90%
현재 단계:   ████████████████████ 100%  2025 processed dataset export 완료
남은 단계:   ██░░░░░░░░░░░░░░░░░░ 10%   2025 full training → 평가/대시보드
```

방향성:

1. 2025년만 분리한 데이터셋을 만든다.
2. train/val/test split이 session 기준으로 분리됐는지 확인한다.
3. full training 명령의 train/val sample 수를 export report 기준으로 다시 고정한다.
4. 그 다음에만 8일 이상 걸리는 Kronos-small 전체 학습을 시작한다.

## 2. 실행 명령

```powershell
C:\Python\64\Python3119\python.exe finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir finetune\qlib_exports\stom_1s_grid_pred60_2025 `
  --lookback-window 300 `
  --predict-window 60 `
  --horizon-seconds 60 `
  --price-mode close_only `
  --time-start 090000 `
  --time-end 093000 `
  --session-start 20250101 `
  --session-end 20251231 `
  --freq 1s `
  --regularize-1s `
  --split-by session
```

실행 시간:

| 항목 | 값 |
|---|---:|
| 시작 | 2026-05-11 11:04:29 |
| 종료 | 2026-05-11 11:28:22 |
| 소요 시간 | 1,433.24초, 약 23분 53초 |
| exit code | 0 |

## 3. 생성 산출물

경로:

```text
finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets
```

| 파일 | 크기 |
|---|---:|
| `train_data.pkl` | 1,325,464,369 bytes, 약 1.234GB |
| `val_data.pkl` | 276,595,451 bytes, 약 0.258GB |
| `test_data.pkl` | 273,245,379 bytes, 약 0.254GB |
| `stom_qlib_export_report.json` | 1,299,962 bytes, 약 1.24MB |

주의: 위 산출물은 대용량 학습 데이터이므로 `.gitignore` 대상이며 커밋하지 않는다.

## 4. export report 검증 결과

주요 설정:

| 항목 | 값 |
|---|---|
| `session_start` | `20250101` |
| `session_end` | `20251231` |
| `lookback_window` | 300 |
| `predict_window` | 60 |
| `horizon_seconds` | 60 |
| `freq` | `1s` |
| `regularize_1s` | true |
| `split_by` | `session` |
| `price_mode` | `close_only` |

전체 export:

| 항목 | 값 |
|---|---:|
| selected_table_count | all |
| exported_group_count | 18,750 |
| exported_row_count | 33,360,325 |
| regularized_groups | 18,750 |
| inserted_rows | 2,925,081 |
| warnings_count | 1 |

split 결과:

| split | sessions | first | last | groups | rows | 가능한 pred60 samples |
|---|---:|---|---|---:|---:|---:|
| train | 168 | 20250103 | 20250910 | 13,256 | 23,579,043 | 18,806,883 |
| val | 36 | 20250911 | 20251106 | 2,764 | 4,920,437 | 3,925,397 |
| test | 36 | 20251107 | 20251230 | 2,730 | 4,860,845 | 3,878,045 |

계산식:

```text
possible_samples = rows - groups * (lookback_window + predict_window)
                 = rows - groups * 360
```

## 5. preflight 재검증 결과

export 후 preflight를 다시 실행했다.

결과:

| 항목 | 값 |
|---|---|
| status | `ready_with_actions` |
| blockers | 0개 |
| warnings | 0개 |
| export_report_loaded | true |
| target sample source | `export_report` |
| next_action | `run_training_2025_full_small` |

학습 대상 샘플 수가 scan report 기준이 아니라 실제 export report 기준으로 재계산되도록 보정했다.

| 항목 | 값 |
|---|---:|
| train samples | 18,806,883 |
| validation samples | 3,925,397 |
| train+validation | 22,732,280 |

## 6. 다음 본 학습 명령

다음 단계에서 실행할 명령은 아래와 같다.

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
  --n-train-iter 18806883 `
  --n-val-iter 3925397 `
  --log-interval 1000
```

dry-run 검증 결과:

- tokenizer stage manifest 생성 확인
- predictor stage manifest 생성 확인
- predictor stage의 `KRONOS_FINETUNED_TOKENIZER_PATH`가 같은 run의 tokenizer checkpoint로 연결됨

## 7. 남은 단계

| 단계 | 내용 | 상태 |
|---:|---|---|
| 1 | 2025년 preflight | 완료 |
| 2 | 2025년 processed dataset export | 완료 |
| 3 | 2025년 Kronos-small tokenizer→predictor full training | 다음 단계 |
| 4 | 학습 checkpoint 검증 | 남음 |
| 5 | 예측 CSV 생성 | 남음 |
| 6 | 웹 대시보드 실제값/예측값/종목별 통계 검증 | 남음 |
| 7 | 성과 개선 시 Kronos-base/전체 연도 확대 판단 | 남음 |

## 8. 다음 권장 OMX 명령

```text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습을 checkpoint/resume와 절전 방지 조건을 확인한 뒤 실행하고, tokenizer/predictor 로그와 checkpoint 생성 여부를 주기적으로 점검하며 완료 후 문서와 commit으로 남기세요.
```

주의:

- 다음 단계부터는 실제 학습이며 4080 Super 기준 약 8일 이상 걸릴 수 있다.
- 실행 전 Windows 절전 방지, 충분한 냉각, 로그 백업, 중단 시 재개 전략을 다시 확인해야 한다.
- 본 학습이 끝나기 전까지 정확도/예측률 개선 여부는 판단할 수 없다.
