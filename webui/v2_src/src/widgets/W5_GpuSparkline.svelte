<script lang="ts">
  import EChartsRenderer from '../charts/EChartsRenderer.svelte';
  import { gpuRing, gpuStatus, systemRing, systemStatus, theme } from '$lib/stores';
  import { fmt } from '$lib/format';

  let ring = $state<any[]>([]);
  gpuRing.subscribe((v) => (ring = v));

  let gpu = $state<any>(null);
  gpuStatus.subscribe((v) => (gpu = v));

  let hostRing = $state<any[]>([]);
  systemRing.subscribe((v) => (hostRing = v));

  let system = $state<any>(null);
  systemStatus.subscribe((v) => (system = v));

  let currentTheme = $state<'light' | 'dark'>('light');
  theme.subscribe((v) => (currentTheme = v));

  let g = $derived(gpu?.gpus?.[0]);
  let cpu = $derived(system?.cpu ?? null);
  let memory = $derived(system?.memory ?? null);

  type GpuTrendPoint = {
    util: number | null;
    temp: number | null;
    vram: number | null;
    ts: number;
  };

  type SystemTrendPoint = {
    cpuUtil: number | null;
    cpuTemp: number | null;
    cpuTempPct: number | null;
    ram: number | null;
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

  function currentSystemPoint(): SystemTrendPoint | null {
    if (!cpu && !memory) return null;
    return {
      cpuUtil: cpu?.utilization_percent ?? null,
      cpuTemp: cpu?.temperature_c ?? null,
      cpuTempPct: cpu?.temperature_percent ?? null,
      ram: memory?.used_percent ?? null,
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

  function seriesValue(value: any): number | null {
    const raw = Array.isArray(value) ? value[1] : value;
    if (raw == null || Number.isNaN(Number(raw))) return null;
    return Number(raw);
  }

  function seriesTs(value: any): number | null {
    const raw = Array.isArray(value) ? value[0] : null;
    if (raw == null || Number.isNaN(Number(raw))) return null;
    return Number(raw);
  }

  function formatGpuTooltip(params: any): string {
    const rows = Array.isArray(params) ? params : [params];
    const ts = seriesTs(rows[0]?.value);
    const body = rows
      .map((p: any) => {
        const value = seriesValue(p.value);
        if (value == null) return '';
        const unit = p.seriesName?.includes('온도') ? '°C' : '%';
        return `<div style="display:flex;gap:10px;justify-content:space-between;min-width:170px">
          <span>${p.marker ?? ''}${p.seriesName}</span>
          <b>${value.toFixed(1)}${unit}</b>
        </div>`;
      })
      .filter(Boolean)
      .join('');
    return `<div style="font-weight:700;margin-bottom:4px">${formatTime(ts)}</div>${body}`;
  }

  let chartGpuRing = $derived.by(() => {
    if (ring.length > 0) return ring as GpuTrendPoint[];
    const point = currentGpuPoint();
    return point ? [point] : [];
  });

  let chartSystemRing = $derived.by(() => {
    if (hostRing.length > 0) return hostRing as SystemTrendPoint[];
    const point = currentSystemPoint();
    return point ? [point] : [];
  });

  let chartLatestTs = $derived.by(() => {
    const timestamps = [...chartGpuRing, ...chartSystemRing].map((p) => p.ts).filter(Boolean);
    return timestamps.length ? Math.max(...timestamps) : null;
  });

  let palette = $derived.by(() => {
    void currentTheme;
    if (typeof window === 'undefined') return null;
    const cs = getComputedStyle(document.documentElement);
    return {
      c2: cs.getPropertyValue('--c-2').trim() || '#3b82f6',
      c3: cs.getPropertyValue('--c-3').trim() || '#eab308',
      c4: cs.getPropertyValue('--c-4').trim() || '#f97316',
      cpu: cs.getPropertyValue('--info').trim() || '#06b6d4',
      cpuTemp: cs.getPropertyValue('--danger').trim() || '#ef4444',
      ram: cs.getPropertyValue('--success').trim() || '#22c55e',
      grid: cs.getPropertyValue('--border-faint').trim() || '#e2e8f0',
      border: cs.getPropertyValue('--border').trim() || '#cbd5e1',
      text: cs.getPropertyValue('--fg').trim() || '#1e293b',
      textDim: cs.getPropertyValue('--dim').trim() || '#64748b',
      surface: cs.getPropertyValue('--surface').trim() || '#ffffff',
    };
  });

  let option = $derived.by(() => {
    void currentTheme;
    if (!palette) return {};
    const gpuData = chartGpuRing;
    const systemData = chartSystemRing;
    const dataAvailable = gpuData.length > 0 || systemData.length > 0;
    const showSymbols = Math.max(gpuData.length, systemData.length) <= 2;
    return {
      backgroundColor: 'transparent',
      textStyle: { color: palette.text, fontFamily: 'Pretendard Variable, sans-serif' },
      grid: { left: 40, right: 24, top: 22, bottom: 32 },
      xAxis: {
        type: 'time',
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
        formatter: (params: any) => formatGpuTooltip(params),
      },
      graphic: !dataAvailable ? [{
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
        { name: 'GPU 사용률 %', type: 'line', smooth: 0.5, symbol: 'circle', showSymbol: showSymbols, symbolSize: 5, data: gpuData.map((p) => [p.ts, p.util]), lineStyle: { color: palette.c3, width: 1.8 } },
        { name: 'VRAM %',       type: 'line', smooth: 0.5, symbol: 'circle', showSymbol: showSymbols, symbolSize: 5, data: gpuData.map((p) => [p.ts, p.vram]), lineStyle: { color: palette.c2, width: 1.8 } },
        { name: 'GPU 온도 °C',  type: 'line', smooth: 0.5, symbol: 'circle', showSymbol: showSymbols, symbolSize: 5, data: gpuData.map((p) => [p.ts, p.temp]), lineStyle: { color: palette.c4, width: 1.8 } },
        { name: 'CPU 사용률 %', type: 'line', smooth: 0.35, symbol: 'circle', showSymbol: showSymbols, symbolSize: 5, data: systemData.map((p) => [p.ts, p.cpuUtil]), lineStyle: { color: palette.cpu, width: 1.7, type: 'dashed' } },
        { name: 'CPU 온도 °C',  type: 'line', smooth: 0.35, symbol: 'circle', showSymbol: showSymbols, symbolSize: 5, data: systemData.map((p) => [p.ts, p.cpuTemp]), lineStyle: { color: palette.cpuTemp, width: 1.7, type: 'dashed' } },
      ],
    };
  });

  // 도넛형 미니 표시기 (Hero 와 유사하나 더 작음)
  function donutDash(pct: number | null | undefined, max: number = 100): string {
    if (pct == null) return '0 264';
    const ratio = Math.max(0, Math.min(1, pct / max));
    return `${ratio * 264} 264`;
  }

  function formatPct(value: number | null | undefined, digits = 0): string {
    return value == null ? '—' : `${fmt.num(value, digits)}%`;
  }

  function formatTemp(value: number | null | undefined): string {
    return value == null ? '미측정' : `${fmt.num(value, 1)}°C`;
  }

  function formatCpuThermal(): string {
    if (cpu?.temperature_percent != null) return `${fmt.num(cpu.temperature_percent, 0)}%`;
    if (cpu?.temperature_limit_c != null && cpu?.temperature_c != null) {
      return `${fmt.num((cpu.temperature_c / cpu.temperature_limit_c) * 100, 0)}%`;
    }
    return '미측정';
  }
</script>

<div class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">W5 · /api/training/gpu + /api/training/system</div>
      <div class="card-title">{g?.name ?? 'GPU'} · GPU/CPU 실시간 트렌드</div>
    </div>
    <div class="row" style="gap:8px;flex-wrap:wrap">
      <span class="pill">
        <span class="dot" style="background:{g?.power_draw_available ? 'var(--success)' : 'var(--muted)'}"></span>
        전원 {g?.power_draw_available ? '실측 OK' : '실측 불가'}
      </span>
      <span class="pill info">
        CPU {formatPct(cpu?.utilization_percent)} · 온도 {formatTemp(cpu?.temperature_c)}
      </span>
    </div>
  </div>

  <div class="row" style="gap:16px;flex-wrap:wrap">
    <span class="legend"><span class="swatch" style="background:var(--c-3)"></span>GPU 사용률 %</span>
    <span class="legend"><span class="swatch" style="background:var(--c-2)"></span>VRAM %</span>
    <span class="legend"><span class="swatch" style="background:var(--c-4)"></span>GPU 온도 °C</span>
    <span class="legend"><span class="swatch dashed" style="background:var(--info)"></span>CPU 사용률 %</span>
    <span class="legend"><span class="swatch dashed" style="background:var(--danger)"></span>CPU 온도 °C</span>
    <span style="margin-left:auto" class="text-caption">버퍼 GPU {ring.length} / CPU {hostRing.length} · 최신 {formatTime(chartLatestTs)}</span>
  </div>

  <EChartsRenderer {option} height="240px" />

  <div class="resource-mini-grid">
    <div class="stack" style="gap:8px;align-items:center">
      <svg viewBox="0 0 100 100" width="84" height="84" aria-hidden="true">
        <circle cx="50" cy="50" r="42" fill="none" stroke="var(--border-faint)" stroke-width="9" />
        <circle
          cx="50" cy="50" r="42"
          fill="none"
          stroke="var(--c-3)"
          stroke-width="9"
          stroke-linecap="round"
          stroke-dasharray={donutDash(g?.utilization_gpu_percent)}
          transform="rotate(-90 50 50)"
          style="transition:stroke-dasharray 300ms ease"
        />
        <text x="50" y="54" text-anchor="middle" font-family="var(--font-mono)" font-size="18" font-weight="700" fill="var(--fg-strong)">
          {g?.utilization_gpu_percent != null ? Math.round(g.utilization_gpu_percent) + '%' : '—'}
        </text>
      </svg>
      <span class="text-caption">GPU 사용률</span>
    </div>
    <div class="stack" style="gap:8px;align-items:center">
      <svg viewBox="0 0 100 100" width="84" height="84" aria-hidden="true">
        <circle cx="50" cy="50" r="42" fill="none" stroke="var(--border-faint)" stroke-width="9" />
        <circle
          cx="50" cy="50" r="42"
          fill="none"
          stroke="var(--c-4)"
          stroke-width="9"
          stroke-linecap="round"
          stroke-dasharray={donutDash(g?.temperature_c, 90)}
          transform="rotate(-90 50 50)"
          style="transition:stroke-dasharray 300ms ease"
        />
        <text x="50" y="54" text-anchor="middle" font-family="var(--font-mono)" font-size="18" font-weight="700" fill="var(--fg-strong)">
          {g?.temperature_c != null ? Math.round(g.temperature_c) + '°' : '—'}
        </text>
      </svg>
      <span class="text-caption">GPU 온도</span>
    </div>
    <div class="stack" style="gap:8px;align-items:center">
      <svg viewBox="0 0 100 100" width="84" height="84" aria-hidden="true">
        <circle cx="50" cy="50" r="42" fill="none" stroke="var(--border-faint)" stroke-width="9" />
        <circle
          cx="50" cy="50" r="42"
          fill="none"
          stroke="var(--c-2)"
          stroke-width="9"
          stroke-linecap="round"
          stroke-dasharray={donutDash(g?.memory_used_percent)}
          transform="rotate(-90 50 50)"
          style="transition:stroke-dasharray 300ms ease"
        />
        <text x="50" y="54" text-anchor="middle" font-family="var(--font-mono)" font-size="18" font-weight="700" fill="var(--fg-strong)">
          {g?.memory_used_percent != null ? Math.round(g.memory_used_percent) + '%' : '—'}
        </text>
      </svg>
      <span class="text-caption">VRAM</span>
    </div>
    <div class="stack" style="gap:8px;align-items:center">
      <svg viewBox="0 0 100 100" width="84" height="84" aria-hidden="true">
        <circle cx="50" cy="50" r="42" fill="none" stroke="var(--border-faint)" stroke-width="9" />
        <circle
          cx="50" cy="50" r="42"
          fill="none"
          stroke="var(--info)"
          stroke-width="9"
          stroke-linecap="round"
          stroke-dasharray={donutDash(cpu?.utilization_percent)}
          transform="rotate(-90 50 50)"
          style="transition:stroke-dasharray 300ms ease"
        />
        <text x="50" y="54" text-anchor="middle" font-family="var(--font-mono)" font-size="18" font-weight="700" fill="var(--fg-strong)">
          {cpu?.utilization_percent != null ? Math.round(cpu.utilization_percent) + '%' : '—'}
        </text>
      </svg>
      <span class="text-caption">CPU 사용률</span>
    </div>
    <div class="stack" style="gap:8px;align-items:center">
      <svg viewBox="0 0 100 100" width="84" height="84" aria-hidden="true">
        <circle cx="50" cy="50" r="42" fill="none" stroke="var(--border-faint)" stroke-width="9" />
        <circle
          cx="50" cy="50" r="42"
          fill="none"
          stroke="var(--danger)"
          stroke-width="9"
          stroke-linecap="round"
          stroke-dasharray={donutDash(cpu?.temperature_percent ?? cpu?.temperature_c, cpu?.temperature_percent != null ? 100 : 95)}
          transform="rotate(-90 50 50)"
          style="transition:stroke-dasharray 300ms ease"
        />
        <text x="50" y="54" text-anchor="middle" font-family="var(--font-mono)" font-size="16" font-weight="700" fill="var(--fg-strong)">
          {cpu?.temperature_c != null ? Math.round(cpu.temperature_c) + '°' : '—'}
        </text>
      </svg>
      <span class="text-caption">CPU 온도</span>
    </div>
  </div>

  {#if g?.memory_used_mib != null && g?.memory_total_mib != null}
    <div class="text-caption resource-caption">
      VRAM 사용 <span class="text-mono" style="color:var(--fg);font-weight:600">{fmt.bytes(g.memory_used_mib)} / {fmt.bytes(g.memory_total_mib)}</span>
      {#if g.power_limit_watts}
        · 전력 한계 <span class="text-mono" style="color:var(--fg);font-weight:600">{g.power_limit_watts.toFixed(0)} W</span>
      {/if}
      · CPU 온도 {formatTemp(cpu?.temperature_c)}
      · CPU 열한도 {formatCpuThermal()}
      {#if memory?.used_percent != null}
        · RAM <span class="text-mono" style="color:var(--fg);font-weight:600">{formatPct(memory.used_percent)}</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .resource-mini-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(110px, 1fr));
    gap: 14px;
    border-top: 1px solid var(--border-faint);
    padding-top: 14px;
    margin-top: 8px;
  }

  .swatch.dashed {
    border: 1px dashed color-mix(in oklch, currentColor 55%, transparent);
  }

  .resource-caption {
    margin-top: 8px;
    text-align: center;
    line-height: 1.65;
  }

  @media (max-width: 980px) {
    .resource-mini-grid {
      grid-template-columns: repeat(3, minmax(110px, 1fr));
    }
  }

  @media (max-width: 560px) {
    .resource-mini-grid {
      grid-template-columns: repeat(2, minmax(110px, 1fr));
    }
  }
</style>
