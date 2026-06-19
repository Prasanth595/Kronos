# STOM Kronos 실시간 학습 모니터링 대시보드

작성일: 2026-05-11 KST  
목적: 2025년 STOM tick pred60 Kronos-small 전체 학습을 시작하기 전에, 며칠 동안 진행되는 학습 상태를 웹에서 확인할 수 있게 한다.

## 1. 왜 이 단계가 먼저 필요한가

2025년 전체 학습은 RTX 4080 SUPER 기준 약 8~9일이 예상된다. 기존 `finetune/run_stom_1s_finetune.py`는 `subprocess.run(..., capture_output=True)` 방식이라 학습 프로세스가 끝나기 전까지 stdout/stderr가 로그 파일로 저장되지 않았다. 따라서 절전, 오류, GPU 사용률 저하, loss 정체를 중간에 확인하기 어려웠다.

이번 단계는 본 학습 자체가 아니라 **본 학습을 안전하게 관측하기 위한 선행 단계**다.

## 2. 이번 단계에서 추가된 기능

| 영역 | 추가 내용 |
|---|---|
| runner | 학습 child process stdout을 실시간 파일 기록 및 현재 터미널에 mirror 출력 |
| progress sidecar | `finetune/outputs/<run>/logs/<stage>.progress.json` 실시간 갱신 |
| web page | `/training` 실시간 학습 모니터 페이지 추가 |
| API | `/api/training/runs`, `/api/training/status`, `/api/training/logs`, `/api/training/gpu` 추가 |
| GPU 상태 | `nvidia-smi` 기반 GPU utilization, VRAM, 전력, 온도 표시 |
| 안전성 | run 이름은 `finetune/outputs`의 직접 하위 폴더만 허용하여 임의 파일 읽기 방지 |
| 테스트 | progress parser/tracker, dashboard helper, Flask route smoke 테스트 추가 |

## 3. 표시되는 정보

`/training` 페이지에서 다음 정보를 확인할 수 있다.

1. 학습 run 목록과 상태
2. 전체 진행률
3. tokenizer/predictor 단계별 진행률
4. epoch, step, total step
5. 최근 train loss
6. validation loss, best validation loss
7. 경과 시간, ETA, samples/sec
8. 실시간 로그 tail
9. GPU 사용률, VRAM 사용량, 전력, 온도
10. 다음 본 학습 권장 명령

## 4. 생성되는 파일 구조

예시 run 이름: `stom_1s_grid_pred60_2025_full_small`

```text
finetune/outputs/stom_1s_grid_pred60_2025_full_small/
  tokenizer_run_manifest.json
  run_manifest.json
  logs/
    tokenizer.stdout.log
    tokenizer.stderr.log
    tokenizer.progress.json
    predictor.stdout.log
    predictor.stderr.log
    predictor.progress.json
```

`*.progress.json`은 학습 로그가 한 줄 출력될 때마다 갱신된다. 웹 대시보드는 이 파일을 읽어서 진행률을 계산한다.

## 5. 실제 학습 시작 전 권장 확인 순서

```text
전체 진행률: ███████████████████░ 95%
현재 단계:   ████████████████████ 100%  실시간 학습 모니터 구현 완료
남은 단계:   █░░░░░░░░░░░░░░░░░░░ 5%   본 학습 실행 후 결과 검증
```

| 단계 | 내용 | 상태 |
|---:|---|---|
| 1 | STOM tick DB 이해 및 OHLCV 변환 | 완료 |
| 2 | 2025년 processed dataset export | 완료 |
| 3 | 공식 tokenizer→predictor 학습 명령 dry-run | 완료 |
| 4 | 실시간 학습 모니터링 구현 | 완료 |
| 5 | 2025년 Kronos-small 전체 학습 실행 | 다음 |
| 6 | checkpoint 검증 및 예측 CSV 생성 | 남음 |
| 7 | `/stom`에서 실제값/예측값/종목별 통계 검증 | 남음 |
| 8 | 성과 개선 시 Kronos-base 또는 전체 연도 확대 판단 | 남음 |

## 6. 웹 대시보드 실행 방법

기존 Flask webui를 실행한다.

```powershell
C:\Python\64\Python3119\python.exe webui\run.py
```

브라우저:

```text
http://127.0.0.1:7070/training
```

예측 결과 검증 페이지:

```text
http://127.0.0.1:7070/stom
```

참고: 별도 검증 서버를 5000 포트로 띄운 경우에는 같은 경로를 `http://127.0.0.1:5000/training`처럼 열면 된다.

## 7. 2025년 전체 학습 권장 명령

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

이 명령을 실행하면 `/training`에서 `tokenizer` → `predictor` 진행이 순서대로 표시된다.

## 8. 검증 결과

실행한 테스트:

```powershell
C:\Python\64\Python3119\python.exe -m pytest `
  tests/test_training_progress.py `
  tests/test_training_monitor.py `
  tests/test_stom_1s_finetune_runner.py::test_runner_dry_run_records_reproducible_env `
  -q
```

결과:

```text
7 passed
```

추가 전체 회귀 검증:

```powershell
C:\Python\64\Python3119\python.exe -m pytest `
  tests/test_training_progress.py `
  tests/test_training_monitor.py `
  tests/test_stom_1s_finetune_runner.py::test_runner_dry_run_records_reproducible_env `
  tests/test_stom_1s_finetune_runner.py::test_sample_stage_sets_staged_full_training_budget `
  tests/test_stom_1s_finetune_runner.py::test_runner_can_build_tokenizer_stage_and_both_stage_handoff `
  tests/test_stom_2025_preflight.py `
  tests/test_stom_qlib_pipeline.py `
  tests/test_stom_tick_dataset.py `
  tests/test_stom_dashboard_helpers.py `
  -q
```

결과:

```text
33 passed, 3 warnings
```

## 9. 브라우저 검증 상태

2026-05-11 KST에 /training 실제 서버/API/브라우저 검증을 완료했다.

- 상세 보고서: docs/stom_training_dashboard_browser_verification.md
- 검증 URL: http://127.0.0.1:5070/training
- 검증 결과: run 목록, 전체 진행률, tokenizer/predictor 단계, GPU, log tail 표시 통과
- 추가 수정: dry-run progress는 0%로 표시하고 dry-run log placeholder를 생성한다.

## 10. 주의사항

- 이 기능은 학습 진행률을 관측하는 기능이지 정확도 개선 기능은 아니다.
- checkpoint resume 자동화는 아직 별도 단계다. 현재는 로그/진행률/상태 확인이 목적이다.
- 전력 수치는 `nvidia-smi`가 제공하는 GPU 전력만 표시한다. 전체 워크스테이션 소비전력은 별도 전력계가 필요하다.
- 학습 중 Windows 절전/재부팅이 발생하면 프로세스가 중단될 수 있으므로 본 학습 전 절전 방지를 별도로 확인해야 한다.
