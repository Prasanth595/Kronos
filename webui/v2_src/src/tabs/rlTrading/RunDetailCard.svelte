<script lang="ts">
  import { num, pct, typeLabel } from '$lib/rlRows';
  import type { RlRunDetail } from '$lib/rlApi';

  interface Props { readonly run: RlRunDetail | null; readonly loading: boolean }
  let { run, loading }: Props = $props();
  const summary = $derived(run?.summary ?? {});
  const context = $derived(run?.strategy_context ?? {});
</script>

<section class="card" data-rl-selected-run-card>
  <div class="card-header">
    <div><div class="card-eyebrow">SELECTED RUN</div><div class="card-title">{run?.name ?? '선택 없음'}</div></div>
    <span class="pill {context.line === 'rule_mainline' ? 'success' : 'accent'}"><span class="dot"></span>{context.label ?? typeLabel(run?.artifact_type)}</span>
  </div>
  {#if loading}
    <p class="text-muted">상세 로딩 중...</p>
  {:else if run}
    <div class="mini-grid">
      <div><span>Artifact</span><strong>{run.artifact_type}</strong></div>
      <div><span>Net evidence</span><strong>{pct(summary.avg_episode_net_return_pct ?? summary.buy_and_hold_avg_episode_net_return_pct, 3)}</strong></div>
      <div><span>Trades</span><strong>{num(summary.trade_count, 0)}</strong></div>
      <div><span>Model</span><strong>{run.model?.model_type ?? 'RULE / table artifact'}</strong></div>
    </div>
    <p class="text-caption safety-note">{context.guardrail ?? 'research evidence only; not live-ready and not a profit model'} · is_live_ready={String(context.is_live_ready)} · is_profit_model={String(context.is_profit_model)}</p>
  {/if}
</section>
