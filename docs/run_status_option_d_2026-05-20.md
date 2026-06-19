# 옵션 D 재학습 실행 상태 기록 — 2026-05-20

## 목적

STOM 1초봉 `pred60` 2025 전체 샘플을 Kronos Small 토크나이저→프리딕터 순서로 다시 학습한다. 사용자는 웹 대시보드에서 학습 진행률, GPU 상태, 로그를 직접 확인할 수 있어야 한다.

## 이번 실행에서 확인한 사실

| 시간(KST) | 항목 | 결과 |
|---|---|---|
| 2026-05-20 10:12 | 이전 실패 산출물 보관 | `finetune/outputs/stom_1s_grid_pred60_2025_full_small_failed_OOM_archive_20260520_101227` 로 이동 |
| 2026-05-20 10:12 | 웹 대시보드 재시작 | `http://127.0.0.1:5070/` HTTP 200 확인 |
| 2026-05-20 10:14 | 옵션 D 학습 1차 시작 | `tokenizer.progress.json` 생성 및 `status=running` 확인 |
| 2026-05-20 10:16 | 옵션 D 학습 1차 실패 | GPU/OOM 문제가 아니라 Windows CP949 stdout 인코딩 문제로 `UnicodeEncodeError` 발생 |
| 2026-05-20 10:20 | 대시보드 직접 경로 보완 | `http://127.0.0.1:5070/training` HTTP 200 확인 |

## 실패 원인

1차 재시작은 데이터 로딩까지 정상 진행되었다.

- 학습 샘플: `18,806,883`
- 검증 샘플: `3,925,397`
- 토크나이저 batch size: `64`
- validation batch size: `1`
- train steps/epoch: `293,858`

그러나 `train_tokenizer.py`의 진행 로그 문자열에 포함된 em dash(`—`)를 Windows CP949 stdout이 인코딩하지 못해 학습 step 0 전에 종료되었다.
따라서 이번 실패는 STOM 데이터, Qlib dataset, CUDA 연산, VRAM 부족, Kronos 모델 구조 문제가 아니다.

## 적용한 수정

1. `finetune/train_tokenizer.py`
   - AMP/torch.compile 진행 로그의 em dash를 ASCII hyphen으로 변경했다.
2. `finetune/run_stom_1s_finetune.py`
   - 자식 학습 프로세스에 `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1` 기본값을 주입해 Windows 콘솔/파이프 인코딩 실패 가능성을 낮췄다.
3. `webui/v2/__init__.py`
   - `/training`, `/dashboard` 직접 접속 경로가 v2 학습 대시보드 shell을 반환하도록 추가했다.
   - 전역 catch-all은 추가하지 않았다. API/static 오류를 숨기지 않기 위해서다.
4. `tests/test_v2_blueprint_isolation.py`
   - `/training`, `/dashboard`가 200 및 `kronos-v2-shell`을 반환하는 회귀 테스트를 추가했다.

## 검증

```powershell
C:\Python\64\Python3119\python.exe -m py_compile finetune\train_tokenizer.py finetune\run_stom_1s_finetune.py
C:\Python\64\Python3119\python.exe -m pytest tests\test_v2_blueprint_isolation.py tests\test_v2_route.py -q
```

결과: `8 passed`.

## 다음 실행 원칙

1. CP949 실패 run을 archive로 보관한다.
2. 같은 옵션 D 명령을 다시 시작한다.
3. 시작 후 5~10분 내 다음을 확인한다.
   - `/api/training/status`가 `status=running`인지
   - `step > 0`인지
   - `samples_per_second > 0`인지
   - GPU 사용률/VRAM이 증가하는지
4. 만약 batch 64에서 실제 CUDA OOM이 발생하면 이 기록과 분리하여 batch 32 또는 16 fallback을 진행한다.

## 2026-05-20 10:25 재시작 결과

CP949 실패 run은 `finetune/outputs/stom_1s_grid_pred60_2025_full_small_failed_cp949_archive_20260520_102513` 로 보관했다.

