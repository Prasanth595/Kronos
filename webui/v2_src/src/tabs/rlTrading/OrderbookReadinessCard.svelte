<script lang="ts">
  import { num, pct } from '$lib/rlRows';
  import type { RlRunRecord } from '$lib/rlApi';

  interface Props { readonly run: RlRunRecord | null }
  let { run }: Props = $props();
  const summary = $derived(run?.summary ?? {});
  const status = $derived(String(summary.readiness_status ?? summary.verdict ?? 'NOT_GENERATED'));
</script>

<section class="card orderbook-readiness-card" data-rl-orderbook-readiness-card>
  <div class="card-header">
    <div>
      <div class="card-eyebrow">ORDERBOOK RL READINESS</div>
      <div class="card-title">시초 극초단타 tick+호가창 강화학습 준비도</div>
    </div>
    <span class="pill warn"><span class="dot"></span>{status}</span>
  </div>
  <div class="mini-grid">
    <div><span>Artifact</span><strong>orderbook_rl_readiness</strong></div>
    <div><span>Action space</span><strong>hold · market_buy · market_exit</strong></div>
    <div><span>Observation</span><strong>tick · best quote · depth imbalance · OFI</strong></div>
    <div><span>Coverage</span><strong>{pct(summary.quote_coverage, 1)} quote · {pct(summary.valid_spread_coverage, 1)} spread</strong></div>
  </div>
  <p class="text-caption safety-note">
    {#if run}
      source: {run.name} · eligible episodes {num(summary.eligible_episode_count, 0)}
    {:else}
      readiness artifact 없음. 이 카드는 환경 준비도만 표시하며 자동매매·수익 보장을 뜻하지 않습니다.
    {/if}
  </p>
</section>
