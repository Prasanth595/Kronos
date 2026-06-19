# Kronos 대시보드 P1.5 UI/시각 디자인 스펙

작성일: 2026-05-13 KST
상태: **P1.5 사전 디자인 스펙 (학습 진행 중, 구현 미진행)**
근거 문서: `docs/kronos_dashboard_overhaul_plan.md` (RALPLAN-DR 합의 계획)

> **중요: 이 문서는 디자인 사양 전용이다. 학습 프로세스를 건드리는 코드/명령은 0건이며, npm/빌드/코드 변경도 이 문서 작성 시점에는 0건이다. 구현은 `predictor_complete=true` 확인 후 별도 PR로 진행한다.**

대상 파일 (P1.5 시작 시 생성):
- `webui/v2_src/src/lib/theme.ts` (P1.5 시작 시 신규 생성)
- `webui/static/v2/css/v2.css` (P1 hand-rolled CSS와 단절 없이 호환)

---

## 1. 미적 방향 (Aesthetic Direction)

**도메인**: 학습 대시보드 / 데이터 모니터링 / 운영 도구 — editorial-leaning default를 **명시적으로 재정의**한다.

**선택한 방향**: Dark Navy Operational (운영 도구용 dark 팔레트)

| 결정 항목 | 값 | 이유 |
|---|---|---|
| 배경 | `#0f172a` (slate-900) | P1에서 이미 확정된 body background — 단절 금지 |
| 카드 | `#111827` (gray-900) | P1 `--chart-bg` 그대로 계승 |
| 보더 | `#243244` | P1 `--chart-grid` 그대로 계승 |
| 액센트 | `#38bdf8` (sky-400) | P1 `--chart-color-primary` 그대로 계승 |
| 서체 (디스플레이) | `'Segoe UI', 'Malgun Gothic', sans-serif` | P1 정의 계승 + Windows 환경 최우선 |
| 서체 (모노) | `'Consolas', 'D2Coding', monospace` | Windows 네이티브 + step/loss 수치 가독성 |
| 포인트 색상 | `#22c55e` 성공, `#f59e0b` 경고, `#ef4444` 위험 | P1 신호등 체계 그대로 |

**차별점**: P1.5에서 새로 추가되는 것은 **더 많은 색**이 아니라, 동일 팔레트 위에 올라오는 micro-interaction(count-up, slide-fade 탭 전환, hover lift, pulse)과 타이포그래피 스케일의 정밀도다.

---

## 2. Design Tokens — CSS 변수 기준선

### 2.1 P1 기존 변수 (v2_shell.html 정의, 변경 금지)

| 변수 | 값 | 사용처 | Tailwind 매핑 |
|---|---|---|---|
| `--chart-color-primary` | `#38bdf8` | 액센트, 활성 nav, ECharts 주 계열 | `sky-400` |
| `--chart-color-secondary` | `#22c55e` | 완료/성공 상태, ETA bar 끝 색 | `green-500` |
| `--chart-color-warn` | `#f59e0b` | 경고 신호등(황), 예측기 대기 | `amber-500` |
| `--chart-color-danger` | `#ef4444` | 위험 신호등(적), 오류 상태 | `red-500` |
| `--chart-bg` | `#111827` | 카드 배경 | `gray-900` |
| `--chart-grid` | `#243244` | 차트 그리드선, 카드 보더, nav 보더 | (커스텀, slate-800~900 사이) |
| `--chart-font-family` | `'Segoe UI','Malgun Gothic',sans-serif` | 차트 라벨, 기본 body | (커스텀) |

### 2.2 P1.5에서 추가할 변수 (theme.ts가 document.documentElement.style에 set)

#### 색상 (Color)

| 변수 | 값 | 사용처 | Tailwind 매핑 |
|---|---|---|---|
| `--color-bg` | `#0f172a` | body 배경 (P1 body background 일치) | `slate-900` |
| `--color-card` | `#111827` | 카드/패널 배경 (`--chart-bg` 별칭) | `gray-900` |
| `--color-card-raised` | `#0b1120` | 중첩 카드, 스파크 카드 (P1 `.w5-spark-card` 배경) | (커스텀) |
| `--color-border` | `#243244` | 카드/nav/스파크 카드 보더 (`--chart-grid` 별칭) | (커스텀) |
| `--color-border-muted` | `#1e293b` | 서브 구분선, stepper connector | `slate-800` |
| `--color-text` | `#e2e8f0` | 본문 텍스트 (P1 body color 일치) | `slate-200` |
| `--color-text-muted` | `#94a3b8` | 보조 텍스트, nav 비활성 (P1 일치) | `slate-400` |
| `--color-text-dim` | `#64748b` | 더 약한 보조 (P1 `.step-name`, `.timeline-label`) | `slate-500` |
| `--color-text-faint` | `#475569` | 섹션 제목, 최약 텍스트 (P1 `.nav-section-title`) | `slate-600` |
| `--color-accent` | `#38bdf8` | 주 액센트 (`--chart-color-primary` 별칭) | `sky-400` |
| `--color-accent-dim` | `rgba(56,189,248,.12)` | 활성 nav 배경 (P1 일치) | — |
| `--color-accent-hover` | `rgba(56,189,248,.08)` | hover nav 배경 (P1 일치) | — |
| `--color-accent-subtle` | `#bfdbfe` | 헤더 h1 색 (P1 일치) | `blue-200` |
| `--color-success` | `#22c55e` | 완료, 신호등 녹 (`--chart-color-secondary`) | `green-500` |
| `--color-success-bg` | `#14532d` | 완료 배지 배경 (P1 일치) | `green-900` |
| `--color-success-text` | `#dcfce7` | 완료 배지 텍스트 (P1 일치) | `green-100` |
| `--color-warn` | `#f59e0b` | 경고 (`--chart-color-warn`) | `amber-500` |
| `--color-warn-bg` | `#422006` | 대기 배지 배경 (P1 일치) | `orange-950` |
| `--color-warn-text` | `#fde68a` | 대기 배지 텍스트 (P1 일치) | `amber-200` |
| `--color-danger` | `#ef4444` | 위험 (`--chart-color-danger`) | `red-500` |
| `--color-info` | `#93c5fd` | 학습중 배지 텍스트, 링크 색 (P1 일치) | `blue-300` |
| `--color-info-bg` | `#0c4a6e` | 학습중 배지 배경 (P1 일치) | `sky-950` |
| `--color-overlay` | `rgba(15,23,42,.8)` | 모달 오버레이, 잠금 위젯 dim | — |
| `--color-header-gradient-start` | `#111827` | 헤더 그라디언트 시작 (P1 일치) | `gray-900` |
| `--color-header-gradient-end` | `#1d4ed8` | 헤더 그라디언트 끝 (P1 일치) | `blue-700` |

