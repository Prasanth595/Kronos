<script lang="ts">
  import { trainingStatus } from '$lib/stores';
  import { finishKst } from '$lib/kstFormat';

  let status = $state<any>(null);
  trainingStatus.subscribe((v) => (status = v));

  let level = $derived(status?.readiness?.level ?? 'waiting');
  let etaSeconds = $derived(status?.latest_stage?.eta_seconds ?? null);
  let updatedAt = $derived(status?.latest_stage?.updated_at ?? null);
  let etaKst = $derived(finishKst(etaSeconds, updatedAt));
</script>

<div class="flex flex-col gap-2 p-3 rounded-md border border-border bg-card-raised">
  <div class="flex items-center justify-center gap-2">
    <div class="tl-dot" class:lit-red={level === 'waiting'}></div>
    <div class="tl-dot" class:lit-yellow={level === 'training'}></div>
    <div class="tl-dot" class:lit-green={level === 'ready'}></div>
    <span class="text-text-muted text-[11px] font-semibold ml-2">
      {level === 'ready' ? '준비 완료' : level === 'training' ? '학습 진행' : '대기'}
    </span>
  </div>
  <div class="border-t border-dashed border-border-muted pt-2 text-center">
    <div class="text-[11px] uppercase tracking-wide text-text-dim">완료 예상 (KST)</div>
    <div class="text-text font-bold text-[14px] mt-1 font-mono">{etaKst}</div>
  </div>
</div>
