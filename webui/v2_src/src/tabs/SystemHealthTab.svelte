<script lang="ts">
  import { gpuStatus, gpuRing, systemStatus, refreshSeconds, lastUpdatedAt, theme } from '$lib/stores';
  import { fmt } from '$lib/format';
  import EChartsRenderer from '../charts/EChartsRenderer.svelte';

  let gpu = $state<any>(null);
  gpuStatus.subscribe((v) => (gpu = v));

  let system = $state<any>(null);
  systemStatus.subscribe((v) => (system = v));

  let ring = $state<any[]>([]);
  gpuRing.subscribe((v) => (ring = v));

  let sec = $state(5);
  refreshSeconds.subscribe((v) => (sec = v));

  let last = $state('-');
  lastUpdatedAt.subscribe((v) => (last = v));

  let currentTheme = $state<'light' | 'dark'>('light');
  theme.subscribe((v) => (currentTheme = v));

  let g = $derived(gpu?.gpus?.[0]);
  let cpu = $derived(system?.cpu);
  let memory = $derived(system?.memory);
  let utilPct = $derived(g?.utilization_gpu_percent);
  let tempC = $derived(g?.temperature_c);
  let vramPct = $derived(g?.memory_used_percent);
  let cpuPct = $derived(cpu?.utilization_percent);
  let cpuTempC = $derived(cpu?.temperature_c);
  let cpuTempPct = $derived(cpu?.temperature_percent);
  let memoryPct = $derived(memory?.used_percent);

  type GpuTrendPoint = {
    util: number | null;
    temp: number | null;
    vram: number | null;
    ts: number;
  };

  function currentGpuPoint(): GpuTrendPoint | null {
    if (!g) return null;
    return {
      util: g.utilization_gpu_percent ?? null,
      temp: g.temperature_c ?? null,
      vram: g.memory_used_percent ?? null,
      ts: Date.now(),
    };
  }

  function formatTime(ts: number | null | undefined): string {
    if (!ts) return '—';
    return new Date(ts).toLocaleTimeString('ko-KR', {
      timeZone: 'Asia/Seoul',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  }

  function formatGpuTooltip(params: any, points: GpuTrendPoint[]): string {
    const rows = Array.isArray(params) ? params : [params];
    const idx = rows[0]?.dataIndex ?? 0;
    const point = points[idx];
    const body = rows
      .map((p: any) => {
        const value = p.value;
        if (value == null || Number.isNaN(Number(value))) return '';
        const unit = p.seriesName?.includes('온도') ? '°C' : '%';
        return `<div style="display:flex;gap:10px;justify-content:space-between;min-width:170px">
          <span>${p.marker ?? ''}${p.seriesName}</span>
          <b>${Number(value).toFixed(1)}${unit}</b>
        </div>`;
      })
      .filter(Boolean)
      .join('');
    return `<div style="font-weight:700;margin-bottom:4px">${formatTime(point?.ts)}</div>${body}`;
  }

  let chartRing = $derived.by(() => {
    if (ring.length > 0) return ring as GpuTrendPoint[];
    const point = currentGpuPoint();
    return point ? [point] : [];
  });

  // util 평균/최고 (ring buffer 기반)
  let stats = $derived.by(() => {
    if (ring.length === 0) return { utilAvg: null, tempMax: null, vramAvg: null };
    const utils = ring.map((p) => p.util).filter((v) => v != null) as number[];
    const temps = ring.map((p) => p.temp).filter((v) => v != null) as number[];
    const vrams = ring.map((p) => p.vram).filter((v) => v != null) as number[];
    return {
      utilAvg: utils.length ? utils.reduce((a, b) => a + b, 0) / utils.length : null,
      tempMax: temps.length ? Math.max(...temps) : null,
      vramAvg: vrams.length ? vrams.reduce((a, b) => a + b, 0) / vrams.length : null,
    };
  });

  // 임계값 색상
  let utilPillKind = $derived(utilPct == null ? '' : utilPct >= 90 ? 'warn' : 'success');
  let tempPillKind = $derived(tempC == null ? '' : tempC >= 80 ? 'danger' : tempC >= 70 ? 'warn' : 'success');
  let vramPillKind = $derived(vramPct == null ? '' : vramPct >= 90 ? 'warn' : 'success');
  let cpuPillKind = $derived(cpuPct == null ? '' : cpuPct >= 95 ? 'warn' : 'success');

  let palette = $derived.by(() => {
    void currentTheme;
    if (typeof window === 'undefined') return null;
    const cs = getComputedStyle(document.documentElement);
    return {
      c2: cs.getPropertyValue('--c-2').trim(),
      c3: cs.getPropertyValue('--c-3').trim(),
      c4: cs.getPropertyValue('--c-4').trim(),
      grid: cs.getPropertyValue('--border-faint').trim(),
      border: cs.getPropertyValue('--border').trim(),
      text: cs.getPropertyValue('--fg').trim(),
      textDim: cs.getPropertyValue('--dim').trim(),
      surface: cs.getPropertyValue('--surface').trim(),
    };
  });

  let multiOption = $derived.by(() => {
    void currentTheme;
    if (!palette) return {};
    const data = chartRing;
    const showSymbols = data.length <= 2;
    return {
      backgroundColor: 'transparent',
      textStyle: { color: palette.text, fontFamily: 'Pretendard Variable, sans-serif' },
      grid: { left: 48, right: 24, top: 20, bottom: 32 },
      xAxis: {
        type: 'category',
        data: data.map((p) => formatTime(p.ts)),
        axisLabel: { show: false },
        axisLine: { lineStyle: { color: palette.border } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { color: palette.textDim, fontSize: 10, formatter: '{value}%' },
        splitLine: { lineStyle: { color: palette.grid } },
        axisLine: { show: false },
      },
      tooltip: {
        trigger: 'axis',
        appendToBody: true,
        confine: true,
        axisPointer: { type: 'line', lineStyle: { color: palette.border, type: 'dashed' } },
        backgroundColor: palette.surface,
        borderColor: palette.border,
        textStyle: { color: palette.text, fontSize: 12 },
        formatter: (params: any) => formatGpuTooltip(params, data),
      },
      graphic: data.length === 0 ? [{
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: 'GPU 데이터 수신 대기 중…',
          fill: palette.textDim,
          fontSize: 12,
          fontFamily: 'Pretendard Variable, sans-serif',
        },
      }] : [],
      series: [
        { name: 'GPU util %', type: 'line', smooth: 0.5, symbol: 'circle', showSymbol: showSymbols, symbolSize: 5, data: data.map((p) => p.util), lineStyle: { color: palette.c3, width: 1.8 } },
        { name: 'VRAM %', type: 'line', smooth: 0.5, symbol: 'circle', showSymbol: showSymbols, symbolSize: 5, data: data.map((p) => p.vram), lineStyle: { color: palette.c2, width: 1.8 } },
        { name: '온도 °C', type: 'line', smooth: 0.5, symbol: 'circle', showSymbol: showSymbols, symbolSize: 5, data: data.map((p) => p.temp), lineStyle: { color: palette.c4, width: 1.8 } },
      ],
    };
  });
</script>

<section class="page-hero">
  <div class="row" style="gap:10px">
    <span class="text-eyebrow">공식 기능</span>
    <span class="pill"><span class="dot" style="background:var(--info)"></span>/api/training/gpu · /api/training/system · 5초 폴링</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">시스템 상태</h1>
  <p class="text-muted" style="margin-top:6px">
    학습 호스트의 GPU·CPU·RAM과 Flask 폴링 상태입니다. GPU는 nvidia-smi, CPU/RAM은 시스템 endpoint에서 읽으며 온도는 OS 센서가 노출될 때만 표시합니다.
  </p>
</section>

<!-- ===== Top KPIs ===== -->
<section class="grid-4-kpi">
  <div class="metric" class:glow={utilPct != null && utilPct >= 50}>
    <div class="metric-head">
      <span class="metric-label">GPU 활용률</span>
      {#if utilPillKind}
        <span class="pill {utilPillKind}" style="padding:2px 8px"><span class="dot"></span>
          {utilPillKind === 'warn' ? '높음' : '정상'}
        </span>
      {/if}
    </div>
    <div class="metric-value tnum">
      {utilPct != null ? utilPct.toFixed(1) : '—'}<span class="metric-unit">%</span>
    </div>
    <div class="metric-foot">
      {g?.name ?? 'GPU'} · 평균 {stats.utilAvg != null ? stats.utilAvg.toFixed(1) + '%' : '—'}
    </div>
  </div>

  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">온도</span>
      {#if tempPillKind}
        <span class="pill {tempPillKind}" style="padding:2px 8px"><span class="dot"></span>
          {tempPillKind === 'danger' ? '경고' : tempPillKind === 'warn' ? '주의' : '정상'}
        </span>
      {/if}
    </div>
    <div class="metric-value tnum">
      {tempC != null ? tempC.toFixed(1) : '—'}<span class="metric-unit">°C</span>
    </div>
    <div class="metric-foot">
      최고 {stats.tempMax != null ? stats.tempMax.toFixed(0) + '°C' : '—'} (최근 {ring.length} 샘플)
    </div>
  </div>

  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">VRAM</span>
      {#if vramPillKind}
        <span class="pill {vramPillKind}" style="padding:2px 8px"><span class="dot"></span>
          {vramPillKind === 'warn' ? '높음' : '정상'}
        </span>
      {/if}
    </div>
    <div class="metric-value tnum">
      {g?.memory_used_mib != null ? (g.memory_used_mib / 1024).toFixed(1) : '—'}<span class="metric-unit">/ {g?.memory_total_mib != null ? (g.memory_total_mib / 1024).toFixed(0) + ' GiB' : '— GiB'}</span>
    </div>
    <div class="metric-foot">
      평균 {stats.vramAvg != null ? stats.vramAvg.toFixed(1) + '%' : '—'} · 현재 {vramPct != null ? vramPct.toFixed(1) + '%' : '—'}
    </div>
  </div>

  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">CPU / RAM</span>
      {#if cpuPillKind}
        <span class="pill {cpuPillKind}" style="padding:2px 8px"><span class="dot"></span>
          {cpuPillKind === 'warn' ? '높음' : '정상'}
        </span>
      {/if}
    </div>
    <div class="metric-value tnum">
      {cpuPct != null ? cpuPct.toFixed(1) : '—'}<span class="metric-unit">%</span>
    </div>
    <div class="metric-foot">
      온도 {cpuTempC != null ? cpuTempC.toFixed(1) + '°C' : '미측정'}
      {#if cpuTempPct != null}({cpuTempPct.toFixed(0)}%){/if}
      · RAM {memoryPct != null ? memoryPct.toFixed(1) + '%' : '—'}
    </div>
  </div>
</section>

<!-- ===== GPU 시계열 ===== -->
<section class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">/api/training/gpu · 시계열</div>
      <div class="card-title">{g?.name ?? 'GPU'} · 자원 트렌드</div>
    </div>
    <div class="row" style="gap:14px;flex-wrap:wrap">
      <span class="legend"><span class="swatch" style="background:var(--c-3)"></span>util %</span>
      <span class="legend"><span class="swatch" style="background:var(--c-2)"></span>VRAM %</span>
      <span class="legend"><span class="swatch" style="background:var(--c-4)"></span>온도 °C</span>
    </div>
  </div>
  <EChartsRenderer option={multiOption} height="280px" />
  <div class="row" style="border-top:1px solid var(--border-faint);padding-top:14px;margin-top:8px;flex-wrap:wrap;gap:24px">
    <div class="stack" style="gap:4px">
      <span class="text-eyebrow">평균 활용률</span>
      <span class="text-mono tnum" style="font-size:18px;font-weight:600">{stats.utilAvg != null ? stats.utilAvg.toFixed(1) + '%' : '—'}</span>
    </div>
    <div class="stack" style="gap:4px">
      <span class="text-eyebrow">최고 온도</span>
      <span class="text-mono tnum" style="font-size:18px;font-weight:600;color:{stats.tempMax != null && stats.tempMax >= 80 ? 'var(--danger)' : stats.tempMax != null && stats.tempMax >= 70 ? 'var(--warn)' : 'var(--fg-strong)'}">
        {stats.tempMax != null ? stats.tempMax.toFixed(0) + '°C' : '—'}
      </span>
    </div>
    <div class="stack" style="gap:4px">
      <span class="text-eyebrow">평균 VRAM</span>
      <span class="text-mono tnum" style="font-size:18px;font-weight:600">{stats.vramAvg != null ? stats.vramAvg.toFixed(1) + '%' : '—'}</span>
    </div>
    <div class="stack" style="gap:4px">
      <span class="text-eyebrow">전력 한계</span>
      <span class="text-mono tnum" style="font-size:18px;font-weight:600">{g?.power_limit_watts != null ? g.power_limit_watts.toFixed(0) + ' W' : '—'}</span>
    </div>
  </div>
</section>

<!-- ===== Detail + Polling ===== -->
<section class="grid-2-detail">
  <div class="card">
    <div class="card-header">
      <div>
        <div class="card-eyebrow">GPU · 디바이스</div>
        <div class="card-title">하드웨어 상세</div>
      </div>
      <span class="pill success" style="padding:2px 8px"><span class="dot"></span>OK</span>
    </div>
    <table class="kv-table">
      <tbody>
        <tr><td>모델명</td><td class="text-mono">{g?.name ?? '—'}</td></tr>
        <tr><td>디바이스 수</td><td class="text-mono tnum">{(gpu?.gpus?.length ?? 1)}개</td></tr>
        <tr><td>VRAM 총량</td><td class="text-mono tnum">{g?.memory_total_mib != null ? fmt.bytes(g.memory_total_mib) : '—'}</td></tr>
        <tr><td>VRAM 사용</td><td class="text-mono tnum">{g?.memory_used_mib != null ? fmt.bytes(g.memory_used_mib) : '—'}</td></tr>
        <tr><td>전력 한계</td><td class="text-mono tnum">{g?.power_limit_watts != null ? g.power_limit_watts.toFixed(0) + ' W' : '—'}</td></tr>
        <tr><td>실측 전력</td><td class="text-mono tnum">
          {g?.power_draw_available && g?.power_draw_watts != null ? g.power_draw_watts.toFixed(0) + ' W' : '실측 불가'}
        </td></tr>
        <tr><td>API 갱신 (KST)</td><td class="text-mono tnum">{gpu?.generated_at ? fmt.kst(gpu.generated_at) : '—'}</td></tr>
      </tbody>
    </table>
    {#if !g?.power_draw_available}
      <div class="text-caption" style="margin-top:8px">
        nvidia-smi 가 현재 환경에서 power draw 를 보고하지 않습니다. 추정값은 표시하지 않습니다.
      </div>
    {/if}
  </div>

  <div class="card">
    <div class="card-header">
      <div>
        <div class="card-eyebrow">FLASK · :5070</div>
        <div class="card-title">대시보드 폴링 상태</div>
      </div>
      <span class="pill success" style="padding:2px 8px"><span class="dot"></span>up</span>
    </div>
    <table class="kv-table">
      <tbody>
        <tr><td>폴링 간격</td><td class="text-mono tnum">{sec} 초</td></tr>
        <tr><td>GPU ring buffer</td><td class="text-mono tnum">{ring.length} / 720 points</td></tr>
        <tr><td>CPU/RAM endpoint</td><td class="text-mono">/api/training/system</td></tr>
        <tr><td>버퍼 시간</td><td class="text-mono tnum">{fmt.durationCompact(ring.length * sec)}</td></tr>
        <tr><td>마지막 화면 갱신</td><td class="text-mono tnum">{last}</td></tr>
        <tr><td>Artifacts 폴링</td><td class="text-mono">30 초 (고정)</td></tr>
        <tr><td>대시보드 모드</td><td class="text-mono">official dist (default)</td></tr>
      </tbody>
    </table>
    <div class="card compact flat" style="background:var(--surface-sunken);border:none;padding:12px;gap:8px;border-radius:12px;margin-top:8px">
      <div class="row" style="gap:8px"><span class="pill success" style="padding:2px 8px"><span class="dot"></span>CPU/RAM 활성</span><span class="text-caption">디스크 측정은 후속 단계</span></div>
      <p class="text-caption" style="line-height:1.5;margin:0">
        CPU 사용률과 RAM 사용률은 현재 노출됩니다. CPU 온도는 Windows/메인보드 센서가 OS에 값을 제공하지 않으면 미측정으로 표시합니다.
      </p>
    </div>
  </div>
</section>

<style>
  .page-hero { padding: 8px 0; }
  .grid-4-kpi {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 16px;
  }
  .grid-2-detail {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }
  @media (max-width: 900px) {
    .grid-4-kpi { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .grid-2-detail { grid-template-columns: 1fr; }
  }
  @media (max-width: 560px) {
    .grid-4-kpi { grid-template-columns: 1fr; }
  }
  .kv-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  .kv-table tbody tr {
    border-bottom: 1px solid var(--border-faint);
  }
  .kv-table tbody tr:last-child {
    border-bottom: none;
  }
  .kv-table td {
    padding: 10px 0;
  }
  .kv-table td:first-child {
    color: var(--muted);
    width: 40%;
  }
  .kv-table td:last-child {
    color: var(--fg-strong);
    text-align: right;
    font-weight: 600;
  }
</style>