#### 타이포그래피 (Typography)

| 변수 | 값 | 사용처 | Tailwind 매핑 |
|---|---|---|---|
| `--font-family-base` | `'Segoe UI','Malgun Gothic',sans-serif` | 본문 전체 (`--chart-font-family` 별칭) | — |
| `--font-family-mono` | `'Consolas','D2Coding',monospace` | step 수치, loss 값, 타임스탬프 | `font-mono` |
| `--font-size-xs` | `0.625rem` (10px) | nav 섹션 제목, 라벨 상단 (P1 일치) | `text-[10px]` |
| `--font-size-sm` | `0.6875rem` (11px) | 보조 레이블, step-name, spark-label (P1 일치) | `text-[11px]` |
| `--font-size-base` | `0.75rem` (12px) | 기본 본문, timeline-value, muted (P1 일치) | `text-xs` |
| `--font-size-md` | `0.8125rem` (13px) | nav 링크, 카드 h3, badge (P1 일치) | `text-[13px]` |
| `--font-size-lg` | `0.9375rem` (15px) | 카드 h2 (P1 일치) | `text-[15px]` |
| `--font-size-xl` | `1rem` (16px) | spark 현재 값 (P1 일치) | `text-base` |
| `--font-size-2xl` | `1.25rem` (20px) | 헤더 h1 (P1 일치) | `text-xl` |
| `--font-size-3xl` | `1.5rem` (24px) | Hero 강조 수치 (P1.5 신규, count-up 대상) | `text-2xl` |
| `--line-height-tight` | `1.25` | 배지, 수치 전용 줄 | — |
| `--line-height-normal` | `1.5` | 일반 본문 (P1 `.w7-message` 일치) | — |
| `--line-height-relaxed` | `1.75` | 잠금 위젯 설명 텍스트 | — |

#### 간격 (Spacing)

| 변수 | 값 | 사용처 | Tailwind 매핑 |
|---|---|---|---|
| `--space-0_5` | `0.125rem` (2px) | 최소 여백 | `space-0.5` |
| `--space-1` | `0.25rem` (4px) | 배지 패딩 상하 (P1 일치) | `p-1` |
| `--space-2` | `0.5rem` (8px) | 아이콘/텍스트 gap, stepper gap (P1 일치) | `gap-2` |
| `--space-3` | `0.75rem` (12px) | 카드 내부 소 여백, spark-card padding (P1 일치) | `p-3` |
| `--space-4` | `1rem` (16px) | nav 좌우 패딩, 카드 마진 (P1 `18px` 근사) | `p-4` |
| `--space-5` | `1.125rem` (18px) | 카드 패딩, hero padding (P1 정확히 18px) | — |
| `--space-6` | `1.5rem` (24px) | 헤더/메인 좌우 padding (P1 일치) | `px-6` |
| `--space-8` | `2rem` (32px) | 섹션 간 대형 여백 | `my-8` |
| `--space-12` | `3rem` (48px) | 잠금 위젯 상하 패딩 (P1 `40px` 근사) | `py-12` |
| `--space-16` | `4rem` (64px) | 빈 상태 최대 패딩 | `py-16` |

#### 라운딩 (Border Radius)

| 변수 | 값 | 사용처 | Tailwind 매핑 |
|---|---|---|---|
| `--radius-sm` | `6px` | 배지 이너, 소형 pill | `rounded` |
| `--radius-md` | `10px` | spark-card (P1 일치) | `rounded-[10px]` |
| `--radius-lg` | `14px` | 카드, hero-strip (P1 일치) | `rounded-2xl` |
| `--radius-xl` | `18px` | 모달, 대형 패널 | `rounded-[18px]` |
| `--radius-full` | `9999px` | 배지 pill, 도트, 프로그레스 바 (P1 일치) | `rounded-full` |

#### 그림자 (Shadow)

