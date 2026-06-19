# STOM/Kronos 웹 대시보드 KST 시간 표준화 작업 기록

작성일: 2026-05-12 (KST)

## 목표

사용자가 `http://127.0.0.1:5070/training`에서 보는 학습 진행 정보와 다른 웹 대시보드의 학습 요약 정보를 모두 한국 시간 기준으로 이해할 수 있게 만드는 것이 목표다.

핵심 요구사항은 다음과 같다.

1. `/training` 학습 모니터의 갱신 시간, 최신 progress 시간, ETA 기반 완료 예상 시각을 KST로 표시한다.
2. `/stom` 성과/예측 대시보드 상단 학습 상태 스트립에도 KST 갱신 시간과 완료 예상 시각을 표시한다.
3. `/` 기본 Kronos 예측 UI 상단 학습 요약 카드에도 KST 갱신 시간과 완료 예상 시각을 표시한다.
4. 기존 학습 프로세스, DB, CUDA/PyTorch 환경, 학습 산출물은 절대 변경하지 않는다.

## 변경 범위

수정한 파일은 웹 표시 계층과 테스트에 한정했다.

- `webui/templates/training_dashboard.html`
  - `Asia/Seoul` 고정 KST 포맷 헬퍼 추가
  - ETA 초 단위를 `완료 예상 시각(KST)`로 변환
  - 마지막/다음 새로고침 시각을 KST로 표시
  - 전체 진행, 단계별 진행, artifact 갱신, GPU 생성 시각, history 갱신 시각을 KST로 표시
- `webui/templates/stom_dashboard.html`
  - 상단 학습 스트립에 `Finish(KST)` 셀 추가
  - KST 시간대 게이트(`stomKstGate`) 추가
  - API의 UTC/ISO 시간과 ETA를 KST 표시로 변환
- `webui/templates/index.html`
  - 기본 예측 UI 상단 학습 요약 카드에 `Finish(KST)` 셀 추가
  - 학습 갱신 시간, 완료 예상 시각, 비교 테이블/슬라이더 날짜 표시를 KST 기준으로 변환
- `tests/test_training_monitor.py`
  - 라우트 HTML에 KST 헬퍼/필드가 포함되는지 확인하는 회귀 테스트 추가

## 현재 live 검증 결과

검증 시각 기준 live API 상태는 다음과 같았다.

- URL: `http://127.0.0.1:5070/api/training/status`
- 상태: `running`
- 단계: `tokenizer`
- step: `1,611,000 / 4,701,721`
- 전체 진행률: `17.132%`
- ETA: `192,354.29초`
- 계산된 완료 예상: `2026-05-14 23:01:04 KST`

HTTP marker 검증:

- `/training`: `Asia/Seoul / KST`, `formatKstDateTime`, `formatKstEtaTarget`, `Finish time(KST)` 확인
- `/stom`: `stomTrainingFinish`, `stomKstGate`, `formatKstDateTime`, `Asia/Seoul / KST` 확인
- `/`: `trainingInlineFinish`, `formatKstDateTime`, `Finish(KST)` 확인

## 테스트/검증 명령

```powershell
C:\Python\64\Python3119\python.exe -m pytest tests\test_training_monitor.py -q
node --check .omx\tmp\js-check\training_dashboard.js
node --check .omx\tmp\js-check\stom_dashboard.js
node --check .omx\tmp\js-check\index.js
```

결과:

- `10 passed in 2.35s`
- 3개 템플릿에서 추출한 JavaScript 모두 `node --check` 통과
- live HTTP 3개 페이지 모두 KST marker 확인

## 주의사항

- 이번 변경은 표시 기준을 바꾼 것이며 학습 데이터, 학습 루프, checkpoint, predictor, CUDA 설정에는 영향을 주지 않는다.
- ETA는 API가 제공하는 `eta_seconds`를 현재 브라우저/서버 요청 시각 기준으로 더해 계산하므로, 학습 속도 변화에 따라 매 새로고침마다 변할 수 있다.
- 브라우저 화면에서 보이는 `KST`는 `Asia/Seoul` timezone을 명시적으로 지정해 생성한다. 로컬 PC의 Windows 시간대 설정과 무관하게 KST로 표시되도록 했다.
