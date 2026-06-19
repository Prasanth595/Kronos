# Kronos 웹 대시보드 전면 개편 RALPLAN-DR 계획 (Draft, iteration 1 revised)

작성일: 2026-05-12 KST
실행 모드: `$ralplan` 합의 계획 단계 (Architect+Critic iteration 1 반영)
대상 repo: `D:\Chanil_Park\Project\Programming\Kronos`
Confidence: **medium-high** (iteration 1 후 risk surface 좁힘, npm 의존성을 학습 완료 후로 격리)
Scope-risk: **moderate** (학습 중 작업은 SSR Jinja 골격으로만 진행, Vite/Node는 predictor 완료 후 별도 PR)

---

## 0. TL;DR (결론 먼저)

- **방향**: 통합 단일 페이지 SPA를 학습이 끝날 때까지 **2단계로 분리** 진행. 기존 Flask 라우트 3개(`/`, `/stom`, `/training`)는 학습 완료 cutover 시점까지 그대로 유지한다.
- **2단계 도입 (iteration 1 핵심 변경)**:
  - **P1 (학습 중, npm 0)**: SSR Jinja `templates/v2_shell.html` + Alpine.js CDN + ECharts CDN 만으로 hero/stage/loss/eta/gpu 6개 위젯의 읽기 전용 골격. server-side marker로 grep 검증 가능.
  - **P1.5 (predictor 완료 후, 별도 PR)**: 그 시점에 `webui/v2_src/` 생성, `npm ci` (Node 20 LTS pin), Vite 도입 + Svelte 5 + Tailwind prebuilt. P1 골격을 progressive enhancement.
- **추천 스택 (최종 형태)**: Svelte 5 + Vite + ECharts + Tailwind prebuilt. 단 학습 중에는 적용하지 않는다.
- **차트**: 메인 **Apache ECharts 5.x** (학습 곡선/스파크라인/대규모 시계열). STOM Diagnostics 탭에서만 **Plotly 2.35.2 dynamic import** 유지.
- **빌드 파이프라인**: Flask가 `webui/static/v2/dist`의 prebuilt 산출물을 정적 서빙. `dist/`는 commit (prebuilt 정책), `node_modules/`는 `.gitignore`. dev Vite 서버는 P1.5 이후에만, 별도 포트.
- **rollback 안전망**: `/v2` 별도 라우트 + `KRONOS_V2_ENABLED` env feature flag + git revert + v1 templates는 cutover 후 `/v1/*` prefix로 **6개월 archive**.
- **학습은 절대 건드리지 않는다.** P1 진행 중 npm/Node 0 의존성, P1.5는 학습 종료 후에만 시작.

상태: **pending approval (Architect+Critic 합의 전)** — 마지막 줄에서 다시 명시.

---

## 1. 현재 기준선 스냅샷 (read-only 관측)

| 항목 | 값 |
|---|---:|
| run | `stom_1s_grid_pred60_2025_full_small` |
| status | `running` |
| stage | `tokenizer` |
| tokenizer step | 1,852,000 / 4,701,721 |
| tokenizer 진행률 | 약 39.39% |
| 전체 both-stage 진행률 | 약 19.69% |
| predictor stage | 미시작 |
| checkpoint 파일 | 0개 |
| GPU | RTX 4080 SUPER · Util 40% · VRAM 22% · 37°C |
| ETA | 약 50시간 (tokenizer만 기준) |

이전 안전 계획 `docs/stom_dashboard_safe_parallel_improvement_plan.md`에서 1~6단계 (공통 readiness UI, artifacts API, history, GPU/ETA 카드, /stom gate, code-review)가 모두 완료되어 read-only 모니터링 토대는 이미 견고하다. 이번 개편은 그 위에 시각적 화려함과 단일 진입점을 얹는다.

---

## 2. RALPLAN-DR 요약

### 2.1 원칙 (Principles, 5개)

1. **학습 불간섭 (P1)**: 실행 중인 STOM full training과 `finetune/` 일체를 절대 수정/재시작하지 않는다. Vite/npm은 별도 프로세스에서만 동작하고, GPU/CUDA/PyTorch 환경에 손대지 않는다.
2. **읽기 전용 데이터 흐름 (P2)**: 모든 신규 API/UI는 read-only. predictor checkpoint가 만들어지기 전까지 정확도/수익률 ready 표시를 절대 켜지 않는다 (기존 readiness gate 정책 100% 계승).
3. **빌드 산출물 분리 (P3)**: 학습 중에는 npm 자원 경쟁을 피하기 위해 Vite dev 서버는 옵션이고, 운영 배포는 prebuilt static 자산만으로 동작한다. Python 측은 `webui/static/v2/dist/*`만 본다.
4. **공존 가능한 점진적 마이그레이션 (P4)**: 기존 `/`, `/stom`, `/training`은 학습 완료 cutover 시점까지 모두 살아 있다. 신규 SPA는 `/v2`에서 격리 검증된 후 합의로 cutover.
5. **시각적 화려함은 비용과 함께 평가 (P5)**: 모션/3D/heavy WebGL은 차트와 분리한다. 화려함은 micro-interaction과 정보 계층 명확성으로 표현하고, 학습 중 GPU 자원 점유를 늘리지 않는다.

### 2.2 결정 동인 (Decision Drivers, Top 3)

1. **D1 학습 보호 (절대 우선)**: 50시간짜리 학습이 깨지면 사용자 손실이 가장 크다. 모든 결정은 "학습에 영향을 주는가"가 첫 필터.
2. **D2 사용자 경험 통합성**: 현재 3개 페이지를 왔다갔다하며 같은 readiness 상태를 다시 확인해야 한다. 단일 SPA에서 한 번에 본다.
3. **D3 시각적 직관성 + 화려함**: tokenizer→predictor 전환 카운트다운, GPU 트렌드, 학습 곡선이 한눈에 들어와야 하며 따분하지 않아야 한다.

(보조 드라이버: 유지보수성, 번들 크기, Windows + Python 3.11.9 환경 호환성)

### 2.3 Viable Options (2개 viable + 1개 invalidated)

> **iteration 1 변경**: 옵션 A의 도입 시점을 P1.5(학습 종료 후)로 명시 격리. P1(학습 중)에는 옵션 B(Alpine.js + ECharts CDN)의 패턴을 SSR Jinja로 그대로 사용한다. 즉 A/B는 양자택일이 아니라 **시간축 분할 시퀀스**다.

#### Option A — **Svelte 5 + Vite + ECharts** (P1.5 이후 채택, 최종 형태)

| 항목 | 내용 |
|---|---|
| 프론트 프레임워크 | Svelte 5 (runes API), TypeScript |
| 빌드 | Vite 5 (`base: '/static/v2/dist/'`) |
| 차트 | Apache ECharts 5 (메인) + Plotly 2.35.2 (STOM diagnostics, dynamic import만) |
| 스타일 | TailwindCSS **prebuilt** (`@tailwindcss/cli` 또는 PostCSS) + 커스텀 dark/navy 테마 — **Play CDN은 금지** (AC-1) |
| 라우팅 | client-side 단일 SPA, `/v2/<path:subpath>` catch-all은 v2 prefix 내부에서만 (글로벌 catch-all 금지, REV-2) |
| 번들 추정 | gzip 약 150~220KB (Svelte ~10KB + ECharts core ~180KB + Tailwind 압축 후 ~30KB) |
| Node version | **20.x LTS pin** (`package.json#engines.node`), `npm ci`로 lockfile 기반 재현 가능 install |

