# 2025년 STOM tick Kronos-small 전체 학습 Preflight 보고서

작성일: 2026-05-11 KST  
대상 단계: 2025년 STOM tick 전체 데이터 → Kronos-small 공식 tokenizer→predictor 학습 전 점검  
관련 상위 문서:

- `docs/stom_kronos_conversation_work_summary.md`
- `docs/stom_gpu_rental_kronos_training_plan.md`
- `docs/stom_kronos_official_execution_plan.md`

## 1. 이번 단계의 목표

이번 단계는 8일 이상 걸릴 수 있는 본 학습을 바로 시작하지 않고, 먼저 다음 조건을 자동으로 확인하는 것이다.

1. STOM tick DB를 read-only로 열 수 있는지
2. 2025년 구간만 export할 수 있는 코드 경로가 있는지
3. CUDA/VRAM/디스크 여유 공간이 본 학습에 적합한지
4. 2025년 train/validation 샘플 수가 공식 학습 명령에 반영되는지
5. tokenizer→predictor 공식 순서와 checkpoint handoff가 유지되는지
6. 다음 장기 실행 명령을 사람이 그대로 복사해도 되는지

## 2. 이번 커밋에서 추가/수정한 내용

| 파일 | 내용 |
|---|---|
| `.gitignore` | `.omx/` 런타임/분석 산출물이 실수로 커밋되지 않도록 제외 |
| `finetune_csv/stom_tick_dataset.py` | `session_start`, `session_end` 필터 추가 |
| `finetune/qlib_stom_pipeline.py` | Qlib/Kronos export 명령에 `--session-start`, `--session-end` 추가 |
| `finetune/preflight_stom_2025_full.py` | 2025년 전체 학습 전 DB/CUDA/디스크/샘플/명령어 preflight 자동화 |
| `tests/test_stom_2025_preflight.py` | preflight 명령 생성 및 DB read-only 검증 테스트 |
| `tests/test_stom_qlib_pipeline.py` | session range export 테스트 추가 |
| `tests/test_stom_tick_dataset.py` | 개별 STOM table session range 읽기 테스트 추가 |

## 3. 실제 preflight 실행 결과

실행 명령:

```powershell
C:\Python\64\Python3119\python.exe finetune\preflight_stom_2025_full.py `
  --python-exe C:\Python\64\Python3119\python.exe `
  --json-output .omx\analysis\stom_2025_full_preflight_report.json
```

핵심 결과:

| 항목 | 결과 |
|---|---:|
| 상태 | `ready_with_actions` |
| blocker | 0개 |
| 경고 | 2025년 processed dataset이 아직 없음 → 다음 단계에서 export 필요 |
| DB 크기 | 27.69GB |
| DB table count | 2,427 |
| DB read-only/query_only | 통과 |
| DB write probe | `attempt to write a readonly database`로 차단됨 |
| GPU | NVIDIA GeForce RTX 4080 SUPER |
| VRAM | 15.99GB |
| PyTorch | 2.9.0+cu128 |
| CUDA | 사용 가능 |
| D: 여유 공간 | 약 538.64GB |

2025년 샘플 기준:

| split | samples |
|---|---:|
| train | 18,771,531 |
| validation | 3,922,758 |
| train+validation | 22,694,289 |

4080 Super 예상 시간:

```text
약 192.81시간 = 약 8.03일
```

이 시간은 공식 200k tokenizer+predictor 실측치 `7,340.567561초 / 240k samples`를 선형 환산한 값이다. 실제 본 학습은 디스크, 절전, 발열, dataloader 상태에 따라 8.5~9일로 보는 것이 안전하다.

## 4. 2025년 dataset export 명령

다음 단계에서 먼저 실행할 명령이다.

```powershell
C:\Python\64\Python3119\python.exe finetune/qlib_stom_pipeline.py export `
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

예상 산출물:

```text
finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets\train_data.pkl
finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets\val_data.pkl
finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets\test_data.pkl
finetune\qlib_exports\stom_1s_grid_pred60_2025\stom_qlib_export_report.json
```

## 5. 2025년 Kronos-small 본 학습 명령

2025년 processed dataset 생성 후 실행할 명령이다.

```powershell
C:\Python\64\Python3119\python.exe finetune/run_stom_1s_finetune.py `
  --horizon 60 `
  --mode full `
  --train-stage both `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets `
  --run-name stom_1s_grid_pred60_2025_full_small `
  --dataset-sample-mode full_sequential `
  --batch-size 4 `
  --num-workers 0 `
  --n-train-iter 18771531 `
  --n-val-iter 3922758 `
  --log-interval 1000
