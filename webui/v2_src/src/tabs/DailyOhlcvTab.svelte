<script lang="ts">
  import { onMount } from 'svelte';
  import {
    dailyOhlcvApi,
    type DailyArtifactsResponse,
    type DailyDatasetChartResponse,
    type DailyDatasetResponse,
    type DailyDbSummaryResponse,
    type DailyModelChartResponse,
    type DailyPortfolioResponse,
    type DailyPredictionResponse,
    type DailyProgressResponse,
    type DailyRegistryResponse,
    type DailyScenarioLabResponse,
    type DailyScenarioRunLedgerResponse,
    type DailySymbolResponse,
    type DailyUniverseResponse,
    type DailyVisualChartResponse,
    type DailyWalkForwardResponse,
  } from '$lib/dailyOhlcvApi';
  import DailyProgressTimeline from './dailyOhlcv/DailyProgressTimeline.svelte';
  import DailyDbQualityCard from './dailyOhlcv/DailyDbQualityCard.svelte';
  import DailyUniverseCard from './dailyOhlcv/DailyUniverseCard.svelte';
  import DailyDatasetBuilderCard from './dailyOhlcv/DailyDatasetBuilderCard.svelte';
  import DailyModelResultsCard from './dailyOhlcv/DailyModelResultsCard.svelte';
  import DailyVisualLabCard from './dailyOhlcv/DailyVisualLabCard.svelte';
  import DailyScenarioLabCard from './dailyOhlcv/DailyScenarioLabCard.svelte';
  import DailyScenarioRunLedgerCard from './dailyOhlcv/DailyScenarioRunLedgerCard.svelte';

  let progress = $state<DailyProgressResponse | null>(null);
  let dbSummary = $state<DailyDbSummaryResponse | null>(null);
  let universe = $state<DailyUniverseResponse | null>(null);
  let artifacts = $state<DailyArtifactsResponse | null>(null);
  let dataset = $state<DailyDatasetResponse | null>(null);
  let datasetChart = $state<DailyDatasetChartResponse | null>(null);
  let prediction = $state<DailyPredictionResponse | null>(null);
  let portfolio = $state<DailyPortfolioResponse | null>(null);
  let walkForward = $state<DailyWalkForwardResponse | null>(null);
  let registry = $state<DailyRegistryResponse | null>(null);
  let predictionChart = $state<DailyModelChartResponse | null>(null);
  let portfolioChart = $state<DailyModelChartResponse | null>(null);
  let walkForwardChart = $state<DailyModelChartResponse | null>(null);
  let decisionCockpit = $state<DailyVisualChartResponse | null>(null);
  let scenarioLab = $state<DailyScenarioLabResponse | null>(null);
  let scenarioRuns = $state<DailyScenarioRunLedgerResponse | null>(null);
  let flowChart = $state<DailyVisualChartResponse | null>(null);
  let glossaryChart = $state<DailyVisualChartResponse | null>(null);
  let researchDiagnosticsChart = $state<DailyVisualChartResponse | null>(null);
  let equityOverlayChart = $state<DailyVisualChartResponse | null>(null);
  let walkForwardHeatmapChart = $state<DailyVisualChartResponse | null>(null);
  let runScatterChart = $state<DailyVisualChartResponse | null>(null);
  let universeBreakdownChart = $state<DailyVisualChartResponse | null>(null);
  let selectedSymbol = $state<DailySymbolResponse | null>(null);
  let selectedSymbolChart = $state<DailyVisualChartResponse | null>(null);
  let selectedSymbolError = $state<string | null>(null);
  let endpointErrors = $state<string[]>([]);
  let loading = $state(false);

  async function loadDailyOhlcv(): Promise<void> {
    loading = true;
    try {
      const [p, d, u, a, ds, dc, pred, port, wf, reg, predChart, portChart, wfChart, decision, scenarios, scenarioRunsResult, flow, glossary, diagnostics, equity, heatmap, scatter, universeBreakdown] = await Promise.all([
        dailyOhlcvApi.progress(),
        dailyOhlcvApi.dbSummary(),
        dailyOhlcvApi.universePreview(),
        dailyOhlcvApi.artifacts(),
        dailyOhlcvApi.datasetLatest(),
        dailyOhlcvApi.datasetChart(),
        dailyOhlcvApi.predictionLatest(),
        dailyOhlcvApi.portfolioLatest(),
        dailyOhlcvApi.walkForwardLatest(),
        dailyOhlcvApi.registryLatest(),
        dailyOhlcvApi.predictionChart(),
        dailyOhlcvApi.portfolioChart(),
        dailyOhlcvApi.walkForwardChart(),
        dailyOhlcvApi.decisionCockpitChart(),
        dailyOhlcvApi.scenarios(),
        dailyOhlcvApi.scenarioRuns(),
        dailyOhlcvApi.flowChart(),
        dailyOhlcvApi.glossaryChart(),
        dailyOhlcvApi.researchDiagnosticsChart(),
        dailyOhlcvApi.equityOverlayChart(),
        dailyOhlcvApi.walkForwardHeatmapChart(),
        dailyOhlcvApi.runScatterChart(),
        dailyOhlcvApi.universeBreakdownChart(),
      ]);
      const resolved = [
        ['progress', p],
        ['db-summary', d],
        ['universe', u],
        ['artifacts', a],
        ['dataset', ds],
        ['dataset-chart', dc],
        ['prediction', pred],
        ['portfolio', port],
        ['walk-forward', wf],
        ['registry', reg],
        ['prediction-chart', predChart],
        ['portfolio-chart', portChart],
        ['walk-forward-chart', wfChart],
        ['decision-cockpit', decision],
        ['scenarios', scenarios],
        ['scenario-runs', scenarioRunsResult],
        ['flow-chart', flow],
        ['glossary-chart', glossary],
        ['research-diagnostics', diagnostics],
        ['equity-overlay', equity],
        ['walk-forward-heatmap', heatmap],
        ['run-scatter', scatter],
        ['universe-breakdown', universeBreakdown],
      ] as const;
      endpointErrors = resolved.filter(([, payload]) => payload === null).map(([name]) => name);
      progress = p;
      dbSummary = d;
      universe = u;
      artifacts = a;
      dataset = ds;
      datasetChart = dc;
      prediction = pred;
      portfolio = port;
      walkForward = wf;
      registry = reg;
      predictionChart = predChart;
      portfolioChart = portChart;
      walkForwardChart = wfChart;
      decisionCockpit = decision;
      scenarioLab = scenarios;
      scenarioRuns = scenarioRunsResult;
      flowChart = flow;
      glossaryChart = glossary;
      researchDiagnosticsChart = diagnostics;
      equityOverlayChart = equity;
      walkForwardHeatmapChart = heatmap;
      runScatterChart = scatter;
      universeBreakdownChart = universeBreakdown;
    } finally {
      loading = false;
    }
  }

  async function loadSymbolDrilldown(code: string): Promise<void> {
    selectedSymbolError = null;
    const normalized = String(code ?? '').trim();
    if (!normalized) return;
    const [payload, chart] = await Promise.all([
      dailyOhlcvApi.symbol(normalized, 20),
      dailyOhlcvApi.symbolChart(normalized, 160),
    ]);
    if (payload) {
      selectedSymbol = payload;
      selectedSymbolChart = chart;
    } else {
      selectedSymbolChart = null;
      selectedSymbolError = `${normalized} 종목 상세를 불러오지 못했습니다.`;
    }
  }

  onMount(() => { void loadDailyOhlcv(); });