**Pros**

- Svelte는 가상 DOM이 없어 런타임 오버헤드 최소, 학습 중 브라우저 부담 적음
- ECharts는 학습 곡선(2M+ step)도 부드럽게 처리 (Canvas 기반)
- 컴파일 결과가 가벼워 Windows powershell 빌드 시간도 짧음 (initial install ~80MB node_modules)
- Plotly와 공존 가능 (script tag 격리)
- micro-interaction (slot transition, FLIP)이 자연스러워 "화려함" 요구를 코드 양 늘리지 않고 달성

**Cons**

- 사용자 측 Svelte 학습 곡선 (단, 코드 수정자가 Claude/사용자 본인이므로 큰 부담 아님)
- npm 의존성 추가 (학습 중 install은 백그라운드/저우선순위 필요)
- 두 차트 라이브러리 공존 = 번들 일시 증가 (단 lazy load로 완화)

#### Option B — **Alpine.js + ECharts CDN, SSR Jinja shell (P1 채택, 학습 중)**

| 항목 | 내용 |
|---|---|
| 프론트 | Alpine.js 3 (CDN) — HTMX는 P1 범위에 불필요 (read-only fetch만) |
| 빌드 | 없음. `templates/v2_shell.html` Jinja 한 장 |
| 차트 | ECharts 5 (CDN, `<script>` defer 로드) + 필요 시 Plotly 2.35.2 (이미 CDN) |
| 스타일 | hand-rolled CSS + 기존 navy 테마 변수 (`--chart-color-primary` 등) 재사용. Tailwind는 P1에서 도입 안 함 (AC-1) |
| 라우팅 | URL fragment 기반 단일 페이지 탭 전환 (Alpine `x-show`) |
| Marker | **SSR-injected `<meta name="kronos-v2-shell" content="hero,live-training,stom,forecast,artifacts">`** + 탭별 `data-tab="..."` (B-2 해결) |

**Pros**

- Node/npm 의존성 0개 → 학습 자원과 100% 격리 확실
- 기존 Flask 템플릿 구조 그대로 점진 이식 가능
- 빌드 파이프라인 없음 = CI 단순, rollback 즉시
- Windows 환경 가장 안전
- server-side marker로 pytest grep 검증 즉시 가능 (B-2 자동 해결)

**Cons**

- "화려함" 요구는 모션/transition만으로 부분 달성 (full polish는 P1.5 Svelte로 미룸)
- Alpine 상태 관리 한계 → 본격 reactive UI는 P1.5로 이동
- 장기 유지보수 시 v1→v2 → v2-svelte 두 번 마이그레이션 (수용 가능, rollback 안전성이 우선)

#### Option C — **React 18 + Vite + TradingView Lightweight Charts** (Invalidated)

**무효화 이유**

- React 런타임이 Svelte 대비 약 4배 무거움 (학습 중 브라우저 자원 점유 증가)
- TradingView Lightweight는 STOM diagnostics의 heatmap/scatter를 직접 그릴 수 없어 ECharts와 함께 두 lib를 또 도입해야 함 → 번들 폭증
- 학습 곡선/GPU 트렌드 같은 일반 분석 차트에는 TradingView가 over-spec
- 사용자 요구 ("화려함 + 직관성")는 Svelte+ECharts 조합으로도 동일 달성 가능
- 결론: React/TradingView 조합의 추가 이득이 없으므로 무효화

(다른 후보 SolidJS는 Svelte와 비교 시 생태계가 작고 ECharts 통합 사례가 적어 보조 옵션으로만 둔다.)

### 2.4 Pre-mortem-lite — 학습 중단 위험 시나리오 3개

| # | 시나리오 | 발생 메커니즘 | 영향 | 완화책 |
|---|---|---|---|---|
| 1 | **npm install 중 GPU/디스크 경쟁** | `npm install`이 동일 디스크에 수만 개 파일을 쓰면서 tokenizer log/checkpoint 디렉터리와 I/O 충돌 | tokenizer step write 지연 → progress.json 갱신 지연 | **iteration 1 변경: P1 단계에서는 npm install 자체를 하지 않는다 (B-1)**. P1.5는 학습 종료(`predictor_complete=true`) 이후에만 시작. P1.5에서 install 진행 시 `PerfMon`/`Get-Counter '\PhysicalDisk(_Total)\% Disk Time'` 베이스라인 ±5% 매트릭스를 첨부, `--prefer-offline --no-audit --no-fund`, low priority 실행 |
| 2 | **Vite dev 서버가 5070 또는 학습 로그 디렉터리에 file watch** | Vite는 기본 `cwd` 전체를 watch. `finetune/outputs/**` 변경 이벤트가 폭주하면 Node CPU 점유 상승 | Node 단독 CPU 점유 (학습 GPU 직접 영향은 없으나 ETA polling 지연) | **P1에서는 Vite를 실행하지 않음**. P1.5의 `vite.config.ts`에 `server.watch.ignored: ['**/finetune/outputs/**', '**/_database/**', '**/checkpoints/**', '**/logs/**', '**/webui/prediction_results/**', '**/webui/stom_predictions/**', '**/*.db']` 명시 (REV-2) |
| 3 | **새 라우트가 기존 read-only API 시그니처를 깨거나 사이드이펙트** | Flask blueprint 추가 시 import 순서 변경, 또는 캐시 변경이 `build_training_readiness` 동작 변경 | readiness gate 잘못 켜져 predictor 완료 전 "ready" 오해 | 신규 코드는 별도 blueprint(`webui/v2/__init__.py`)로 격리. **catch-all 라우트는 `/v2/<path:subpath>`로 v2 prefix 내부에서만**. 글로벌 `/<path:p>` 금지 (REV-2). 기존 라우트/헬퍼 import 변경 0, `tests/test_training_monitor.py`의 assertion을 변경 없이 유지 |

추가 안전 장치:

- 작업 시작 전마다 학습 살아있음 확인 (정확한 PowerShell 명령):
  ```powershell
  Invoke-RestMethod -Uri 'http://127.0.0.1:7070/api/training/status' `
    | Select-Object status, `
        @{n='stage';e={$_.latest_stage.train_stage}}, `
        @{n='step';e={$_.latest_stage.step}}, `
        @{n='pct';e={$_.latest_stage.overall_percent}}
  ```
  (이전 `Get-Process python ... MainWindowTitle` 패턴은 빈 문자열 함정 — REV-부수 수정)
- 각 phase 끝에 `live /api/training/status`가 여전히 running인지 grep 검증
- Phase 단위 commit. 한 phase 안에서 학습 영향 있는 명령을 절대 섞지 않음

---

## 3. 정보 아키텍처 (단일 SPA 레이아웃)