| 변수 | 값 | 사용처 | Tailwind 매핑 |
|---|---|---|---|
| `--shadow-sm` | `0 1px 3px rgba(0,0,0,.4)` | 비활성 카드 | `shadow-sm` |
| `--shadow-md` | `0 4px 12px rgba(0,0,0,.5)` | hover lift 기본 상태 | `shadow-md` |
| `--shadow-lg` | `0 8px 24px rgba(0,0,0,.6)` | hover lift 활성 상태 | `shadow-lg` |
| `--shadow-xl` | `0 16px 40px rgba(0,0,0,.7)` | 모달, 커맨드 팔레트 | `shadow-xl` |
| `--shadow-glow-accent` | `0 0 8px #38bdf8` | (미사용, P1.5 예약) | — |
| `--shadow-glow-green` | `0 0 8px #22c55e` | 신호등 lit-green (P1 `.tl-dot.lit-green` 일치) | — |
| `--shadow-glow-yellow` | `0 0 8px #f59e0b` | 신호등 lit-yellow (P1 일치) | — |
| `--shadow-glow-red` | `0 0 8px #ef4444` | 신호등 lit-red (P1 일치) | — |

#### 트랜지션 (Transition)

| 변수 | 값 | 사용처 | Tailwind 매핑 |
|---|---|---|---|
| `--transition-fast` | `100ms ease` | 배지 상태 변경 | `duration-100` |
| `--transition-base` | `150ms ease` | nav hover, 신호등, progress bar (P1 일치) | `duration-150` |
| `--transition-slow` | `400ms ease` | ETA bar fill, count-up 애니 (P1 `.timeline-bar-fill` 일치) | `duration-[400ms]` |
| `--transition-tab` | `200ms ease-out` | 탭 slide/fade 전환 | — |
| `--transition-lift` | `150ms ease` | 카드 hover lift | — |

#### 브레이크포인트 (Breakpoints, 참조용 CSS 변수가 아닌 미디어 쿼리 상수)

| 상수 | 값 | 의미 |
|---|---|---|
| `--bp-sm` | `480px` | 소형 모바일 |
| `--bp-md` | `768px` | 태블릿 |
| `--bp-lg` | `900px` | 기존 P1 `.main-grid` 단열 전환 기준 (P1 일치) |
| `--bp-xl` | `1280px` | 데스크탑 기준 레이아웃 |
| `--bp-2xl` | `1536px` | 와이드 스크린 |

---

## 3. Theme.ts 코드 스펙

> **주의**: 아래는 구현이 아닌 사양(specification)이다. P1.5 시작 시 `webui/v2_src/src/lib/theme.ts`로 신규 생성한다.

