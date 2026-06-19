<script lang="ts">
  import { num, text } from '$lib/rlRows';
  import type { RlRunDetail, RlTableRow } from '$lib/rlApi';

  interface Props {
    readonly run: RlRunDetail | null;
    readonly proxyRows: readonly RlTableRow[];
    readonly orderbookRows: readonly RlTableRow[];
    readonly studyRows: readonly RlTableRow[];
    readonly ablationRows: readonly RlTableRow[];
  }
  let { run, proxyRows, orderbookRows, studyRows, ablationRows }: Props = $props();
  const missingProxyColumns = $derived(run?.summary?.['missing_proxy_columns']);
  const missingText = $derived(Array.isArray(missingProxyColumns) ? missingProxyColumns.join(', ') : '-');
  const evidenceLabel = $derived(
    run?.artifact_type === 'opening_30m_rule_filter'
      ? 'RULE FILTER EVIDENCE'
      : (run?.strategy_context?.label ?? 'RESEARCH EVIDENCE')
  );
</script>

<section class="card" data-rl-participant-proxy-card>
  <div class="card-header">
    <div>
      <div class="card-eyebrow">PARTICIPANT PROXY EVIDENCE</div>
      <div class="card-title">ORDERBOOK PERSISTENCE · PROXY AVAILABILITY · FEATURE ABLATION</div>
    </div>
    <span class="pill danger"><span class="dot"></span>NO-GO visible</span>
  </div>
  <p class="text-caption safety-note">
    {evidenceLabel} · 23bp · not live-ready · participant proxy evidence only; actor identity is not inferred.
  </p>
  <div class="mini-grid">
    <div><span>Missing proxy columns</span><strong>{missingText}</strong></div>
    <div><span>Proxy rows</span><strong>{num(proxyRows.length, 0)}</strong></div>
    <div><span>Orderbook components</span><strong>{num(orderbookRows.length, 0)}</strong></div>
    <div><span>Ablations</span><strong>{num(ablationRows.length, 0)}</strong></div>
  </div>
  <div class="table-wrap" style="margin-top:12px">
    <table>
      <thead><tr><th>proxy</th><th>status</th><th>source</th></tr></thead>
      <tbody>
        {#each proxyRows.slice(0, 8) as row}
          <tr><td>{text(row, 'proxy')}</td><td>{text(row, 'status')}</td><td>{text(row, 'source_column', text(row, 'feature_group'))}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
  <div class="table-wrap" style="margin-top:12px">
    <table>
      <thead><tr><th>orderbook component</th><th>value</th><th>study / ablation</th></tr></thead>
      <tbody>
        {#each orderbookRows.slice(0, 6) as row}
          <tr><td>{text(row, 'component')}</td><td>{num(row.value, 3)}</td><td>ORDERBOOK PERSISTENCE</td></tr>
        {/each}
        {#each studyRows.slice(0, 3) as row}
          <tr><td>{text(row, 'group')}</td><td>{num(row.episode_count, 0)}</td><td>participant study</td></tr>
        {/each}
        {#each ablationRows.slice(0, 3) as row}
          <tr><td>{text(row, 'feature_ablation', text(row, 'feature_set_id'))}</td><td>{text(row, 'verdict', String(row.passed ?? 'NO-GO'))}</td><td>FEATURE ABLATION</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>