### 3.1 메인 SPA `/v2` 레이아웃 (1280px 기준)

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADER: KRONOS · run name · 학습 상태 배지 · KST clock          │
├─────────────────────────────────────────────────────────────────┤
│ LEFT NAV (240px)        │ MAIN CANVAS                            │
│ ▸ Live Training          │ ┌─ Hero Strip ─────────────────────┐ │
│ ▸ Forecast Workbench     │ │ readiness · stage · step · ETA   │ │
│ ▸ STOM Diagnostics       │ └──────────────────────────────────┘ │
│ ▸ Artifacts & Models     │ ┌─ Tab content (router outlet) ────┐ │
│ ▸ History & Runs         │ │                                  │ │
│ ▸ System Health (GPU)    │ │   widgets…                       │ │
│ ─────────────            │ │                                  │ │
│ Command Palette (Cmd+K)  │ └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

- 좌측 NAV는 기존 보라색→네이비 사이드바 톤을 계승해 시각적 충돌 최소.
- Hero Strip은 모든 탭에서 항상 보이며, 학습 readiness gate를 그대로 표시 (P2 준수).
- Command Palette는 `Ctrl+K`로 run 전환, 위젯 점프, refresh interval 변경.

### 3.2 신규 위젯 후보 (8개, 최소 5개 채택) + polling/limit/buffer 한도 (B-4)

> **공통 polling cadence**: `DEFAULT_TRAINING_REFRESH_SECONDS=5` (`webui/app.py:181` 계승). 사용자 토글로 2~3600s 범위에서 변경 가능 (기존 `resolve_training_refresh_seconds` 재사용). 학습 중 동안 단축 금지.

| # | 위젯 | 데이터 소스 | API 파라미터 | Client buffer | 시각화 형태 | 도입 시점 |
|---|---|---|---|---|---|---|
| W1 | **Stage Stepper** (tokenizer → predictor 2단계) | `/api/training/status` `stages[]` | n/a | n/a | 가로 단계 표시 + per-stage progress bar | P1 |
| W2 | **Predictor 전환 카운트다운 + Readiness 신호등** | readiness `level` + tokenizer ETA | n/a | n/a | 신호등 (적/황/녹) + KST 카운트다운 | P1 |
| W3 | **Loss Curve (zoom + brush)** | `/api/training/history` `points[]` | **`limit=200`** (기본). dataZoom 시 `limit=1000`까지 lazy fetch | ECharts dataset **상한 1000 points**, 초과 시 oldest 폐기 | ECharts line + dataZoom + brush | P1 (CDN ECharts) → P1.5 정식 컴포넌트 |
| W4 | **ETA 타임라인 (KST)** | `latest_progress.updated_at` + `eta_seconds` (원본 변경 금지) | n/a | n/a | 가로 타임라인 (현재→완료 예상) | P1 |
| W5 | **GPU 트렌드 스파크라인** | `/api/training/gpu` 클라이언트 ring buffer | n/a (poll 5s) | **ring buffer 720 points** = 1시간 (5s × 720) | util/temp/VRAM 3개 스파크라인 (`power_draw_available=false`면 power 미표시) | P1 |
| W6 | **손실 변동 통계** (rolling mean/std) | history 클라이언트 계산 | W3과 공유 | W3 buffer 재사용 | small multiple 통계 카드 (window=20) | P4 |
| W7 | **"지금 무엇을 기다리는지" 메인 상태 배지** | readiness + artifact level 조합 | n/a | n/a | 큰 배지 + 1줄 카피 | P1 |
| W8 | **백테스트 비교 갤러리** (predictor 완료 후 활성) | `/api/stom/qlib-backtests`, `/api/stom/filter-reports` | 기본 limit | n/a | 카드 그리드 + 미리보기. `predictor_complete=false`면 lock placeholder | P5 placeholder, predictor 완료 후 unlock |

**P1 (학습 중, SSR)에서 W1, W2, W4, W5, W7 골격 우선 구현** (W3는 CDN ECharts로 단순 라인 차트). P1.5(predictor 완료 후)에서 W3 dataZoom/brush 완성 + W6 활성, P5에서 W8 placeholder, predictor 완료 후 unlock.

### 3.3 라우팅과 페이지 매핑

| SPA 탭 | 기존 페이지 대응 | 활성화 시점 |
|---|---|---|
| Live Training | `/training` 전부 + index의 trainingInlinePanel | P1 (SSR 골격) → P2 (정식) |
| Forecast Workbench | `/`의 lookback/pred_len/temperature/top_p 슬라이더 + `/api/predict` | P3 |
| STOM Diagnostics | `/stom`의 diagnostics + topk + recommendations | P4 |
| Artifacts & Models | `/api/training/artifacts`, `/api/available-models`, `/api/model-status` | P1 (read-only 표시) → P2 (interactive) |
| History & Runs | `/api/training/runs`, `/api/training/history` | P1 |
| System Health | `/api/training/gpu` 트렌드 | P1 |

### 3.4 핵심 코드 스니펫 (REV-2)

**`webui/v2/__init__.py` (P1, Blueprint)**

```python
from flask import Blueprint, render_template, send_from_directory, current_app
import os

v2_bp = Blueprint('v2', __name__)

@v2_bp.route('/v2')
def v2_index():
    # P1: SSR Jinja 골격. predictor 완료 후 P1.5에서 dist/index.html로 교체.
    dist_index = os.path.join(current_app.static_folder, 'v2', 'dist', 'index.html')
    if os.path.exists(dist_index) and os.environ.get('KRONOS_V2_DIST', '0') == '1':
        return send_from_directory(
            os.path.join(current_app.static_folder, 'v2', 'dist'),
            'index.html',
        )
    return render_template('v2_shell.html')

@v2_bp.route('/v2/<path:subpath>')
def v2_spa_fallback(subpath):
    # v2 prefix 내부 catch-all만 허용. 글로벌 /<path:p>는 절대 금지.
    return v2_index()
```

**`webui/v2_src/vite.config.ts` (P1.5)**

```ts
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  base: '/static/v2/dist/',
  plugins: [svelte()],
  build: {
    outDir: '../static/v2/dist',
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    watch: {
      ignored: [
        '**/finetune/outputs/**',
        '**/_database/**',
        '**/checkpoints/**',
        '**/logs/**',
        '**/webui/prediction_results/**',
        '**/webui/stom_predictions/**',
        '**/*.db',
      ],
    },
  },
});
```

**`templates/v2_shell.html` 헤더 (P1, B-2 SSR marker)**

```html
<meta name="kronos-v2-shell" content="hero,live-training,stom,forecast,artifacts,history,system-health">
<meta name="kronos-v2-version" content="p1-ssr">
<section data-tab="live-training" id="hero-strip">...</section>
<nav data-tab-list="root">
  <a data-tab="live-training" href="#live-training">Live Training</a>
  ...
</nav>
```

이 marker는 server-side에 정적 문자열로 박혀 있어 `requests`/pytest grep으로 즉시 검증 가능 (B-2 해결).

### 3.5 차트 라이브러리 공존 경계 (REV-4)

- **ECharts**: hero/live training/forecast/artifacts/history/system-health 모든 시계열·메트릭. P1에서 CDN, P1.5에서 npm 패키지.
- **Plotly**: `/v2#stom` (STOM Diagnostics 탭) 진입 시에만 dynamic import (`import('plotly.js-dist-min')`). 다른 탭에서는 로드하지 않는다.
- **`src/lib/theme.ts`** 한 파일에 CSS 변수 집중 (`--chart-color-primary`, `--chart-font-family`, `--chart-bg`, `--chart-grid`). 두 라이브러리는 mount 직전 이 변수를 읽고 옵션을 동기화.

