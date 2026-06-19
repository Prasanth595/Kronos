<script lang="ts">
  import { num, text } from '$lib/rlRows';
  import type { JsonValue, RlProgressResponse, RlRunDetail, RlTableRow } from '$lib/rlApi';

  interface Props { readonly run: RlRunDetail | null; readonly progress: RlProgressResponse | null }
  let { run, progress }: Props = $props();

  function isTableRow(value: JsonValue): value is RlTableRow {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  function asRows(value: JsonValue | undefined): readonly RlTableRow[] {
    if (!Array.isArray(value)) return [];
    return value.filter(isTableRow);
  }

  function asTextRows(value: JsonValue | undefined, key: string): readonly RlTableRow[] {
    if (!Array.isArray(value)) return [];
    return value.map((item) => ({ [key]: String(item) }));
  }

  function objectValue(value: JsonValue | undefined, key: string): JsonValue | undefined {
    return isTableRow(value) ? value[key] : undefined;
  }

  const isOpeningRun = $derived(run?.artifact_type === 'opening_30m_rl_workflow');
  const isRuleFilterRun = $derived(run?.artifact_type === 'opening_30m_rule_filter');
  const panelEyebrow = $derived(isRuleFilterRun ? 'OPENING 30M RULE FILTER' : 'OPENING 30M RL WORKFLOW');
  const panelTitle = $derived(isRuleFilterRun ? 'RULE FILTER evidence panel' : 'RL EXPERIMENT evidence panel');
  const safetyNote = $derived(
    isRuleFilterRun
      ? 'rule/meta-label evidence · OOS BASELINE · negative controls · feature ablation / FEATURE ABLATION · FAILURE REASONS · cumulative equity curve · time-bucket performance · ts_imb RULE baseline · 23bp · not live-ready · not a profit model. Execution controls and training actions are intentionally absent.'
      : 'OPENING 30M RL CANDIDATES · OOS BASELINE · negative controls · feature ablation / FEATURE ABLATION · CONTEXT FEATURE SAMPLE · FAILURE REASONS · cumulative equity curve · time-bucket performance · ts_imb RULE baseline · 23bp · not live-ready · CUMULATIVE REWARD EVIDENCE only. Execution controls and training actions are intentionally absent.'
  );
  const summary = $derived(run?.summary ?? {});
  const detail = $derived(run?.detail ?? {});
  const stageRows = $derived(asRows(detail['stages']));
  const config = $derived(objectValue(detail['config'], 'cost_bps'));
  const progressPage = $derived(progress?.pages.find((page) => page.page === 'Opening 30M RL Workflow') ?? null);
  const lifecycle = $derived(objectValue(detail['candidate_lifecycle'], 'training') ? detail['candidate_lifecycle'] : undefined);
  const training = $derived(objectValue(lifecycle, 'training'));
  const gate = $derived(objectValue(lifecycle, 'promotion_gate'));
  const splitManifest = $derived(objectValue(lifecycle, 'split_manifest'));
  const controls = $derived(objectValue(lifecycle, 'controls'));
  const ablations = $derived(objectValue(lifecycle, 'ablations'));
  const contextFeatures = $derived(objectValue(lifecycle, 'context_features'));
  const candidateRows = $derived(asRows(objectValue(training, 'candidates')));
  const controlRows = $derived(asRows(objectValue(controls, 'controls')));
  const ablationRows = $derived(asRows(objectValue(ablations, 'ablations')));
  const equityRows = $derived(asRows(objectValue(gate, 'equity_curve')));
  const timeBucketRows = $derived(asRows(objectValue(gate, 'time_bucket_performance')));
  const failureRows = $derived(asTextRows(objectValue(gate, 'blocking_reasons'), 'reason'));
  const contextNames = $derived(asTextRows(objectValue(contextFeatures, 'feature_names'), 'feature_name'));
  const contextStatus = $derived(String(objectValue(contextFeatures, 'status') ?? 'missing'));
  const verdict = $derived(
    String(objectValue(gate, 'verdict') ?? summary['candidate_verdict'] ?? summary['verdict'] ?? detail['verdict'] ?? progress?.evidence?.['latest_opening_workflow_verdict'] ?? 'NO-GO')
  );
  const costBps = $derived(summary['cost_bps'] ?? config ?? 23);
  const splitHash = $derived(String(summary['split_hash'] ?? objectValue(splitManifest, 'split_hash') ?? '-'));
  const controlStage = $derived(stageRows.find((row) => text(row, 'name') === 'controls') ?? null);
  const controlStatus = $derived(text(controlStage, 'status', 'NO-GO'));
  const baselineDelta = $derived(summary['baseline_delta_pct'] ?? summary['baseline_delta'] ?? '-');
</script>

<section class="card" data-rl-opening-workflow-card>
  <div class="card-header">
    <div>
      <div class="card-eyebrow">{panelEyebrow}</div>
      <div class="card-title">{panelTitle}</div>
    </div>
    <span class="pill danger"><span class="dot"></span>{verdict}</span>
  </div>
  <p class="text-caption safety-note">
    {safetyNote}
  </p>
  <div class="mini-grid">
    <div><span>Artifact</span><strong>{run?.artifact_type ?? 'opening_30m_rl_workflow'}</strong></div>
    <div><span>Cost</span><strong>{num(costBps, 1)}bp</strong></div>
    <div><span>Split hash</span><strong>{splitHash}</strong></div>
    <div><span>Candidates</span><strong>{candidateRows.length}</strong></div>
    <div><span>Baseline delta</span><strong>{String(baselineDelta)}</strong></div>
    <div><span>Controls</span><strong>{controlStatus}</strong></div>
  </div>
  {#if isOpeningRun && candidateRows.length}
    <div class="table-wrap" style="margin-top:12px">
      <table>
        <thead><tr><th>candidate</th><th>algo</th><th>status</th><th>OOS net</th><th>model path</th></tr></thead>
        <tbody>
          {#each candidateRows.slice(0, 8) as row}
            <tr>
              <td>{text(row, 'candidate_id')}</td>
              <td>{text(row, 'algorithm')}</td>
              <td>{text(row, 'status')}</td>
              <td>{String(row['oos_net_return_pct'] ?? '-')}</td>
              <td>{text(row, 'model_path', '-')}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
  {#if isOpeningRun && (controlRows.length || ablationRows.length)}
    <div class="table-wrap" style="margin-top:12px">
      <table>
        <thead><tr><th>evidence</th><th>id</th><th>verdict/status</th><th>delta / source</th></tr></thead>
        <tbody>
          {#each controlRows.slice(0, 4) as row}
            <tr><td>OOS BASELINE / negative control</td><td>{text(row, 'control_type')}</td><td>{text(row, 'verdict', 'NO-GO')}</td><td>{text(row, 'evaluation_source', '-')}</td></tr>
          {/each}
          {#each ablationRows.slice(0, 5) as row}
            <tr><td>FEATURE ABLATION</td><td>{text(row, 'feature_set_id')}</td><td>{text(row, 'comparison_status', text(row, 'passed', 'NO-GO'))}</td><td>{text(row, 'delta_vs_full_oos_pct', '-')}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
  {#if isOpeningRun && (equityRows.length || timeBucketRows.length || failureRows.length || contextNames.length)}
    <div class="table-wrap" style="margin-top:12px">
      <table>
        <thead><tr><th>panel</th><th>item</th><th>value</th></tr></thead>
        <tbody>
          {#each equityRows.slice(0, 4) as row}
            <tr><td>cumulative equity curve</td><td>{text(row, 'step')}</td><td>{text(row, 'net_return_pct')}</td></tr>
          {/each}
          {#each timeBucketRows.slice(0, 4) as row}
            <tr><td>time-bucket performance</td><td>{text(row, 'bucket')}</td><td>{text(row, 'net_return_pct')}</td></tr>
          {/each}
          {#each failureRows.slice(0, 4) as row}
            <tr><td>FAILURE REASONS</td><td>{text(row, 'reason')}</td><td>NO-GO visible</td></tr>
          {/each}
          {#each contextNames.slice(0, 4) as row}
            <tr><td>CONTEXT FEATURE SAMPLE</td><td>{text(row, 'feature_name')}</td><td>{contextStatus}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
  {#if isOpeningRun && stageRows.length}
    <div class="table-wrap" style="margin-top:12px">
      <table>
        <thead><tr><th>stage</th><th>status</th><th>evidence</th></tr></thead>
        <tbody>
          {#each stageRows.slice(0, 10) as row}
            <tr><td>{text(row, 'name')}</td><td>{text(row, 'status')}</td><td>{text(row, 'evidence', text(row, 'reason'))}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else if progressPage?.criteria?.length}
    <div class="table-wrap" style="margin-top:12px">
      <table>
        <thead><tr><th>criterion</th><th>status</th><th>evidence</th></tr></thead>
        <tbody>
          {#each progressPage.criteria.slice(0, 10) as criterion}
            <tr><td>{criterion.label}</td><td>{criterion.passed ? 'passed' : 'NO-GO'}</td><td>{criterion.evidence ?? '-'}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <p class="text-muted">Select an opening_30m_rl_workflow run to inspect stage evidence.</p>
  {/if}
</section>