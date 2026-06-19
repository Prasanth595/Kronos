<script lang="ts">
  import type { DailyScenarioRunLedgerResponse } from '$lib/dailyOhlcvApi';

  interface Props {
    ledger: DailyScenarioRunLedgerResponse | null;
  }

  let { ledger }: Props = $props();

  const rows = (items: readonly Record<string, unknown>[] | undefined, limit = 8) => (items ?? []).slice(0, limit);
  const listText = (value: unknown): string => Array.isArray(value) ? value.join(' · ') : String(value ?? '—');
  const boolText = (value: unknown): string => value === true ? 'true' : value === false ? 'false' : '—';
  const recordText = (value: unknown): string => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return '—';
    return Object.entries(value as Record<string, unknown>).map(([key, count]) => `${key}:${count}`).join(' · ');
  };
  const tone = (status: unknown): string => {
    const normalized = String(status ?? '').toUpperCase();
    if (normalized.includes('ERROR') || normalized.includes('NO-GO')) return 'danger';
    if (normalized.includes('RESEARCH') || normalized.includes('DRY_RUN')) return 'warn';
    return '';
  };
</script>

<section class="panel" data-daily-scenario-run-ledger>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Scenario Run Ledger · SCENARIO_BATCH_RUNNER_MVP</div>
      <h2 class="text-h3">실행된 가정·시나리오 모델 비교</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{ledger?.status ?? 'RESEARCH_ONLY'}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    대시보드는 read-only 입니다. 여러 모델/가정 실행은 명시적 CLI인 stom_rl.daily_scenario_batch 또는 stom_rl.daily_scenario_runner 로만 생성하고, 여기서는 scenario_batch_manifest.json 과 scenario_manifest.json 을 비교합니다. no live/broker/orders 및 수익 보장 금지 가드레일은 항상 유지합니다.
  </p>

  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">scenario runs</div><div class="metric-value tnum">{ledger?.scenario_run_count ?? 0}</div></div>
    <div class="metric"><div class="metric-label">batches</div><div class="metric-value tnum">{ledger?.batch_count ?? 0}</div></div>
    <div class="metric"><div class="metric-label">model_run_generation_available</div><div class="metric-value">{boolText(ledger?.model_run_generation_available)}</div></div>
    <div class="metric"><div class="metric-label">dashboard_mutation_available</div><div class="metric-value">{boolText(ledger?.dashboard_mutation_available)}</div></div>
  </div>

  <div class="command-list" data-daily-scenario-batch-commands>
    <strong>가장 빠른 실행 명령</strong>
    {#each ledger?.quick_start_commands ?? ['py -3.11 -m stom_rl.daily_scenario_batch --emit-template'] as command}
      <code>{command}</code>
    {/each}
    <span class="text-muted">required_controls: {listText(ledger?.required_controls)}</span>
  </div>

  <div class="table-wrap" style="margin-top:12px; max-height:320px; overflow:auto" data-daily-scenario-batch-grid>
    <table>
      <thead><tr><th>batch</th><th>status</th><th>scenarios</th><th>gate counts</th><th>artifact</th></tr></thead>
      <tbody>
        {#each rows(ledger?.batches) as batch}
          <tr class={tone(batch.status)}>
            <td class="mono">{batch.batch_id}</td>
            <td>{batch.status}</td>
            <td class="tnum">{batch.scenario_count}</td>
            <td>{recordText(batch.gate_status_counts)}</td>
            <td class="mono">scenario_batch_manifest.json</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  <div class="table-wrap" style="margin-top:12px; max-height:360px; overflow:auto" data-daily-scenario-run-grid>
    <table>
      <thead><tr><th>run</th><th>status</th><th>strategy</th><th>fold/purge/embargo</th><th>costs</th><th>blockers</th></tr></thead>
      <tbody>
        {#each rows(ledger?.runs, 10) as run}
          <tr class={tone(run.status)}>
            <td class="mono">{run.run_id}</td>
            <td>{run.status}</td>
            <td>{run.selected_strategy ?? '—'}</td>
            <td class="tnum">{run.n_folds ?? '—'} / {run.purge_days ?? '—'} / {run.embargo_days ?? '—'}</td>
            <td>{listText(run.cost_sensitivity_bp)}</td>
            <td>{listText(run.blocking_reasons)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p class="text-muted" style="margin-top:8px">comparison_rows 는 배치 manifest 안에 저장되며, GO/NO-GO는 D5 게이트와 0/23/46bp 비용 민감도 기준으로만 읽습니다.</p>
</section>

<style>
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th, td { border-bottom:1px solid var(--border-faint); padding:7px; text-align:left; vertical-align:top; }
  .mono { font-family: var(--font-mono); font-size:11px; color:var(--muted); }
  tr.warn td { background:rgba(245, 158, 11, 0.06); }
  tr.danger td { background:rgba(239, 68, 68, 0.06); }
  .command-list { margin-top:16px; padding:12px; border:1px solid var(--border-faint); border-radius:12px; display:grid; gap:8px; }
  code { display:block; white-space:pre-wrap; font-family:var(--font-mono); font-size:12px; color:var(--text); }
</style>
