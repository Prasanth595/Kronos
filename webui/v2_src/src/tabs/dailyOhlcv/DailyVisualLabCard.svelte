<script lang="ts">
  import type { DailyRegistryResponse, DailyVisualChartResponse } from '$lib/dailyOhlcvApi';

  interface Props {
    decision: DailyVisualChartResponse | null;
    flow: DailyVisualChartResponse | null;
    glossary: DailyVisualChartResponse | null;
    researchDiagnostics: DailyVisualChartResponse | null;
    equityOverlay: DailyVisualChartResponse | null;
    heatmap: DailyVisualChartResponse | null;
    runScatter: DailyVisualChartResponse | null;
    universeBreakdown: DailyVisualChartResponse | null;
    registry: DailyRegistryResponse | null;
    symbolChart: DailyVisualChartResponse | null;
  }

  let { decision, flow, glossary, researchDiagnostics, equityOverlay, heatmap, runScatter, universeBreakdown, registry, symbolChart }: Props = $props();

  const finiteNumber = (value: unknown): number | null => {
    if (value === null || value === undefined || value === '') return null;
    const parsed = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const pct = (value: unknown) => {
    const numeric = finiteNumber(value);
    return numeric === null ? '—' : `${(numeric * 100).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}%`;
  };
  const cellText = (value: unknown) => Array.isArray(value) ? value.join(';') : (value && typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—'));
  const list = (value: unknown): readonly Record<string, unknown>[] => Array.isArray(value) ? value.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object') : [];
  const D7_FALLBACK_DIAGNOSTICS: readonly Record<string, unknown>[] = [
    {
      id: 'D7_FEATURE_DIAGNOSTICS',
      label: 'Feature diagnostics',
      status: 'PLACEHOLDER_READY',
      summary: 'feature/regime/correlation/failure diagnostics require explicit read-only artifacts before claims.',
      next_artifact: 'feature_importance_by_fold.csv',
      guardrail: 'feature importance is explanatory only; no profit/live/broker/order claim.',
      allowed_use: 'feature별 fold 기여도와 drift를 비교해 D3/D4 실패 원인을 설명합니다.',
      blocked_use: 'feature 중요도를 종목 선택, 수익 주장, live signal로 사용하지 않습니다.',
      how_to_read_ko: 'fold마다 같은 feature가 반복되는지와 price_basis unknown 민감도를 먼저 봅니다.',
      current_gap: 'feature_importance_by_fold.csv가 생성되기 전까지 PLACEHOLDER_READY입니다.',
    },
    {
      id: 'D7_REGIME_DIAGNOSTICS',
      label: 'Regime diagnostics',
      status: 'PLACEHOLDER_READY',
      summary: 'regime buckets must be forward-only and cannot retune OOS folds.',
      next_artifact: 'regime_bucket_metrics.csv',
      guardrail: 'regime labels are research diagnostics only.',
      allowed_use: '추세·변동성·유동성 regime별 baseline/RL 실패 구간을 찾습니다.',
      blocked_use: 'OOS fold를 보고 regime 정의를 재튜닝하지 않습니다.',
      how_to_read_ko: 'forward-only regime 규칙으로 한 구간 좋은 결과를 전체 성과처럼 말하지 않습니다.',
      current_gap: 'regime_bucket_metrics.csv가 생성되기 전까지 PLACEHOLDER_READY입니다.',
    },
    {
      id: 'D7_CORRELATION_RISK',
      label: 'Correlation and concentration',
      status: 'PLACEHOLDER_READY',
      summary: 'correlation/concentration diagnostics prevent single-theme exposure from being hidden.',
      next_artifact: 'correlation_cluster_summary.csv',
      guardrail: 'correlation views are risk diagnostics, not selection proof.',
      allowed_use: '상관·집중도·테마 쏠림을 보며 포트폴리오 리스크를 설명합니다.',
      blocked_use: '상관 클러스터를 종목 추천이나 배포 가능한 allocation으로 사용하지 않습니다.',
      how_to_read_ko: '손실 fold와 고상관 cluster가 겹치는지 확인하고 penalty 가설로만 사용합니다.',
      current_gap: 'correlation_cluster_summary.csv가 생성되기 전까지 PLACEHOLDER_READY입니다.',
    },
    {
      id: 'D7_FAILURE_ANALYSIS',
      label: 'Failure analysis',
      status: 'PLACEHOLDER_READY',
      summary: 'NO-GO reasons, invalid actions, drawdown spikes, and fold failures stay visible.',
      next_artifact: 'failure_reason_attribution.csv',
      guardrail: 'failure visibility is mandatory; weak or flat RL outcomes must not be hidden.',
      allowed_use: 'NO-GO reason, invalid action, drawdown spike, fold failure를 다음 실험 가설로 묶습니다.',
      blocked_use: '실패 fold를 숨기거나 성공 fold만 골라 GO처럼 표현하지 않습니다.',
      how_to_read_ko: 'D0/D1/D3/D5 blocker를 먼저 확인하고 reward/action 변경은 사전등록합니다.',
      current_gap: 'failure_reason_attribution.csv가 생성되기 전까지 PLACEHOLDER_READY입니다.',
    },
  ];
  const mergeD7DiagnosticCard = (fallback: Record<string, unknown>, card: Record<string, unknown> | undefined) => {
    if (!card) return fallback;
    return {
      ...fallback,
      ...card,
      allowed_use: card.allowed_use || fallback.allowed_use,
      blocked_use: card.blocked_use || fallback.blocked_use,
      how_to_read_ko: card.how_to_read_ko || fallback.how_to_read_ko,
      current_gap: card.current_gap || fallback.current_gap,
      next_artifact: card.next_artifact || fallback.next_artifact,
      guardrail: card.guardrail || fallback.guardrail,
      summary: card.summary || fallback.summary,
    };
  };
  const d7DiagnosticCards = () => {
    const cards = list(researchDiagnostics?.cards);
    const byId = new Map(cards.map((card) => [String(card.id), card]));
    const requiredIds = new Set(D7_FALLBACK_DIAGNOSTICS.map((card) => String(card.id)));
    return [
      ...D7_FALLBACK_DIAGNOSTICS.map((fallback) => mergeD7DiagnosticCard(fallback, byId.get(String(fallback.id)))),
      ...cards.filter((card) => !requiredIds.has(String(card.id))),
    ];
  };
  const isDailyUsageGuide = (value: unknown): value is Record<string, unknown> => {
    if (!value || typeof value !== 'object') return false;
    const stage = String((value as Record<string, unknown>).stage ?? '');
    return stage === 'D6' || stage === 'D7';
  };
  const usageGuideRows = () => {
    const fromDecision = list(decision?.usage_guide);
    if (fromDecision.length > 0) return fromDecision;
    return list(flow?.nodes).map((node) => node.usage_guide).filter(isDailyUsageGuide);
  };
  const symbolUsageGuideRows = () => list(symbolChart?.usage_guide);
  const rows = (items: readonly Record<string, unknown>[] | undefined, limit = 12) => (items ?? []).slice(0, limit);
  const registryEvidenceText = (value: unknown, missing: string, empty = 'none') => Array.isArray(value) ? (value.length ? value.join(' · ') : empty) : missing;
  const registryFlagText = (value: unknown) => typeof value === 'boolean' ? String(value) : 'MISSING_REGISTRY_FLAG_UNSAFE';
  const registryBlockScore = (row: Record<string, unknown>) => /BLOCK|NO-GO|UNSAFE|INVALID|MISSING/i.test(JSON.stringify(row)) ? 1 : 0;
  const registryRows = (items: unknown, limit = 12) => {
    if (!Array.isArray(items) || items.length === 0) return [{ evidence_status: 'MISSING_SAMPLE_EVIDENCE', reason: 'registry sample field missing or empty' }];
    return [...list(items)].sort((left, right) => registryBlockScore(right) - registryBlockScore(left)).slice(0, limit);
  };
  const registryHiddenCount = (items: unknown, limit = 12) => Array.isArray(items) && items.length > 0 ? String(Math.max(0, list(items).length - limit)) : 'MISSING_SAMPLE_EVIDENCE';
  const entries = (record: Readonly<Record<string, number>> | undefined, limit = 8) => Object.entries(record ?? {}).sort((a, b) => b[1] - a[1]).slice(0, limit);
  const maxEntry = (record: Readonly<Record<string, number>> | undefined) => Math.max(1, ...Object.values(record ?? {}).map((value) => Math.abs(value)));

  function tone(value: unknown): string {
    const status = String(value ?? '');
    if (status === 'PASS') return 'success';
    if (status === 'WATCH' || status === 'RESEARCH_ONLY' || status === 'REFERENCE_ONLY') return 'warn';
    if (status === 'NO-GO' || status === 'BLOCKED' || status === 'LOCKED') return 'danger';
    return '';
  }

  function severityClass(value: unknown): string {
    const severity = String(value ?? 'neutral');
    if (severity === 'pass') return 'pass';
    if (severity === 'watch') return 'watch';
    if (severity === 'block') return 'block';
    return 'neutral';
  }

  function sparkHeight(value: unknown): number | null {
    const numeric = finiteNumber(value);
    return numeric === null ? null : Math.max(8, Math.min(96, 12 + numeric * 70));
  }

  function scatterX(value: unknown): number | null {
    const drawdown = finiteNumber(value);
    return drawdown === null ? null : Math.max(4, Math.min(96, 96 + drawdown * 260));
  }

  function scatterY(value: unknown): number | null {
    const ret = finiteNumber(value);
    return ret === null ? null : Math.max(4, Math.min(96, 78 - ret * 90));
  }

  function formatNumber(value: unknown, maximumFractionDigits = 3): string {
    const numeric = finiteNumber(value);
    return numeric === null ? '—' : numeric.toLocaleString('ko-KR', { maximumFractionDigits });
  }
</script>


<section class="panel" data-daily-visual-lab-card>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">STOM-inspired Visual Lab</div>
      <h2 class="text-h3">검토·게이트·성과 착시 방지 시각화</h2>
    </div>
    <span class="pill {tone(decision?.status)}"><span class="dot"></span>{decision?.status ?? 'NOT_STARTED'}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    STOM 대시보드의 Research Criteria, Metric Glossary, Active Strategy, Equity Overlay, Heatmap, Run Compare 아이디어를 Kronos 일봉 연구 증거에 맞게 읽기 전용으로 반영했습니다. 수익 보장·실거래·브로커·주문 준비 상태가 아닙니다. D6는 증거를 읽는 화면이고 D7은 실패 원인과 다음 가설을 좁히는 연구 노트입니다.
  </p>

  <div class="usage-guide" data-daily-d6-d7-usage-guide data-daily-page-progress-guide>
    <div class="text-eyebrow">D6/D7 사용 안내 · 할 수 있는 것 / 금지 / 다음 증거</div>
    <div class="guide-grid">
      {#each rows(usageGuideRows(), 6) as guide}
        <div class="guide-card">
          <strong>{guide.stage} · {guide.page}</strong>
          <span>가능: {guide.can_do}</span>
          <span>금지: {guide.must_not}</span>
          <small>다음: {guide.next_action}</small>
        </div>
      {/each}
    </div>
  </div>

  <div class="visual-grid" style="margin-top:16px">
    <div class="visual-box" data-daily-decision-cockpit>
      <div class="box-head"><span>Decision Cockpit</span><strong>{decision?.model_build_allowed ? 'UNLOCKED' : 'LOCKED'}</strong></div>
      <div class="decision-cards">
        {#each rows(decision?.cards, 4) as card}
          <div class="decision-card {severityClass(card.severity)}">
            <small>{card.id}</small>
            <strong>{card.status}</strong>
            <span>{card.label}</span>
          </div>
        {/each}
      </div>
      <div class="blocker-list">
        {#each list(decision?.blockers) as blocker}
          <div class="blocker {severityClass(blocker.severity)}">
            <strong>{blocker.id}</strong>
            <span>{blocker.title}</span>
            <small>{blocker.required_fix}</small>
          </div>
        {/each}
      </div>
    </div>

    <div class="visual-box" data-daily-flow-map>
      <div class="box-head"><span>Evidence Flow</span><strong>{flow?.model_build_allowed ? 'GO' : 'NO-GO'}</strong></div>
      <div class="flow-row">
        {#each rows(flow?.nodes, 10) as node, index}
          <div class="flow-node {severityClass(node.severity)}">
            <strong>{node.id}</strong>
            <span>{node.label}</span>
            <small>{node.status}</small>
          </div>
          {#if index < rows(flow?.nodes, 10).length - 1}<span class="flow-arrow">→</span>{/if}
        {/each}
      </div>
    </div>

    <div class="visual-box" data-daily-metric-glossary>
      <div class="box-head"><span>Metric Glossary</span><strong>{glossary?.status ?? 'REFERENCE_ONLY'}</strong></div>
      <div class="term-grid">
        {#each rows(glossary?.items, 12) as item}
          <div class="term-card">
            <strong>{item.term}</strong>
            <span>{item.meaning}</span>
            <small>{item.guardrail}</small>
          </div>
        {/each}
      </div>
    </div>


    <div class="visual-box wide" data-daily-research-diagnostics>
      <div class="box-head"><span>D7 Research Diagnostics</span><strong>{researchDiagnostics?.status ?? 'WATCH'}</strong></div>
      <p class="text-muted">{String(researchDiagnostics?.summary?.korean ?? 'D7 연구 진단은 feature/regime/correlation/failure 원인 분석을 위한 읽기 전용 확장 영역입니다.')}</p>
      <div class="term-grid" style="margin-top:12px">
        {#each rows(d7DiagnosticCards(), 8) as item}
          <div class="term-card">
            <strong>{item.id}</strong>
            <span>{item.label} · {item.status}</span>
            <small>{item.summary}</small>
            <small>next: {item.next_artifact}</small>
            <small>{item.guardrail}</small>
            <small>allowed: {item.allowed_use}</small>
            <small>blocked: {item.blocked_use}</small>
            <small>{item.how_to_read_ko}</small>
            <small>gap: {item.current_gap}</small>
          </div>
        {/each}
      </div>
      <div class="mini-list" style="margin-top:12px">
        {#each Object.entries(researchDiagnostics?.summary ?? {}).slice(0, 5) as [label, value]}
          <div><span>{label}</span><strong>{cellText(value)}</strong></div>
        {/each}
      </div>
      <small class="guardrail">{researchDiagnostics?.guardrail ?? 'D7 diagnostics are explanatory research surfaces only; no profit, live, broker, order, or deployable model claim.'}</small>
    </div>

    <div class="visual-box wide" data-daily-equity-overlay>
      <div class="box-head"><span>Equity Overlay</span><strong>{equityOverlay?.status ?? 'NOT_STARTED'}</strong></div>
      <div class="curve-stack">
        {#each rows(equityOverlay?.curves, 6) as curve}
          <div class="curve-row">
            <div class="curve-label"><strong>{curve.label}</strong><small>{curve.kind} · {curve.status}</small></div>
            <div class="sparkline" aria-label="{curve.label} equity preview">
              {#each list(curve.points).slice(0, 42) as point}
                {@const height = sparkHeight(point.y)}
                {#if height === null}
                  <i class="incomplete" title="INCOMPLETE_NUMERIC_EVIDENCE"></i>
                {:else}
                  <i style={`height:${height}%`}></i>
                {/if}
              {/each}
            </div>
          </div>
        {/each}
      </div>
      <small class="guardrail">{equityOverlay?.guardrail}</small>
    </div>

    <div class="visual-box wide" data-daily-walk-forward-heatmap>
      <div class="box-head"><span>Walk-forward Heatmap</span><strong>{heatmap?.model_build_allowed ? 'MODEL BUILD GO' : 'MODEL BUILD LOCK'}</strong></div>
      <div class="heat-grid">
        {#each rows(heatmap?.cells, 48) as cell}
          <div class="heat-cell {severityClass(cell.severity)}">
            <small>{cell.fold_id}</small>
            <strong>{cell.metric}</strong>
            <span>{cell.metric === 'mean_turnover' ? formatNumber(cell.value, 3) : pct(cell.value)}</span>
          </div>
        {/each}
      </div>
      <div class="cost-strip">
        {#each rows(heatmap?.cost_series, 12) as cost}
          <span>{cost.fold_id}:{formatNumber(cost.cost_bp, 0)}bp {pct(cost.total_net_return)}</span>
        {/each}
      </div>
    </div>

    <div class="visual-box" data-daily-run-scatter>
      <div class="box-head"><span>Run Compare Scatter</span><strong>{runScatter?.status ?? 'NOT_STARTED'}</strong></div>
      <div class="scatter-plot">
        <span class="axis x">MDD worse ←</span>
        <span class="axis y">return ↑</span>
        {#each rows(runScatter?.points, 18) as point}
          {@const x = scatterX(point.x_max_drawdown)}
          {@const y = scatterY(point.y_total_net_return)}
          {#if x === null || y === null}
            <i class="scatter-point incomplete" title={`${point.label}: INCOMPLETE_NUMERIC_EVIDENCE`}></i>
          {:else}
            <i class="scatter-point {tone(point.status)}" style={`left:${x}%; top:${y}%`} title={`${point.label}: ${pct(point.y_total_net_return)} / DD ${pct(point.x_max_drawdown)}`}></i>
          {/if}
        {/each}
      </div>
      <div class="mini-list">
        {#each rows(runScatter?.points, 6) as point}
          <div><span>{point.kind}</span><strong>{point.label} · {pct(point.y_total_net_return)}</strong></div>
        {/each}
      </div>
    </div>

    <div class="visual-box wide" data-daily-registry-paper-forward>
      <div class="box-head"><span>D8/D9 Registry · Paper-forward</span><strong>{registry?.promotion_status ?? registry?.status ?? 'NOT_STARTED'}</strong></div>
      <div class="decision-cards">
        <div class="decision-card {registry?.model_build_allowed === true ? 'pass' : 'block'}">
          <small>model_build_allowed</small>
          <strong>{registryFlagText(registry?.model_build_allowed)}</strong>
          <span>strict D5 gate controls promotion</span>
        </div>
        <div class="decision-card {registry?.paper_forward_allowed === true ? 'watch' : 'block'}">
          <small>paper_forward_allowed</small>
          <strong>{registryFlagText(registry?.paper_forward_allowed)}</strong>
          <span>paper-only planning, never orders</span>
        </div>
        <div class="decision-card block">
          <small>live_broker_order_allowed</small>
          <strong>{registryFlagText(registry?.live_broker_order_allowed)}</strong>
          <span>no live/broker/orders</span>
        </div>
        <div class="decision-card block">
          <small>no_live_broker_order_readiness</small>
          <strong>{registry?.no_live_broker_order_readiness === true ? 'true' : 'UNKNOWN_OR_UNSAFE'}</strong>
          <span>true means explicitly not broker/order ready; missing/false is unsafe</span>
        </div>
      </div>
      <div class="mini-list" style="margin-top:12px">
        <div><span>run</span><strong>{registry?.run_id ?? '—'}</strong></div>
        <div><span>config_hash</span><strong>{String(registry?.config_hash ?? '—').slice(0, 16)}</strong></div>
        <div><span>data_hash</span><strong>{String(registry?.data_hash ?? '—').slice(0, 16)}</strong></div>
        <div><span>code_hash</span><strong>{String(registry?.code_hash ?? '—').slice(0, 16)}</strong></div>
      </div>
      <div class="mini-list" data-daily-registry-effective-gates>
        <div><span>effective_gate_blockers</span><strong>{registryEvidenceText(registry?.effective_gate_blockers, 'MISSING_EFFECTIVE_GATE_EVIDENCE')}</strong></div>
        <div><span>invariant_errors</span><strong>{registryEvidenceText(registry?.invariant_errors, 'MISSING_INVARIANT_EVIDENCE')}</strong></div>
        <div><span>read_only_note</span><strong>{registry?.read_only_dashboard_note ?? 'GET-only D8/D9 evidence surface'}</strong></div>
      </div>
      <div class="mini-list" data-daily-registry-hidden-counts>
        <div><span>paper_selected_hidden</span><strong>{registryHiddenCount(registry?.samples?.paper_selected, 3)}</strong></div>
        <div><span>realized_returns_hidden</span><strong>{registryHiddenCount(registry?.samples?.realized_returns, 6)}</strong></div>
        <div><span>drawdown_hidden</span><strong>{registryHiddenCount(registry?.samples?.drawdown, 6)}</strong></div>
        <div><span>drift_hidden</span><strong>{registryHiddenCount(registry?.samples?.drift, 6)}</strong></div>
        <div><span>decision_log_hidden</span><strong>{registryHiddenCount(registry?.samples?.decision_log, 3)}</strong></div>
      </div>
      <div class="term-grid" style="margin-top:12px">
        {#each registryRows(registry?.samples?.drift, 6) as row}
          <div class="term-card">
            <strong>{row.metric ?? row.evidence_status}</strong>
            <span>{row.value ?? row.reason ?? 'MISSING_SAMPLE_EVIDENCE'} · {row.status ?? row.evidence_status}</span>
            <small>{row.action ?? row.reason ?? 'registry drift sample missing or empty'}</small>
          </div>
        {/each}
      </div>
      <div class="table-wrap" style="margin-top:12px; max-height:180px; overflow:auto">
        <table>
          <thead><tr><th>surface</th><th>status/date</th><th>value</th><th>reason/source</th></tr></thead>
          <tbody>
            {#each registryRows(registry?.samples?.paper_selected, 3) as row}
              <tr><td>paper_selected</td><td>{cellText(row.selection_status)}</td><td>{cellText(row.strategy)}</td><td>{cellText(row.reason)}</td></tr>
            {/each}
            {#each registryRows(registry?.samples?.realized_returns, 6) as row}
              <tr><td>realized_returns</td><td>{cellText(row.date)}</td><td>{pct(row.realized_return)}</td><td>{cellText(row.source ?? row.evidence_status ?? row.numeric_error)}</td></tr>
            {/each}
            {#each registryRows(registry?.samples?.drawdown, 6) as row}
              <tr><td>drawdown</td><td>{cellText(row.date)}</td><td>{pct(row.paper_forward_drawdown)}</td><td>{cellText(row.source ?? row.evidence_status ?? row.numeric_error)}</td></tr>
            {/each}
            {#each registryRows(registry?.samples?.decision_log, 3) as row}
              <tr><td>decision_log</td><td>{cellText(row.event)}</td><td>{cellText(row.status)}</td><td>{cellText(row.detail ?? row.reasons)}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
      <small class="guardrail">drawdown source: research_policy_nav_not_live_account · returns source: policy_nav_research_artifact_not_live_trade</small>
      <small class="guardrail">{registry?.guardrail ?? 'D8/D9 registry is research-only; no live/broker/orders or profit claim.'}</small>
    </div>

    <div class="visual-box" data-daily-universe-breakdown>
      <div class="box-head"><span>Universe Breakdown</span><strong>{universeBreakdown?.status ?? 'WATCH'}</strong></div>
      <div class="bar-list">
        {#each entries(universeBreakdown?.counts_by_type, 7) as [label, value]}
          <div class="bar-row"><span>{label}</span><b style={`width:${Math.max(4, value / maxEntry(universeBreakdown?.counts_by_type) * 100)}%`}></b><strong>{value.toLocaleString('ko-KR')}</strong></div>
        {/each}
      </div>
      <div class="mini-list">
        {#each Object.entries(universeBreakdown?.summary ?? {}).slice(0, 6) as [label, value]}
          <div><span>{label}</span><strong>{String(value ?? '—')}</strong></div>
        {/each}
      </div>
    </div>

    <div class="visual-box wide" data-daily-symbol-chart>
      <div class="box-head"><span>Symbol OHLCV Preview</span><strong>{symbolChart?.code ?? 'no symbol'}</strong></div>
      {#if symbolChart?.ohlcv?.length}
        <div class="symbol-bars">
          {#each rows(symbolChart.ohlcv, 60) as point}
            {@const close = finiteNumber(point.close)}
            {@const high = finiteNumber(point.high)}
            {#if close === null || high === null || high === 0}
              <i class="incomplete" title={`${point.date} INCOMPLETE_NUMERIC_EVIDENCE`}></i>
            {:else}
              <i style={`height:${Math.max(8, Math.min(96, close / high * 92))}%`} title={`${point.date} close ${point.close}`}></i>
            {/if}
          {/each}
        </div>
        <small class="guardrail">{symbolChart.guardrail}</small>
        {#if symbolUsageGuideRows().length}
          <div class="mini-list" data-daily-symbol-usage-guide>
            {#each rows(symbolUsageGuideRows(), 3) as guide}
              <div><span>{guide.section ?? 'symbol guide'}</span><strong>{guide.can_do}</strong></div>
              <div><span>금지</span><strong>{guide.must_not}</strong></div>
              <div><span>다음</span><strong>{guide.next_action}</strong></div>
            {/each}
          </div>
        {/if}
      {:else}
        <div class="notice">종목을 선택하면 OHLCV 막대 미리보기가 표시됩니다.</div>
      {/if}
    </div>
  </div>
</section>

<style>
  .visual-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap:14px; }
  .visual-box { border:1px solid var(--border); border-radius:var(--r-lg); padding:14px; background:var(--surface); min-height:220px; }
  .visual-box.wide { grid-column: span 2; }
  .box-head { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:12px; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
  .box-head strong { color:var(--text); font-family:var(--font-mono); }
  .decision-cards, .term-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:8px; }
  .usage-guide { border:1px solid var(--border); border-radius:var(--r-lg); padding:12px; margin-top:14px; background:var(--surface); }
  .guide-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:8px; margin-top:8px; }
  .guide-card { border:1px solid var(--border-faint); border-radius:12px; padding:10px; display:flex; flex-direction:column; gap:5px; font-size:12px; }
  .guide-card strong { font-family:var(--font-mono); }
  .guide-card span, .guide-card small { color:var(--muted); overflow-wrap:anywhere; word-break:break-word; }
  .decision-card, .term-card, .blocker { border:1px solid var(--border-faint); border-radius:12px; padding:10px; display:flex; flex-direction:column; gap:4px; }
  .decision-card strong, .term-card strong, .blocker strong { font-family:var(--font-mono); }
  .decision-card.pass, .heat-cell.pass { border-color:rgba(22,163,74,.5); background:rgba(22,163,74,.08); }
  .decision-card.watch, .heat-cell.watch { border-color:rgba(217,119,6,.5); background:rgba(217,119,6,.08); }
  .decision-card.block, .blocker.block, .heat-cell.block { border-color:rgba(220,38,38,.55); background:rgba(220,38,38,.08); }
  .blocker-list { display:grid; gap:8px; margin-top:10px; }
  .blocker span, .term-card span { color:var(--text); font-size:12px; }
  .blocker small, .term-card small, .decision-card small { color:var(--muted); font-size:11px; }
  .term-card strong, .term-card span, .term-card small { overflow-wrap:anywhere; word-break:break-word; }
  .flow-row { display:flex; align-items:stretch; gap:8px; overflow:auto; padding-bottom:4px; }
  .flow-node { min-width:92px; border:1px solid var(--border-faint); border-radius:14px; padding:10px; text-align:center; display:flex; flex-direction:column; gap:3px; }
  .flow-node.pass { background:rgba(22,163,74,.08); }
  .flow-node.watch { background:rgba(217,119,6,.08); }
  .flow-node.block { background:rgba(220,38,38,.08); }
  .flow-arrow { align-self:center; color:var(--muted); }
  .curve-stack { display:grid; gap:10px; }
  .curve-row { display:grid; grid-template-columns: 180px 1fr; gap:12px; align-items:end; }
  .curve-label { display:flex; flex-direction:column; gap:3px; font-size:12px; }
  .curve-label small, .guardrail { color:var(--muted); font-size:11px; }
  .sparkline, .symbol-bars { height:96px; border:1px solid var(--border-faint); border-radius:12px; display:flex; align-items:end; gap:2px; padding:8px; overflow:hidden; background:linear-gradient(180deg, transparent, rgba(16,185,129,.05)); }
  .sparkline i, .symbol-bars i { flex:1; min-width:3px; border-radius:999px 999px 0 0; background:linear-gradient(180deg, rgba(16,185,129,.95), rgba(59,130,246,.55)); }
  .sparkline i.incomplete, .symbol-bars i.incomplete { background:repeating-linear-gradient(135deg, rgba(100,116,139,.45), rgba(100,116,139,.45) 4px, rgba(148,163,184,.2) 4px, rgba(148,163,184,.2) 8px); height:18%; }
  .heat-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap:6px; }
  .heat-cell { border:1px solid var(--border-faint); border-radius:10px; padding:8px; display:flex; flex-direction:column; gap:3px; font-size:11px; }
  .cost-strip { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; color:var(--muted); font-family:var(--font-mono); font-size:11px; }
  .scatter-plot { position:relative; height:220px; border:1px solid var(--border-faint); border-radius:14px; background:radial-gradient(circle at 70% 25%, rgba(16,185,129,.12), transparent 30%), linear-gradient(90deg, rgba(220,38,38,.08), transparent); overflow:hidden; }
  .scatter-point { position:absolute; width:11px; height:11px; border-radius:999px; background:var(--accent); transform:translate(-50%, -50%); box-shadow:0 0 0 3px rgba(16,185,129,.12); }
  .scatter-point.danger { background:#dc2626; }
  .scatter-point.warn { background:#d97706; }
  .scatter-point.success { background:#16a34a; }
  .scatter-point.incomplete { background:#64748b; box-shadow:0 0 0 3px rgba(100,116,139,.18); left:50%; top:50%; }
  .axis { position:absolute; color:var(--muted); font-size:11px; }
  .axis.x { left:10px; bottom:8px; }
  .axis.y { left:10px; top:8px; }
  .mini-list { display:grid; gap:4px; margin-top:10px; font-size:12px; }
  .mini-list div { display:flex; justify-content:space-between; gap:10px; border-bottom:1px solid var(--border-faint); padding:4px 0; }
  .mini-list span { color:var(--muted); }
  .mini-list strong { overflow-wrap:anywhere; word-break:break-word; text-align:right; }
  .table-wrap table { width:100%; border-collapse:collapse; font-size:12px; table-layout:fixed; }
  .table-wrap th, .table-wrap td { border-bottom:1px solid var(--border-faint); padding:7px; text-align:left; vertical-align:top; overflow-wrap:anywhere; word-break:break-word; }
  .bar-list { display:grid; gap:8px; }
  .bar-row { display:grid; grid-template-columns: 130px 1fr 64px; gap:8px; align-items:center; font-size:12px; }
  .bar-row b { display:block; height:9px; border-radius:999px; background:linear-gradient(90deg, rgba(16,185,129,.35), rgba(16,185,129,.95)); min-width:4px; }
  @media (max-width: 900px) {
    .visual-box.wide { grid-column: span 1; }
    .curve-row { grid-template-columns:1fr; }
  }
</style>
