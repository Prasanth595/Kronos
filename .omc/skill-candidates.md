# Kronos v2 — 스킬 후보 (session-wrap 2026-05-18 추출)

본 세션에서 7개 탭에 걸쳐 반복적으로 등장한 패턴들. 추후 `/oh-my-claudecode:skillify` 또는 `/oh-my-claudecode:learner` 로 재사용 스킬로 변환 가능.

---

## P1 · 5단 카드 헤더 패턴

**등장**: 7개 탭 전부, ~20곳 이상

```svelte
<div class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">{ENDPOINT_OR_PHASE}</div>
      <div class="card-title">{HUMAN_TITLE}</div>
    </div>
    <span class="pill {STATUS_KIND}"><span class="dot"></span>{STATUS_LABEL}</span>
  </div>
  <!-- body -->
</div>
```

5층 계층: card → header → eyebrow(작은 라벨) → title(굵은 제목) → 우측 status pill. 데이터 출처 표기(/api/...)는 eyebrow 에, 사람이 읽는 제목은 title 에, 현재 상태는 pill 에.

---

## P2 · KPI 메트릭 스트립 (.metric × N)

**등장**: Live Training, History, System Health, STOM, Artifacts

```svelte
<section class="grid-1-1-1-1">
  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">{LABEL}</span>
      <span class="delta {up|down|flat}">▼ {pct}%</span>
    </div>
    <div class="metric-value tnum">{value}<span class="metric-unit">{unit}</span></div>
    <div class="metric-foot">{context_data}</div>
  </div>
  ...
</section>
```

핵심: `tabular-nums` 로 숫자 정렬 + delta 화살표 색상 분기(▼=down=success / ▲=up=danger) + 미니 컨텍스트.

---

## P3 · Status Pill 4-way 분기

**등장**: 모든 탭

```ts
function statusKind(s: string): 'success' | 'danger' | 'accent' | 'warn' | '' {
  if (['completed','complete','success','done'].includes(s)) return 'success';
  if (['failed','error'].includes(s)) return 'danger';
  if (['running','active'].includes(s)) return 'accent';
  if (['waiting','pending'].includes(s)) return 'warn';
  return '';
}
```

색상 매핑 단일 owner 함수 → CSS `.pill.success / .danger / .accent / .warn` 와 자동 매칭.

---

## P4 · ECharts theme-aware palette 추출

**등장**: W3, W5, SystemHealth, Forecast

```ts
let palette = $derived.by(() => {
  void currentTheme;  // ← theme store 의존성 강제 등록
  if (typeof window === 'undefined') return null;
  const cs = getComputedStyle(document.documentElement);
  return {
    accent: cs.getPropertyValue('--accent').trim(),
    grid: cs.getPropertyValue('--border-faint').trim(),
    text: cs.getPropertyValue('--fg').trim(),
    // ...
  };
});
```

light/dark 전환 시 CSS 변수가 자동으로 바뀌고 `theme` store 구독으로 derived 가 재계산 → ECharts option 이 새 palette 로 setOption 호출됨.

---

## P5 · Svelte 5 stores + subscribe 패턴

**등장**: 모든 컴포넌트

```svelte
<script lang="ts">
  import { trainingStatus } from '$lib/stores';

  let status = $state<any>(null);
  trainingStatus.subscribe((v) => (status = v));

  let latest = $derived(status?.latest_stage ?? {});
  let pct = $derived(latest?.overall_percent ?? 0);
</script>
```

핵심: `$state + subscribe + $derived` 3단 체인으로 store 데이터를 reactive 하게 사용. App.svelte 가 polling 시작 → stores 갱신 → 모든 컴포넌트가 자동 업데이트.

---

## P6 · data-active 속성 기반 토글

**등장**: Sidebar nav, tabs, seg buttons, file rows

```svelte
<button
  data-active={current === id ? 'true' : 'false'}
  onclick={() => current = id}
>...</button>
```

```css
.nav-item[data-active="true"] { background: var(--accent-soft); border-color: var(--accent); }
.tabs button[data-active="true"] { border-bottom: 2px solid var(--accent); color: var(--accent-strong); }
```

class 분기 대신 data attribute 로 토글 — CSS attribute selector 가 더 가벼우면서 JS 코드 단순화.

---

## 변환 우선순위

가장 가치 큰 순서:
1. **P1 (5단 카드 헤더)** — 새 탭 추가 시 boilerplate 자동화
2. **P4 (ECharts palette 추출)** — 다른 차트 라이브러리 도입 시 동일 패턴 재사용
3. **P3 (Status pill 분기)** — 다른 도메인의 status 표시 통일
