<script lang="ts">
  import { trainingStatus } from '$lib/stores';
  import { readinessVisual } from '$lib/readinessMap';

  let status = $state<any>(null);
  trainingStatus.subscribe((v) => (status = v));

  let readiness = $derived(status?.readiness ?? { level: 'waiting', label: '확인 중...', message: '-' });
  let visual = $derived(readinessVisual(readiness.level));
</script>

<div class="flex flex-col gap-2">
  <div class="text-[10px] uppercase tracking-wide text-text-faint font-bold">학습 준비 상태</div>
  <div class="px-3 py-2 rounded-md {visual.bgClass} {visual.textClass} font-semibold text-[13px] inline-flex items-center gap-2">
    {readiness.label || visual.shortLabel}
  </div>
  <p class="text-text-muted text-[12px] leading-normal m-0">{readiness.message || '-'}</p>
  {#if status?.status}
    <div class="text-[10px] text-text-dim mt-1">상태: <span class="text-text">{status.status}</span></div>
  {/if}
</div>
