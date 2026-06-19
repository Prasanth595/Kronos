# Kronos 통합 대시보드 — Claude Designer 리모델링 핸드오프

> **이 문서 하나로 Claude `frontend-design` 스킬이 전체 대시보드를 시각적으로 리모델링할 수 있도록 작성한 단일 핸드오프 파일이다. 기존 도메인 기능과 API는 그대로 두고 UI 표현 계층만 재구성한다.**

**작성일**: 2026-05-16 KST · **마지막 갱신**: 2026-05-18 KST (Designer 프로토타입 통합 + P6 cutover 반영)
**대상 스킬**: `document-skills:frontend-design`
**핸드오프 범위**: webui v2 SPA (`/`) 전체 시각 리모델링 + 미구현 탭(P2~P6) 디자인 사양 포함
**대상 디렉터리**: `D:\Chanil_Park\Project\Programming\Kronos\webui\v2_src\src\`
**금지 디렉터리**: `D:\Chanil_Park\Project\Programming\Kronos\webui\app.py`, `finetune/`, `model/`, `_database/` (백엔드/모델 무변경)

---

## 0. 최종 상태 (2026-05-18)

| Phase | 상태 | Commit |
|---|---|---|
| P0 합의 계획 | ✅ 완료 | 5c46ccd |
| P1 SSR Jinja shell | ✅ 완료 | 888bb08 |
| P1.5 Vite+Svelte 빌드 인프라 | ✅ 완료 | 2695151 |
| 디자인 시스템 v2 (light+dark, mint accent) | ✅ 완료 | ce42ab4 |
| Live Training 탭 리디자인 | ✅ 완료 | a631b54 |
| Artifacts/SystemHealth/Settings/History 탭 | ✅ 완료 | 7ff0d71 ~ 8f1beb4 |
| Forecast Workbench (P3) | ✅ 완료 | 7e38c18 |
| STOM Diagnostics (P4) | ✅ 완료 | 98d66d2 |
| **P6 Cutover** — `/` = v2, `/v1/*` archive, `/v2` → 301 | ✅ 완료 | **8562c64** |
| P5 Lighthouse a11y/perf gate | ⏸ 미진행 | - |

**핵심 결과**:
- 사용자는 이제 `http://127.0.0.1:5070/` 로 진입하면 새 통합 대시보드를 본다
- 기존 화면 3개 (`/`, `/training`, `/stom`) 는 `/v1/*` 로 archive (6개월 후 삭제 판단)
- `/v2` 북마크는 `/` 로 영구 리다이렉트 (301)
- 7개 탭 모두 정식 기능 작동 (placeholder 0개)

---

## 1. TL;DR (3문장 요약)

1. **무엇이 있는가**: Flask + 7 탭 v2 SPA (`/`) + 5개 legacy 라우트 (`/v1/*`) + 24개 read-only API. Svelte 5 + Vite 5 + Tailwind prebuilt + ECharts + Pretendard Variable + JetBrains Mono. light+dark 토글.
2. **무엇이 더 필요한가**: P5 Lighthouse 정식 측정 + a11y 검증 + 잔여 폴리시 (Candlestick / Plotly heatmap / top-k 카드 / CSV 다운로드).
3. **무엇을 건드리면 안 되는가**: Flask `app.py` 의 `/api/*`, 학습 코드, DB, finetune outputs, readiness gate 정책.

---

## 2. 프로젝트 컨텍스트

### 2.1 Kronos
- **도메인**: K-line(캔들차트) 시계열 예측 모델 (금융 시장 데이터)
- **모델**: 2단계 학습 — Tokenizer → Predictor
- **데이터**: STOM (Securities Time-series Open Market), pred60
- **사용자**: 단일 ML 엔지니어 (Windows 11, RTX 4080 SUPER, Python 3.11.13)

### 2.2 학습 현황
- 마지막 run `stom_1s_grid_pred60_2025_full_small`: tokenizer ~75% 에서 validation OOM 으로 실패
- predictor 미진입 → checkpoint 0개 → readiness gate `waiting`
- 재학습 시 OOM 원인 수정 필요 (batch size 축소 등) — 별도 PR

---

## 3. 라우트 맵 (P6 cutover 이후)

| URL | 핸들러 | 대상 | 비고 |
|---|---|---|---|
| **`/`** | `webui/v2/__init__.py::v2_root` | v2 SPA (dist 모드: `webui/static/v2/dist/index.html`, fallback: `webui/templates/v2_shell.html`) | **신 통합 대시보드** |
| **`/v1/`** | `webui/app.py::v1_index` | `templates/index.html` | v1 메인 예측 화면 (legacy) |
| **`/v1/training`** | `webui/app.py::v1_training_dashboard_page` | `templates/training_dashboard.html` | v1 학습 모니터 |
| **`/v1/stom`** | `webui/app.py::v1_stom_dashboard_page` | `templates/stom_dashboard.html` | v1 STOM 진단 |
| `/v2` | `webui/v2/__init__.py::v2_legacy_redirect` | 301 → `/` | 호환 |
| `/v2/<path>` | `webui/v2/__init__.py::v2_legacy_subpath` | 301 → `/` | 호환 |
| `/api/*` | 변경 없음 | `webui/app.py` | 24개 read-only endpoint |

---

## 4. v2 SPA 탭 (7개, 전부 정식 구현 완료)

| 탭 ID | 라벨 | 구현 상태 | 사용 API | 핵심 위젯/기능 |
|---|---|---|---|---|
| `live-training` | 실시간 학습 | ✅ 정식 | status/history/artifacts/gpu | Hero 도넛 + 스테퍼 + 메트릭 4 카드 + W3 Loss + W6 통계 + W4 ETA + W5 GPU |
| `forecast` | 예측 워크벤치 | ✅ 정식 (P3) | available-models / data-files / load-model / load-data / **predict** | 모델/데이터 selector + 4 슬라이더 + Seed 토글 + 결과 차트 |
| `stom` | 예측 진단 | ✅ 정식 (P4) | stom/summary + 8개 list/detail | DB KPI 4 + 파일 브라우저 + diagnostics 자동 조회 |
| `artifacts` | 아티팩트 & 모델 | ✅ 정식 | training/artifacts | Checkpoint/Weight/Predictor 3 카드 + 파일 row |
| `history` | 기록 & 런 | ✅ 정식 (P2) | training/runs | 4 KPI + 필터/정렬 + 14 run 그리드 |
| `system-health` | 시스템 상태 | ✅ 정식 | training/gpu | 3 KPI + 시계열 차트 + 하드웨어 표 |
| `settings` | 설정 | ✅ 정식 | localStorage only | 테마 카드 + 새로고침 5단계 + Notification API + 초기화 |

---

## 5. 디자인 시스템 v2 (현재 적용 중)

### 5.1 핵심 결정
- **방향**: human-approachable (Airbnb/Mercury 톤) + ML 운영 도구 정보 밀도 (Datadog/Linear)
- **베이스**: 라이트 cool-tint `oklch(98% 0.004 240)` (다크 토글 가능)
- **액센트**: 민트 `oklch(56% 0.12 170)` — 페이지당 최대 2회 등장
- **글로우**: 활성 RUN + 핵심 KPI 2곳에만
- **이모지 금지** — 모든 아이콘 inline SVG

### 5.2 토큰 owner
- 색상: `webui/v2_src/src/styles/core.css` `:root` / `[data-theme="dark"]`
- 컴포넌트: `webui/v2_src/src/styles/components.css` (`.card / .metric / .pill / .signal / .stepper / .hero ...`)
- TS 토큰: `webui/v2_src/src/lib/theme.ts` (ECharts/Plotly 옵션 owner)

### 5.3 폰트
- 디스플레이/본문: `Pretendard Variable` (CDN)
- 모노: `JetBrains Mono` (Google Fonts)
- 시스템 폴백: Segoe UI / Malgun Gothic

---

## 6. 절대 제약 사항 (Hard Constraints)

### 6.1 변경 금지
| 경로 | 이유 |
|---|---|
| `webui/app.py` (특히 `/api/*` 핸들러) | 24개 endpoint — 모든 SPA + v1 화면이 공유 |
| `webui/templates/{index,training_dashboard,stom_dashboard}.html` | v1 archive (6개월 보존) |
| `finetune/`, `model/`, `_database/` | 학습 코드 + 모델 + DB |
| `webui/v2/__init__.py` | Flask Blueprint 분기 + cutover 라우팅 (P6 완료) |

### 6.2 행동 금지
- ❌ 신규 `/api/*` endpoint 추가 (모든 데이터는 기존 24개)
- ❌ predictor 미완료 상태에서 정확도/수익률 ready 표시
- ❌ `power_draw_available=false` 시 추정값 표시
- ❌ KST 변환을 API timestamp 자체에서 (표시 계층에서만)
- ❌ 이모지 아이콘
- ❌ 보라/바이올렛 그라데이션 배경

### 6.3 행동 의무
- ✅ SSR meta marker (`kronos-v2-shell`, `kronos-v2-version`) 모든 변형에서 보존
- ✅ Vite `base: '/static/v2/dist/'` 유지
- ✅ light + dark 양 모드 모두 검증
- ✅ Dist commit 정책 (REV-7) — `webui/static/v2/dist/`는 git에 포함

---

## 7. 미진행 / 보강 후보

### 7.1 P5 정식 quality gate (남은 가장 큰 작업)
- [ ] Lighthouse a11y ≥ 90 측정 (`lighthouse http://127.0.0.1:5070/ --output=json`)
- [ ] Lighthouse perf ≥ 80 측정 (FLASK_ENV=production + gzip + waitress 환경에서)
- [ ] code-reviewer 결과를 `docs/kronos_dashboard_overhaul_p5_review.md` 별도 저장
- [ ] WCAG AA 색상 대비 4.5:1 검증 (특히 light 모드 muted 텍스트)
- [ ] 키보드 네비게이션: Tab/Enter 로 모든 탭/슬라이더 접근

### 7.2 잔여 폴리시 (응답 스키마 확정 후)
- [ ] Forecast Candlestick 차트 (현재 라인) — `/api/predict` 응답 OHLC 형태 확정 시
- [ ] STOM Plotly heatmap (dynamic import) — `/api/stom/diagnostics` 응답 hexmap 구조 확정 시
- [ ] STOM top-k 추천 카드 — `/api/stom/recommendations?date=` 검증
- [ ] STOM backtest 상세 모달 — `/api/stom/backtest-report?file=` 검증
- [ ] Forecast CSV 다운로드 (client-side Blob)
- [ ] Settings 학습 단계 알림 watcher (Notification API)
- [ ] History run 클릭 시 손실 곡선 미니어처 (run 별 history endpoint 필요 — P3.5)

### 7.3 운영
- [ ] production 배포 환경 (FLASK_ENV=production + waitress 또는 gunicorn)
- [ ] v1 archive 6개월 후 삭제 검토

---

## 8. 빌드/배포 (운영 절차)

```powershell
# 빌드 (변경 후 매번)
cd D:\Chanil_Park\Project\Programming\Kronos\webui\v2_src
npm run build

# Flask 가동
cd D:\Chanil_Park\Project\Programming\Kronos
$env:KRONOS_WEBUI_PORT = "5070"
$env:KRONOS_V2_DIST = "1"
C:\Python\64\Python3119\python.exe webui\run.py

# 접속
# http://127.0.0.1:5070/        — 새 통합 대시보드 (v2 SPA)
# http://127.0.0.1:5070/v1/     — v1 메인 (legacy archive)
# http://127.0.0.1:5070/v1/training — v1 학습 모니터
# http://127.0.0.1:5070/v1/stom    — v1 STOM 진단

# 테스트
C:\Python\64\Python3119\python.exe -m pytest tests/test_v2_route.py tests/test_v2_dist_marker.py tests/test_v2_blueprint_isolation.py -v

# Rollback (v1 임시 사용 / dist 비활성화)
$env:KRONOS_V2_DIST = "0"  # P1 SSR Jinja shell 로 폴백
# 또는
git revert <commit>
```

---

## 9. 참고 파일 색인

### 9.1 필독
- `webui/v2_src/README.md` — 빌드/배포/디렉터리 구조
- `docs/kronos_dashboard_overhaul_plan.md` — RALPLAN-DR 합의 마스터 플랜
- `docs/kronos_dashboard_p1_5_design_spec.md` — 디자인 토큰 상세
- `docs/kronos_dashboard_p1_5_build_checklist.md` — 빌드 운영 체크리스트

### 9.2 디자인 시스템 출처
- `template/extracted/DESIGN.md` — human-approachable 디자인 철학 + 토큰 사양
- `template/extracted/styles/core.css` — 라이트/다크 OKLch 토큰
- `template/extracted/styles/components.css` — `.card / .metric / .stepper` 등

### 9.3 최근 commit 히스토리
```
8562c64 P6 cutover — / 가 v2 SPA, /v1/* archive, /v2 → 301
98d66d2 예측 진단 (STOM) 탭 P4 본격 구현
7e38c18 예측 워크벤치 탭 P3 본격 구현
8f1beb4 기록 & 런 탭 P2 정식 패널 구현
3f17e78 설정 탭 확장 (테마 카드 + 새로고침 + 알림 + 초기화)
5ba3009 시스템 상태 탭 정식화
7ff0d71 아티팩트 & 모델 탭 정식화
a631b54 Live Training 탭 본격 리디자인
ce42ab4 Designer 프로토타입 디자인 시스템 v2 이식
2695151 P1.5 Vite Svelte SPA 정식 전환
9411a23 P1.5 디자인 스펙 + 운영 체크리스트
888bb08 P1 SSR 골격 구축
5c46ccd ralplan 합의 계획 (P0)
```

---

## 10. 한 줄 미션 (달성 완료)

> ~~"학습 모니터링 + 예측 워크벤치 + STOM 진단 + 아티팩트 + 시스템 상태 — 5개 도메인을 단 하나의 시각적으로 화려하고 직관적인 Svelte SPA로 통합하라."~~
>
> ✅ **달성**: 7개 탭 모두 실 API 통합 + 디자인 시스템 v2 (human-approachable, light+dark, mint accent) + P6 cutover 완료.
>
> **다음 미션**: P5 Lighthouse quality gate + 잔여 폴리시 + 재학습.

---

*핸드오프 작성자: Claude (현 세션)*
*최초 작성: 2026-05-16 KST · 마지막 갱신: 2026-05-18 KST*
