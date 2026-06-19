<script lang="ts">
  import { num, pct, text } from '$lib/rlRows';
  import type { RlTableRow } from '$lib/rlApi';

  interface Props {
    readonly leaderboardRows: readonly RlTableRow[];
    readonly tradeRows: readonly RlTableRow[];
    readonly ruleFilterControlRows?: readonly RlTableRow[];
    readonly ruleFilterAblationRows?: readonly RlTableRow[];
    readonly ruleFilterFailureRows?: readonly RlTableRow[];
  }
  let { leaderboardRows, tradeRows, ruleFilterControlRows = [], ruleFilterAblationRows = [], ruleFilterFailureRows = [] }: Props = $props();
</script>

<section class="card" data-rl-leaderboard-table>
  <div class="card-title">성과 리더보드 · DQN/PPO vs RULE</div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>rank</th><th>source</th><th>model</th><th>net evidence</th><th>cost gate</th></tr></thead>
      <tbody>
        {#each leaderboardRows.slice(0, 12) as row, idx}
          <tr><td>{num(row.rank ?? idx + 1, 0)}</td><td>{text(row, 'source')}</td><td>{text(row, 'model', text(row, 'policy'))}</td><td>{pct(row.avg_episode_net_return_pct, 3)}</td><td>{String(row.passes_cost_gate ?? '-')}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>

<section class="card" data-rl-trade-table>
  <div class="card-title">거래별 net-return evidence</div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>symbol</th><th>policy/model</th><th>episode</th><th>net</th></tr></thead>
      <tbody>
        {#each tradeRows.slice(0, 16) as row}
          <tr><td>{text(row, 'symbol')}</td><td>{text(row, 'model', text(row, 'policy'))}</td><td>{text(row, 'episode_id')}</td><td>{pct(row.net_return_pct, 3)}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>


{#if ruleFilterControlRows.length || ruleFilterAblationRows.length || ruleFilterFailureRows.length}
  <section class="card" data-rule-filter-evidence-table>
    <div class="card-title">RULE filter controls ? ablations ? NO-GO reasons</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>type</th><th>id</th><th>filter</th><th>comparison</th><th>passed</th></tr></thead>
        <tbody>
          {#each ruleFilterControlRows.slice(0, 8) as row}
            <tr><td>control</td><td>{text(row, 'control_type')}</td><td>{pct(row.filter_oos_net_return_pct, 3)}</td><td>{pct(row.control_net_return_pct, 3)}</td><td>{String(row.passed ?? '-')}</td></tr>
          {/each}
          {#each ruleFilterAblationRows.slice(0, 8) as row}
            <tr><td>ablation</td><td>{text(row, 'feature_set_id')}</td><td>{pct(row.full_context_return_pct, 3)}</td><td>{pct(row.ablated_return_pct, 3)}</td><td>{String(row.passed ?? '-')}</td></tr>
          {/each}
          {#each ruleFilterFailureRows.slice(0, 8) as row}
            <tr><td>NO-GO</td><td>{text(row, 'reason')}</td><td>-</td><td>-</td><td>false</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>
{/if}
<span class="sr-only">25bp cost gate compatibility marker</span>
