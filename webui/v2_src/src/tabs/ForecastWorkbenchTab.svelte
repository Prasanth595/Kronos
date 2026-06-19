<script lang="ts">
  import { onMount } from 'svelte';
  import { fmt } from '$lib/format';
  import { ICONS } from '$lib/icons';
  import EChartsRenderer from '../charts/EChartsRenderer.svelte';
  import { theme } from '$lib/stores';

  // ── 모델 / 데이터 카탈로그 ──────────────────────────────────────
  let availableModels = $state<any>({});
  let modelAvailable = $state<boolean | null>(null);
  let modelImportError = $state<string | null>(null);
  let dataFiles = $state<any[]>([]);
  let selectedModel = $state<string>('');
  let selectedDataFile = $state<string>('');
  let modelLoaded = $state(false);
  let dataLoaded = $state(false);
  let currentModelLabel = $state<string>('');
  let currentDataLabel = $state<string>('');

  // 슬라이더 상태 (v1 메인 화면 기본값과 일치)
  let lookback = $state(400);
  let predLen = $state(120);
  let temperature = $state(1.0);
  let topP = $state(0.9);
  let nSamples = $state(1);
  let seedFixed = $state(true);
  let seed = $state(42);

  // 디바이스 (학습 중 GPU 옵션 잠금 — 현재 학습 없으므로 cpu 기본)
  let device = $state<'cpu' | 'cuda'>('cpu');

  // 예측 결과
  let predicting = $state(false);
  let predictionResult = $state<any>(null);
  let predictionError = $state<string | null>(null);
  let loadingModel = $state(false);
  let loadingData = $state(false);
  let loadError = $state<string | null>(null);

  let currentTheme = $state<'light' | 'dark'>('light');
  theme.subscribe((v) => (currentTheme = v));

  async function loadAvailableModels() {
    try {
      const r = await fetch('/api/available-models');
      if (!r.ok) return;
      const d = await r.json();
      availableModels = d.models ?? {};
      modelAvailable = !!d.model_available;
      modelImportError = d.model_import_error;
      const keys = Object.keys(availableModels);
      if (keys.length > 0 && !selectedModel) selectedModel = keys[0];
    } catch (e) {
      modelAvailable = false;
    }
  }

  async function loadDataFiles() {
    try {
      const r = await fetch('/api/data-files');
      if (!r.ok) return;
      const d = await r.json();
      dataFiles = Array.isArray(d) ? d : Array.isArray(d.files) ? d.files : [];
      if (dataFiles.length > 0 && !selectedDataFile) {
        const first = dataFiles[0];
        selectedDataFile = typeof first === 'string' ? first : (first.path ?? first.name ?? '');
      }
    } catch {}
  }

  onMount(() => {
    loadAvailableModels();
    loadDataFiles();
  });

  async function loadModelAction() {
    if (!selectedModel || loadingModel) return;
    loadingModel = true;
    loadError = null;
    try {
      const r = await fetch('/api/load-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_key: selectedModel, device }),
      });
      const d = await r.json();
      if (!r.ok || d.success === false) {
        loadError = d?.error ?? d?.message ?? `HTTP ${r.status}`;
        modelLoaded = false;
      } else {
        modelLoaded = true;
        currentModelLabel = availableModels[selectedModel]?.name ?? selectedModel;
      }
    } catch (e: any) {
      loadError = e?.message ?? '모델 로드 실패';
    } finally {
      loadingModel = false;
    }
  }

  async function loadDataAction() {
    if (!selectedDataFile || loadingData) return;
    loadingData = true;
    loadError = null;
    try {
      const r = await fetch('/api/load-data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: selectedDataFile }),
      });
      const d = await r.json();
      if (!r.ok || d.success === false) {
        loadError = d?.error ?? d?.message ?? `HTTP ${r.status}`;
        dataLoaded = false;
      } else {
        dataLoaded = true;
        currentDataLabel = selectedDataFile.split(/[/\\]/).pop() ?? selectedDataFile;
      }
    } catch (e: any) {
      loadError = e?.message ?? '데이터 로드 실패';
    } finally {
      loadingData = false;
    }
  }

  async function runPredict() {
    if (predicting) return;
    predicting = true;
    predictionError = null;
    try {
      const r = await fetch('/api/predict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lookback,
          pred_len: predLen,
          temperature,
          top_p: topP,
          n_samples: nSamples,
          seed: seedFixed ? seed : null,
          device,
        }),
      });
      const d = await r.json();
      if (!r.ok || d.success === false) {
        predictionError = d?.error ?? d?.message ?? `HTTP ${r.status}`;
        return;
      }
      predictionResult = d;
    } catch (e: any) {
      predictionError = e?.message ?? '예측 실행 실패';
    } finally {
      predicting = false;
    }
  }

  // 결과 차트 옵션
  let chartOption = $derived.by(() => {
    void currentTheme;
    if (!predictionResult || typeof window === 'undefined') return {};
    const cs = getComputedStyle(document.documentElement);
    const accent = cs.getPropertyValue('--accent').trim();
    const c2 = cs.getPropertyValue('--c-2').trim();
    const c4 = cs.getPropertyValue('--c-4').trim();
    const grid = cs.getPropertyValue('--border-faint').trim();
    const text = cs.getPropertyValue('--fg').trim();
    const dim = cs.getPropertyValue('--dim').trim();
    const surface = cs.getPropertyValue('--surface').trim();

    // 응답 구조 추정: predictionResult.actual / .predicted / .historical 등 다양한 변형 대응
    const hist = predictionResult.historical ?? predictionResult.history ?? predictionResult.input ?? [];
    const pred = predictionResult.predicted ?? predictionResult.prediction ?? predictionResult.forecast ?? [];
    const actual = predictionResult.actual ?? predictionResult.truth ?? [];

    const histSeries = hist.map((p: any, i: number) => [
      typeof p === 'object' ? (p.timestamp ?? p.time ?? p.date ?? i) : i,
      typeof p === 'object' ? (p.close ?? p.value ?? p.y ?? p) : p,
    ]);
    const predSeries = pred.map((p: any, i: number) => [
      typeof p === 'object' ? (p.timestamp ?? p.time ?? p.date ?? hist.length + i) : hist.length + i,
      typeof p === 'object' ? (p.close ?? p.value ?? p.y ?? p) : p,
    ]);
    const actualSeries = actual.map((p: any, i: number) => [
      typeof p === 'object' ? (p.timestamp ?? p.time ?? p.date ?? hist.length + i) : hist.length + i,
      typeof p === 'object' ? (p.close ?? p.value ?? p.y ?? p) : p,
    ]);

    return {
      backgroundColor: 'transparent',
      textStyle: { color: text, fontFamily: 'Pretendard Variable, sans-serif' },
      grid: { left: 56, right: 24, top: 24, bottom: 36 },
      xAxis: {
        type: 'category',
        axisLabel: { color: dim, fontSize: 10 },
        splitLine: { lineStyle: { color: grid } },
        axisLine: { lineStyle: { color: grid } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: dim, fontSize: 10 },
        splitLine: { lineStyle: { color: grid } },
        axisLine: { show: false },
      },
      tooltip: { trigger: 'axis', backgroundColor: surface, borderColor: grid, textStyle: { color: text, fontSize: 12 } },
      legend: { textStyle: { color: dim, fontSize: 11 }, icon: 'roundRect' },
      series: [
        { name: '입력 (lookback)', type: 'line', data: histSeries, smooth: 0.3, symbol: 'none', lineStyle: { color: c2, width: 1.5 } },
        { name: '예측', type: 'line', data: predSeries, smooth: 0.3, symbol: 'none', lineStyle: { color: accent, width: 2, type: 'solid' } },
        ...(actualSeries.length > 0 ? [{ name: '실측', type: 'line', data: actualSeries, smooth: 0.3, symbol: 'none', lineStyle: { color: c4, width: 1.5, type: 'dashed' as const } }] : []),
      ],
    };
  });