### 3.6 v2 UI에서 device GPU 옵션 disable (REV-6 변형)

`webui/app.py:1107`의 `/api/load-model` 핸들러는 변경하지 않는다 (기본 device는 이미 `cpu`). 변경 지점은 v2 UI 단:

- v2 `Forecast Workbench`의 device 선택 UI에서 GPU 옵션을 **`predictor_complete=true`일 때까지 disable**
- 툴팁: "학습 중에는 CPU만 사용 가능 — 예측기 학습 완료 후 GPU 사용 가능"
- `predictor_complete` 신호는 `/api/training/status` `readiness.predictor_complete`에서 직접 읽음 (별도 API 추가 없음)

---

## 4. 단계별 Phase 계획 (iteration 1: P1 분할 + cutover 정량화)

> **핵심 변경 (B-1)**: 기존 P1(Vite 부트스트랩)을 학습 중 안전 모드 **P1**과 predictor 완료 후 **P1.5**로 분리. P2~P4는 학습 종료 후에만 진행. 학습 중에는 P0 + P1 + 일부 P2 SSR 골격만 작업.

| Phase | 학습 상태 | 목적 | 주요 파일 | 검증 | Commit 기준 |
|---|---|---|---|---|---|
| **P0. 학습 안전 기준선 고정 + 계획 commit** | running | 기준선 스냅샷, 본 계획 문서 확정 | `docs/kronos_dashboard_overhaul_plan.md` (이 파일) | `live /api/training/status` running 확인, 기존 pytest pass, 학습 PID/step 기록 | `docs: ralplan 합의 초안 작성` |
| **P1. v2 SSR 골격 (npm 0, 학습 중 안전 모드)** | running | SSR Jinja `templates/v2_shell.html` + Alpine.js CDN + ECharts CDN. W1/W2/W4/W5/W7 골격 + W3 단순 라인 + 좌측 NAV. server-side marker. | `webui/app.py` (Blueprint register 1줄), `webui/v2/__init__.py` (신규), `webui/templates/v2_shell.html` (신규), `webui/static/v2/css/v2.css` (신규, hand-rolled), `tests/test_v2_route.py` (신규) | `GET /v2` 200 OK, `<meta name="kronos-v2-shell">` 포함 / 기존 `/`, `/stom`, `/training` 응답 무변경 / `pytest tests/test_training_monitor.py tests/test_training_progress.py tests/test_stom_dashboard_helpers.py tests/test_v2_route.py -q` 통과 / 학습 step delta 측정 후 acceptance AC-6 만족 | `feat(webui): /v2 SSR 골격을 격리 blueprint로 부트스트랩` |
| **P1.5. Vite + Svelte 전환 (predictor 완료 후 별도 PR)** | **`predictor_complete=true` 진입 후에만 시작** | `webui/v2_src/` 생성, `npm ci` (Node 20 LTS pin, `package-lock.json` commit), Vite + Svelte 5 + Tailwind prebuilt. P1 골격을 컴포넌트로 progressive enhancement | `webui/v2_src/package.json`, `webui/v2_src/package-lock.json`, `webui/v2_src/vite.config.ts`, `webui/v2_src/src/App.svelte`, `webui/v2_src/src/main.ts`, `webui/v2_src/src/lib/theme.ts`, `webui/static/v2/dist/*` (빌드 산출물, commit) | `npm ci` 실행 전 디스크 베이스라인 `Get-Counter '\PhysicalDisk(_Total)\% Disk Time'` 5분 표본 채취, install 후 ±5% 내 / `npm run build` 성공 / `KRONOS_V2_DIST=1`로 dist 서빙 / SSR 골격 marker는 빌드 산출물 `index.html`에 `<meta>` 그대로 유지 | `feat(webui-v2): Vite+Svelte 정식 SPA로 P1 골격 승격` |
| **P2. Live Training 탭 정식 컴포넌트 + Cmd+K palette** | predictor 완료 후 | W3 dataZoom/brush 정식, Stage Stepper / ETA / GPU 트렌드 정식 svelte 컴포넌트, Cmd+K palette | `src/lib/api.ts`, `src/components/{Hero,StageStepper,LossChart,EtaTimeline,GpuSparkline,Readiness}.svelte`, `src/routes/LiveTraining.svelte` | live `/v2` 모든 위젯 렌더, ECharts loss chart 응답 < 200ms / 기존 pytest 무변경 통과 / `tests/test_v2_smoke.py` SSR marker 동일 | `feat(webui-v2): live training 정식 컴포넌트` |
| **P3. Forecast Workbench 탭 (예측 슬라이더 UI)** | predictor 완료 후 | lookback/pred_len/temperature/top_p UI를 SPA로 이식. `/api/predict` 호출 동일 | `src/routes/ForecastWorkbench.svelte`, `src/components/{TimeWindowSlider,PredictionChart,ComparisonTable}.svelte` (Plotly dynamic import) | `/v2#forecast`가 기존 `/`의 응답 **schema 동일성** (필드 존재/타입) + **MAE/RMSE/MAPE tolerance ≤ 1e-6** (B-3). seed protocol: `torch.manual_seed(SEED)`, `np.random.seed(SEED)`, `random.seed(SEED)`를 검증 스크립트에서 명시 후 비교. | `feat(webui-v2): forecast workbench 이식` |
| **P4. STOM Diagnostics + Artifacts/History/System Health** | predictor 완료 후 | diagnostics heatmap, top-k, recommendations, qlib backtest, filter report, artifact gallery, history 테이블, GPU 상세 | `src/routes/{StomDiagnostics,Artifacts,History,SystemHealth}.svelte`, `src/components/{TopKTable,RecommendationsTable,DiagnosticsHeatmap}.svelte` | `/v2#stom`이 기존 `/stom` 데이터와 schema 1:1 일치 (AC-7: `curl /api/stom/diagnostics \| jq 'keys'` diff = ∅), data 동일성은 동시 호출 시에만, 시간 의존이면 schema diff로 약화 / artifact gate가 checkpoint 0개에서 "predictor checkpoint 대기" 표시 / W6 활성 | `feat(webui-v2): STOM 진단/아티팩트/히스토리/GPU 통합` |
| **P5. 시각적 폴리시 + W8 placeholder + 최종 code-review** | predictor 완료 후 | micro-interaction (FLIP transition), 다크/라이트 토글, a11y pass, 빈 상태 일러스트, W8 placeholder (predictor 결과가 있으면 자동 unlock) | `src/components/EmptyState.svelte`, `src/lib/theme.ts`, `src/routes/BacktestGallery.svelte` + `docs/kronos_dashboard_overhaul_p5_review.md` (신규, code-reviewer 결과 별도 파일 저장 — AC-4 자기 승인 방지) | code-reviewer 결과 CRITICAL=0, HIGH=0 + Critic 메타-게이트 1회 / **Lighthouse 측정 환경: Flask production-mode (`FLASK_ENV=production`, gunicorn 또는 waitress) + gzip + Chrome headless `lighthouse http://127.0.0.1:7070/v2 --output=json --output-path=docs/lighthouse_v2.json --chrome-flags='--headless=new --no-sandbox'`** / a11y > 90, performance > 80 | `chore(webui-v2): v2 SPA 시각적 폴리시 + p5 review` |
| **P6. Cutover (predictor 완료 + 1주 병행 후 별도 PR)** | predictor 완료 + 1주 후 | feature flag `KRONOS_V2_ENABLED=1` 기본화. `/`를 v2 shell로 redirect, v1 라우트는 **`/v1/`, `/v1/training`, `/v1/stom` prefix로 6개월 archive** 후 별도 PR에서 삭제 판단 | `webui/app.py` route mapping + `webui/templates/v1_redirect.html` | **Rollback trigger 정량 기준 (B-5)**: (a) readiness gate 오분류 1회 발견 즉시 / (b) p95 API latency > 500ms (cutover 전 baseline 대비 +50%) / (c) error rate > 1% (5분 윈도우) / (d) 사용자 critical bug 보고 1건 / 어느 하나 trigger 시 `KRONOS_V2_ENABLED=0` toggle + Lighthouse 재측정 | (별도 후속 PR) `feat(webui): v2 SPA를 기본 라우트로 cutover` |