```ts
// webui/v2_src/src/lib/theme.ts
// P1.5 시작 시 생성. ECharts + Plotly 두 라이브러리의 테마 옵션을 단일 파일에서 관리한다.

import type { EChartsOption } from 'echarts';

// ── 1. 토큰 정의 ────────────────────────────────────────────────────
export const theme = {
  colors: {
    bg:               '#0f172a',
    card:             '#111827',
    cardRaised:       '#0b1120',
    border:           '#243244',
    borderMuted:      '#1e293b',
    text:             '#e2e8f0',
    textMuted:        '#94a3b8',
    textDim:          '#64748b',
    textFaint:        '#475569',
    accent:           '#38bdf8',
    accentDim:        'rgba(56,189,248,.12)',
    accentHover:      'rgba(56,189,248,.08)',
    accentSubtle:     '#bfdbfe',
    success:          '#22c55e',
    successBg:        '#14532d',
    successText:      '#dcfce7',
    warn:             '#f59e0b',
    warnBg:           '#422006',
    warnText:         '#fde68a',
    danger:           '#ef4444',
    info:             '#93c5fd',
    infoBg:           '#0c4a6e',
  },
  typography: {
    fontBase:  "'Segoe UI','Malgun Gothic',sans-serif",
    fontMono:  "'Consolas','D2Coding',monospace",
    // 크기는 rem 단위. chart label용 px 환산은 getter 사용.
    size: { xs: '0.625rem', sm: '0.6875rem', base: '0.75rem',
            md: '0.8125rem', lg: '0.9375rem', xl: '1rem',
            '2xl': '1.25rem', '3xl': '1.5rem' },
  },
  spacing: {
    '0_5': '0.125rem', '1': '0.25rem', '2': '0.5rem', '3': '0.75rem',
    '4': '1rem', '5': '1.125rem', '6': '1.5rem', '8': '2rem',
    '12': '3rem', '16': '4rem',
  },
  radius: { sm: '6px', md: '10px', lg: '14px', xl: '18px', full: '9999px' },
  shadow: {
    sm:  '0 1px 3px rgba(0,0,0,.4)',
    md:  '0 4px 12px rgba(0,0,0,.5)',
    lg:  '0 8px 24px rgba(0,0,0,.6)',
    xl:  '0 16px 40px rgba(0,0,0,.7)',
    glowAccent: '0 0 8px #38bdf8',
    glowGreen:  '0 0 8px #22c55e',
    glowYellow: '0 0 8px #f59e0b',
    glowRed:    '0 0 8px #ef4444',
  },
  transition: {
    fast:  '100ms ease',
    base:  '150ms ease',
    slow:  '400ms ease',
    tab:   '200ms ease-out',
    lift:  '150ms ease',
  },
} as const;

// ── 2. CSS 변수 적용 ─────────────────────────────────────────────────
// P1의 기존 --chart-color-* 변수도 동일 값으로 다시 set → 두 모드 공존 보장
export function applyTheme(): void {
  const root = document.documentElement.style;
  const c = theme.colors;
  const t = theme.typography;

  // P1 호환 (기존 변수 유지)
  root.setProperty('--chart-color-primary',   c.accent);
  root.setProperty('--chart-color-secondary', c.success);
  root.setProperty('--chart-color-warn',      c.warn);
  root.setProperty('--chart-color-danger',    c.danger);
  root.setProperty('--chart-bg',              c.card);
  root.setProperty('--chart-grid',            c.border);
  root.setProperty('--chart-font-family',     t.fontBase);

  // P1.5 신규 변수
  root.setProperty('--color-bg',             c.bg);
  root.setProperty('--color-card',           c.card);
  root.setProperty('--color-card-raised',    c.cardRaised);
  root.setProperty('--color-border',         c.border);
  root.setProperty('--color-border-muted',   c.borderMuted);
  root.setProperty('--color-text',           c.text);
  root.setProperty('--color-text-muted',     c.textMuted);
  root.setProperty('--color-text-dim',       c.textDim);
  root.setProperty('--color-text-faint',     c.textFaint);
  root.setProperty('--color-accent',         c.accent);
  root.setProperty('--color-accent-dim',     c.accentDim);
  root.setProperty('--color-success',        c.success);
  root.setProperty('--color-warn',           c.warn);
  root.setProperty('--color-danger',         c.danger);
  root.setProperty('--color-info',           c.info);
  root.setProperty('--font-family-base',     t.fontBase);
  root.setProperty('--font-family-mono',     t.fontMono);
  // ... (spacing, radius, shadow, transition 변수도 동일 패턴으로 set)
}

// ── 3. ECharts 테마 옵션 ─────────────────────────────────────────────
// W3(LossCurve), W5(GpuSparkline) 공통으로 사용
export function getEChartsTheme(): Partial<EChartsOption> {
  const c = theme.colors;
  return {
    backgroundColor:  c.card,
    textStyle: { fontFamily: theme.typography.fontBase, color: c.textMuted },
    color: [c.accent, c.success, c.warn, c.danger, c.info],
    axisPointer: { lineStyle: { color: c.border } },
    grid: { borderColor: c.border },
    xAxis: {
      axisLine:  { lineStyle: { color: c.border } },
      splitLine: { lineStyle: { color: c.border, type: 'dashed' } },
      axisLabel: { color: c.textDim, fontFamily: theme.typography.fontBase },
    },
    yAxis: {
      axisLine:  { lineStyle: { color: c.border } },
      splitLine: { lineStyle: { color: c.border, type: 'dashed' } },
      axisLabel: { color: c.textDim, fontFamily: theme.typography.fontBase },
    },
    tooltip: {
      backgroundColor: c.cardRaised,
      borderColor:     c.border,
      textStyle:       { color: c.text },
    },
  };
}

// ── 4. Plotly 레이아웃 (STOM Diagnostics 탭 전용, dynamic import 후 사용) ──
// 반환 타입은 Plotly dynamic import 완료 후 Plotly.Layout에 맞게 캐스팅
export function getPlotlyLayout(): Record<string, unknown> {
  const c = theme.colors;
  return {
    paper_bgcolor: c.card,
    plot_bgcolor:  c.card,
    font:          { family: theme.typography.fontBase, color: c.textMuted, size: 11 },
    colorway:      [c.accent, c.success, c.warn, c.danger, c.info],
    xaxis:  { gridcolor: c.border, linecolor: c.border, tickfont: { color: c.textDim } },
    yaxis:  { gridcolor: c.border, linecolor: c.border, tickfont: { color: c.textDim } },
    hoverlabel: { bgcolor: c.cardRaised, bordercolor: c.border,
                  font: { family: theme.typography.fontBase, color: c.text } },
    margin: { t: 32, r: 16, b: 40, l: 48 },
  };
}

// ── 5. Readiness 레벨 → 색상/카피 매핑 (readinessMap.ts에서 재사용) ──
export const readinessColorMap = {
  ready:    { bg: '#14532d', text: '#dcfce7', glow: '0 0 8px #22c55e' },
  training: { bg: '#0c4a6e', text: '#bae6fd', glow: '0 0 8px #38bdf8' },
  waiting:  { bg: '#422006', text: '#fde68a', glow: '0 0 8px #f59e0b' },
} as const;
```

**theme.ts 소유권 규칙**:
- ECharts 옵션은 `W3_LossCurve.svelte`, `W5_GpuSparkline.svelte` mount 직전 `getEChartsTheme()`를 호출해 baseOption에 spread한다.
- Plotly 옵션은 `/v2#stom` 탭 진입 시 `import('plotly.js-dist-min')` 완료 후 `getPlotlyLayout()`을 merge한다.
- 두 차트 라이브러리가 **동일 색 토큰**을 읽으므로 한 화면에 동시에 떠도 폰트·배경·그리드·색상이 일치한다.

---

## 4. Svelte 컴포넌트 트리

### 4.1 디렉터리 구조 (P1.5 빌드 후)

