<script lang="ts">
  import type { DailyDatasetChartResponse, DailyDatasetResponse } from '$lib/dailyOhlcvApi';

  interface Props {
    dataset: DailyDatasetResponse | null;
    chart: DailyDatasetChartResponse | null;
  }

  let { dataset, chart }: Props = $props();

  const num = (value: unknown) => typeof value === 'number' ? value.toLocaleString('ko-KR') : (value ?? '—');
  function recordValue(record: Record<string, unknown> | undefined, key: string): unknown {
    return record?.[key] ?? '—';
  }

  function stringList(record: Record<string, unknown> | undefined, key: string): string[] {
    const value = record?.[key];
    return Array.isArray(value) ? value.map((item) => String(item)) : [];
  }
  const listValue = (value: readonly string[] | undefined) => value?.length ? value : ['—'];
  const guidanceValue = (row: Readonly<Record<string, unknown>>, key: string) => typeof row[key] === 'string' ? row[key] : String(row[key] ?? '—');

  function featureStats(record: Record<string, unknown> | undefined): Array<[string, Record<string, unknown>]> {
    const features = record?.features;
    if (!features || typeof features !== 'object' || Array.isArray(features)) return [];
    return Object.entries(features as Record<string, Record<string, unknown>>).slice(0, 8);
  }
  function recordEntries(record: unknown): Array<[string, Record<string, unknown>]> {
    if (!record || typeof record !== 'object' || Array.isArray(record)) return [];
    return Object.entries(record as Record<string, Record<string, unknown>>);
  }

  function intervalList(value: unknown): Array<Record<string, unknown>> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
    const intervals = (value as Record<string, unknown>).intervals;
    return Array.isArray(intervals) ? intervals as Array<Record<string, unknown>> : [];
  }


  function tone(status: string | undefined): string {
    if (status === 'PASS') return 'success';
    if (status === 'WATCH' || status === 'RUNNING') return 'warn';
    if (status === 'NO-GO' || status === 'BLOCKED') return 'danger';
    return '';
  }
</script>

