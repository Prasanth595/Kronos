# 학습 대시보드 자동 새로고침/웹 통합 개발 계획

작성일: 2026-05-12 KST
Autopilot phase: ralplan

## 목표

STOM tick 전체 데이터 기반 Kronos 파인튜닝의 목적을 유지하면서, 사용자가 CMD를 보지 않아도 웹 전체에서 학습 상태를 확인할 수 있게 한다.

핵심 목표:

1. `/training` 실시간 학습 대시보드에 설정 가능한 자동 새로고침을 제공한다.
2. 학습 상태가 `running`일 때 설정 간격마다 runs/status/log/gpu를 다시 읽는다.
3. `/` 메인 Kronos UI와 `/stom` 예측/성과 대시보드에서도 현재 학습 상태 요약과 `/training` 링크를 보여준다.
4. 장기 학습 프로세스는 절대 종료하지 않고 관측만 한다.
5. 테스트와 code-review까지 통과한 상태로 commit한다.

## 현재 확인된 구현 상태

| 영역 | 현재 상태 | 개선 필요 |
|---|---|---|
| `/training` | 진행률/log/GPU 표시 가능 | 5초 고정 `setInterval`, 사용자 설정 없음 |
| `/` | 기본 Kronos 예측 UI | 학습 상태 요약/학습 대시보드 링크 부족 |
| `/stom` | 실제값 vs 예측값 성과 대시보드 | 학습 진행 상태 요약/학습 대시보드 링크 부족 |
| API | `/api/training/*` 존재 | UI에서 설정 가능한 refresh 제어 필요 |

## 구현 계획

### 1. Flask 설정값 추가

- `webui/app.py`에 refresh interval 파서 추가
- query parameter `refresh_interval` 또는 기본값을 받아 template에 전달
- 너무 빠른 polling 방지를 위해 최소/최대 초 단위 clamp 적용

### 2. `/training` 대시보드 개선

- 자동 새로고침 ON/OFF checkbox
- 새로고침 간격 seconds input
- 설정 저장: `localStorage`
- running 상태에서만 자동 반복 새로고침
- 완료/실패/중단 상태면 자동 새로고침 대기 또는 정지 메시지 표시
- 마지막 갱신 시각/다음 갱신 예정 표시

### 3. 전체 웹 통합

- `/` 메인 UI에 실시간 학습 상태 요약 카드 추가
- `/stom` 성과 대시보드에 실시간 학습 상태 요약 카드 추가
- 두 페이지 모두 `/training` 링크 제공
- 작은 위젯은 과도한 로그까지 가져오지 않고 `/api/training/status`만 사용한다

### 4. 테스트 계획

- Flask route test에서 `/training?refresh_interval=...` 기본값/clamp 확인
- `/`, `/stom`, `/training` HTML에 학습 상태 위젯/자동 새로고침 컨트롤이 포함되는지 확인
- 기존 `/api/training/*` 테스트 유지
- 최소 실행: `python -m pytest tests/test_training_monitor.py`
- 가능하면 관련 progress test도 실행: `python -m pytest tests/test_training_monitor.py tests/test_training_progress.py`

## 완료 기준

| 기준 | 완료 판단 |
|---|---|
| 자동 새로고침 설정 | `/training`에서 UI로 초 단위 변경 가능 |
| running 조건 | running 중인 run이 있으면 설정 간격마다 갱신 |
| 전체 웹 통합 | `/`, `/stom`에서 학습 요약과 `/training` 링크 확인 가능 |
| 테스트 | 관련 pytest 통과 |
| code-review | 자체 리뷰에서 BLOCK/REQUEST CHANGES 없음 |
| commit | 계획/구현/리뷰가 Lore commit으로 남음 |

## 현재 진행률

~~~text
전체 프로젝트 진행률: ███████████████████░ 97%
Autopilot 계획 단계: ████████████████████ 100%
구현 단계:           ░░░░░░░░░░░░░░░░░░░░ 0%
~~~