```
webui/v2_src/
├── index.html              # Vite entry. SSR marker <meta> 정적 삽입 (P1과 동일 내용)
├── vite.config.ts          # base: '/static/v2/dist/', watch.ignored 학습 경로 전부 제외
├── tsconfig.json
├── package.json            # engines.node: "^20"
├── package-lock.json       # npm ci 재현 가능 설치용, commit 대상
├── tailwind.config.js
├── postcss.config.js
└── src/
    ├── main.ts             # applyTheme() 최초 호출 → App mount
    ├── App.svelte          # 최상위: Layout(Sidebar + HeroStrip + TabContent)
    ├── lib/
    │   ├── theme.ts        # 디자인 토큰 (§3)
    │   ├── api.ts          # fetch 래퍼: /api/training/{status,history,artifacts,gpu}
    │   ├── stores.ts       # Svelte writable stores (§6 참조)
    │   ├── polling.ts      # startPolling(store, fetcher, intervalMs)
    │   ├── ringBuffer.ts   # RingBuffer<T>(capacity) — GPU 720pt, history 1000pt
    │   ├── kstFormat.ts    # toKstString(isoOrEpoch) — Asia/Seoul Intl.DateTimeFormat
    │   └── readinessMap.ts # readiness.level → { label, message, colorClass } 매핑
    ├── layout/
    │   ├── Sidebar.svelte
    │   ├── HeroStrip.svelte
    │   └── TabContent.svelte
    ├── widgets/
    │   ├── W1_StageStepper.svelte
    │   ├── W2_ReadinessCountdown.svelte
    │   ├── W3_LossCurve.svelte
    │   ├── W4_EtaTimeline.svelte
    │   ├── W5_GpuSparkline.svelte
    │   ├── W6_LossVolatility.svelte   # P4 도입, P1.5에서 placeholder
    │   ├── W7_StatusBadge.svelte
    │   └── W8_BacktestGallery.svelte  # P5 도입, P1.5에서 locked placeholder
    ├── tabs/
    │   ├── LiveTrainingTab.svelte
    │   ├── ForecastWorkbenchTab.svelte   # P3 도입, P1.5에서 locked placeholder
    │   ├── StomDiagnosticsTab.svelte     # P4 도입, Plotly dynamic import
    │   ├── ArtifactsModelsTab.svelte
    │   ├── HistoryRunsTab.svelte
    │   ├── SystemHealthTab.svelte
    │   └── SettingsTab.svelte
    └── charts/
        ├── EChartsRenderer.svelte       # ECharts 래퍼 (eager load)
        └── PlotlyRenderer.svelte        # Plotly 래퍼 (StomDiagnosticsTab 진입 시만 import)
```

### 4.2 컴포넌트별 인터페이스 표

#### 레이아웃 컴포넌트

| 컴포넌트 | props | state(local) | store 의존 | 자식 |
|---|---|---|---|---|
| `App.svelte` | — | — | `activeTab` | `Sidebar`, `HeroStrip`, `TabContent` |
| `Sidebar.svelte` | — | — | `activeTab`, `refreshInterval`, `lastUpdated` | — |
| `HeroStrip.svelte` | — | — | `trainingStatus`, `activeTab` | `W7_StatusBadge`, `W1_StageStepper`, `W2_ReadinessCountdown` |
| `TabContent.svelte` | — | — | `activeTab` | 각 Tab 컴포넌트 |

#### 탭 컴포넌트

| 컴포넌트 | props | state(local) | store 의존 | 자식 |
|---|---|---|---|---|
| `LiveTrainingTab.svelte` | — | — | `trainingStatus`, `trainingHistory`, `gpuStatus` | `W3_LossCurve`, `W4_EtaTimeline`, `W5_GpuSparkline` |
| `ForecastWorkbenchTab.svelte` | — | `locked: boolean` | `trainingStatus` (`predictor_complete` 읽기) | locked placeholder |
| `StomDiagnosticsTab.svelte` | — | `plotlyLoaded: boolean` | `activeTab` (진입 감지 → dynamic import) | `PlotlyRenderer` |
| `ArtifactsModelsTab.svelte` | — | — | `trainingArtifacts` | — |
| `HistoryRunsTab.svelte` | — | — | `trainingHistory` | — |
| `SystemHealthTab.svelte` | — | — | `gpuStatus` | `W5_GpuSparkline` (전체 크기) |
| `SettingsTab.svelte` | — | `draft: number` | `refreshInterval` | — |

#### 위젯 컴포넌트

| 컴포넌트 | props | state(local) | store 의존 | 자식 |
|---|---|---|---|---|
| `W1_StageStepper.svelte` | — | — | `trainingStatus` (`stages[]`) | — |
| `W2_ReadinessCountdown.svelte` | — | `tick: number` (매초 Svelte tick) | `trainingStatus` (`readiness`, `eta_seconds`) | — |
| `W3_LossCurve.svelte` | `height?: number` | `echarts: ECharts instance` | `trainingHistory` (ring buffer) | `EChartsRenderer` |
| `W4_EtaTimeline.svelte` | — | `nowKst: string` (매초 갱신) | `trainingStatus` (`eta_seconds`, `updated_at`, `overall_percent`) | — |
| `W5_GpuSparkline.svelte` | `compact?: boolean` | `charts: ECharts[]` | `gpuStatus` (ring buffer 720pt) | `EChartsRenderer` (3개 인스턴스) |
| `W6_LossVolatility.svelte` | `window?: number` | `stats: {mean,std,cv}` | `trainingHistory` (W3 buffer 재사용) | — |
| `W7_StatusBadge.svelte` | — | — | `trainingStatus` (`readiness.level`, `readiness.label`) | — |
| `W8_BacktestGallery.svelte` | — | `locked: boolean` | `trainingStatus` (`predictor_complete`) | locked placeholder |