각 phase 종료 직후 `git status --short --branch` clean 확인 후 stage-by-stage commit. **한 phase 안에 학습 영향 명령은 절대 섞지 않는다. P1.5~P6는 학습 완료 전 절대 시작 금지.**

---

## 5. 테스트 계획

### 5.1 기존 테스트 (그대로 통과 의무)

```powershell
C:\Python\64\Python3119\python.exe -m pytest `
  tests\test_training_monitor.py `
  tests\test_training_progress.py `
  tests\test_stom_dashboard_helpers.py `
  -q
```

기존 13 + α 케이스는 v2 도입 전후 동일하게 통과해야 한다. `webui/app.py`의 기존 라우트/헬퍼 시그니처 변경은 금지.

### 5.2 신규 Python 테스트 (P1, SSR marker grep — B-2)

| 파일 | 목적 |
|---|---|
| `tests/test_v2_route.py` | `GET /v2`가 200을 반환하고 SSR 응답 본문에 `<meta name="kronos-v2-shell" content="hero,live-training,stom,forecast,artifacts,history,system-health">`와 `<meta name="kronos-v2-version" content="p1-ssr">`이 server-side로 박혀 있음을 grep. 학습 헬퍼는 import만 되고 호출되지 않음을 monkeypatch 카운터로 확인 |
| `tests/test_v2_blueprint_isolation.py` | `webui/v2/__init__.py` blueprint 등록 후 기존 `/`, `/stom`, `/training` 라우트 핸들러가 v2 핸들러로 덮어쓰여지지 않음을 `app.url_map` 비교로 검증. 글로벌 `/<path:p>` catch-all이 등록되지 않았음 확인 |
| `tests/test_v2_static_assets.py` | `KRONOS_V2_DIST=1` + `webui/static/v2/dist/index.html` 존재 시 P1.5 dist 모드로 분기, mimetype·캐시 헤더 정상 (P1.5에서 활성) |
| `tests/test_v2_smoke.py` | (P1부터) `requests`로 `/v2`를 호출해 `data-tab="live-training"`, `id="hero-strip"`, `kronos-v2-shell` marker 3종이 모두 포함되어 있는지 검증. SPA dist 모드에서도 SSR-injected `<meta>`가 살아 있음 보장 (B-2) |

### 5.3 프론트엔드 검증 (P1.5부터, 학습 종료 후만)

- 빌드: `npm ci && npm run build` (P1.5 이후, `--prefer-offline --no-audit --no-fund` 권장)
- 타입체크: `tsc --noEmit` (CI 게이트로 사용 시 학습 자원과 무관)
- 신택스 검증: `node --check` 로 빌드 산출물 sanity check
- Node version: **20.x LTS 강제 pin** (`package.json#engines.node: "^20"`), CI가 어긋난 버전 거부
- **Playwright는 도입하지 않는다** (Chromium 설치 자원 + Windows 신뢰성). `tests/test_v2_smoke.py` (requests 기반)로 대체. 추후 predictor 완료 후 자원 회수 시 재평가 (Follow-up)
- **P1에서는 frontend 빌드 0건**: P1은 정적 HTML/CSS/Alpine.js CDN만 사용. 검증은 §5.2의 pytest로 완결

### 5.4 Live 확인 매트릭스

| URL | 기대 (P1 기간) | 기대 (P1.5+ 기간) |
|---|---|---|
| `http://127.0.0.1:7070/` | 기존 vanilla UI 무변경 | (P6 cutover 이후) v2 redirect 또는 동일 v1 |
| `http://127.0.0.1:7070/stom` | 무변경 | 무변경 (P6 후 `/v1/stom`으로 archive) |
| `http://127.0.0.1:7070/training` | 무변경 | 무변경 (P6 후 `/v1/training`으로 archive) |
| `http://127.0.0.1:7070/v2` | SSR Jinja shell + Alpine + ECharts CDN | Vite 빌드 SPA dist 서빙 |
| `http://127.0.0.1:7070/v2/anything` | SPA fallback (P1: Jinja 동일, P1.5+: dist index) | 동일 |
| `http://127.0.0.1:7070/api/training/status` | `readiness.performance_ready=false`, `predictor_started=false` | (predictor 완료 후) `performance_ready=true` |

### 5.5 학습 영향 확인 (각 phase 끝, 정확한 PowerShell)

**Phase 시작 시 (`step_start` 기록)**

```powershell
$status_start = Invoke-RestMethod -Uri 'http://127.0.0.1:7070/api/training/status'
$step_start = $status_start.latest_stage.step
$pct_start = $status_start.latest_stage.overall_percent
$eta_start = $status_start.latest_stage.eta_seconds
Write-Output "PHASE_START step=$step_start pct=$pct_start eta=$eta_start status=$($status_start.status)"
```

**Phase 종료 시 (delta 검증, AC-6)**

```powershell
$status_end = Invoke-RestMethod -Uri 'http://127.0.0.1:7070/api/training/status' `
  | Select-Object status, `
      @{n='stage';e={$_.latest_stage.train_stage}}, `
      @{n='step';e={$_.latest_stage.step}}, `
      @{n='pct';e={$_.latest_stage.overall_percent}}, `
      @{n='eta';e={$_.latest_stage.eta_seconds}}
