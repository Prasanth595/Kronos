# Session Wrap Followups — 2026-05-18

본 세션(디자인 시스템 v2 통합 + 7 탭 본격 구현 + P3/P4/P6 cutover)의 후속 작업 목록. 다음 세션 시작 시 참조용.

---

## 🔴 우선순위 HIGH — 학습 의존 + 정식 게이트

### 1. 재학습 (validation OOM 수정 후 finetune 재실행)
- **사유**: predictor 단계 진입 전제 — P3 Forecast 실 검증, STOM 결과 채움, readiness gate `ready` 전환에 필수
- **블로커**: validation batch size 가 GPU VRAM 한계 초과 — finetune 코드 검토 필요
- **권장 조치**:
  - `finetune/configs/*.yaml` 의 validation batch size 축소 (예: 32 → 8)
  - 또는 `gradient_checkpointing=True` 추가
  - 또는 mixed precision validation 활성화
- **영역**: finetune 코드 (디자인/v2 와 무관)
- **검증**: tokenizer 100% 진입 + predictor stage 자동 전환 + checkpoint 1개 이상 생성

### 2. P5 Lighthouse + a11y 정식 quality gate
- **사유**: plan §4 P5 정식 게이트 — execution complete 표시를 위한 마지막 phase
- **체크리스트**:
  - [ ] `lighthouse http://127.0.0.1:5070/ --output=json --output-path=docs/lighthouse_v2.json --chrome-flags='--headless=new'`
  - [ ] a11y 점수 ≥ 90 (WCAG AA 색상 대비 4.5:1, focus ring, aria-label)
  - [ ] perf 점수 ≥ 80 (FLASK_ENV=production + waitress + gzip 환경)
  - [ ] code-reviewer 결과를 `docs/kronos_dashboard_overhaul_p5_review.md` 별도 저장 (자기 승인 방지)
  - [ ] 키보드 네비게이션 검증 (Tab/Enter 로 모든 탭/슬라이더 접근)
- **권장 환경**: FLASK_ENV=production + waitress 또는 gunicorn + gzip 미들웨어

---

## 🟠 우선순위 MEDIUM — 응답 스키마 의존

### 3. Forecast Candlestick 차트 전환
- **현재**: ECharts 라인 차트 (입력/예측/실측)
- **목표**: OHLC 캔들 차트 + 예측 영역 음영 표시
- **블로커**: `/api/predict` 응답이 OHLC 구조 (`open, high, low, close`) 인지 검증 필요
- **위치**: `webui/v2_src/src/tabs/ForecastWorkbenchTab.svelte` 의 `chartOption` derived
- **참고**: ECharts `candlestick` series type 사용

### 4. STOM Plotly heatmap dynamic import
- **현재**: diagnostics 응답을 raw JSON pre 로 표시
- **목표**: Plotly heatmap 으로 시각화
- **블로커**: `/api/stom/diagnostics` 의 heatmap 데이터 구조 확정 필요
- **위치**: `webui/v2_src/src/tabs/StomDiagnosticsTab.svelte`
- **구현 방식**: `const Plotly = await import('plotly.js-dist-min')` dynamic import — STOM 탭 진입 시에만 로드 (P1.5 design_spec §7)
- **테마 연동**: `kronos:theme` 이벤트 핸들러로 light/dark 색상 자동 갱신

### 5. STOM top-k 추천 카드
- **현재**: 미구현
- **목표**: `/api/stom/recommendations?date=YYYY-MM-DD` 응답을 카드 그리드로
- **블로커**: 날짜 파라미터 필수 + 응답 스키마 검증 필요
- **위치**: `StomDiagnosticsTab.svelte` 에 새 섹션 추가
- **UX**: 날짜 picker (or 가장 최근 날짜 자동) + top-k 표

### 6. STOM backtest 상세 모달
- **현재**: 백테스트 파일 목록만 표시
- **목표**: 클릭 시 `/api/stom/backtest-report?file=` 응답을 모달로
- **위치**: `StomDiagnosticsTab.svelte` 의 `selectFile` 함수에 backtest 케이스 추가

---

## 🟡 우선순위 LOW — 부가 폴리시

### 7. Forecast 결과 CSV 다운로드
- **사유**: 예측 결과를 외부 분석에 활용
- **구현**: client-side `Blob` 생성 — 백엔드 endpoint 추가 0
- **위치**: `ForecastWorkbenchTab.svelte` 에 "내보내기" 버튼 + Blob 생성 함수

### 8. Settings 학습 단계 알림 watcher
- **사유**: tokenizer → predictor 전환 시 자동 알림
- **구현**: `polling.ts` 의 `pollStatus()` 후 stage 변화 감지 → `new Notification()`
- **권한**: 이미 SettingsTab 에서 권한 요청 UI 구현됨

### 9. History run 별 손실 곡선 미니어처
- **블로커**: `/api/training/runs/<name>/history` endpoint 없음 — 백엔드 추가 필요 (별도 PR)
- **대안**: 현재 진행 중 run 만 손실 곡선 표시 (이미 Live Training 탭에 있음)

---

## 🟢 우선순위 OPTIONAL — 운영/정리

### 10. v1 페이지 6개월 archive 후 삭제 결정
- **시점**: P6 cutover (2026-05-18) + 6개월 = 2026-11-18 이후
- **결정 기준**: 그 시점에 v2 SPA 의 동등 기능 완비 확인 후 사용자 명시 OK
- **삭제 대상**: `webui/templates/{index,training_dashboard,stom_dashboard}.html` + `webui/app.py` 의 `@app.route('/v1/*')` 3 핸들러

### 11. Production 배포 환경 분리
- **현재**: Flask `debug=True` (dev mode)
- **목표**: `FLASK_ENV=production` + waitress (Windows) 또는 gunicorn — gzip 미들웨어 추가
- **사유**: P5 Lighthouse perf 측정 정확도 + production-equivalent 검증

---

## 다음 세션 시작 시 권장 순서

1. **재학습**: validation OOM 수정 후 finetune 재시작 (별도 영역)
2. **재학습 진행 중**: P5 Lighthouse 측정 시도 (학습 중 GPU 영향 없음, Chrome headless 만 사용)
3. **재학습 종료 시**: Forecast/STOM 응답 스키마 확정 → Candlestick + Plotly heatmap 도입
4. **그 후**: 부가 폴리시 (CSV 다운로드, 알림 watcher) + production 환경 분리

---

*작성: Claude (현 세션)*
*세션 기간: 2026-05-12 ~ 2026-05-18 KST*
*총 commit 수: 약 20 (P0 ~ P6 cutover + docs + session-wrap)*