#### 차트 렌더러

| 컴포넌트 | props | state(local) | store 의존 | 자식 |
|---|---|---|---|---|
| `EChartsRenderer.svelte` | `option: EChartsOption`, `height?: number`, `onReady?: (chart) => void` | `chart: echarts.ECharts` | — | — |
| `PlotlyRenderer.svelte` | `data: Plotly.Data[]`, `layout?: Partial<Plotly.Layout>`, `height?: number` | `plotly: typeof Plotly`, `loaded: boolean` | — | — |

---

## 5. 탭 → 위젯 매핑 (단계별)

| 탭 | P1 위젯 (라이브) | P2 추가 | P3 추가 | P4 추가 | P5 추가 |
|---|---|---|---|---|---|
| **Live Training** | W7 배지, W1 스테퍼, W2 신호등/ETA, W3 단순 라인 차트, W4 ETA 타임라인, W5 GPU 스파크라인 | W3 dataZoom/brush 정식, Cmd+K 팔레트 | — | W6 손실 변동 통계 | micro-interaction 폴리시 |
| **Forecast Workbench** | 잠금 placeholder | — | lookback/pred_len/temperature/top_p 슬라이더, `/api/predict` 호출, 예측 차트, GPU device disable(학습중) | — | — |
| **STOM Diagnostics** | 잠금 placeholder | — | — | diagnostics heatmap(Plotly), top-k 테이블, 추천 테이블 | — |
| **Artifacts & Models** | 아티팩트 목록 (read-only) | interactive 아티팩트 갤러리 | — | — | W8 백테스트 갤러리 placeholder → predictor 완료 시 unlock |
| **History & Runs** | 기록 텍스트 목록 | 정식 runs 테이블 | — | — | — |
| **System Health** | (Live Training의 W5 재사용) | W5 전체 크기 GPU 상세 차트 | — | — | — |
| **Settings** | 폴링 간격 표시 | refresh interval 토글 (2~3600s) | — | dark/light 모드 토글 예약 | light 모드 토글 실 구현 |

---

## 6. State / Data Flow

### 6.1 Svelte writable stores (`src/lib/stores.ts`)

| store | 타입 | 데이터 소스 | 폴링 주기 | 버퍼 |
|---|---|---|---|---|
| `trainingStatus` | `TrainingStatusResponse \| null` | `/api/training/status` | `refreshInterval` (기본 5s) | 없음 (최신 단일 객체) |
| `trainingHistory` | `RingBuffer<HistoryPoint>` | `/api/training/history?limit=200` (기본), dataZoom 시 `limit=1000` lazy fetch | `refreshInterval` | 최대 1,000pt, 초과 시 oldest 폐기 |
| `trainingArtifacts` | `string[]` | `/api/training/artifacts` | `refreshInterval` | 없음 |
| `gpuStatus` | `RingBuffer<GpuPoint>` | `/api/training/gpu` | `refreshInterval` | 최대 720pt (1시간 = 5s × 720) |
| `refreshInterval` | `number` (ms) | 사용자 설정 (SettingsTab) | — | 기본값 5000 |
| `activeTab` | `string` | 사용자 클릭 / URL fragment | — | — |
| `lastUpdated` | `string \| null` | 가장 최근 폴링 완료 시각 (KST) | — | — |

### 6.2 폴링 시퀀스 (`src/lib/polling.ts`)

```ts
// 사양: 모든 store에 동일 패턴 적용
function startPolling<T>(
  store: Writable<T>,
  fetcher: () => Promise<T>,
  intervalMs: number,
): () => void;  // 반환값: cleanup 함수 (onDestroy에서 호출)
```

- 4개 fetch (status, history, artifacts, gpu)가 **병렬**로 동시에 폴링된다.
- 학습에 영향을 주지 않는 read-only API이므로 병렬 호출 허용.
- `fetch` 실패 시 store는 이전 값을 유지하고 콘솔 경고만 출력 (학습 중단 아님).
- `refreshInterval` store 변경 시 현재 인터벌을 clear하고 새 주기로 재시작.

### 6.3 데이터 흐름 다이어그램 (텍스트)

```
[Flask API]
  /api/training/status   ──→ polling.ts ──→ trainingStatus  ──→ W7, W1, W2, W4, HeroStrip
  /api/training/history  ──→ polling.ts ──→ trainingHistory ──→ W3, W6, HistoryRunsTab
  /api/training/artifacts──→ polling.ts ──→ trainingArtifacts──→ ArtifactsModelsTab
  /api/training/gpu      ──→ polling.ts ──→ gpuStatus       ──→ W5, SystemHealthTab

[사용자 이벤트]
  탭 클릭          ──→ activeTab    ──→ TabContent (tab 전환)
  간격 변경        ──→ refreshInterval ──→ polling.ts (재시작)
  dataZoom 이벤트  ──→ W3_LossCurve (lazy fetch limit=1000) ──→ trainingHistory
  /v2#stom 진입    ──→ StomDiagnosticsTab ──→ import('plotly.js-dist-min') → PlotlyRenderer
```

---

