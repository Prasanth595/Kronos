# STOM 학습 대시보드 병렬 개선 4단계: GPU/ETA/속도 카드

작성일: 2026-05-12 KST
작업 범위: 현재 실행 중인 STOM full training을 중단하지 않고, `/training` 웹 대시보드의 GPU/ETA/속도 표시를 read-only로 고도화

## 1. 이번 단계 목표

사용자는 긴 학습을 CMD가 아니라 웹 화면에서 확인하고 싶어 했습니다. 4단계는 `학습이 실제로 계속 진행 중인지`, `속도는 어느 정도인지`, `남은 시간은 얼마인지`, `GPU가 어느 정도 사용되는지`를 한눈에 볼 수 있게 만드는 단계입니다.

중요 제한:

- 학습 프로세스 중단/재시작 금지
- CUDA/PyTorch/학습 코드/DB/finetune 출력물 수정 금지
- `progress.json`, stdout log, `nvidia-smi` 조회 결과만 읽기
- predictor 완료 전 예측 성과/정확도 판단 금지

## 2. 구현 내용

### 학습 속도 / ETA 카드

`webui/templates/training_dashboard.html`에 `runtimeSummaryCard`를 추가했습니다.

표시 항목:

- 현재 단계
- 단계 상태
- samples/sec
- 경과 시간
- 남은 시간
- 예상 완료 시각
- 최근 loss
- 최근 갱신 시각

### GPU / 전력 카드 개선

`webui/training_monitor.py`의 `query_gpu_status()`가 기존 개별 GPU 값 외에 summary 값을 함께 반환하도록 확장했습니다.

추가된 값:

- `average_utilization_gpu_percent`
- `total_memory_used_mib`
- `total_memory_total_mib`
- `total_memory_used_percent`
- `total_power_limit_watts`
- `power_draw_available`
- GPU별 `power_draw_available`

`nvidia-smi`가 현재 워크스테이션에서 power draw를 실측하지 못하는 경우에도, 전력 제한값은 보여주고 실측 전력은 `실측 불가`로 명확하게 표시합니다.

### UI 개선

`/training` GPU 테이블을 다음 항목으로 확장했습니다.

- GPU 이름
- Util %
- VRAM %
- VRAM MiB
- Power
- Limit
- Temp

## 3. live 학습 상태 스냅샷

검증 시점 기준 live API 관측값입니다.

```text
status: running
run: stom_1s_grid_pred60_2025_full_small
stage: tokenizer
step: 1,329,000 / 4,701,721
tokenizer stage 진행률: 28.2662%
전체 both-stage 진행률: 14.1331%
최근 loss: -0.0319
속도: 약 65.37 samples/sec
ETA: 약 206,362초
```

GPU live API 관측값:

```text
GPU: NVIDIA GeForce RTX 4080 SUPER
average utilization: 39.0%
VRAM: 3,212 / 16,376 MiB, 19.61%
power draw: 실측 불가
power limit: 320.0 W
temperature: 44 C
```

## 4. 검증 증거

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py tests\test_training_progress.py -q
# 13 passed in 1.94s

C:\Python\64\Python3119\python.exe -m compileall webui
# 통과

git diff --check
# 통과
```

Live HTTP 확인:

```text
/api/training/gpu
- available: true
- average_utilization_gpu_percent: 39.0
- total_memory_used_percent: 19.61
- power_draw_available: false
- total_power_limit_watts: 320.0

/api/training/status
- status: running
- latest_stage.train_stage: tokenizer
- samples_per_second: 약 65.37
- eta_seconds: 약 206,362

/training?refresh_interval=10
- runtimeSummaryCard 확인
- runtimeMetrics 확인
- gpuSummaryMetrics 확인
- Power/Limit 컬럼 확인
```

## 5. AI slop cleaner 점검

범위는 이번 Ralph 세션 변경 파일로 제한했습니다.

- `webui/training_monitor.py`: GPU summary 계산은 기존 `query_gpu_status()` 안에서 유지해 새 의존성/새 계층을 만들지 않았습니다.
- `webui/templates/training_dashboard.html`: 숫자/시간/전력 format helper를 추가해 반복 포맷을 줄였습니다.
- `tests/test_training_monitor.py`: power draw 미지원 환경 회귀 테스트를 추가했습니다.
- 신규 의존성: 없음
- 학습 산출물/DB 변경: 없음

## 6. 진행률

```text
1단계 공통 readiness UI/API       [██████████] 100%
2단계 read-only artifacts API      [██████████] 100%
3단계 진행률 히스토리 표시        [██████████] 100%
4단계 GPU/ETA/속도 카드 개선      [██████████] 100%
5단계 /stom 성과 준비 상태 연결   [░░░░░░░░░░] 0%
6단계 최종 code-review 문서       [░░░░░░░░░░] 0%
프론트엔드 고도화 전체            [████████░░] 80%
학습 산출물 전체 진행률           [█░░░░░░░░░] 14.13%
```

## 7. 다음 권장 OMX 명령

```text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획의 5단계를 구현하세요. 목표는 /stom 성과 대시보드 상단에도 predictor 미시작/성과 대기/학습 진행 상태와 artifact readiness를 더 명확히 연결해, predictor 완료 전에는 예측 성과를 오해하지 않도록 하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고 live HTTP 확인 후 Lore commit으로 남기세요.
```