$step_delta = $status_end.step - $step_start
$eta_drift_pct = [math]::Abs(($status_end.eta - $eta_start) / $eta_start) * 100
Write-Output "PHASE_END status=$($status_end.status) step_delta=$step_delta eta_drift_pct=$eta_drift_pct"
```

**Acceptance (AC-6)**: phase 5분 이상 소요 작업 기준
- `status_end.status == "running"` (학습 살아있음)
- `step_delta ≥ 100` (현 samples/sec ~63 기준 5분 ≈ 18,900 samples / batch 4 ≈ 4,725 steps 보수치 1/47)
- `eta_drift_pct < 10` (ETA 급변 없음 → 학습 정체 신호 아님)

`MainWindowTitle` 패턴은 빈 문자열 함정으로 사용 금지. process 확인이 필요하면 `Get-Process python | Select-Object Id, StartTime, CPU`로 PID 기록만 한다.

---

## 6. Acceptance Criteria (phase별, iteration 1 정량화)

| Phase | 측정 가능한 완료 기준 |
|---|---|
| P0 | 본 plan 파일 존재 / `git status` clean / 학습 status `running` 유지 / 기존 pytest 통과 / `step_start` 기록 commit 메시지에 포함 |
| P1 | `GET /v2` 200 + 응답 본문에 SSR marker 3종 (`kronos-v2-shell`, `kronos-v2-version=p1-ssr`, `data-tab="live-training"`) / 기존 `/`, `/stom`, `/training` 응답 HTML 길이 변동 = 0 byte / `tests/test_v2_route.py`, `tests/test_v2_blueprint_isolation.py`, `tests/test_v2_smoke.py` 신규 통과 / **학습 step_delta ≥ 100, eta_drift_pct < 10, status=running** (AC-6) / **npm 명령 0회 실행** 증거 (shell history grep) |
| P1.5 | `npm ci` 디스크 베이스라인 ±5% (B-1 매트릭스 `docs/p1_5_disk_baseline.md`에 첨부) / `npm run build` 성공 / `webui/static/v2/dist/index.html` 존재 + SSR marker `<meta>` 유지 / `KRONOS_V2_DIST=1`로 dist 서빙 검증 / P1 SSR marker grep 테스트가 dist 모드에서도 통과 / Node 20 LTS pin 확인 |
| P2 | `/v2` 첫 페인트 < 1.5s (로컬, Chrome DevTools Performance) / Hero readiness 표시 / Loss Chart W3 dataZoom/brush 동작 (limit=200 기본, 1000 lazy) / W5 GPU sparkline 720-point ring buffer 동작 / `power_draw_available=false`면 power 미표시 / Cmd+K palette 동작 / 기존 pytest 무변경 통과 |
| P3 | `/v2#forecast` `/api/predict` 호출 응답 **schema 동일성** (필드 존재/타입 set 동일) + **MAE/RMSE/MAPE tolerance ≤ 1e-6** (B-3 해결책 1+2 병용). seed protocol 검증 스크립트 `tests/test_v2_forecast_parity.py`에 `torch.manual_seed(SEED)`, `np.random.seed(SEED)`, `random.seed(SEED)`, `SEED=42`를 명시 호출 후 비교. v2 UI GPU device 옵션은 `predictor_complete=true` 전에는 disable + 툴팁 (REV-6 변형) |
| P4 | `/v2#stom` diagnostics endpoint **schema diff = ∅** (AC-7): `curl /api/stom/diagnostics?file=<f> \| jq 'keys, .overall \| keys' > buf1` 와 v2 UI가 호출한 동일 응답 비교 / topk row 수 일치 / artifact gallery가 `predictor_complete=false`에서 "predictor checkpoint 대기" 명시 |
| P5 | code-reviewer 결과를 `docs/kronos_dashboard_overhaul_p5_review.md` 별도 파일에 저장 (AC-4 자기 승인 방지). CRITICAL=0, HIGH=0 / Critic 메타-게이트 1회 통과 / Lighthouse 측정 환경: `FLASK_ENV=production` + waitress/gunicorn + gzip + `lighthouse http://127.0.0.1:7070/v2 --output=json --output-path=docs/lighthouse_v2.json --chrome-flags='--headless=new --no-sandbox'` / a11y ≥ 90, performance ≥ 80 |
| P6 (cutover, 별도 PR) | predictor checkpoint ≥ 1 / 백테스트 1회 통과 / **Rollback trigger 정량 (B-5)**: readiness gate 오분류 0회 + p95 latency ≤ baseline +50% (500ms) + error rate ≤ 1% (5분 윈도우) + critical bug 보고 0건 — 트리거 하나라도 발생 시 `KRONOS_V2_ENABLED=0` 즉시 toggle / v1 라우트는 `/v1/`, `/v1/training`, `/v1/stom`으로 **6개월 archive** 후 별도 PR에서 삭제 판단 (즉시 삭제 금지) / 사용자 명시적 OK |

---

## 7. ADR (Architecture Decision Record, iteration 1 revised)

- **Decision**:
  - 단일 SPA `/v2`를 **2단계 시퀀스**로 구축한다. P1 (학습 중)은 SSR Jinja shell + Alpine.js CDN + ECharts CDN으로 npm 의존성 0개를 유지한다. P1.5 (predictor 완료 후, 별도 PR)에서 **Svelte 5 + Vite + ECharts + Tailwind prebuilt + Node 20 LTS pin**으로 progressive enhancement. Flask가 prebuilt `webui/static/v2/dist/`를 서빙. 기존 3개 라우트는 P6 cutover 시점까지 유지.

- **Drivers**:
  1. 학습 보호 (D1) — npm/Node 도입 시점을 학습 완료 후로 격리해 자원 경쟁 0
  2. 사용자 단일 진입점 (D2) — readiness gate를 한 번만 보고 모든 탭에서 일관 유지
  3. 시각적 화려함 + 직관성 (D3) — P1.5의 Svelte 모션 + ECharts 대형 시계열

- **Alternatives considered**:
  - **단일 P1 (즉시 Vite 도입)**: 학습 중 npm install이 디스크 I/O로 tokenizer progress.json 갱신 지연 가능 → P1/P1.5 분리로 기각 (B-1)
  - **Alpine.js only (P1.5 없음)**: 시각적 화려함과 컴포넌트 재사용성 한계 → P1만으로는 D3 달성 어려움
  - **React+TradingView Lightweight Charts**: 런타임 무게 + 차트 라이브러리 중복 → 무효화 (변경 없음)
  - **즉시 cutover (별도 라우트 없이 기존 라우트 교체)**: 학습 중 위험 + rollback 어려움 → 기각

- **Why chosen**:
  - P1은 npm 0 의존성이라 학습 자원과 100% 격리 검증 가능 (D1 만족)
  - SSR marker 패턴은 server-side grep으로 pytest 검증 즉시 가능 (B-2 자동 해결)
  - P1.5는 학습 종료 후에만 시작하므로 npm install의 디스크 영향이 학습에 0
  - 기존 read-only 정책과 readiness gate 코드(`build_training_readiness`)는 import만 하여 재사용 → P2 (readonly) 자동 준수
  - `/v2` 격리 + feature flag `KRONOS_V2_ENABLED`로 rollback이 환경변수 toggle로 끝남

- **Consequences**:
  - (+) 학습 영향 0. 모든 작업은 `webui/v2/`, `webui/templates/v2_shell.html`, `webui/static/v2/` 하위로 격리
  - (+) UX 통합 + 시각적 향상 (P1.5 이후)
  - (+) phase 단위 rollback 가능 (각 phase commit 단위)
  - (+) **dist commit 정책 (REV-7)**: `webui/static/v2/dist/`는 git commit (prebuilt 정책, 학습 머신에서 build 안 함), `webui/v2_src/`도 commit (소스), `node_modules/`는 `.gitignore`. 미래 prod 배포는 별도 머신 빌드 → artifact upload 옵션도 가능하나 현 단계 over-engineering
  - (+) **device GPU 옵션 (REV-6 변형)**: `webui/app.py:1107` 무변경. v2 UI 단에서 `predictor_complete=true`일 때까지 GPU 선택지 disable + 툴팁 "학습 중에는 CPU만 사용 가능"
  - (−) npm 의존성 추가 (~80MB node_modules, gitignore) — 단 P1.5 이후
  - (−) v1 라우트 archive 정책 결정 필요 (P6 후속, 6개월 유지)
  - (−) 두 차트 라이브러리(ECharts + Plotly) 공존 → 번들 약간 증가, dynamic import로 완화 (REV-4)

