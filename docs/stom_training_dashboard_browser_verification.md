# STOM Kronos 실시간 학습 모니터 브라우저 검증 보고서

작성일: 2026-05-11 KST  
검증 대상: `http://127.0.0.1:5070/training`  
검증 목적: 2025년 STOM tick pred60 Kronos-small 전체 학습을 시작하기 전에 `/training` 대시보드가 실제 서버/API/브라우저에서 동작하는지 확인한다.

## 1. 이번 단계의 위치

이번 단계는 **본 학습 실행 전 최종 모니터링 검증 단계**다.

```text
전체 진행률: ███████████████████░ 96%
현재 단계:   ████████████████████ 100%  /training 서버·API·브라우저 검증 완료
남은 단계:   █░░░░░░░░░░░░░░░░░░░ 4%   2025 full training → checkpoint → 예측/성과 검증
```

목적을 잃지 않기 위한 판단:

- 지금 목표는 대시보드를 꾸미는 것이 아니라 **8~9일짜리 전체 학습을 안전하게 관측 가능한 상태로 시작하는 것**이다.
- 따라서 이번 단계에서는 실시간 모니터의 실제 표시와 API 응답을 먼저 검증했다.
- 본 학습은 아직 시작하지 않았다.

## 2. 검증용 run artifact

대시보드가 즉시 읽을 수 있도록 2025 processed dataset 기반 dry-run artifact를 생성했다.

```powershell
C:\Python\64\Python3119\python.exe finetune\run_stom_1s_finetune.py `
  --horizon 60 `
  --mode smoke `
  --train-stage both `
  --dataset-dir finetune\qlib_exports\stom_1s_grid_pred60_2025\processed_datasets `
  --run-name stom_training_dashboard_visual_smoke `
  --dataset-sample-mode full_sequential `
  --batch-size 1 `
  --num-workers 0 `
  --n-train-iter 2 `
  --n-val-iter 1 `
  --dry-run
```

검증 결과:

| 항목 | 값 |
|---|---:|
| run | `stom_training_dashboard_visual_smoke` |
| status | `dry_run` |
| stage_count | 2 |
| tokenizer progress | 생성됨 |
| predictor progress | 생성됨 |
| dry-run overall_percent | 0.0 |
| dry-run log tail | `dry-run only; tokenizer command was not executed.` |

이번 검증 중 발견한 UX 문제와 수정:

1. dry-run이면 실제 학습을 하지 않았는데 stage index 때문에 전체 진행률이 50%처럼 보일 수 있었다.
2. dry-run에서는 stdout 파일이 없어 log API가 에러처럼 보일 수 있었다.

수정 내용:

- dry-run progress는 전체 진행률을 0%로 유지한다.
- dry-run도 placeholder stdout/stderr log를 생성한다.

## 3. 서버 검증

실행 서버:

```text
http://127.0.0.1:5070/training
```

서버 상태:

| 항목 | 결과 |
|---|---|
| `/api/training/runs` | 200 OK |
| `/api/training/status?run=stom_training_dashboard_visual_smoke` | 200 OK |
| `/api/training/logs?run=stom_training_dashboard_visual_smoke&lines=5` | 200 OK |
| `/api/training/gpu` | 200 OK |

GPU API 확인:

| 항목 | 값 |
|---|---|
| GPU | NVIDIA GeForce RTX 4080 SUPER |
| VRAM total | 16,376 MiB |
| 온도 | 약 47~48°C |
| 전력 | 이 환경의 `nvidia-smi` power.draw가 N/A라 `-`로 표시 |

## 4. 브라우저 렌더링 검증

Playwright headless 브라우저로 `/training` 페이지를 열어 확인했다. browser-use skill은 로드했지만 이 세션에서 Node REPL browser tool이 노출되지 않아, 검증은 Playwright fallback으로 수행했다.

확인 항목:

| 체크 | 결과 |
|---|---|
| 페이지 title | `STOM Kronos Training Monitor` |
| run 목록 표시 | 통과 |
| `stom_training_dashboard_visual_smoke` 표시 | 통과 |
| `dry_run` 표시 | 통과 |
| 전체 진행률 0.00% 표시 | 통과 |
| tokenizer/predictor stage 카드 표시 | 통과 |
| GPU 영역 표시 | 통과 |
| 실시간 로그 tail 표시 | 통과 |
| console error | 0개 |
| page error | 0개 |

브라우저 검증 artifact:

```text
.omx/browser-check/training_dashboard_browser_check.json
.omx/browser-check/training_dashboard_5070.png
```

위 파일은 런타임 검증 산출물이므로 커밋하지 않는다.

## 5. 테스트 검증

실행:

```powershell
C:\Python\64\Python3119\python.exe -m compileall -q finetune webui tests

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

## 6. 현재 결론

`/training` 대시보드는 본 학습 시작 전 모니터링 용도로 사용할 수 있다.

다음 단계는 **실제 2025년 Kronos-small 전체 학습 실행**이다. 단, 실행 전에는 아래 조건을 다시 확인해야 한다.

1. Windows 절전/재부팅 방지
2. 충분한 냉각
3. D: 여유 공간
4. `/training` 페이지 접속 가능
5. 시작 후 tokenizer 로그가 `tokenizer.stdout.log`와 `tokenizer.progress.json`에 갱신되는지 1차 확인

## 7. 다음 권장 OMX 명령

```text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습을 시작하고, /training 대시보드에서 tokenizer 단계의 progress/log/GPU 상태가 실제로 갱신되는지 1차 확인한 뒤 장기 학습 상태로 전환하세요. 완료 전까지 checkpoint와 progress를 주기적으로 점검하고 단계별 문서와 commit을 남기세요.
```

