<script lang="ts">
  import { onMount } from 'svelte';
  import { fmt } from '$lib/format';
  import EChartsRenderer from '../charts/EChartsRenderer.svelte';

  interface StomSummary {
    compatible_stock_table_count?: number;
    db_size_bytes?: number;
    eligible_group_count?: number;
    estimated_samples?: number;
    table_count?: number;
    total_rows_stock_groups?: number;
    excluded_tables?: string[];
    warnings?: string[];
    inspect_available?: boolean;
    scale_available?: boolean;
  }

  interface FileItem {
    name: string;
    path: string;
    directory?: string;
    modified_at?: number;
    size_bytes?: number;
    artifact_type?: string;
  }

  type ViewName = 'prediction' | 'backtest' | 'filter';

  let summary = $state<StomSummary | null>(null);
  let horizonComparison = $state<any>(null);
  let predFiles = $state<FileItem[]>([]);
  let backtestFiles = $state<FileItem[]>([]);
  let filterFiles = $state<FileItem[]>([]);
  let loadingSummary = $state(false);
  let summaryError = $state<string | null>(null);

  let view = $state<ViewName>('prediction');
  let selectedFile = $state<FileItem | null>(null);
  let selectedArtifact = $state<any>(null);
  let diagnostics = $state<any>(null);
  let predictionDetail = $state<any>(null);
  let backtestReport = $state<any>(null);
  let loadingDiag = $state(false);
  let diagError = $state<string | null>(null);

  onMount(() => {
    void loadSummary();
    void loadAllLists();
  });

  async function loadSummary() {
    loadingSummary = true;
    summaryError = null;
    try {
      const r = await fetch('/api/stom/summary');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      summary = await r.json();
    } catch (e: any) {
      summaryError = e?.message ?? 'STOM 요약 조회 실패';
    } finally {
      loadingSummary = false;
    }
  }

  async function loadList(url: string): Promise<FileItem[]> {
    try {
      const r = await fetch(url);
      if (!r.ok) return [];
      const d = await r.json();
      return Array.isArray(d.files) ? d.files : Array.isArray(d) ? d : [];
    } catch {
      return [];
    }
  }

  async function loadAllLists() {
    const [pred, backtests, filters, horizonRes] = await Promise.all([
      loadList('/api/stom/prediction-files'),
      loadList('/api/stom/qlib-backtests'),
      loadList('/api/stom/filter-reports'),
      fetch('/api/stom/horizon-comparison').catch(() => null),
    ]);
    predFiles = pred;
    backtestFiles = backtests;
    filterFiles = filters;
    if (horizonRes?.ok) horizonComparison = await horizonRes.json();
    const latest = preferredPredictionFile();
    if (!selectedFile && latest && view === 'prediction') {
      await selectFile(latest);
    }
  }

  function fileQuery(f: FileItem): string {
    return f.name || f.path;
  }

  async function selectFile(f: FileItem) {
    selectedFile = f;
    selectedArtifact = null;
    diagnostics = null;
    predictionDetail = null;
    backtestReport = null;
    diagError = null;
    loadingDiag = true;
    try {
      const query = encodeURIComponent(fileQuery(f));
      if (view === 'prediction') {
        const [diagRes, predictionRes, reportRes] = await Promise.all([
          fetch(`/api/stom/diagnostics?file=${query}&max_symbols=30`),
          fetch(`/api/stom/prediction?file=${query}`),
          fetch(`/api/stom/backtest-report?file=${query}&top_k=5`),
        ]);
        if (!diagRes.ok) throw new Error(`진단 HTTP ${diagRes.status}`);
        if (!predictionRes.ok) throw new Error(`예측 상세 HTTP ${predictionRes.status}`);
        diagnostics = await diagRes.json();
        predictionDetail = await predictionRes.json();
        backtestReport = reportRes.ok ? await reportRes.json() : null;
      } else if (view === 'backtest') {
        const r = await fetch(`/api/stom/qlib-backtests?file=${query}`);
        if (!r.ok) throw new Error(`백테스트 HTTP ${r.status}`);
        selectedArtifact = await r.json();
      } else {
        const r = await fetch(`/api/stom/filter-reports?file=${query}`);
        if (!r.ok) throw new Error(`필터 리포트 HTTP ${r.status}`);
        selectedArtifact = await r.json();
      }
    } catch (e: any) {
      diagError = e?.message ?? '상세 조회 실패';
    } finally {
      loadingDiag = false;
    }
  }

  function switchView(next: ViewName) {
    view = next;
    selectedFile = null;
    selectedArtifact = null;
    diagnostics = null;
    predictionDetail = null;
    backtestReport = null;
    diagError = null;
    const list = next === 'prediction' ? sortedPredFiles : next === 'backtest' ? sortedBacktestFiles : sortedFilterFiles;
    if (list[0]) void selectFile(list[0]);
  }

  function gib(b: number | undefined | null): string {
    if (b == null) return '—';
    if (b >= 1024 ** 3) return (b / 1024 ** 3).toFixed(2) + ' GiB';
    if (b >= 1024 ** 2) return (b / 1024 ** 2).toFixed(1) + ' MiB';
    if (b >= 1024) return (b / 1024).toFixed(1) + ' KiB';
    return `${b} B`;
  }

  function predictionPriority(name: string): number {
    if (name.includes('_kronos.csv')) return 0;
    if (name.includes('_persistence.csv')) return 1;
    if (name.includes('_random.csv')) return 2;
    return 3;
  }

  function horizonPriority(name: string): number {
    const match = name.match(/pred(\d+)/);
    return match ? -Number(match[1]) : 0;
  }

  function sortFilesForDisplay(files: FileItem[], currentView: ViewName): FileItem[] {
    return [...files].sort((a, b) => {
      if (currentView === 'prediction') {
        const horizon = horizonPriority(a.name) - horizonPriority(b.name);
        if (horizon !== 0) return horizon;
        const priority = predictionPriority(a.name) - predictionPriority(b.name);
        if (priority !== 0) return priority;
      }
      const modified = (b.modified_at ?? 0) - (a.modified_at ?? 0);
      if (Math.abs(modified) > 120) return modified;
      return a.name.localeCompare(b.name);
    });
  }

  const sortedPredFiles = $derived(sortFilesForDisplay(predFiles, 'prediction'));
  const sortedBacktestFiles = $derived(sortFilesForDisplay(backtestFiles, 'backtest'));
  const sortedFilterFiles = $derived(sortFilesForDisplay(filterFiles, 'filter'));
  const activeFiles = $derived(view === 'prediction' ? sortedPredFiles : view === 'backtest' ? sortedBacktestFiles : sortedFilterFiles);
  const viewLabel = $derived(view === 'prediction' ? '예측 결과' : view === 'backtest' ? '백테스트' : '필터 리포트');

  function preferredPredictionFile(): FileItem | undefined {
    return sortedPredFiles.find((file) => file.name.includes('_kronos.csv')) ?? sortedPredFiles[0];
  }

  function pct(value: unknown, digits = 1): string {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return `${n.toFixed(digits)}%`;
  }

  function ratioPct(value: unknown, digits = 1): string {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return `${(n * 100).toFixed(digits)}%`;
  }

  function num(value: unknown, digits = 3): string {
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    if (Math.abs(n) >= 1000) return fmt.int(n);
    return n.toFixed(digits);
  }

  function verdict(overall: any): { label: string; tone: 'success' | 'warn' | 'danger'; message: string } {
    const direction = Number(overall?.direction_accuracy ?? 0);
    const avgReturn = Number(overall?.avg_actual_return ?? 0);
    if (direction >= 0.5 && avgReturn >= 0) {
      return { label: '실전 후보 검토 가능', tone: 'success', message: '방향 적중률이 50% 이상입니다. 그래도 비용 반영 rolling 검증을 함께 확인해야 합니다.' };
    }
    if (direction >= 0.4) {
      return { label: '조건식 보완 필요', tone: 'warn', message: '방향성은 일부 있지만 50%를 넘지 못했거나 비용 검증이 부족합니다. 조건식과 horizon 비교가 필요합니다.' };
    }
    return { label: '실전 사용 보류', tone: 'danger', message: '현재 결과만으로 자동매매 신호로 사용하기 어렵습니다.' };
  }

  const resultVerdict = $derived(verdict(diagnostics?.overall));

  const horizonRows = $derived(horizonComparison?.rows ?? []);
  const bestHorizon = $derived(horizonComparison?.best_by_rolling_net ?? horizonComparison?.best_by_direction ?? null);
  const horizonChartOption = $derived.by(() => {
    const rows = horizonRows;
    if (!rows.length) return {};
    return {
      backgroundColor: 'transparent',
      grid: { left: 52, right: 24, top: 42, bottom: 44 },
      tooltip: { trigger: 'axis' },
      legend: { top: 0, textStyle: { color: 'inherit' } },
      xAxis: { type: 'category', data: rows.map((r: any) => `${r.horizon}s`), axisLabel: { color: '#64748b' } },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%', color: '#64748b' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.2)' } } },
      series: [
        { name: 'Kronos 방향 적중률', type: 'bar', data: rows.map((r: any) => Number(r.direction_accuracy ?? 0) * 100), itemStyle: { color: '#2563eb' } },
        { name: 'Random 방향 적중률', type: 'bar', data: rows.map((r: any) => Number(r.random_direction_accuracy ?? 0) * 100), itemStyle: { color: '#94a3b8' } },
        { name: 'Rolling net', type: 'line', data: rows.map((r: any) => Number(r.rolling_net_return_pct ?? 0)), lineStyle: { color: '#ef4444', width: 3 }, symbolSize: 8 },
      ],
    };
  });

  const actualPredictionOption = $derived.by(() => {
    const rows = predictionDetail?.visual?.window_series ?? [];
    if (!rows.length) return {};
    return {
      backgroundColor: 'transparent',
      grid: { left: 52, right: 24, top: 34, bottom: 42 },
      tooltip: { trigger: 'axis' },
      legend: { top: 0, textStyle: { color: 'inherit' } },
      xAxis: { type: 'category', data: rows.map((r: any) => String(r.timestamp).slice(11, 19)), axisLabel: { color: '#64748b' } },
      yAxis: { type: 'value', scale: true, axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.22)' } } },
      series: [
        { name: '실제 종가', type: 'line', smooth: 0.25, symbol: 'none', data: rows.map((r: any) => r.actual_close), lineStyle: { color: '#0f172a', width: 2.2 } },
        { name: 'Kronos 예측', type: 'line', smooth: 0.25, symbol: 'none', data: rows.map((r: any) => r.pred_close), lineStyle: { color: '#ef4444', width: 2, type: 'dashed' } },
      ],
    };
  });

  const returnScatterOption = $derived.by(() => {
    const rows = predictionDetail?.visual?.return_scatter ?? [];
    if (!rows.length) return {};
    return {
      backgroundColor: 'transparent',
      grid: { left: 54, right: 24, top: 26, bottom: 46 },
      tooltip: {
        trigger: 'item',
        formatter: (p: any) => {
          const r = rows[p.dataIndex];
          return `${r.symbol}<br/>예측 ${num(r.pred_return_window, 3)}%<br/>실제 ${num(r.actual_return_window, 3)}%<br/>${r.direction_hit_window ? '방향 적중' : '방향 실패'}`;
        },
      },
      xAxis: { type: 'value', name: '예측 등락률 %', axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.2)' } } },
      yAxis: { type: 'value', name: '실제 등락률 %', axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: 'rgba(148,163,184,.2)' } } },
      series: [
        {
          name: 'window',
          type: 'scatter',
          symbolSize: 7,
          data: rows.map((r: any) => [r.pred_return_window, r.actual_return_window]),
          itemStyle: { color: (p: any) => rows[p.dataIndex]?.direction_hit_window ? '#22c55e' : '#ef4444', opacity: 0.72 },
        },
      ],
    };
  });

  function fileModified(file: FileItem): string {
    if (!file.modified_at) return '—';
    return new Date(file.modified_at * 1000).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
  }
