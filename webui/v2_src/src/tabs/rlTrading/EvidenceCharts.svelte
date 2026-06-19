<script lang="ts">
  import EChartsRenderer from '../../charts/EChartsRenderer.svelte';
  import type { RlTableRow } from '$lib/rlApi';
  import { actionPnlChartOption, costGateChartOption, equityChartOption, leaderboardChartOption, tradeChartOption } from './chartOptions';

  interface Props {
    readonly leaderboardRows: readonly RlTableRow[];
    readonly gateRows: readonly RlTableRow[];
    readonly equityRows: readonly RlTableRow[];
    readonly actionRows: readonly RlTableRow[];
    readonly episodeRows: readonly RlTableRow[];
    readonly tradeRows: readonly RlTableRow[];
    readonly selectedName: string;
  }
  let { leaderboardRows, gateRows, equityRows, actionRows, episodeRows, tradeRows, selectedName }: Props = $props();
  const leaderboardOption = $derived(leaderboardChartOption(leaderboardRows));
  const costGateOption = $derived(costGateChartOption(gateRows));
  const equityOption = $derived(equityChartOption(equityRows));
  const actionPnlOption = $derived(actionPnlChartOption(actionRows, episodeRows, selectedName));
  const tradeOption = $derived(tradeChartOption(tradeRows));
</script>

<section class="chart-grid">
  <section class="card" data-rl-leaderboard-chart>
    <div class="card-title">Performance leaderboard</div>
    {#if leaderboardRows.length}<EChartsRenderer option={leaderboardOption} height="300px" />{:else}<p class="empty">No leaderboard rows.</p>{/if}
  </section>
  <section class="card" data-rl-cost-gate-table>
    <div class="card-title">23bp cost gate evidence</div>
    {#if gateRows.length}<EChartsRenderer option={costGateOption} height="300px" />{:else}<p class="empty">No cost gate rows.</p>{/if}
  </section>
  <section class="card">
    <div class="card-title">CUMULATIVE REWARD EVIDENCE + ts_imb baseline</div>
    {#if actionRows.length}<EChartsRenderer option={actionPnlOption} height="300px" />{:else}<p class="empty">No actions/live event data for cumulative reward evidence.</p>{/if}
  </section>
  <section class="card">
    <div class="card-title">Time equity curve / net-return evidence</div>
    {#if equityRows.length}<EChartsRenderer option={equityOption} height="300px" />{:else}<EChartsRenderer option={tradeOption} height="300px" />{/if}
  </section>
</section>