수정 커밋 후 같은 옵션 D 명령을 다시 시작했다.

| 확인 항목 | 값 |
|---|---|
| launcher PID | `91084` |
| runner PID | `20784` |
| tokenizer PID | `93016` |
| dashboard URL | `http://127.0.0.1:5070/training` |
| `/training` HTTP 상태 | `200` |
| 학습 상태 | `running` |
| 현재 단계 | `tokenizer` |
| batch size | `64` |
| validation batch size | `1` |
| train samples | `18,806,883` |
| val samples | `3,925,397` |
| train steps/epoch | `293,858` |
| torch.compile | `enabled - mode=max-autotune fullgraph=False` |
| AMP | `bf16`, scaler `False` |

10:29 기준 진행률 JSON은 아직 `step=0`이다. 이는 `torch.compile max-autotune` 첫 그래프 컴파일/워밍업 중일 가능성이 높다. 프로세스는 살아 있고 GPU 사용률도 관측되므로, 다음 점검은 `step > 0`, `samples_per_second > 0`, `loss` 생성 여부에 집중한다.

## 2026-05-20 10:42 torch.compile / Triton 실패

재시작된 옵션 D 학습은 step 0에서 실패했다. 원인은 데이터/OOM이 아니라 `torch.compile` 실행 중 PyTorch Inductor가 Triton을 요구했지만 현재 Windows 워크스테이션 Python 환경에 `triton` 모듈이 없었기 때문이다.

핵심 로그:

```text
torch._inductor.exc.InductorError: LoweringException: ModuleNotFoundError: No module named 'triton'
target: aten.addmm.default
```

판단:

- STOM 1초봉 dataset 로딩은 정상이다.
- train/val sample count 계산도 정상이다.
- batch 64 자체 OOM으로 실패한 증거는 없다.
- 실패 지점은 첫 compiled forward pass 전후다.
- 공식 Kronos fine-tuning 목적에는 `torch.compile`이 필수 조건이 아니므로, 현재 Windows 4080 SUPER 환경에서는 compile을 자동 skip하고 eager + bf16 AMP로 진행하는 것이 더 안정적이다.

적용 조치:

1. `train_tokenizer.py`에서 CUDA + compile 요청 상태라도 `triton` 모듈이 없으면 `torch.compile`을 건너뛰도록 보호했다.
2. 보호 메시지: `[Rank 0] torch.compile skipped - Triton is not installed; using eager mode.`
3. 기존 batch 64 / bf16 AMP / val batch 1 / full sample 조건은 유지한다.

검증:

```powershell
C:\Python\64\Python3119\python.exe -m py_compile finetune\train_tokenizer.py finetune\run_stom_1s_finetune.py
C:\Python\64\Python3119\python.exe -m pytest tests\test_v2_blueprint_isolation.py tests\test_v2_route.py -q
```

결과: `8 passed`.

## 2026-05-20 10:52 대시보드 live elapsed 보정

토크나이저 학습은 현재 첫 100 step 로그가 나오기 전까지 stdout/progress 파일이 갱신되지 않는 구조다. 이 때문에 실제 프로세스가 살아 있어도 대시보드의 elapsed 값이 마지막 progress 파일 기록 시점에 멈춰 보일 수 있다.

조치:

- `webui/training_monitor.py`에서 `status=running`이면 `timing.started_at` 기준 live elapsed를 API 응답 시점에 다시 계산하도록 보정했다.
- `seconds_since_update` 필드를 추가해 progress 파일이 얼마나 오래 갱신되지 않았는지도 확인할 수 있게 했다.
- 학습 자체는 건드리지 않았고, 웹 대시보드 표시/모니터링 품질만 개선했다.

검증:

```powershell
C:\Python\64\Python3119\python.exe -m py_compile webui\training_monitor.py
C:\Python\64\Python3119\python.exe -m pytest tests\test_v2_blueprint_isolation.py tests\test_v2_route.py -q
```

결과: `8 passed`.

## 2026-05-20 10:54 학습 step 진입 확인