- **Follow-ups**:
  1. predictor checkpoint 완성 후 W8(백테스트 비교 갤러리)을 실데이터로 활성
  2. cutover (P6) 시 v1 라우트를 `/v1/`, `/v1/training`, `/v1/stom` prefix로 6개월 archive, root는 v2 SPA로 redirect
  3. P1.5의 `vite.config.ts`는 `server.watch.ignored: ['**/finetune/outputs/**', '**/_database/**', '**/checkpoints/**', '**/logs/**', '**/webui/prediction_results/**', '**/webui/stom_predictions/**', '**/*.db']` 명시 (REV-2)
  4. 향후 Playwright e2e 도입 여부는 predictor 완료 후 자원 회수 시 재평가
  5. P1.5 `npm ci` 전 디스크 베이스라인 `Get-Counter '\PhysicalDisk(_Total)\% Disk Time'` 5분 표본, install 후 ±5% 매트릭스 `docs/p1_5_disk_baseline.md` 첨부 (B-1)

---

## 8. 명시적 금지 사항 (iteration 1: 4건 추가)

```text
실행 중 STOM full training 프로세스 중단/재시작/시그널
finetune/* 소스 또는 outputs 수정
_database/*.db 또는 data/* 수정
CUDA/PyTorch/requirements.txt 변경
predictor checkpoint 없이 정확도/수익률 ready 표시
power_draw 추정값 표시 (실측 안 되면 "실측 불가" 그대로)
eta_seconds 원본 변형 (KST 표시는 표시 계층에서만)
기존 /, /stom, /training 라우트의 응답 schema 변경
신규 API에 write/delete 동작 추가
학습이 running인 동안 무거운 백테스트 병렬 실행
[NEW] P1 단계에서 npm/yarn/pnpm/Vite 명령 실행 금지 (학습 종료 전 모든 Node 명령 금지)
[NEW] 글로벌 catch-all 라우트 (/<path:p>) 등록 금지. /v2/<path:subpath>는 v2 prefix 내부에서만 허용
[NEW] v2 UI에서 device=GPU 옵션을 predictor_complete=false 상태에서 활성화 금지
[NEW] Tailwind Play CDN 또는 dev-mode 자산을 P1.5 dist에 포함 금지 (prebuilt만 허용)
[NEW] P5 code-reviewer 결과를 본 plan 파일 안에 직접 append 금지 (별도 docs/kronos_dashboard_overhaul_p5_review.md에 저장 — 자기 승인 방지)
```

---

## 9. 다음 권장 OMX 명령 (iteration 2 합의용)

```text
$architect docs/kronos_dashboard_overhaul_plan.md iteration 1 revised를 검토하고,
1) P1/P1.5 분리가 학습 중 npm 0 의존성 약속을 정말 보장하는지
2) SSR-injected meta marker (kronos-v2-shell) 패턴이 P1.5 dist 모드에서도 유지되는지
3) /v2/<path:subpath> catch-all이 v2 prefix 내부에만 묶여 있고 글로벌 라우트를 깨지 않는지
4) B-1~B-5 5개 blocker가 모두 해소되었는지
5) Pre-mortem 시나리오 외에 누락된 학습 영향 경로가 있는지
를 평가하고 합의/이의를 표하세요.

$critic 같은 문서를 적대적 시각으로 재검토하고,
- B-3 seed protocol이 KronosPredictor의 sampling stochasticity를 정말 결정론으로 만드는지
- B-4 ring buffer 720-point 한도가 메모리/성능에 적정한지
- B-5 rollback trigger (p95<500ms, error<1%) 임계값이 baseline 측정 없이 정해진 게 아닌지
- AC-4 별도 p5_review.md 분리가 실제로 자기 승인을 막는 구조인지
를 따져 잔여 반대 의견을 제기하세요.
```

---

## 10. 진척도 (iteration 1 시점)

```text
계획 작성 + iteration 1 revise   [████████████████████] 100%
Architect/Critic iter 2 합의     [░░░░░░░░░░░░░░░░░░░░] 0%
P0 학습 기준선 commit            [░░░░░░░░░░░░░░░░░░░░] 0%
P1 v2 SSR 골격 (npm 0)           [░░░░░░░░░░░░░░░░░░░░] 0%
P1.5 Vite+Svelte 전환            [░░░░░░░░░░░░░░░░░░░░] 0% (predictor 완료 후)
P2 Live Training 정식 컴포넌트   [░░░░░░░░░░░░░░░░░░░░] 0%
P3 Forecast Workbench            [░░░░░░░░░░░░░░░░░░░░] 0%
P4 STOM Diagnostics 등           [░░░░░░░░░░░░░░░░░░░░] 0%
P5 폴리시 + p5_review.md         [░░░░░░░░░░░░░░░░░░░░] 0%
P6 cutover (1주 병행 후)         [░░░░░░░░░░░░░░░░░░░░] 0%
STOM full training (read-only)   [████░░░░░░░░░░░░░░░░] 19.69%
```

---

## 부록: Revision Log

### iteration 1 (2026-05-12 KST, Architect+Critic 검토 결과 반영)

Critic verdict ITERATE를 받아 5개 CRITICAL blocker (B-1~B-5)와 부수 revision (REV-*, AC-*)을 plan 본문에 반영.