## 7. ECharts ↔ Plotly 공존 규칙

### 7.1 로딩 전략

| 라이브러리 | 로딩 시점 | 방법 |
|---|---|---|
| **ECharts 5.x** | 앱 초기화 시 eager load | `package.json` devDependency → Vite 번들 |
| **Plotly 2.35.2** | `/v2#stom` 탭 진입 시만 | `import('plotly.js-dist-min').then(P => { plotly = P.default; plotlyLoaded = true; })` |

### 7.2 테마 동기화 규칙

1. **ECharts**: `W3_LossCurve.svelte`와 `W5_GpuSparkline.svelte` mount 직전 `getEChartsTheme()`를 호출해 `baseOption`에 spread.
2. **Plotly**: `PlotlyRenderer.svelte`에서 dynamic import 완료 후 `getPlotlyLayout()`을 `Plotly.newPlot(el, data, layout)` 호출 시 merge.
3. 두 라이브러리 모두 `theme.colors.card`를 배경, `theme.colors.border`를 그리드, `theme.colors.textDim`을 축 레이블, `theme.typography.fontBase`를 폰트로 사용 → **한 화면에 동시에 표시해도 색상/폰트 단절 없음**.

### 7.3 검증 절차 (P1.5 PR 시)
1. `/v2#stom` 탭을 열고 ECharts 차트(W5 GPU 스파크라인이 SystemHealth에서 표시)와 Plotly diagnostics heatmap이 동시에 보이도록 레이아웃 조정.
2. 스크린샷 수평 비교: 배경색 `#111827`, 그리드 `#243244`, 폰트 색 `#64748b`가 양쪽에서 동일함을 확인.
3. DevTools에서 CSS 변수 `--color-card`, `--color-border` 값이 두 차트 컨테이너에 모두 적용됨을 확인.

---

## 8. P1 → P1.5 마이그레이션 안전망

### 8.1 이중 서빙 모드

| 환경 변수 | 서빙 대상 | 동작 |
|---|---|---|
| `KRONOS_V2_DIST=0` (기본) | `templates/v2_shell.html` (Jinja SSR) | P1 Alpine+ECharts CDN 그대로 |
| `KRONOS_V2_DIST=1` | `webui/static/v2/dist/index.html` (Vite 빌드 산출물) | P1.5 Svelte SPA |

전환은 환경변수 한 줄로 즉시 이루어지며 Flask 재시작만 필요하다 (`v2/__init__.py:224` 분기 로직).

### 8.2 SSR 마커 보존 원칙

P1에서 `templates/v2_shell.html`의 SSR 마커:
```html
<meta name="kronos-v2-shell" content="hero,live-training,stom,forecast,artifacts,history,system-health">
<meta name="kronos-v2-version" content="p1-ssr">
```

P1.5 dist 모드에서 `webui/v2_src/index.html`에 **동일 내용을 정적으로 삽입**한다. Vite 빌드는 `index.html`을 그대로 복사하므로 `dist/index.html`에도 마커가 살아있다.

검증:
```powershell
# P1 모드 (KRONOS_V2_DIST=0)
Invoke-WebRequest -Uri 'http://127.0.0.1:5070/v2' | Select-Object -ExpandProperty Content |
  Select-String 'kronos-v2-shell'

# P1.5 모드 (KRONOS_V2_DIST=1)
Invoke-WebRequest -Uri 'http://127.0.0.1:5070/v2' | Select-Object -ExpandProperty Content |
  Select-String 'kronos-v2-shell'
```
두 모드 모두 `kronos-v2-shell` 문자열이 포함되어야 하며, 기존 `tests/test_v2_smoke.py`가 dist 모드에서도 그대로 통과해야 한다.

### 8.3 색상 단절 방지 절차

1. P1.5 빌드 후 `KRONOS_V2_DIST=0`(P1)과 `KRONOS_V2_DIST=1`(P1.5)을 번갈아 실행.
2. 동일 화면을 나란히 스크린샷: body 배경(`#0f172a`), 카드(`#111827`), 보더(`#243244`), 액센트(`#38bdf8`) 일치 확인.
3. `applyTheme()` 호출이 `main.ts`에서 App mount 이전에 실행되는지 확인 (FOUC 방지).

---

## 9. P1.5에서 추가될 Micro-interaction

### 9.1 신규 인터랙션 (Svelte 전용)

| 인터랙션 | 대상 | 구현 방식 | 타이밍 |
|---|---|---|---|
| **Hero Strip 숫자 카운트업** | W4 진행률, W2 ETA 초 단위 | Svelte `tweened` store + `spring` | 초기 mount 시 0 → 실제값으로 400ms |
| **탭 전환 slide/fade** | TabContent 내 콘텐츠 | Svelte `transition:fade` + `in:fly={{x: -16}}` | 200ms ease-out |
| **카드 hover lift** | `.card` 전체 | CSS `transition: transform 150ms, box-shadow 150ms` | hover 즉시 |
| **Readiness 신호등 pulse** | `.tl-dot.lit-*` | CSS `@keyframes pulse` (box-shadow 반복) | 신호 활성 시 무한 반복, 2s 주기 |
| **Loss 차트 dataZoom+brush** | W3_LossCurve | ECharts `dataZoom`, `brush` 컴포넌트 + lazy fetch | 사용자 드래그 시 |
| **KST 카운트다운 매초 갱신** | W2_ReadinessCountdown, W4 현재 시각 | Svelte `onMount` 내 `setInterval(1000)` + `onDestroy` cleanup | 1초 주기 |
| **Nav 활성 인디케이터 슬라이드** | `.v2-nav a.active` border-left | CSS transition + Svelte class binding | 탭 전환 150ms |
| **빈 상태 일러스트 fade-in** | locked-widget, 아티팩트 없음 | Svelte `transition:fade={{delay:100}}` | 탭 진입 시 |

