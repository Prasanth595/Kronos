# 2025년 STOM tick pred60 Kronos-small 전체 학습 시작 보고서

작성일: 2026-05-11 KST  
목적: 2025년 STOM tick pred60 전체 데이터셋으로 Kronos-small 공식 tokenizer→predictor full training을 실제로 시작하고, `/training` 대시보드에서 초기 progress/log/GPU 갱신을 확인한다.

## 1. 이번 단계의 위치

이번 단계는 **본 학습을 백그라운드로 시작하고 초기 학습이 실제로 도는지 확인하는 단계**다. 전체 학습 완료 단계가 아니다.

```text
전체 진행률: ███████████████████░ 97%
현재 단계:   ████████████████████ 100%  2025 full training 시작 및 초기 live 검증 완료
남은 단계:   █░░░░░░░░░░░░░░░░░░░ 3%   장기 학습 완료 → checkpoint → 예측/성과 검증
```

방향성:

1. 2025년 전체 데이터셋을 사용한다.
2. Kronos 공식 순서인 tokenizer → predictor를 지킨다.
3. 학습 완료까지 기다리지 않고 먼저 live progress/log/GPU가 정상 갱신되는지 확인한다.
4. 장기 학습 완료 후 checkpoint로 예측 CSV를 만들고 `/stom`에서 실제값/예측값을 검증한다.

## 2. 시작 전 확인

| 항목 | 결과 |
|---|---|
| git 상태 | clean, `master...origin/master [ahead 49]` 상태에서 시작 |
| 중복 학습 프로세스 | 없음 |
| 2025 processed dataset | 존재 |
| `/training` 서버 | `http://127.0.0.1:5070/training`, 200 OK |
| GPU | NVIDIA GeForce RTX 4080 SUPER |

데이터셋 파일:

| 파일 | 크기 |
|---|---:|
| `train_data.pkl` | 1,325,464,369 bytes |
| `val_data.pkl` | 276,595,451 bytes |
| `test_data.pkl` | 273,245,379 bytes |

## 3. 실제 실행 명령

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

백그라운드 프로세스:

| 역할 | PID |
|---|---:|
| runner `run_stom_1s_finetune.py` | 3944 |
| child `train_tokenizer.py` | 70448 |
| `/training` webui parent | 147452 |
| `/training` webui child/reloader | 101468 |

런타임 로그:

```text
.omx/training-launch/stom_2025_full_runner.out.log
.omx/training-launch/stom_2025_full_runner.err.log
finetune/outputs/stom_1s_grid_pred60_2025_full_small/logs/tokenizer.stdout.log
finetune/outputs/stom_1s_grid_pred60_2025_full_small/logs/tokenizer.progress.json
```

주의: 위 런타임 산출물과 학습 output은 `.gitignore` 대상이며 커밋하지 않는다.

## 4. 초기 live 검증 결과

학습은 tokenizer 단계에서 정상 시작되었다.

데이터셋/step 확인:

| 항목 | 값 |
|---|---:|
| train samples | 18,806,883 |
| validation samples | 3,925,397 |
| tokenizer train steps/epoch | 4,701,721 |
| validation steps | 981,350 |
| batch size | 4 |
| sample mode | `full_sequential` |

첫 training step 로그 확인:

```text
[Rank 0, Epoch 1/1, Step 1000/4701721] LR 0.000020, Loss: -0.0308
[Rank 0, Epoch 1/1, Step 2000/4701721] LR 0.000020, Loss: -0.0299
```

`/api/training/status` 확인 시점의 핵심 값:

| 항목 | 값 |
|---|---:|
| status | `running` |
| current stage | `tokenizer` |
| step | 2,000 / 4,701,721 |
| tokenizer stage percent | 0.0425% |
| overall percent | 0.0213% |
| last loss | -0.0299 |
| samples/sec | 약 50.52 |
| GPU utilization | 약 37~40% |
| VRAM 사용량 | 약 3,109 MiB / 16,376 MiB |
| GPU 온도 | 약 46~51°C |

브라우저 검증:

- URL: `http://127.0.0.1:5070/training`
- 확인: run 목록, `running`, tokenizer stage, step/loss, GPU, log tail 표시
- console/page error: 0개
- 검증 artifact: `.omx/training-launch/training_dashboard_live_step_check.json`, `.omx/training-launch/training_dashboard_live_step.png`

## 5. 시간 해석

대시보드의 초기 ETA는 tokenizer stage 기준으로 약 4일대가 표시되었다. 다만 이 값은 step 1,000~2,000 근처의 매우 초기 속도 기준이므로 흔들릴 수 있다.

운영 판단은 여전히 다음처럼 잡는다.

```text
보수적 전체 예상: 8~9일
초기 관측 기반 tokenizer 예상: 약 4일대
predictor까지 포함한 전체 완료 시점은 계속 모니터링 필요
```

## 6. 현재 결론

2025년 STOM tick pred60 Kronos-small 전체 학습은 실제로 시작되었고, `/training` 대시보드도 실제 학습 progress/log/GPU를 표시하고 있다.

현재 완료된 것:

- full training background launch 완료
- tokenizer child process 실행 확인
- 전체 train/val sample 수 확인
- step/loss 로그 확인
- progress JSON 갱신 확인
- `/training` 브라우저 표시 확인

아직 완료되지 않은 것:

- tokenizer epoch 완료
- tokenizer checkpoint 저장
- predictor 학습 시작/완료
- 최종 checkpoint 검증
- 예측 CSV 생성
- `/stom` 실제값/예측값/종목별 통계 검증

## 7. 모니터링 명령

상태 확인:

```powershell
Get-Content finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.progress.json -Tail 80
```

로그 확인:

```powershell
Get-Content finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.stdout.log -Tail 40
```

프로세스 확인:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'run_stom_1s_finetune|train_tokenizer|train_predictor' } |
  Select-Object ProcessId,CommandLine
```

GPU 확인:

```powershell
nvidia-smi
```

웹 확인:

```text
http://127.0.0.1:5070/training
```

## 8. 다음 권장 OMX 명령

```text
$ralph 2025년 STOM tick pred60 Kronos-small 전체 학습의 tokenizer 단계가 계속 정상 진행 중인지 progress/log/GPU를 재점검하고, checkpoint 생성 전까지 중간 상태를 문서와 commit으로 주기적으로 남기세요.
```

중요:

- 학습 프로세스를 종료하지 말 것.
- Windows 절전/재부팅을 피할 것.
- 학습 산출물은 커밋하지 말 것.
- tokenizer 완료 후 predictor가 자동 시작되는지 확인할 것.