<section class="panel" data-daily-ohlcv-dataset-card>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">D2 Dataset Builder</div>
      <h2 class="text-h3">일봉 데이터셋·누수 점검</h2>
    </div>
    <span class="pill {tone(dataset?.status)}"><span class="dot"></span>{dataset?.status ?? 'NOT_STARTED'}</span>
  </div>

  <p class="text-muted" style="margin-top:8px">
    D2는 학습/강화학습 실행이 아니라, 코스피·코스닥 보통주 유니버스에서 누수 없는 feature/label/split 증거를 만드는 단계입니다. 수익·실거래·주문 준비 주장이 아닙니다. no training/order/live/profit.
  </p>

  {#if dataset?.status === 'NOT_STARTED' || !dataset}
    <div class="notice" style="margin-top:12px">D2 데이터셋 artifact가 아직 없습니다. D3/D4/D5는 잠금 상태입니다.</div>
  {:else}
    <div class="grid-4-kpi" style="margin-top:16px">
      <div class="metric"><div class="metric-label">run</div><div class="metric-value tnum" style="font-size:18px">{dataset.run_id ?? '—'}</div></div>
      <div class="metric"><div class="metric-label">scope</div><div class="metric-value">{dataset.artifact_scope ?? '—'}</div></div>
      <div class="metric"><div class="metric-label">features</div><div class="metric-value tnum">{num(dataset.row_counts?.feature_rows)}</div></div>
      <div class="metric"><div class="metric-label">eligible</div><div class="metric-value tnum">{num(dataset.row_counts?.eligible_rows)}</div></div>
    </div>

    <div class="grid-4-kpi" style="margin-top:12px">
      <div class="metric"><div class="metric-label">leakage</div><div class="metric-value">{dataset.leakage_status ?? '—'}</div></div>
      <div class="metric"><div class="metric-label">split</div><div class="metric-value">{dataset.split_chronology_status ?? '—'}</div></div>
      <div class="metric"><div class="metric-label">price_basis</div><div class="metric-value">{dataset.price_basis ?? 'unknown'}</div></div>
      <div class="metric"><div class="metric-label">universe</div><div class="metric-value" style="font-size:18px">{dataset.universe_verdict ?? '—'}</div></div>
      <div class="metric"><div class="metric-label">upstream blockers</div><div class="metric-value" style="font-size:18px">{dataset.upstream_gate_blockers?.length ?? 0}</div></div>
      <div class="metric"><div class="metric-label">D1 certification</div><div class="metric-value" style="font-size:16px">{dataset.universe_certification_status ?? 'BLOCKED'}</div></div>
    </div>

    <div class="notice warn" style="margin-top:12px">
      {dataset.model_readiness ?? 'DATASET_RESEARCH_PREVIEW_BLOCKED_BY_MISSING_READINESS_EVIDENCE'} · D3 베이스라인과 D5 워크포워드 전에는 RL 수익 모델 생성/GO 요약을 열지 않습니다.
    </div>
    <div class="notice warn" style="margin-top:12px" data-daily-dataset-upstream-blockers>
      <strong>상위 차단:</strong>
      {listValue(dataset.upstream_gate_blockers).join(', ')} ·
      <span>blocked uses: {listValue(dataset.dataset_blocked_uses).join(', ')}</span>
    </div>
    <div class="table-wrap mini" style="margin-top:12px" data-daily-dataset-user-guidance>
      <table>
        <thead><tr><th>section</th><th>meaning</th><th>action</th></tr></thead>
        <tbody>
          {#each dataset.dataset_user_guidance ?? [] as row}
            <tr>
              <td>{guidanceValue(row, 'section')}</td>
              <td>{guidanceValue(row, 'meaning')}</td>
              <td>{guidanceValue(row, 'action')}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="evidence-grid" style="margin-top:16px">
      <div class="evidence-box" data-daily-dataset-manifest-detail>
        <div class="text-eyebrow">Manifest provenance</div>
        <div class="mini-kv"><span>manifest_sha</span><strong class="tnum">{dataset.manifest_sha ?? '—'}</strong></div>
        <div class="mini-kv"><span>universe_manifest_sha</span><strong class="tnum">{dataset.universe_manifest_sha ?? '—'}</strong></div>
        <div class="mini-kv"><span>cost_round_trip_bp</span><strong>{num(dataset.cost_assumption_round_trip_bp)}</strong></div>
        <div class="mini-kv"><span>purge_days</span><strong>{num(dataset.split_policy?.purge_days)}</strong></div>
        <div class="mini-kv"><span>embargo_days</span><strong>{num(dataset.split_policy?.embargo_days)}</strong></div>
      </div>
      <div class="evidence-box" data-daily-dataset-split-intervals>
        <div class="text-eyebrow">Purge/embargo & blocked intervals</div>
        {#each recordEntries(dataset.split_summary?.date_ranges) as [split, range]}
          <div class="interval-row">
            <strong>{split}</strong>
            <span>{intervalList(range).map((item) => `${item.start ?? '—'}→${item.end ?? '—'}`).join(', ') || `${range.start ?? '—'}→${range.end ?? '—'}`}</span>
          </div>
        {/each}
      </div>
    </div>

    <div class="split-bars" style="margin-top:16px">
      {#each chart?.split_series ?? [] as item}
        <div class="bar-row">
          <span>{item.label}</span>
          <div class="bar"><i style={`width:${Math.min(100, Number(item.value || 0) / Math.max(1, Number(dataset.row_counts?.split_assignment_rows || item.value || 1)) * 100)}%`}></i></div>
          <strong class="tnum">{num(item.value)}</strong>
        </div>
      {/each}
    </div>

    <div class="evidence-grid" style="margin-top:16px">
      <div class="evidence-box" data-daily-dataset-leakage-detail>
        <div class="text-eyebrow">Leakage report detail</div>
        <div class="mini-kv"><span>status</span><strong>{recordValue(dataset.leakage_report, 'status')}</strong></div>
        <div class="mini-kv"><span>forbidden_feature_columns</span><strong>{stringList(dataset.leakage_report, 'forbidden_feature_columns').join(', ') || '[]'}</strong></div>
        <div class="mini-kv"><span>split_chronology_status</span><strong>{recordValue(dataset.leakage_report, 'split_chronology_status')}</strong></div>
        <ul>
          {#each stringList(dataset.leakage_report, 'checks') as check}
            <li>{check}</li>
          {/each}
        </ul>
      </div>
      <div class="evidence-box" data-daily-dataset-normalization-detail>
        <div class="text-eyebrow">Normalization stats detail</div>
        <div class="mini-kv"><span>fit_split</span><strong>{recordValue(dataset.normalization_stats, 'fit_split')}</strong></div>
        <div class="mini-kv"><span>fit_row_count</span><strong>{num(recordValue(dataset.normalization_stats, 'fit_row_count'))}</strong></div>
        <div class="norm-list">
          {#each featureStats(dataset.normalization_stats) as [name, stats]}
            <div><span>{name}</span><strong>{String(stats.status ?? '—')} · n={num(stats.count)}</strong></div>
          {/each}
        </div>
      </div>
    </div>

    <div class="table-wrap" data-daily-dataset-blocked-windows style="margin-top:16px; max-height:180px; overflow:auto">
      <table>
        <thead><tr><th>blocked date</th><th>code</th><th>previous</th><th>reason</th></tr></thead>
        <tbody>
          {#each dataset.samples?.blocked_windows ?? [] as row}
            <tr>
              <td class="tnum">{row.date}</td>
              <td class="tnum">{row.code}</td>
              <td class="tnum">{row.previous_date}</td>
              <td>{row.reason}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="table-wrap" style="margin-top:16px; max-height:260px; overflow:auto">
      <table>
        <thead><tr><th>date</th><th>code</th><th>split</th><th>eligible</th><th>block</th></tr></thead>
        <tbody>
          {#each dataset.samples?.split_assignments ?? [] as row}
            <tr>
              <td class="tnum">{row.date}</td>
              <td class="tnum">{row.code}</td>
              <td>{row.split}</td>
              <td>{row.eligible_for_training}</td>
              <td>{row.block_reason ?? '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<style>
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th, td { border-bottom:1px solid var(--border-faint); padding:7px; text-align:left; vertical-align:top; }
  .evidence-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:12px; }
  .evidence-box { border:1px solid var(--border); border-radius:var(--r-lg); padding:12px; background:var(--surface); }
  .evidence-box ul { margin:8px 0 0; padding-left:18px; color:var(--muted); font-size:12px; }
  .mini-kv, .norm-list div { display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid var(--border-faint); padding:6px 0; font-size:12px; }
  .mini-kv span, .norm-list span { color:var(--muted); }
  .interval-row { display:grid; grid-template-columns: 160px 1fr; gap:10px; border-bottom:1px solid var(--border-faint); padding:6px 0; font-size:12px; }
  .interval-row span { color:var(--muted); }
  .split-bars { display:grid; gap:8px; }
  .bar-row { display:grid; grid-template-columns: 190px 1fr 90px; align-items:center; gap:10px; color:var(--muted); font-size:12px; }
  .bar { height:8px; border-radius:999px; background:var(--surface-muted); overflow:hidden; }
  .bar i { display:block; height:100%; border-radius:999px; background:var(--accent); }
</style>