Triton guard 적용 후 옵션 D 학습을 다시 시작했고, 웹 대시보드를 재기동해 `http://127.0.0.1:5070/training` 직접 접속을 확인했다.

| 항목 | 값 |
|---|---|
| 대시보드 URL | `http://127.0.0.1:5070/training` |
| `/training` | HTTP `200` |
| `/api/training/status` | HTTP `200` |
| 상태 | `running` |
| 단계 | `tokenizer` |
| step | `900 / 293,858` |
| tokenizer 단계 진행률 | `0.3063%` |
| 전체 학습 진행률 | `0.1531%` |
| samples/sec | 약 `95.11` |
| loss | `-0.0279` |
| last line | `[Rank 0, Epoch 1/1, Step 900/293858] LR 0.000025, Loss: -0.0279` |

해석:

- 이제 실제 학습 step이 증가하고 있으므로 더 이상 step 0 초기화/컴파일/인코딩 실패 상태가 아니다.
- `torch.compile`은 Triton 부재로 스킵되었지만, 공식 fine-tuning 자체는 eager + bf16 AMP로 정상 진행 중이다.
- 현재 관측 속도 기준 단순 계산 시 tokenizer train 구간만 약 54~56시간 수준이다. validation 구간은 batch 1이므로 별도 시간이 추가될 수 있다.
- 다음 점검은 30~60분 간격으로 `samples/sec`, `loss`, `ETA`, GPU 사용률, checkpoint 생성 여부를 확인하는 것이다.

## 2026-05-20 11:40:04 +09:00ST 학습 모니터링 스냅샷

Ralph 점검 명령을 다시 수행했고, 현재 옵션 D 전체 샘플 tokenizer 학습은 정상적으로 계속 진행 중이다. 웹 대시보드는 직접 브라우저로 다시 열었다.