</script>

<section class="page-hero">
  <div class="row" style="gap:10px;flex-wrap:wrap">
    <span class="text-eyebrow">본격</span>
    <span class="pill"><span class="dot" style="background:var(--info)"></span>STOM 1초봉 · read-only</span>
    <span class="pill"><span class="dot" style="background:{summary?.inspect_available ? 'var(--success)' : 'var(--warn)'}"></span>
      inspect {summary?.inspect_available ? 'OK' : '제한'}</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">예측 진단</h1>
  <p class="text-muted" style="margin-top:6px">
    STOM 1초봉 예측, 백테스트, 필터 산출물과 horizon별 성과를 한 화면에서 비교합니다.
    모든 데이터는 read-only이며, 런타임 예측 CSV는 소스 커밋에 포함하지 않습니다.
  </p>
</section>

{#if loadingSummary && !summary}
  <div class="card">요약 로딩 중...</div>
{:else if summaryError}
  <div class="card error-card">요약 조회 실패: {summaryError}</div>
{:else if summary}
  <section class="kpi-grid">
    <div class="card kpi"><span>호환 테이블</span><strong>{fmt.int(summary.compatible_stock_table_count ?? 0)}</strong><small>stock table</small></div>
    <div class="card kpi"><span>학습 후보 그룹</span><strong>{fmt.int(summary.eligible_group_count ?? 0)}</strong><small>lookback/predict 가능</small></div>
    <div class="card kpi"><span>예상 샘플</span><strong>{fmt.int(summary.estimated_samples ?? 0)}</strong><small>lookback 300 기준</small></div>
    <div class="card kpi"><span>DB 크기</span><strong>{gib(summary.db_size_bytes)}</strong><small>STOM tick database</small></div>
  </section>
{/if}

{#if horizonRows.length}
  <section class="card horizon-card">
    <div class="section-head">
      <div>
        <div class="card-eyebrow">HORIZON COMPARISON · 30/60/120/300초 비교</div>
        <h2>어느 예측 시간이 가장 의미 있는가?</h2>
        <p>동일 checkpoint로 각 horizon을 walk-forward 평가하고, 비용 25bp 기준 rolling gate까지 비교합니다.</p>
      </div>
      <span class="pill {horizonComparison?.passes_any_gate ? 'success' : 'warn'}">
        {horizonComparison?.passes_any_gate ? '확장 가능' : '확장 보류'}
      </span>
    </div>
    <div class="verdict-card {horizonComparison?.passes_any_gate ? 'success' : 'warn'}">
      <div>
        <div class="text-eyebrow">현재 결론</div>
        <h3>{bestHorizon ? `${bestHorizon.horizon}초가 상대적으로 가장 유망` : '비교 결과 없음'}</h3>
        <p>{horizonComparison?.message}</p>
      </div>
      {#if bestHorizon}
        <span class="pill accent">Rolling net {pct(bestHorizon.rolling_net_return_pct, 3)}</span>
      {/if}
    </div>
    <EChartsRenderer option={horizonChartOption} height="320px" />
    <div class="table-scroll">
      <table class="result-table">
        <thead>
          <tr>
            <th>horizon</th><th>방향 적중</th><th>random 대비</th><th>Top-K net</th><th>최적 필터 net</th><th>Rolling net</th><th>Rolling 방향</th><th>Gate</th>
          </tr>
        </thead>
        <tbody>
          {#each horizonRows as row}
            <tr class:best-row={bestHorizon?.horizon === row.horizon}>
              <td><strong>{row.horizon}초</strong></td>
              <td>{ratioPct(row.direction_accuracy, 2)}</td>
              <td class={row.direction_edge_vs_random >= 0 ? 'positive' : 'negative'}>{pct(row.direction_edge_vs_random * 100, 2)}</td>
              <td class={row.topk_net_return_pct >= 0 ? 'positive' : 'negative'}>{pct(row.topk_net_return_pct, 3)}</td>
              <td class={row.best_filter_net_return_pct >= 0 ? 'positive' : 'negative'}>{pct(row.best_filter_net_return_pct, 3)}</td>
              <td class={row.rolling_net_return_pct >= 0 ? 'positive' : 'negative'}>{pct(row.rolling_net_return_pct, 3)}</td>
              <td>{ratioPct(row.rolling_direction_hit_rate, 2)}</td>
              <td><span class="pill {row.passes_gate ? 'success' : 'warn'}">{row.passes_gate ? '통과' : '보류'}</span></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{/if}

<section class="card workspace">
  <div class="tabs">
    <button class={view === 'prediction' ? 'active' : ''} onclick={() => switchView('prediction')}>예측 결과</button>
    <button class={view === 'backtest' ? 'active' : ''} onclick={() => switchView('backtest')}>백테스트</button>
    <button class={view === 'filter' ? 'active' : ''} onclick={() => switchView('filter')}>필터 리포트</button>
  </div>

  <div class="workspace-grid">
    <aside class="file-list">
      <div class="file-list-head">
        <div>
          <div class="card-eyebrow">{viewLabel}</div>
          <h3>산출물 목록</h3>
        </div>
        <button class="ghost" onclick={loadAllLists}>갱신</button>
      </div>
      {#if activeFiles.length}
        {#each activeFiles.slice(0, 80) as file}
          <button class="file-row {selectedFile?.name === file.name ? 'selected' : ''}" onclick={() => selectFile(file)}>
            <strong>{file.name}</strong>
            <span>{gib(file.size_bytes)} · {fileModified(file)}</span>
          </button>
        {/each}
      {:else}
        <div class="empty">표시할 산출물이 없습니다.</div>
      {/if}
    </aside>

    <main class="detail-panel">
      {#if loadingDiag}
        <div class="loading-box">상세 분석 로딩 중...</div>
      {:else if diagError}
        <div class="error-card">⚠ {diagError}</div>
      {:else if view === 'prediction' && diagnostics}
        <div class="card-eyebrow" style="margin-bottom:8px">EVALUATION SUMMARY · 사용자가 바로 읽는 성과 요약</div>
        {#if diagnostics.overall}
          <div class="verdict-card {resultVerdict.tone}">
            <div>
              <div class="text-eyebrow">MODEL VERDICT</div>
              <h3>{resultVerdict.label}</h3>
              <p>{resultVerdict.message}</p>
            </div>
            <span class="pill {resultVerdict.tone}">방향 적중 {ratioPct(diagnostics.overall.direction_accuracy, 2)}</span>
          </div>

          <div class="eval-kpi-grid">
            <div class="eval-kpi"><span>방향 적중률</span><strong>{ratioPct(diagnostics.overall.direction_accuracy, 2)}</strong><small>50% 기준 대비 {Number(diagnostics.overall.direction_accuracy ?? 0) >= 0.5 ? '상회' : '미달'}</small></div>
            <div class="eval-kpi"><span>MAPE</span><strong>{pct(diagnostics.overall.mape, 3)}</strong><small>가격 경로 평균 오차율</small></div>
            <div class="eval-kpi"><span>평가 범위</span><strong>{fmt.int(diagnostics.overall.windows)} windows</strong><small>{fmt.int(diagnostics.overall.symbols)}종목 · {fmt.int(diagnostics.overall.sessions)}거래일</small></div>
            <div class="eval-kpi"><span>평균 실제 등락률</span><strong>{pct(diagnostics.overall.avg_actual_return, 3)}</strong><small>예측 window 최종 시점 기준</small></div>
          </div>
        {/if}

        {#if backtestReport?.filters}
          <div class="card-eyebrow" style="margin:16px 0 8px">조건식/Top-K 필터별 성과</div>
          <div class="filter-grid">
            {#each backtestReport.filters.slice(0, 6) as row}
              <div class="filter-card">
                <span>{row.label}</span>
                <strong>{ratioPct(row.hit_rate, 1)}</strong>
                <small>count {fmt.int(row.count)} · 실제 {pct(row.avg_actual_return, 3)}</small>
              </div>
            {/each}
          </div>
        {/if}

        {#if predictionDetail?.visual?.window_series?.length}
          <div class="chart-section">
            <div class="chart-title">
              <div><div class="card-eyebrow">ACTUAL VS PREDICTION</div><h3>선택 window 실제 종가와 Kronos 예측 종가</h3></div>
              {#if predictionDetail.visual.selected_window}
                <span class="pill accent">{predictionDetail.visual.selected_window.symbol} · window {predictionDetail.visual.selected_window.window_id}</span>
              {/if}
            </div>
            <EChartsRenderer option={actualPredictionOption} height="320px" />
          </div>
          <div class="chart-section">
            <div class="chart-title">
              <div><div class="card-eyebrow">RETURN SCATTER</div><h3>전체 window 예측 등락률 vs 실제 등락률</h3></div>
              <span class="text-caption">초록=방향 적중 · 빨강=방향 실패</span>
            </div>
            <EChartsRenderer option={returnScatterOption} height="320px" />
          </div>
        {/if}

        {#if predictionDetail?.recommendations?.length}
          <div class="card-eyebrow" style="margin:16px 0 8px">KRONOS 점수 상위 후보</div>
          <div class="table-scroll">
            <table class="result-table">
              <thead><tr><th>순위</th><th>종목</th><th>일자</th><th>점수</th><th>신호</th><th>예측 등락률</th><th>실제 등락률</th><th>방향</th></tr></thead>
              <tbody>
                {#each predictionDetail.recommendations.slice(0, 10) as row, idx}
                  <tr>
                    <td>{idx + 1}</td><td class="text-mono">{row.symbol}</td><td class="text-mono">{row.session}</td><td>{num(row.kronos_score, 1)}</td>
                    <td><span class="pill {row.signal === 'BUY_CANDIDATE' ? 'success' : row.signal === 'WATCH' ? 'warn' : 'danger'}">{row.signal}</span></td>
                    <td>{pct(row.pred_return_window, 3)}</td><td>{pct(row.actual_return_window, 3)}</td><td>{row.direction_hit_window ? '적중' : '실패'}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      {:else if selectedArtifact}
        <div class="artifact-summary">
          <div class="card-eyebrow">ARTIFACT DETAIL</div>
          <h3>{selectedFile?.name}</h3>
          {#if selectedArtifact.metrics}
            <div class="eval-kpi-grid">
              <div class="eval-kpi"><span>평균 gross</span><strong>{pct(selectedArtifact.metrics.avg_gross_return_pct, 3)}</strong></div>
              <div class="eval-kpi"><span>평균 net</span><strong>{pct(selectedArtifact.metrics.avg_net_return_pct, 3)}</strong></div>
              <div class="eval-kpi"><span>방향 적중</span><strong>{ratioPct(selectedArtifact.metrics.direction_hit_rate, 2)}</strong></div>
              <div class="eval-kpi"><span>누적 수익</span><strong>{pct(selectedArtifact.metrics.cumulative_return_pct, 2)}</strong></div>
            </div>
          {:else if selectedArtifact.summary}
            <div class="eval-kpi-grid">
              <div class="eval-kpi"><span>fold 수</span><strong>{fmt.int(selectedArtifact.summary.fold_count ?? 0)}</strong></div>
              <div class="eval-kpi"><span>test net</span><strong>{pct(selectedArtifact.summary.avg_test_net_return_pct, 3)}</strong></div>
              <div class="eval-kpi"><span>positive fold</span><strong>{ratioPct(selectedArtifact.summary.positive_test_fold_rate, 2)}</strong></div>
              <div class="eval-kpi"><span>overfit gap</span><strong>{pct(selectedArtifact.summary.overfit_gap_pct, 3)}</strong></div>
            </div>
          {:else if selectedArtifact.best_filter}
            <div class="eval-kpi-grid">
              <div class="eval-kpi"><span>best net</span><strong>{pct(selectedArtifact.best_filter.avg_net_return_pct, 3)}</strong></div>
              <div class="eval-kpi"><span>direction</span><strong>{ratioPct(selectedArtifact.best_filter.direction_hit_rate, 2)}</strong></div>
              <div class="eval-kpi"><span>trades</span><strong>{fmt.int(selectedArtifact.best_filter.trade_count ?? 0)}</strong></div>
              <div class="eval-kpi"><span>coverage</span><strong>{ratioPct(selectedArtifact.best_filter.coverage, 2)}</strong></div>
            </div>
          {/if}
          <pre class="diag-json">{JSON.stringify(selectedArtifact, null, 2).slice(0, 2000)}{JSON.stringify(selectedArtifact).length > 2000 ? '\n...' : ''}</pre>
        </div>
      {:else}
        <div class="empty detail-empty">왼쪽에서 산출물을 선택하세요.</div>
      {/if}
    </main>
  </div>
</section>

<style>
  .kpi-grid,
  .eval-kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }
  .kpi span,
  .eval-kpi span { color: var(--muted); font-size: 12px; }
  .kpi strong,
  .eval-kpi strong { display: block; margin-top: 6px; font-size: 24px; color: var(--text); }
  .kpi small,
  .eval-kpi small { color: var(--muted); }
  .horizon-card { margin-bottom: 16px; }
  .section-head,
  .verdict-card,
  .chart-title,
  .file-list-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
  }
  .section-head h2,
  .verdict-card h3,
  .chart-title h3 { margin: 4px 0; }
  .section-head p,
  .verdict-card p { margin: 0; color: var(--muted); }
  .verdict-card {
    padding: 14px;
    margin: 14px 0;
    border-radius: 16px;
    border: 1px solid rgba(148,163,184,.24);
    background: rgba(248,250,252,.72);
  }
  .verdict-card.success { border-color: rgba(34,197,94,.35); background: rgba(240,253,244,.72); }
  .verdict-card.warn { border-color: rgba(245,158,11,.35); background: rgba(255,251,235,.8); }
  .verdict-card.danger { border-color: rgba(239,68,68,.35); background: rgba(254,242,242,.78); }
  .tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
  .tabs button,
  .ghost {
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    border-radius: 999px;
    padding: 8px 14px;
    cursor: pointer;
  }
  .tabs button.active { background: var(--primary); color: white; border-color: var(--primary); }
  .workspace-grid { display: grid; grid-template-columns: minmax(260px, 340px) 1fr; gap: 16px; }
  .file-list { border-right: 1px solid var(--border); padding-right: 14px; max-height: 980px; overflow: auto; }
  .file-row {
    display: block;
    width: 100%;
    text-align: left;
    border: 1px solid var(--border);
    background: var(--surface);
    border-radius: 12px;
    padding: 10px;
    margin: 8px 0;
    cursor: pointer;
  }
  .file-row strong { display: block; font-size: 12px; word-break: break-all; }
  .file-row span { display: block; margin-top: 4px; color: var(--muted); font-size: 11px; }
  .file-row.selected { border-color: var(--primary); box-shadow: 0 0 0 2px rgba(37,99,235,.14); }
  .detail-panel { min-width: 0; }
  .filter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
  .filter-card,
  .eval-kpi {
    border: 1px solid var(--border);
    background: rgba(255,255,255,.72);
    border-radius: 14px;
    padding: 12px;
  }
  .filter-card strong { display:block; font-size: 22px; margin: 4px 0; }
  .chart-section { margin-top: 16px; padding: 14px; border: 1px solid var(--border); border-radius: 16px; background: rgba(255,255,255,.62); }
  .table-scroll { overflow: auto; margin-top: 10px; }
  .result-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .result-table th,
  .result-table td { border-bottom: 1px solid var(--border); padding: 8px 10px; text-align: left; white-space: nowrap; }
  .result-table th { color: var(--muted); font-size: 12px; }
  .best-row { background: rgba(37,99,235,.07); }
  .positive { color: #16a34a; font-weight: 700; }
  .negative { color: #dc2626; font-weight: 700; }
  .diag-json { margin-top: 16px; padding: 14px; border-radius: 14px; background: #0f172a; color: #e2e8f0; overflow: auto; max-height: 420px; font-size: 12px; }
  .empty,
  .loading-box,
  .error-card { padding: 18px; border: 1px dashed var(--border); border-radius: 14px; color: var(--muted); }
  .error-card { color: var(--danger); border-color: rgba(239,68,68,.4); }
  .pill.success { background: rgba(34,197,94,.12); color: #15803d; }
  .pill.warn { background: rgba(245,158,11,.14); color: #b45309; }
  .pill.danger { background: rgba(239,68,68,.12); color: #b91c1c; }
  .pill.accent { background: rgba(37,99,235,.12); color: #1d4ed8; }
  @media (max-width: 1000px) {
    .workspace-grid,
    .kpi-grid,
    .eval-kpi-grid,
    .filter-grid { grid-template-columns: 1fr; }
    .file-list { border-right: 0; padding-right: 0; }
    .section-head,
    .verdict-card,
    .chart-title { flex-direction: column; }
  }
</style>