### 9.2 P1 hand-rolled CSS에서도 이미 동작하는 것

| 인터랙션 | P1 구현 위치 |
|---|---|
| nav hover 배경 | `v2-nav a:hover { transition: background .15s, color .15s, border-color .15s }` |
| ETA progress bar fill | `.timeline-bar-fill { transition: width .5s ease }` |
| 신호등 transition | `.tl-dot { transition: background .3s, box-shadow .3s }` |
| progress bar fill | `.progress-fill { transition: width .4s ease }` |
| ECharts update 애니 | ECharts 기본 제공 (setOption 시 자동) |

P1.5에서는 P1의 CSS transition을 **제거하지 않고** Svelte 컴포넌트 내 class에서 동일 변수로 참조해 연속성을 유지한다.

---

## 10. 검증 체크리스트 (P1.5 PR 시 디자인 측면)

### 10.1 차트 시각 일관성

- [ ] `/v2#stom` 탭에서 ECharts 차트와 Plotly 차트가 동시에 표시될 때 배경색(`--color-card`), 그리드 색(`--color-border`), 축 레이블 색(`--color-text-dim`), 폰트(`--font-family-base`)가 육안으로 동일함
- [ ] W3 Loss Curve와 W5 GPU Sparkline의 주 색상이 각각 `#38bdf8` (sky-400)과 `#22c55e` (green-500)로 일치
- [ ] Plotly heatmap의 `paper_bgcolor`, `plot_bgcolor`가 `#111827`임을 DevTools에서 확인

### 10.2 P1 ↔ P1.5 색상 단절 없음

- [ ] `KRONOS_V2_DIST=0` (P1 SSR)과 `KRONOS_V2_DIST=1` (P1.5 dist)를 번갈아 불러도 body 배경, 카드 배경, 액센트 색상이 픽셀 수준에서 동일
- [ ] P1.5 빌드 후 `applyTheme()` 호출로 `--chart-color-primary` 등 P1 변수가 동일 값으로 유지됨을 `getComputedStyle(document.documentElement)` 확인
- [ ] FOUC(Flash of Unstyled Content) 없음: `main.ts`에서 `applyTheme()`가 첫 mount 이전에 동기적으로 실행됨

### 10.3 접근성 (Accessibility)

- [ ] Lighthouse a11y 점수 ≥ 90 (측정 환경: `FLASK_ENV=production` + waitress + `--chrome-flags='--headless=new --no-sandbox'`)
- [ ] 텍스트 대비율 4.5:1 이상: `#e2e8f0`(텍스트) on `#111827`(카드) ≥ 10:1 ✓, `#94a3b8`(muted) on `#111827` ≥ 4.6:1 ✓
- [ ] 주의: `#475569`(faint) on `#111827` 는 대비율 약 4.0:1로 **AA 위반 경계** — 이 색은 섹션 제목 등 비필수 장식 텍스트에만 사용하고 본문 정보에는 사용 금지
- [ ] 모든 인터랙티브 요소(탭, 설정 슬라이더, Cmd+K)에 `aria-label` 또는 가시적 레이블 존재
- [ ] focus ring이 `outline: 2px solid #38bdf8` 또는 동등 이상으로 가시적
- [ ] 키보드 탭 순서가 좌측 NAV → HeroStrip → TabContent 순으로 논리적

### 10.4 반응형 레이아웃

| 해상도 | 기대 동작 |
|---|---|
| 모바일 375×812 | `.main-grid` 단열, hero-strip 세로 스택, 사이드바 숨김(또는 햄버거 메뉴), 카드 전폭 |
| 태블릿 768×1024 | 사이드바 축소(icon-only) 또는 오버레이 | 
| 데스크탑 1280×900 | 2열 그리드, 240px 사이드바, P1 레이아웃과 동일 비율 |
| 데스크탑 1440×900 | 기준 레이아웃 (P1과 동일) |
| 4K 3840×2160 | 최대 너비 클램프(`max-width: 1920px, margin: auto`) 또는 그리드 칼럼 추가 검토 |

- [ ] 900px 이하에서 `.main-grid`가 단열로 전환 (P1 `@media (max-width: 900px)` 규칙 계승)
- [ ] 375px에서 hero-strip flex-direction이 column으로 전환 (P1 규칙 계승)
- [ ] 4K에서 카드가 화면 전체로 늘어나지 않도록 max-width 제한

### 10.5 다크/라이트 모드 (P5 예약)

- [ ] P1.5 시점: 다크 모드 전용, 라이트 모드 없음 (P5에서 추가)
- [ ] P5에서 라이트 모드 추가 시 `applyTheme('light')`가 호출되면 CSS 변수를 교체하고 ECharts/Plotly 양쪽에 `setOption` 재호출 → 즉시 업데이트 확인

---

상태: **P1.5 사전 디자인 스펙 (predictor 완료 후 PR로 구현)**