| ID | 범주 | 영향 위치 | 변경 요약 |
|---|---|---|---|
| **B-1** | CRITICAL | §0 TL;DR, §2.3 옵션, §2.4 pre-mortem, §4 phase, §6 acceptance, §7 ADR, §8 금지사항 | Phase 1을 **P1 (학습 중 SSR Jinja + Alpine + ECharts CDN, npm 0)** 과 **P1.5 (predictor 완료 후 Vite + Svelte, 별도 PR)** 로 2단계 분리. P1.5에는 `Get-Counter '\PhysicalDisk(_Total)\% Disk Time'` 5분 베이스라인 ±5% 매트릭스 첨부 의무 |
| **B-2** | CRITICAL | §3.4 코드 스니펫, §5.2 신규 테스트, §6 P1 acceptance | smoke test marker를 client-side DOM이 아닌 **SSR-injected `<meta name="kronos-v2-shell">`**로 변경. server-side grep 즉시 검증. P1.5 dist 모드에서도 `<meta>`를 빌드 산출물에 유지 |
| **B-3** | CRITICAL | §4 P3 phase, §6 P3 acceptance | P3 "동일 입력 → 동일 출력 hash" acceptance를 **schema 동일성 + tolerance ≤ 1e-6 + seed protocol** (`torch.manual_seed(SEED)`, `np.random.seed(SEED)`, `random.seed(SEED)`, SEED=42)로 약화 + 명시 |
| **B-4** | CRITICAL | §3.2 위젯 표 | polling cadence = `DEFAULT_TRAINING_REFRESH_SECONDS=5` (`webui/app.py:181` 계승), W3 `/api/training/history?limit=200` 기본 + dataZoom 시 limit=1000 lazy fetch, client ECharts dataset 상한 1000 points, W5 GPU ring buffer 720 points = 1시간 명시 |
| **B-5** | CRITICAL | §4 P6 phase, §6 P6 acceptance | Rollback trigger 정량화: readiness 오분류 1회/p95>500ms/error>1%/critical bug 1건 → 환경변수 toggle. v1 archive는 `/v1/`, `/v1/training`, `/v1/stom` prefix로 **6개월 유지** (즉시 삭제 금지). Lighthouse 환경 `FLASK_ENV=production`+gzip+`lighthouse ... --chrome-flags='--headless=new --no-sandbox'` 명시 |
| **REV-2** | MAJOR | §3.4 (신규) | `webui/v2/__init__.py` Blueprint 코드 스니펫과 `vite.config.ts` (P1.5)의 `base: '/static/v2/dist/'` + `server.watch.ignored` 패턴을 plan 본문에 포함. catch-all은 `/v2/<path:subpath>` 내부에만 |
| **REV-4** | MAJOR | §3.5 (신규) | Plotly는 `/v2#stom` 진입 시 dynamic import만, 다른 탭은 로드 안 함. `src/lib/theme.ts` 단일 파일에 `--chart-color-primary` 등 CSS 변수 집중 |
| **REV-6** | MAJOR | §3.6 (신규), §7 ADR Consequences, §8 금지사항 | `webui/app.py:1107` 무변경. v2 UI에서 device GPU 옵션을 `predictor_complete=false`에서 disable + 툴팁, 완료 후 자동 unlock |
| **REV-7** | MAJOR | §7 ADR Consequences | dist commit 정책 명시: `webui/static/v2/dist/`는 commit (prebuilt), `node_modules/`는 `.gitignore` |
| **AC-1** | MAJOR | §2.3 Option A, §8 금지사항 | Tailwind는 **prebuilt** (`@tailwindcss/cli` 또는 PostCSS). Play CDN 금지. P1 단계에서는 Tailwind 도입 안 함 (hand-rolled CSS) |
| **AC-4** | MAJOR | §4 P5 phase, §6 P5 acceptance, §8 금지사항 | P5 code-reviewer 결과를 **`docs/kronos_dashboard_overhaul_p5_review.md` 별도 파일에 저장**. Critic 메타-게이트 1회 검토 |
| **AC-6** | MAJOR | §5.5 학습 영향 확인, §6 P1 acceptance | step delta 정량 기준 (phase 5분당 step_delta ≥ 100, eta_drift_pct < 10) PowerShell 명령 추가 |
| **AC-7** | MAJOR | §6 P4 acceptance | P4 STOM Diagnostics 1:1 일치 검증을 `jq 'keys'` schema diff = ∅로 약화 (data 시간 의존성 회피) |
| **부수** | MINOR | §2.4 pre-mortem, §5.5 | `Get-Process python ... MainWindowTitle` 함정 제거. 정확한 `Invoke-RestMethod` 명령으로 교체. Node 20 LTS pin + `npm ci` 명시 |

### Confidence/Scope-risk 재평가

- 이전: Confidence **medium**, Scope-risk **wide**
- iteration 1 후: Confidence **medium-high** (B-1 분리로 학습 중 작업의 risk surface가 npm 도입 영역에서 SSR Jinja로 축소), Scope-risk **moderate** (P1.5~P6는 학습 종료 후로 미뤄 학습 중 작업 범위가 좁아짐)

---

합의 결과 (iteration 2, 2026-05-12 KST):
- Architect: APPROVE_AS_IS (MINOR concerns 4건은 plan 본문 수정 강제 아님)
- Critic: APPROVE (5 blocker + 7 AC 모두 RESOLVED, 자기-모순 해소, 코드 정합성 검증 완료)

---

## 부록 B: Phase 실행 결과 (2026-05-18 갱신)

| Phase | 계획 상태 | 실행 결과 | 핵심 Commit |
|---|---|---|---|
| P0 | ✅ pending approval → APPROVED | ✅ 사용자 승인 후 commit | `5c46ccd` |
| P1 | predictor 미시작 상태에서 SSR 골격 | ✅ npm 0 의존성으로 학습 영향 0 | `888bb08` |
| P1.5 | predictor 완료 후 예정이었으나 학습 실패로 디스크 해방 → 진행 | ✅ Vite+Svelte+TS+Tailwind 정식 | `2695151` |
| (외 1) | 디자인 시스템 v2 도입 — 계획 외 추가 (사용자 요청) | ✅ Designer 프로토타입 통합 | `ce42ab4` |
| P2 | Live Training/History 정식 패널 | ✅ Loss 카드/메트릭/History 14 run 그리드 | `a631b54`, `8f1beb4` |
| P3 | Forecast Workbench `/api/predict` 통합 | ✅ predictor 학습 전이지만 base/mini 모델로 작동 | `7e38c18` |
| P4 | STOM Diagnostics + 9 endpoint 통합 | ✅ 4 KPI + 3 tabs + 파일 브라우저 + diagnostics | `98d66d2` |
| P5 | Lighthouse a11y ≥ 90 / perf ≥ 80 + code-reviewer 메타-게이트 | ⏸ **미진행** (별도 PR 권장) | - |
| **P6** | Cutover (`KRONOS_V2_ENABLED=1`, v1 → `/v1/` 6 개월 archive) | ✅ 사용자 요청에 따라 즉시 진행 | `8562c64` |

### B.1 Plan 대비 실측 차이
- **B-1 GO/NOGO 대안 경로 사용**: predictor 학습 완료 대신 학습 실패로 디스크 해방 — `docs/p1_5_nogo_reason.md` 에 예외 처리 근거 commit
- **REV-7 dist commit**: `webui/static/v2/dist/` 정상 commit 중 (`.gitignore` 의 `dist/` 패턴은 `!webui/static/v2/dist/` 예외로 해소)
- **Cutover 시점**: 계획은 predictor 완료 + 1주일 병행 운영 후였으나 사용자 명시 요청으로 즉시 진행 — v1 페이지는 6개월 archive 정책 유지

### B.2 Plan 대비 추가된 작업
| 항목 | 사유 | Commit |
|---|---|---|
| 디자인 시스템 v2 (Pretendard + JetBrains Mono + OKLch 토큰 + light/dark) | 사용자가 별도 제작한 프로토타입 zip 을 통합 | `ce42ab4` |
| 7개 탭 본격 시각 리디자인 | 디자인 시스템 v2 적용 + 실 API 통합 | `a631b54` ~ `98d66d2` |
| P0 메트릭 스트립 + 모바일 반응형 + 데스크탑 폴리시 | 학습 중 진행한 P1 폴리시 사이클 | `d0d58b2`, `c6ca0ae`, `249a785`, `4e54f45` |

### B.3 미진행 / 잔여 작업
- **P5 정식 quality gate** (Lighthouse + code-reviewer + WCAG)
- **재학습** (validation OOM 수정 후 finetune 재실행 — 사용자 영역)
- **잔여 폴리시**: Forecast Candlestick / STOM Plotly heatmap / top-k / CSV 다운로드 / 학습 단계 알림
- **v1 archive 6개월 후 삭제 결정**

---

상태: **execution complete** (P0~P4, P6 ✅ · P5 ⏸ deferred · 재학습 deferred)
사용자 승인: ✅ P0+P1 시작 (5c46ccd) · ✅ P6 cutover 즉시 진행 요청
