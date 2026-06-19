<script lang="ts">
  import { onMount } from 'svelte';
  import {
    rlApi,
    type RlCostGateResponse,
    type RlProgressResponse,
    type RlRunDetail,
    type RlRunRecord,
    type RlTableRow,
  } from '$lib/rlApi';
  import { errorMessage } from '$lib/rlRows';
  import RLHero from './rlTrading/RLHero.svelte';
  import OrderbookReadinessCard from './rlTrading/OrderbookReadinessCard.svelte';
  import RiskSummaryCard from './rlTrading/RiskSummaryCard.svelte';
  import RunSelector from './rlTrading/RunSelector.svelte';
  import RunDetailCard from './rlTrading/RunDetailCard.svelte';
  import OpeningWorkflowCard from './rlTrading/OpeningWorkflowCard.svelte';
  import ParticipantProxyCard from './rlTrading/ParticipantProxyCard.svelte';
  import EvidenceCharts from './rlTrading/EvidenceCharts.svelte';
  import RunTables from './rlTrading/RunTables.svelte';
  import { costGatePassCount } from './rlTrading/chartOptions';

  let runs = $state<readonly RlRunRecord[]>([]);
  let selectedName = $state('');
  let selectedRun = $state<RlRunDetail | null>(null);
  let progress = $state<RlProgressResponse | null>(null);
  let costGate = $state<RlCostGateResponse | null>(null);
  let leaderboardRows = $state<readonly RlTableRow[]>([]);
  let trades = $state<readonly RlTableRow[]>([]);
  let actions = $state<readonly RlTableRow[]>([]);
  let equity = $state<readonly RlTableRow[]>([]);
  let episodes = $state<readonly RlTableRow[]>([]);
  let participantProxyRows = $state<readonly RlTableRow[]>([]);
  let orderbookPersistenceRows = $state<readonly RlTableRow[]>([]);
  let participantStudyRows = $state<readonly RlTableRow[]>([]);
  let featureAblationRows = $state<readonly RlTableRow[]>([]);
  let ruleFilterControlRows = $state<readonly RlTableRow[]>([]);
  let ruleFilterAblationRows = $state<readonly RlTableRow[]>([]);
  let ruleFilterFailureRows = $state<readonly RlTableRow[]>([]);
  let loading = $state(false);
  let detailLoading = $state(false);
  let error = $state<string | null>(null);

  const ruleRun = $derived(
    runs.find((run) => run.strategy_context?.line === 'rule_mainline' || run.artifact_type === 'baseline') ?? null
  );
  const openingCandidateRun = $derived(
    runs.find((run) => run.artifact_type === 'opening_30m_rl_workflow' && run.name.includes('oos_candidate')) ??
      runs.find((run) => run.artifact_type === 'opening_30m_rl_workflow') ??
      null
  );
  const readinessRun = $derived(runs.find((run) => run.artifact_type === 'orderbook_rl_readiness') ?? null);
  const gateRows = $derived<readonly RlTableRow[]>(costGate?.gate?.rows ?? []);
  const progressPct = $derived(progress?.overall_progress_pct ?? 0);
  const selectedLabel = $derived(
    selectedRun?.strategy_context?.label ?? ruleRun?.strategy_context?.label ?? 'RULE MAINLINE'
  );

  onMount(() => {
    void loadDashboard();
  });

  function choosePreferredRun(candidates: readonly RlRunRecord[]): RlRunRecord | undefined {
    return (
      candidates.find((run) => run.artifact_type === 'opening_30m_rule_filter') ??
      candidates.find((run) => run.artifact_type === 'opening_30m_rl_workflow' && run.name.includes('oos_candidate')) ??
      candidates.find((run) => run.artifact_type === 'opening_30m_rl_workflow') ??
      candidates.find((run) => run.strategy_context?.line === 'rule_mainline') ??
      candidates.find((run) => run.artifact_type === 'baseline') ??
      candidates.find((run) => run.artifact_type === 'performance_leaderboard') ??
      candidates[0]
    );
  }

  async function loadDashboard(): Promise<void> {
    loading = true;
    error = null;
    try {
      const [runPayload, progressPayload] = await Promise.all([rlApi.rlRuns(50), rlApi.rlProgress()]);
      runs = runPayload?.runs ?? [];
      progress = progressPayload;
      const preferred = choosePreferredRun(runs);
      if (preferred) await selectRun(preferred.name, runs);
    } catch (caught) {
      error = errorMessage(caught, 'RL dashboard load failed');
    } finally {
      loading = false;
    }
  }

  async function loadOptionalRows(name: string, table: string): Promise<readonly RlTableRow[]> {
    try {
      return (await rlApi.rlTable(name, table, 200)).rows ?? [];
    } catch (caught) {
      if (caught instanceof Error) return [];
      throw caught;
    }
  }

  async function selectRun(name: string, runPool: readonly RlRunRecord[] = runs): Promise<void> {
    selectedName = name;
    detailLoading = true;
    error = null;
    try {
      const costRun = runPool.find((run) => run.artifact_type === 'cost_gate');
      const leaderboardRun = runPool.find((run) => run.artifact_type === 'performance_leaderboard');
      const [detail, leaderboard, tradePayload, actionPayload, equityPayload, episodePayload, gatePayload] =
        await Promise.all([
          rlApi.rlRun(name),
          leaderboardRun ? rlApi.rlTable(leaderboardRun.name, 'leaderboard', 200) : Promise.resolve(null),
          rlApi.rlTrades(name, 160),
          rlApi.rlActions(name, 2000),
          rlApi.rlEquity(name, 360),
          rlApi.rlEpisodes(name, 160),
          costRun ? rlApi.rlCostGate(costRun.name, 120) : Promise.resolve(null),
        ]);
      selectedRun = detail;
      ruleFilterControlRows = [];
      ruleFilterAblationRows = [];
      ruleFilterFailureRows = [];
      if (detail.artifact_type === 'opening_30m_rule_filter') {
        const [ruleEquity, ruleBuckets, ruleControls, ruleAblations, ruleFailures, ruleOpportunity, proxyRows, orderbookRows] = await Promise.all([
          loadOptionalRows(name, 'rule_filter_equity_curve'),
          loadOptionalRows(name, 'rule_filter_time_buckets'),
          loadOptionalRows(name, 'rule_filter_controls'),
          loadOptionalRows(name, 'rule_filter_ablations'),
          loadOptionalRows(name, 'rule_filter_failure_reasons'),
          loadOptionalRows(name, 'rule_filter_opportunity_cost'),
          loadOptionalRows(name, 'rule_filter_proxy_availability'),
          loadOptionalRows(name, 'rule_filter_orderbook_persistence'),
        ]);
        leaderboardRows = [];
        costGate = null;
        trades = ruleBuckets;
        actions = ruleFailures;
        equity = ruleEquity;
        episodes = ruleOpportunity;
        participantProxyRows = proxyRows;
        orderbookPersistenceRows = orderbookRows;
        participantStudyRows = [];
        featureAblationRows = ruleAblations;
        ruleFilterControlRows = ruleControls;
        ruleFilterAblationRows = ruleAblations;
        ruleFilterFailureRows = ruleFailures;
      } else if (detail.artifact_type === 'opening_30m_rl_workflow') {
        const [candidateEquity, candidateBuckets, candidateControls, candidateAblations, proxyRows, orderbookRows, studyRows, ablationRows] = await Promise.all([
          loadOptionalRows(name, 'candidate_equity_curve'),
          loadOptionalRows(name, 'candidate_time_buckets'),
          loadOptionalRows(name, 'candidate_controls'),
          loadOptionalRows(name, 'candidate_ablations'),
          loadOptionalRows(name, 'proxy_availability'),
          loadOptionalRows(name, 'orderbook_persistence'),
          loadOptionalRows(name, 'participant_study_groups'),
          loadOptionalRows(name, 'feature_ablation'),
        ]);
        leaderboardRows = [];
        costGate = null;
        trades = candidateBuckets;
        actions = [];
        equity = candidateEquity;
        episodes = candidateControls;
        participantProxyRows = proxyRows;
        orderbookPersistenceRows = orderbookRows;
        participantStudyRows = studyRows;
        featureAblationRows = candidateAblations.length ? candidateAblations : ablationRows;
      } else {
        leaderboardRows = leaderboard?.rows ?? [];
        trades = tradePayload?.rows ?? [];
        actions = actionPayload?.rows ?? [];
        equity = equityPayload?.rows ?? [];
        episodes = episodePayload?.rows ?? [];
        costGate = gatePayload;
        participantProxyRows = [];
        orderbookPersistenceRows = [];
        participantStudyRows = [];
        featureAblationRows = [];
        ruleFilterControlRows = [];
        ruleFilterAblationRows = [];
        ruleFilterFailureRows = [];
      }
    } catch (caught) {
      error = errorMessage(caught, `${name} detail load failed`);
    } finally {
      detailLoading = false;
    }
  }