```

공식 순서:

1. `train_tokenizer.py`
2. `train_predictor.py`
3. predictor 실행 시 tokenizer checkpoint 자동 전달

## 6. Smoke 검증

### 6.1 2025 session filter export smoke

실행:

```powershell
C:\Python\64\Python3119\python.exe finetune\qlib_stom_pipeline.py export `
  --db _database\stock_tick_back.db `
  --output-dir .omx\smoke\stom_2025_session_filter_export_smoke `
  --max-tables 3 `
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

결과:

| 항목 | 값 |
|---|---:|
| selected_table_count | 3 |
| exported_group_count | 5 |
| exported_row_count | 8,786 |
| split sessions | 모두 2025년 |

### 6.2 tokenizer→predictor dry-run

실행:

```powershell
C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode smoke `
  --train-stage both `
  --dataset-dir .omx\smoke\stom_2025_session_filter_export_smoke\processed_datasets `
  --run-name stom_2025_preflight_dryrun `
  --dataset-sample-mode full_sequential `
  --batch-size 1 `
  --num-workers 0 `
  --n-train-iter 3 `
  --n-val-iter 1 `
  --dry-run
```

결과:

- tokenizer manifest 생성 확인
- predictor manifest 생성 확인
- predictor의 `KRONOS_FINETUNED_TOKENIZER_PATH`가 tokenizer checkpoint 경로로 연결되는 것 확인

## 7. 테스트 결과

실행:

```powershell
C:\Python\64\Python3119\python.exe -m pytest `
  tests/test_stom_2025_preflight.py `
  tests/test_stom_qlib_pipeline.py `
  tests/test_stom_tick_dataset.py `
  -q
```

결과:

```text
13 passed, 1 warning
```

## 8. 전체 계획/현재 단계/남은 단계

```text
전체 진행률: ████████████████░░░░ 80%
현재 단계:   ████████████████████ 100%  2025 full preflight 완료
남은 단계:   ████░░░░░░░░░░░░░░░░ 20%   export → 학습 → 평가 → 대시보드
```

| 단계 | 내용 | 상태 |
|---:|---|---|
| 1 | STOM DB 구조 이해/변환 | 완료 |
| 2 | 공식 tokenizer→predictor 200k 학습 | 완료 |
| 3 | 대시보드 실제값/예측값 검증 | 완료 |
| 4 | GPU 대여/시간/비용 검토 | 완료 |
| 5 | 2025년 전체 학습 preflight | 완료 |
| 6 | 2025년 processed dataset export | 다음 단계 |
| 7 | 2025년 Kronos-small 전체 학습 | 남음 |
| 8 | 2025 test + 2026 forward 검증 | 남음 |
| 9 | 대시보드 성과 비교 및 Kronos-base 확대 판단 | 남음 |

## 9. 다음 권장 OMX 명령

다음은 바로 dataset export를 진행하는 단계다.

```text
$ralph 2025년 STOM tick pred60 processed dataset export를 실행하고 export report, train/val/test pkl 생성 여부, session split, row/sample 수를 검증한 뒤 문서와 commit으로 남기세요.
```

주의:

- 이 단계는 학습이 아니라 dataset export다.
- export 성공 후에야 8일 이상 걸리는 본 학습 명령을 실행할 수 있다.
- Windows 절전 방지와 장기 실행 로그/백업 정책은 본 학습 직전에 다시 확인해야 한다.

---

## 10. 2026-05-11 추가 확인: 2025 processed dataset export 완료

preflight 이후 실제 2025년 dataset export를 완료했다.

- export output: `finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets`
- export duration: 1,433.24초
- `train_data.pkl`: 1,325,464,369 bytes
- `val_data.pkl`: 276,595,451 bytes
- `test_data.pkl`: 273,245,379 bytes
- export report 기준 train samples: 18,806,883
- export report 기준 validation samples: 3,925,397
- preflight 재실행 결과: `next_action=run_training_2025_full_small`, blocker 0개, warning 0개

따라서 이 문서의 다음 단계는 이제 export가 아니라 **2025년 Kronos-small full training 실행**이다. 상세 export 보고서는 `docs/stom_2025_dataset_export_report.md`를 기준으로 한다.