| 항목 | 값 |
|---|---|
| 대시보드 URL | http://127.0.0.1:5070/training |
| /training | HTTP 200 |
| /api/training/status | HTTP 200 |
| 상태 | $(@{generated_at=2026-05-20T02:40:04Z; latest_stage=; overall_percent=5.8021; readiness=; run_name=stom_1s_grid_pred60_2025_full_small; run_path=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small; stage_count=1; stages=System.Object[]; status=running; updated_at=2026-05-20T02:40:00Z}.status) |
| 단계 | $(@{best_val_loss=; elapsed_seconds=3314.215636; epoch=1; epochs=1; eta_seconds=25217.688689933493; horizon=60; last_line=[Rank 0, Epoch 1/1, Step 34100/293858] LR 0.000196, Loss: -0.0304; last_loss=-0.0304; last_validation_loss=; mode=full; overall_percent=5.8021; run_name=stom_1s_grid_pred60_2025_full_small; samples_per_second=659.2401153177947; seconds_since_update=4.215636; source_path=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.progress.json; stage_count=2; stage_index=1; stage_percent=11.6042; status=running; stdout_log=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.stdout.log; step=34100; total_steps=293858; train_stage=tokenizer; updated_at=2026-05-20T02:40:00Z}.train_stage) |
| step | $(@{best_val_loss=; elapsed_seconds=3314.215636; epoch=1; epochs=1; eta_seconds=25217.688689933493; horizon=60; last_line=[Rank 0, Epoch 1/1, Step 34100/293858] LR 0.000196, Loss: -0.0304; last_loss=-0.0304; last_validation_loss=; mode=full; overall_percent=5.8021; run_name=stom_1s_grid_pred60_2025_full_small; samples_per_second=659.2401153177947; seconds_since_update=4.215636; source_path=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.progress.json; stage_count=2; stage_index=1; stage_percent=11.6042; status=running; stdout_log=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.stdout.log; step=34100; total_steps=293858; train_stage=tokenizer; updated_at=2026-05-20T02:40:00Z}.step) / 293858 |
| tokenizer 단계 진행률 | $stagePercent% |
| 전체 학습 진행률 | $overallPercent% |
| samples/sec | $([math]::Round(659.240115317795,2)) |
| 최근 loss | $(@{best_val_loss=; elapsed_seconds=3314.215636; epoch=1; epochs=1; eta_seconds=25217.688689933493; horizon=60; last_line=[Rank 0, Epoch 1/1, Step 34100/293858] LR 0.000196, Loss: -0.0304; last_loss=-0.0304; last_validation_loss=; mode=full; overall_percent=5.8021; run_name=stom_1s_grid_pred60_2025_full_small; samples_per_second=659.2401153177947; seconds_since_update=4.215636; source_path=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.progress.json; stage_count=2; stage_index=1; stage_percent=11.6042; status=running; stdout_log=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.stdout.log; step=34100; total_steps=293858; train_stage=tokenizer; updated_at=2026-05-20T02:40:00Z}.last_loss) |
| 최근 로그 | $(@{best_val_loss=; elapsed_seconds=3314.215636; epoch=1; epochs=1; eta_seconds=25217.688689933493; horizon=60; last_line=[Rank 0, Epoch 1/1, Step 34100/293858] LR 0.000196, Loss: -0.0304; last_loss=-0.0304; last_validation_loss=; mode=full; overall_percent=5.8021; run_name=stom_1s_grid_pred60_2025_full_small; samples_per_second=659.2401153177947; seconds_since_update=4.215636; source_path=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.progress.json; stage_count=2; stage_index=1; stage_percent=11.6042; status=running; stdout_log=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.stdout.log; step=34100; total_steps=293858; train_stage=tokenizer; updated_at=2026-05-20T02:40:00Z}.last_line) |
| train ETA | 약 $etaHours 시간 |
| train 예상 완료(KST) | $etaKst |
| progress 갱신 지연 | $([math]::Round([double]@{best_val_loss=; elapsed_seconds=3314.215636; epoch=1; epochs=1; eta_seconds=25217.688689933493; horizon=60; last_line=[Rank 0, Epoch 1/1, Step 34100/293858] LR 0.000196, Loss: -0.0304; last_loss=-0.0304; last_validation_loss=; mode=full; overall_percent=5.8021; run_name=stom_1s_grid_pred60_2025_full_small; samples_per_second=659.2401153177947; seconds_since_update=4.215636; source_path=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.progress.json; stage_count=2; stage_index=1; stage_percent=11.6042; status=running; stdout_log=D:\Chanil_Park\Project\Programming\Kronos\finetune\outputs\stom_1s_grid_pred60_2025_full_small\logs\tokenizer.stdout.log; step=34100; total_steps=293858; train_stage=tokenizer; updated_at=2026-05-20T02:40:00Z}.seconds_since_update,1)) 초 |

GPU API 원문 요약:

`json
{"available":true,"average_utilization_gpu_percent":93.0,"generated_at":"2026-05-20T02:40:04Z","gpus":[{"index":0,"memory_total_mib":16376.0,"memory_used_mib":6851.0,"memory_used_percent":41.84,"name":"NVIDIA GeForce RTX 4080 SUPER","power_draw_available":true,"power_draw_watts":191.44,"power_limit_watts":320.0,"temperature_c":67.0,"utilization_gpu_percent":93.0}],"power_draw_available":true,"total_memory_total_mib":16376.0,"total_memory_used_mib":6851.0,"total_memory_used_percent":41.84,"total_power_draw_watts":191.44,"total_power_limit_watts":320.0}
`

해석:

- 직전 기록의 step 1,600에서 이번 점검 기준 step 34100까지 증가했다.
- samples/sec가 $([math]::Round(659.240115317795,2))로 안정적으로 관측되어 실제 데이터 학습이 진행 중이다.
- 현재 진행률은 tokenizer 기준 $stagePercent%, 전체 both-stage 기준 $overallPercent%다.
- 다음 점검은 tokenizer 20~30% 구간 또는 30~60분 뒤에 수행해 속도 유지, loss 이상치, GPU 사용률, ETA 변화를 기록한다.
