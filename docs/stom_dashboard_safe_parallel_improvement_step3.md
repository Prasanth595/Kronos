# STOM 학습 대시보드 병렬 개선 3단계: 진행률 히스토리

작성일: 2026-05-12 KST
작업 범위: 현재 실행 중인 STOM full training을 중단하지 않고, 웹 대시보드가 stdout/progress JSON을 읽기 전용으로 분석해 최근 step 흐름을 보여주도록 개선

## 1. 이번 단계 목표

사용자는 CMD 로그가 아니라 웹 화면에서 학습 진행 상태를 빠르게 보고 싶어 했습니다. 3단계의 목표는 `/training` 화면에 다음 정보를 추가하는 것입니다.

- 최근 학습 step 히스토리
- 단계 진행률(stage %)과 전체 진행률(overall %)
- learning rate와 loss 변화
- predictor 단계가 아직 시작되지 않았을 때 tokenizer 로그를 잘못 보여주지 않는 안전장치

## 2. 구현 내용

### API

- `webui/training_monitor.py`
  - Kronos 학습 stdout 라인 형식 `[Rank 0, Epoch 1/1, Step ...] LR ..., Loss: ...`를 파싱하는 정규식 추가
  - `load_training_history()` 추가
  - 최근 stdout tail에서 학습 step만 추출하여 `points`, `latest_point`, `latest_progress` 반환
  - 명시적으로 선택한 단계에 stdout 로그가 없으면 최신 다른 단계 로그로 fallback하지 않도록 보정

- `webui/app.py`
  - `/api/training/history` 추가
  - `run`, `stage`, `limit` 쿼리 지원

### UI

- `webui/templates/training_dashboard.html`
  - `/training`에 `진행률 히스토리` 카드 추가
  - 최근 step, stage %, overall %, LR, loss 테이블 표시
  - 자동 새로고침 흐름에 history API 호출 포함
  - 단계 클릭 시 로그뿐 아니라 history도 즉시 갱신

### 테스트

- `tests/test_training_monitor.py`
  - stdout 로그에서 최근 step 히스토리를 파싱하는 단위 테스트 추가
  - predictor처럼 아직 stdout 로그가 없는 명시 단계는 tokenizer 로그로 fallback하지 않는 회귀 테스트 추가
  - `/api/training/history` route 등록 테스트 추가

## 3. live 학습 상태 스냅샷

검증 시점 기준 live API 관측값입니다.

```text
status: running
run: stom_1s_grid_pred60_2025_full_small
stage: tokenizer
step: 1,320,000 / 4,701,721
tokenizer stage 진행률: 28.0748%
전체 both-stage 진행률: 14.0374%
최근 loss: -0.0301
속도: 약 65.44 samples/sec
ETA: 약 206,714초
readiness: 성과 대기(tokenizer 학습 중, predictor 미시작)
```

## 4. 검증 증거

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py tests\test_training_progress.py -q
# 12 passed in 2.07s

C:\Python\64\Python3119\python.exe -m compileall webui
# 통과
```

Live HTTP 확인:

```text
/api/training/history?limit=5
- point_count: 5
- latest_point.step: 1,320,000
- latest_point.stage_percent: 28.0748
- latest_point.overall_percent: 14.0374

/api/training/history?stage=predictor&limit=5
- stage: predictor
- point_count: 0
- error: no stdout log found for this run

/training?refresh_interval=10
- HTTP 200
- historyRows 마커 확인
- historySummary 마커 확인
- refreshIntervalSeconds 마커 확인
```

## 5. AI slop cleaner 점검

범위는 이번 Ralph 세션 변경 파일로 제한했습니다.

- 중복/불필요한 추상화: 별도 제거 필요 없음
- 잘못된 fallback 위험: 발견되어 보정 완료
- 테스트 보강: predictor 미시작 단계 fallback 금지 회귀 테스트 추가
- 신규 의존성: 없음

## 6. 진행률

```text
1단계 공통 readiness UI/API       [██████████] 100%
2단계 read-only artifacts API      [██████████] 100%
3단계 진행률 히스토리 표시        [██████████] 100%
4단계 GPU/ETA/속도 카드 개선      [░░░░░░░░░░] 0%
5단계 /stom 성과 준비 상태 연결   [░░░░░░░░░░] 0%
6단계 최종 code-review 문서       [░░░░░░░░░░] 0%
프론트엔드 고도화 전체            [██████░░░░] 60%
학습 산출물 전체 진행률           [█░░░░░░░░░] 14.04%
```

## 7. 다음 권장 OMX 명령

```text
$ralph 현재 실행 중인 STOM full training은 중단하지 말고, docs/stom_dashboard_safe_parallel_improvement_plan.md 계획의 4단계를 구현하세요. 목표는 /training의 GPU/ETA/속도 카드를 개선해 samples/sec, ETA, GPU util/VRAM/온도/전력 상태를 더 명확히 표시하는 것입니다. tests/test_training_monitor.py와 tests/test_training_progress.py를 통과시키고 live HTTP 확인 후 Lore commit으로 남기세요.
```
