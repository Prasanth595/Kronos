<script lang="ts">
  import { fmt } from '$lib/format';

  interface Stats {
    mean: number | null;
    std: number | null;
    min: number | null;
    max: number | null;
    n: number;
  }
  interface Trend {
    dir: 'down' | 'up' | 'flat';
    pct: number;
  }
  interface Props {
    stats: Stats;
    trend: Trend;
  }
  let { stats, trend }: Props = $props();

  // σ가 임계값 미만이면 안정 (예: tokenizer loss σ < 0.06)
  let stableThreshold = 0.06;
  let isStable = $derived(stats.std != null && stats.std < stableThreshold);
</script>

<div class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">W6 · 손실 변동성</div>
      <div class="card-title">최근 {stats.n} step</div>
    </div>
    {#if trend.dir === 'down'}
      <span class="pill success">▼ {fmt.num(trend.pct, 1)}%</span>
    {:else if trend.dir === 'up'}
      <span class="pill danger">▲ {fmt.num(trend.pct, 1)}%</span>
    {:else}
      <span class="pill">평탄</span>
    {/if}
  </div>

  <div class="stack" style="gap:12px">
    <div class="row spread" style="border-bottom:1px solid var(--border-faint);padding-bottom:10px">
      <span class="text-eyebrow">평균 (μ)</span>
      <span class="text-mono tnum" style="font-size:18px;font-weight:600;color:var(--fg-strong)">
        {stats.mean != null ? stats.mean.toFixed(4) : '—'}
      </span>
    </div>
    <div class="row spread" style="border-bottom:1px solid var(--border-faint);padding-bottom:10px">
      <span class="text-eyebrow">표준편차 (σ)</span>
      <span class="text-mono tnum" style="font-size:18px;font-weight:600;color:var(--fg-strong)">
        {stats.std != null ? stats.std.toFixed(4) : '—'}
      </span>
    </div>
    <div class="row spread" style="border-bottom:1px solid var(--border-faint);padding-bottom:10px">
      <span class="text-eyebrow">최저</span>
      <span class="text-mono tnum" style="font-size:16px;font-weight:600;color:var(--success)">
        {stats.min != null ? stats.min.toFixed(4) : '—'}
      </span>
    </div>
    <div class="row spread">
      <span class="text-eyebrow">최고</span>
      <span class="text-mono tnum" style="font-size:16px;font-weight:600;color:var(--danger)">
        {stats.max != null ? stats.max.toFixed(4) : '—'}
      </span>
    </div>
  </div>

  {#if stats.n > 0}
    <div class="card compact flat" style="background:var(--surface-sunken);padding:12px;gap:8px;border:none;border-radius:12px;margin-top:8px">
      <div class="row" style="gap:8px">
        {#if isStable}
          <span class="pill accent" style="padding:2px 8px"><span class="dot"></span>안정</span>
          <span class="text-caption">σ가 임계값 {stableThreshold} 미만</span>
        {:else}
          <span class="pill warn" style="padding:2px 8px"><span class="dot"></span>변동</span>
          <span class="text-caption">σ가 임계값 {stableThreshold} 이상</span>
        {/if}
      </div>
      <p class="text-caption" style="line-height:1.5;margin:0">
        {#if isStable}
          손실이 평탄해지고 있어 단계가 수렴 구간에 진입한 것으로 보입니다.
        {:else}
          손실이 아직 크게 움직이고 있어 추가 학습이 필요한 구간입니다.
        {/if}
      </p>
    </div>
  {/if}
</div>
