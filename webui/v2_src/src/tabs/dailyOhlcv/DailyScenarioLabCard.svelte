<script lang="ts">
  import type { DailyScenarioLabResponse } from '$lib/dailyOhlcvApi';

  interface Props {
    scenarioLab: DailyScenarioLabResponse | null;
  }

  let { scenarioLab }: Props = $props();

  const rows = (items: readonly Record<string, unknown>[] | undefined, limit = 10) => (items ?? []).slice(0, limit);
  const listText = (value: unknown): string => Array.isArray(value) ? value.join(' · ') : String(value ?? '—');
  const boolText = (value: unknown): string => value === true ? 'true' : value === false ? 'false' : '—';
  const blockerTone = (row: Record<string, unknown>): string => {
    const status = String(row.status ?? '');
    if (status === 'NO-GO' || status === 'BLOCKED') return 'danger';
    if (status === 'HYPOTHESIS_ONLY' || status === 'RESEARCH_ONLY') return 'warn';
    return '';
  };
</script>

<section class="panel" data-daily-scenario-lab-card>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Scenario Lab · SCENARIO_GENERATOR_MVP</div>
      <h2 class="text-h3">가정·시나리오 생성 플랫폼</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{scenarioLab?.status ?? 'RESEARCH_ONLY'}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    여러 비용·데이터 수리·후보 모델 계약 가정을 한 번에 생성해 비교합니다. 현재 단계는 read-only scenario generation이며 model_run_generation_available=false 입니다. 수익 보장, 실거래, 브로커, 주문 준비 상태가 아니고 no live/broker/orders 가드레일을 유지합니다.
  </p>

  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">scenario_count</div><div class="metric-value tnum">{scenarioLab?.scenario_count ?? 0}</div></div>
    <div class="metric"><div class="metric-label">scenario_generation_available</div><div class="metric-value">{boolText(scenarioLab?.scenario_generation_available)}</div></div>
    <div class="metric"><div class="metric-label">model_run_generation_available</div><div class="metric-value">{boolText(scenarioLab?.model_run_generation_available)}</div></div>
    <div class="metric"><div class="metric-label">read_only</div><div class="metric-value">{boolText(scenarioLab?.read_only)}</div></div>
  </div>

  <div class="scenario-contract" data-daily-scenario-model-contract>
    <strong>Model input contract</strong>
    <span>allowed_inputs: {listText(scenarioLab?.model_input_contract?.allowed_inputs)}</span>
    <span>required_outputs: {listText(scenarioLab?.model_input_contract?.required_outputs)}</span>
    <span>must_not_generate: {listText(scenarioLab?.model_input_contract?.must_not_generate)}</span>
  </div>

  <div class="table-wrap" style="margin-top:12px; max-height:360px; overflow:auto" data-daily-scenario-grid>
    <table>
      <thead><tr><th>scenario</th><th>cost</th><th>status</th><th>assumptions</th><th>blockers</th><th>next artifacts</th></tr></thead>
      <tbody>
        {#each rows(scenarioLab?.scenario_rows, 12) as row}
          <tr class={blockerTone(row)}>
            <td class="mono">{row.scenario_id}</td>
            <td class="tnum">{row.cost_bps}bp</td>
            <td>{row.status}</td>
            <td>{listText(row.assumption_changes)}</td>
            <td>{listText(row.blocking_reasons)}</td>
            <td>{listText(row.required_next_artifacts)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p class="text-muted" style="margin-top:8px">핵심 current scenario marker: cost_23bp_current_evidence. 모델 후보 생성은 scenario_manifest.json과 fresh_oos_walk_forward_manifest.json이 생긴 뒤에만 비교 가능합니다.</p>
</section>

<style>
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th, td { border-bottom:1px solid var(--border-faint); padding:7px; text-align:left; vertical-align:top; }
  .mono { font-family: var(--font-mono); font-size:11px; color:var(--muted); }
  tr.warn td { background:rgba(245, 158, 11, 0.06); }
  tr.danger td { background:rgba(239, 68, 68, 0.06); }
  .scenario-contract { margin-top:16px; padding:12px; border:1px solid var(--border-faint); border-radius:12px; display:grid; gap:6px; font-size:12px; }
</style>
