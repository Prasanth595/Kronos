# STOM 학습 유지 웹 대시보드 개선 1단계 구현 기록

작성일: 2026-05-12 KST
실행 모드: `$ralph`
기준 계획: `docs/stom_dashboard_safe_parallel_improvement_plan.md`

## 1. 이번 단계의 목표

현재 실행 중인 STOM full training을 중단하지 않고, `/training`, `/`, `/stom`이 같은 기준으로 학습 상태와 예측 성과 준비 상태를 표시하도록 개선했다.

핵심 목표:

1. checkpoint/predictor 전환 전에는 예측 성과를 표시하지 않는다.
2. API가 공통 readiness 정책을 내려주고, 세 화면은 같은 의미의 상태를 표시한다.
3. 웹 변경은 학습 process, DB, current output을 수정하지 않는다.

## 2. 구현 내용

### 공통 readiness 정책

`webui/app.py`에 `build_training_readiness()`를 추가했다.

판단 기준:

- tokenizer 단계 또는 running 상태: `성과 대기: tokenizer 학습 중`
- predictor 단계 진행 중: `predictor 학습 중`
- predictor 완료: `예측 성과 확인 가능`

`/api/training/status` 응답에 아래 필드를 추가했다.

```json
{
  "readiness": {
    "level": "waiting",
    "label": "성과 대기: tokenizer 학습 중",
    "message": "현재 tokenizer 단계입니다. checkpoint와 predictor가 아직 준비되지 않아 예측 정확도/수익률을 판단하지 않습니다.",
    "performance_ready": false,
    "predictor_started": false,
    "predictor_complete": false
  }
}
```

### `/training`

- `예측 성과 준비 상태` 카드를 추가했다.
- readiness label/message/predictor 시작/완료/성과 가능 여부를 표시한다.
- API/log 값은 기존처럼 escape 처리된 경로만 사용한다.

### `/`

- 상단 `실시간 학습 상태` 카드에 `성과 상태` 필드를 추가했다.
- readiness message를 별도 안내 박스로 표시한다.

### `/stom`

- 상단 학습 strip에 `성과 상태` 필드를 추가했다.
- predictor 전환 전에는 실제값/예측값 성과를 확정하지 않는다는 안내를 표시한다.

## 3. 현재 live 학습 상태

구현/검증 중 live API 기준:

```text
status: running
stage: tokenizer
step: 1,177,000 / 4,701,721
tokenizer 진행률: 25.0334%
전체 both-stage 진행률: 12.5167%
readiness: 성과 대기: tokenizer 학습 중
```

## 4. 검증

테스트:

```text
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py tests\test_training_progress.py -q
9 passed in 1.70s
```

컴파일:

```text
C:\Python\64\Python3119\python.exe -m compileall webui
통과
```

Live HTTP:

```text
/training?refresh_interval=10: trainingReadinessCard, readiness-card 확인
/?refresh_interval=10: trainingInlineReadiness, training-readiness-note 확인
/stom?refresh_interval=10: stomTrainingReadiness, training-readiness-note 확인
```

Git:

```text
git diff --check
통과
```

## 5. 현재/남은 단계

```text
1단계 공통 readiness UI/API       [████████████████████] 100%
학습 모니터링 체계                [████████████████████] 100%
웹 기본 통합                      [████████████████████] 100%
프론트엔드 고도화                 [██████████░░░░░░░░░░] 50%
read-only artifacts API            [░░░░░░░░░░░░░░░░░░░░] 0%
진행률 히스토리 시각화             [░░░░░░░░░░░░░░░░░░░░] 0%
학습 산출물 전체 진행률            [███░░░░░░░░░░░░░░░░░] 12.52%
```

## 6. 다음 권장 OMX 명령

```text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획의 2단계를 구현하세요. 목표는 checkpoint/predictor/weight artifact 상태를 읽기 전용 API로 노출하고, /training과 /stom에서 checkpoint 생성 여부를 명확히 표시하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고 live HTTP 확인 후 Lore commit으로 남기세요.
```