</script>

<RLHero progressPct={progressPct} costGatePassCount={costGatePassCount(gateRows)} />
{#if error}
  <section class="card error-card">
    <div class="card-title">강화학습 대시보드 조회 실패</div>
    <p class="text-muted">{error}</p>
  </section>
{/if}
<OrderbookReadinessCard run={readinessRun ?? openingCandidateRun} />
<section class="rl-layout">
  <RunSelector runs={runs} selectedName={selectedName} onSelect={(name) => void selectRun(name)} />
  <div class="stack" style="--gap:16px;min-width:0">
    {#if loading && !runs.length}
      <section class="card"><p class="text-muted">강화학습 산출물을 불러오는 중...</p></section>
    {/if}
    <RiskSummaryCard ruleRun={ruleRun} selectedLabel={selectedLabel} />
    <RunDetailCard run={selectedRun} loading={detailLoading} />
    <OpeningWorkflowCard run={selectedRun} {progress} />
    <ParticipantProxyCard
      run={selectedRun}
      proxyRows={participantProxyRows}
      orderbookRows={orderbookPersistenceRows}
      studyRows={participantStudyRows}
      ablationRows={featureAblationRows}
    />
    <EvidenceCharts
      {leaderboardRows}
      gateRows={gateRows}
      equityRows={equity}
      actionRows={actions}
      episodeRows={episodes}
      tradeRows={trades}
      {selectedName}
    />
    <RunTables leaderboardRows={leaderboardRows} tradeRows={trades} ruleFilterControlRows={ruleFilterControlRows} ruleFilterAblationRows={ruleFilterAblationRows} ruleFilterFailureRows={ruleFilterFailureRows} />
  </div>
</section>

<style>
  .rl-layout {
    display: grid;
    grid-template-columns: minmax(220px, 300px) minmax(0, 1fr);
    gap: 18px;
    align-items: start;
  }
  :global(.run-list) {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 620px;
    overflow: auto;
  }
  :global(.run-list button) {
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--card);
    padding: 10px;
    text-align: left;
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }
  :global(.run-list button.active) {
    border-color: #14b8a6;
    box-shadow: 0 0 0 2px rgba(20, 184, 166, 0.16);
  }
  :global(.mini-grid) {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
  }
  :global(.mini-grid div) {
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 10px;
    background: rgba(148, 163, 184, 0.06);
  }
  :global(.mini-grid span) {
    display: block;
    color: var(--text-muted);
    font-size: 12px;
    margin-bottom: 4px;
  }
  :global(.chart-grid) {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 16px;
  }
  :global(.safety-note) {
    margin-top: 10px;
  }
  @media (max-width: 900px) {
    .rl-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