</script>

<section class="page-hero" data-daily-ohlcv-tab>
  <div class="row" style="gap:10px; flex-wrap:wrap">
    <span class="text-eyebrow">Daily OHLCV Research</span>
    <span class="pill warn"><span class="dot"></span>READ_ONLY · WATCH</span>
    <span class="pill"><span class="dot"></span>no live/broker/orders</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">일봉 기반 딥러닝·강화학습 준비 대시보드</h1>
  <p class="text-muted" style="margin-top:6px">
    현재 화면은 D0 DB 분석, D1 유니버스, D2 데이터셋, D3 예측 베이스라인, D4 포트폴리오 RL, D5 워크포워드/게이트, D6 시각화, D7 연구 진단, D8/D9 레지스트리·페이퍼 포워드 잠금 증거를 표시합니다. 수익 보장, 실거래, 주문, 브로커 준비 상태가 아니며 현재 모델 생성 GO가 아니라 NO-GO/RESEARCH_ONLY 상태를 그대로 노출합니다.
  </p>
  <div style="margin-top:12px">
    <button type="button" class="btn" onclick={() => void loadDailyOhlcv()} disabled={loading}>{loading ? '갱신 중…' : '새로고침'}</button>
  </div>
  {#if endpointErrors.length > 0}
    <div class="notice danger" data-daily-api-error style="margin-top:12px">
      API_UNAVAILABLE: {endpointErrors.join(', ')} · 데이터 없음(NOT_STARTED)과 API 실패를 분리합니다. decision locks remain false; no model/profit/live readiness is inferred.
    </div>
  {/if}
</section>

<DailyProgressTimeline {progress} />
<DailyScenarioLabCard {scenarioLab} />
<DailyScenarioRunLedgerCard ledger={scenarioRuns} />
<DailyDbQualityCard summary={dbSummary} />
<DailyUniverseCard {universe} onSymbolSelect={(code) => void loadSymbolDrilldown(code)} />
<DailyDatasetBuilderCard {dataset} chart={datasetChart} />
<DailyModelResultsCard {prediction} {portfolio} {walkForward} {predictionChart} {portfolioChart} {walkForwardChart} />
<DailyVisualLabCard
  decision={decisionCockpit}
  flow={flowChart}
  glossary={glossaryChart}
  researchDiagnostics={researchDiagnosticsChart}
  equityOverlay={equityOverlayChart}
  heatmap={walkForwardHeatmapChart}
  runScatter={runScatterChart}
  universeBreakdown={universeBreakdownChart}
  registry={registry}
  symbolChart={selectedSymbolChart}
/>

<section class="panel" data-daily-symbol-panel>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">D0 Symbol Drilldown</div>
      <h2 class="text-h3">종목 상세 조회</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{selectedSymbol?.price_basis ?? 'unknown'}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">유니버스 미리보기의 상세 버튼은 `/api/daily-ohlcv/symbol/{'{code}'}`를 호출하며 000250 같은 선행 0 코드를 문자열로 유지합니다.</p>
  {#if selectedSymbolError}
    <div class="notice danger" style="margin-top:12px">{selectedSymbolError}</div>
  {:else if selectedSymbol}
    <div class="grid-4-kpi" style="margin-top:16px">
      <div class="metric"><div class="metric-label">code</div><div class="metric-value tnum">{selectedSymbol.code}</div></div>
      <div class="metric"><div class="metric-label">table</div><div class="metric-value tnum">{selectedSymbol.table}</div></div>
      <div class="metric"><div class="metric-label">rows</div><div class="metric-value tnum">{selectedSymbol.row_count?.toLocaleString('ko-KR') ?? '—'}</div></div>
      <div class="metric"><div class="metric-label">range</div><div class="metric-value tnum" style="font-size:18px">{selectedSymbol.first_date ?? '—'} → {selectedSymbol.last_date ?? '—'}</div></div>
    </div>
  {:else}
    <div class="notice" style="margin-top:12px">아직 선택된 종목이 없습니다. 유니버스 미리보기에서 상세 버튼을 누르세요.</div>
  {/if}
</section>

<section class="panel" data-daily-ohlcv-artifacts>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Artifacts</div>
      <h2 class="text-h3">생성 증거 파일</h2>
    </div>
    <span class="pill"><span class="dot"></span>GET-only</span>
  </div>
  <div class="table-wrap" style="margin-top:12px; max-height:300px; overflow:auto">
    <table>
      <thead><tr><th>kind</th><th>run</th><th>file</th><th>bytes</th></tr></thead>
      <tbody>
        {#each artifacts?.artifacts ?? [] as row}
          <tr>
            <td>{row.kind}</td>
            <td>{row.run_id}</td>
            <td class="mono">{row.primary_file}</td>
            <td class="tnum">{row.size_bytes}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>

<style>
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th, td { border-bottom:1px solid var(--border-faint); padding:7px; text-align:left; vertical-align:top; }
  .mono { font-family: var(--font-mono); font-size:11px; color:var(--muted); }
</style>
