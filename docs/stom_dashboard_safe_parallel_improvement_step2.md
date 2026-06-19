# STOM 학습 유지 웹 대시보드 개선 2단계 구현 기록

작성일: 2026-05-12 KST
실행 모드: `$ralph`
기준 계획: `docs/stom_dashboard_safe_parallel_improvement_plan.md`

## 1. 이번 단계의 목표

현재 실행 중인 STOM full training을 중단하지 않고, checkpoint/predictor/model weight artifact 상태를 읽기 전용으로 확인하는 API와 웹 표시를 추가했다.

핵심 목표:

1. current run output을 수정하지 않고 artifact 상태만 읽는다.
2. tokenizer/predictor checkpoint 생성 여부를 `/api/training/artifacts`로 확인한다.
3. `/training`과 `/stom`에서 checkpoint가 아직 없음을 명확히 표시한다.
4. predictor checkpoint 전에는 예측 성과를 확정하지 않는다.

## 2. 구현 내용

### read-only artifact API

`webui/training_monitor.py`에 `inspect_training_artifacts()`를 추가했다.

확인 항목:

- `finetune_tokenizer/checkpoints`
- `finetune_predictor/checkpoints`
- `.pt`, `.pth`, `.safetensors`, `.ckpt`, `.bin` weight 파일
- tokenizer/predictor progress/log/manifest 존재 여부

`webui/app.py`에 아래 endpoint를 추가했다.

```text
GET /api/training/artifacts
GET /api/training/artifacts?run=<run_name>
```

현재 live 응답 요약:

```text
level: waiting
label: checkpoint 대기
model_weight_file_count: 0
checkpoint_file_count: 0
tokenizer_checkpoint_ready: false
predictor_checkpoint_ready: false
```

### `/training`

- `Checkpoint / Predictor Artifact` 카드를 추가했다.
- model weight 파일 수, checkpoint 후보 파일 수, tokenizer/predictor checkpoint 상태, predictor 시작 여부를 표시한다.

### `/stom`

- 상단 학습 strip 아래에 artifact 상태 문구를 추가했다.
- 현재 checkpoint/model artifact가 없으면 `checkpoint 대기` 상태로 표시된다.

## 3. 현재 live 학습 상태

구현/검증 중 live API 기준:

```text
status: running
stage: tokenizer
step: 1,198,000 / 4,701,721
tokenizer 진행률: 25.4800%
전체 both-stage 진행률: 12.7400%
artifact: checkpoint 대기, model weight 0개, checkpoint 0개
```

## 4. 검증

테스트:

```text
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py tests\test_training_progress.py -q
10 passed in 2.17s
```

컴파일:

```text
C:\Python\64\Python3119\python.exe -m compileall webui
통과
```

Live HTTP:

```text
/api/training/status: readiness 확인
/api/training/artifacts: checkpoint 대기, weight 0개 확인
/training?refresh_interval=10: trainingArtifactCard 확인
/stom?refresh_interval=10: stomTrainingArtifacts 확인
```

Git:

```text
git diff --check
통과
```

## 5. Ralph deslop 점검

범위:

- `webui/training_monitor.py`
- `webui/app.py`
- `webui/templates/training_dashboard.html`
- `webui/templates/stom_dashboard.html`
- `tests/test_training_monitor.py`

점검 결과:

- 새 API는 읽기 전용 helper에만 추가되어 학습 프로세스와 분리됨
- path traversal은 기존 `resolve_run_dir()`/`_is_relative_to()` 경계를 재사용함
- UI는 existing escape 경로와 textContent 중심으로 표시함
- 2단계 범위를 넘어서는 히스토리 차트/추가 프론트 통합은 다음 단계로 보류함

## 6. 현재/남은 단계

```text
1단계 공통 readiness UI/API       [████████████████████] 100%
2단계 read-only artifacts API      [████████████████████] 100%
학습 모니터링 체계                [████████████████████] 100%
웹 기본 통합                      [████████████████████] 100%
프론트엔드 고도화                 [████████████░░░░░░░░] 60%
진행률 히스토리 시각화             [░░░░░░░░░░░░░░░░░░░░] 0%
학습 산출물 전체 진행률            [███░░░░░░░░░░░░░░░░░] 12.74%
```

## 7. 다음 권장 OMX 명령

```text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획의 3단계를 구현하세요. 목표는 tokenizer progress JSON/log를 읽기 전용으로 사용해 /training에 간단한 진행률 히스토리 카드 또는 표를 추가하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고 live HTTP 확인 후 Lore commit으로 남기세요.
```
