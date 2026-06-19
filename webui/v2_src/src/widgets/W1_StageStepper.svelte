<script lang="ts">
  import { trainingStatus } from '$lib/stores';

  let status = $state<any>(null);
  trainingStatus.subscribe((v) => (status = v));

  let stages = $derived<any[]>(Array.isArray(status?.stages) ? status.stages : []);

  function isDone(s: any): boolean {
    return ['ok', 'recovered', 'complete', 'completed', 'done', 'finished', 'success', 'succeeded'].includes(s?.status);
  }

  function isActive(s: any): boolean {
    return s?.status === 'running' || s?.status === 'active';
  }
</script>

<div class="flex flex-col gap-2">
  <div class="text-[10px] uppercase tracking-wide text-text-faint font-bold">학습 단계</div>
  {#if stages.length === 0}
    <div class="text-text-dim text-[12px]">단계 정보 없음</div>
  {:else}
    <div class="flex items-center gap-2 flex-wrap">
      {#each stages as s, i}
        <div class="flex items-center gap-2">
          <div class="flex flex-col items-center min-w-[80px]">
            <div
              class="w-[32px] h-[32px] rounded-full border-2 flex items-center justify-center font-bold text-[13px] transition-colors duration-base
              {isDone(s) ? 'border-success bg-success-bg text-[#dcfce7]' :
                isActive(s) ? 'border-accent bg-accent/[.12] text-accent' :
                'border-border bg-card-raised text-text-faint'}"
            >
              {i + 1}
            </div>
            <span class="text-[11px] text-text-muted mt-1">{s?.train_stage ?? s?.stage ?? '-'}</span>
            {#if s?.stage_percent != null}
              <span class="text-[10px] text-text-dim">{s.stage_percent.toFixed(1)}%</span>
            {/if}
          </div>
          {#if i < stages.length - 1}
            <div class="w-12 h-[2px] bg-border-muted"></div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>