</script>

<section class="page-hero">
  <div class="row" style="gap:10px;flex-wrap:wrap">
    <span class="text-eyebrow">본격</span>
    <span class="pill {modelAvailable === true ? 'success' : modelAvailable === false ? 'warn' : ''}">
      <span class="dot"></span>
      {modelAvailable === true ? '모델 라이브러리 사용 가능' : modelAvailable === false ? '모델 라이브러리 미가용 (시뮬레이션)' : '확인 중'}
    </span>
    <span class="pill"><span class="dot" style="background:var(--info)"></span>/api/predict · POST</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">예측 워크벤치</h1>
  <p class="text-muted" style="margin-top:6px">
    사전학습 Kronos 모델로 K-line 시계열 예측을 실행합니다. 예측기(predictor) 학습 완료 전에는 base/small/mini 사전학습 weight 가 적용됩니다.
    Seed 고정 시 동일 파라미터에 대해 결정성이 보장됩니다.
  </p>
  {#if modelImportError}
    <div class="card compact flat" style="background:var(--warn-soft);border-color:transparent;margin-top:10px;padding:10px 14px">
      <span class="text-caption">⚠ {modelImportError}</span>
    </div>
  {/if}
</section>

<!-- ===== Setup: 모델 + 데이터 ===== -->
<section class="grid-2-setup">
  <div class="card">
    <div class="card-header">
      <div>
        <div class="card-eyebrow">MODEL · 사전학습 weight</div>
        <div class="card-title">모델 선택 / 로드</div>
      </div>
      {#if modelLoaded}
        <span class="pill success"><span class="dot"></span>{currentModelLabel}</span>
      {:else}
        <span class="pill"><span class="dot"></span>미로드</span>
      {/if}
    </div>
    <select
      class="fw-select"
      bind:value={selectedModel}
      disabled={Object.keys(availableModels).length === 0}
    >
      {#each Object.entries(availableModels) as [key, m]}
        {@const meta = m as any}
        <option value={key}>{meta.name ?? key} · {meta.params ?? '?'} · ctx {meta.context_length ?? '?'}</option>
      {/each}
    </select>
    {#if selectedModel && availableModels[selectedModel]}
      <div class="text-caption" style="margin-top:8px;line-height:1.5">
        {availableModels[selectedModel].description}
      </div>
    {/if}
    <div class="row" style="gap:8px;margin-top:12px">
      <button class="btn primary" disabled={!selectedModel || loadingModel} onclick={loadModelAction}>
        {loadingModel ? '로드 중…' : '모델 로드'}
      </button>
      <select class="fw-select" bind:value={device} style="max-width:120px">
        <option value="cpu">CPU</option>
        <option value="cuda">GPU (CUDA)</option>
      </select>
    </div>
  </div>

  <div class="card">
    <div class="card-header">
      <div>
        <div class="card-eyebrow">DATA · 입력 시계열</div>
        <div class="card-title">데이터 파일 선택 / 로드</div>
      </div>
      {#if dataLoaded}
        <span class="pill success"><span class="dot"></span>{currentDataLabel}</span>
      {:else}
        <span class="pill"><span class="dot"></span>미로드</span>
      {/if}
    </div>
    {#if dataFiles.length === 0}
      <div class="text-caption">로드 가능한 데이터 파일이 없습니다</div>
    {:else}
      <select class="fw-select" bind:value={selectedDataFile}>
        {#each dataFiles as f}
          {@const path = typeof f === 'string' ? f : (f.path ?? f.name ?? '')}
          {@const label = path.split(/[/\\]/).pop()}
          <option value={path}>{label}</option>
        {/each}
      </select>
      <div class="text-caption" style="margin-top:8px">{selectedDataFile}</div>
    {/if}
    <div class="row" style="gap:8px;margin-top:12px">
      <button class="btn primary" disabled={!selectedDataFile || loadingData} onclick={loadDataAction}>
        {loadingData ? '로드 중…' : '데이터 로드'}
      </button>
    </div>
  </div>
</section>

{#if loadError}
  <div class="card" style="border-color:var(--danger-soft);background:var(--danger-soft)">
    <div class="text-caption" style="color:var(--danger);font-weight:600">⚠ {loadError}</div>
  </div>
{/if}

<!-- ===== Sliders ===== -->
<section class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">PARAMETERS · sampling</div>
      <div class="card-title">예측 파라미터</div>
    </div>
    <span class="pill"><span class="dot" style="background:var(--info)"></span>seed {seedFixed ? `고정 ${seed}` : '랜덤'}</span>
  </div>
  <div class="grid-2-params">
    <div class="param-row">
      <div class="row spread">
        <label for="lookback" class="lbl-sm">Lookback (입력 길이)</label>
        <span class="text-mono tnum" style="font-weight:600">{lookback}</span>
      </div>
      <input id="lookback" type="range" min="64" max="512" step="32" bind:value={lookback} />
      <div class="text-caption">최근 {lookback} step 의 캔들을 입력으로 사용</div>
    </div>
    <div class="param-row">
      <div class="row spread">
        <label for="pred_len" class="lbl-sm">Pred Length (예측 길이)</label>
        <span class="text-mono tnum" style="font-weight:600">{predLen}</span>
      </div>
      <input id="pred_len" type="range" min="10" max="240" step="10" bind:value={predLen} />
      <div class="text-caption">앞으로 {predLen} step 의 캔들을 예측</div>
    </div>
    <div class="param-row">
      <div class="row spread">
        <label for="temperature" class="lbl-sm">Temperature (다양성)</label>
        <span class="text-mono tnum" style="font-weight:600">{temperature.toFixed(2)}</span>
      </div>
      <input id="temperature" type="range" min="0.1" max="2.0" step="0.05" bind:value={temperature} />
      <div class="text-caption">낮을수록 보수적 · 높을수록 다양한 시나리오 생성</div>
    </div>
    <div class="param-row">
      <div class="row spread">
        <label for="top_p" class="lbl-sm">Top-P (누클리어스)</label>
        <span class="text-mono tnum" style="font-weight:600">{topP.toFixed(2)}</span>
      </div>
      <input id="top_p" type="range" min="0.1" max="1.0" step="0.05" bind:value={topP} />
      <div class="text-caption">누적 확률 {topP.toFixed(2)} 미만의 토큰만 샘플링</div>
    </div>
  </div>

  <div class="row" style="gap:16px;flex-wrap:wrap;border-top:1px solid var(--border-faint);padding-top:14px;margin-top:8px">
    <label class="row" style="gap:6px;cursor:pointer">
      <input type="checkbox" bind:checked={seedFixed} />
      <span class="text-caption">Seed 고정 (결정성)</span>
    </label>
    {#if seedFixed}
      <label class="row" style="gap:6px">
        <span class="text-caption">SEED</span>
        <input type="number" bind:value={seed} class="fw-input-num" min="0" max="2147483647" />
      </label>
    {/if}
    <button
      class="btn primary lg"
      style="margin-left:auto;min-width:160px"
      disabled={!modelLoaded || !dataLoaded || predicting}
      onclick={runPredict}
    >
      {#if predicting}
        예측 실행 중…
      {:else}
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">{@html ICONS.play}</svg>
        예측 실행
      {/if}
    </button>
  </div>

  {#if !modelLoaded || !dataLoaded}
    <div class="text-caption" style="margin-top:8px;color:var(--muted)">
      💡 예측 실행을 위해서는 모델과 데이터를 먼저 로드해야 합니다.
    </div>
  {/if}
</section>

<!-- ===== Results ===== -->
{#if predictionError}
  <div class="card" style="border-color:var(--danger-soft)">
    <div class="card-header">
      <div class="card-title" style="color:var(--danger)">예측 실패</div>
      <span class="pill danger"><span class="dot"></span>오류</span>
    </div>
    <div class="text-caption" style="white-space:pre-wrap">{predictionError}</div>
  </div>
{:else if predictionResult}
  <section class="card">
    <div class="card-header">
      <div>
        <div class="card-eyebrow">RESULT · /api/predict</div>
        <div class="card-title">예측 결과</div>
      </div>
      <div class="row" style="gap:8px">
        <span class="pill success"><span class="dot"></span>완료</span>
        {#if predictionResult.elapsed_seconds != null}
          <span class="pill"><span class="dot"></span>{predictionResult.elapsed_seconds.toFixed(2)}s</span>
        {/if}
      </div>
    </div>
    <EChartsRenderer option={chartOption} height="380px" />
    {#if predictionResult.metrics}
      <div class="row" style="gap:24px;border-top:1px solid var(--border-faint);padding-top:14px;margin-top:8px;flex-wrap:wrap">
        {#each Object.entries(predictionResult.metrics) as [k, v]}
          <div class="stack" style="gap:4px">
            <span class="text-eyebrow">{k}</span>
            <span class="text-mono tnum" style="font-size:18px;font-weight:600">
              {typeof v === 'number' ? (v as number).toFixed(4) : String(v)}
            </span>
          </div>
        {/each}
      </div>
    {/if}
  </section>
{/if}

<style>
  .page-hero { padding: 8px 0; }
  .grid-2-setup {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }
  .grid-2-params {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px 32px;
  }
  @media (max-width: 900px) {
    .grid-2-setup, .grid-2-params { grid-template-columns: 1fr; }
  }
  .fw-select {
    width: 100%;
    padding: 10px 12px;
    border-radius: var(--r-sm);
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--fg);
    font: 500 13px/1.3 var(--font-mono);
    cursor: pointer;
  }
  .fw-select:focus { border-color: var(--accent); outline: none; }
  .fw-input-num {
    width: 100px;
    padding: 6px 10px;
    border-radius: var(--r-sm);
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--fg);
    font: 500 12px/1.3 var(--font-mono);
  }
  .lbl-sm {
    font: 600 12px/1.3 var(--font-display);
    color: var(--fg-strong);
  }
  .param-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .param-row input[type="range"] {
    -webkit-appearance: none;
    width: 100%;
    height: 6px;
    background: var(--surface-sunken);
    border-radius: var(--r-pill);
    outline: none;
  }
  .param-row input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    border: 2px solid var(--surface);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  }
  .param-row input[type="range"]::-moz-range-thumb {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    border: 2px solid var(--surface);
  }
</style>
