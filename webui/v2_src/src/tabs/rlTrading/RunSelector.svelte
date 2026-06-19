<script lang="ts">
  import { runLabel, typeLabel, typeTone } from '$lib/rlRows';
  import type { RlRunRecord } from '$lib/rlApi';

  interface Props {
    readonly runs: readonly RlRunRecord[];
    readonly selectedName: string;
    readonly onSelect: (name: string) => void;
  }
  let { runs, selectedName, onSelect }: Props = $props();
</script>

<section class="card">
  <div class="card-header"><div><div class="card-eyebrow">RUN SELECTOR</div><div class="card-title">강화학습 산출물</div></div></div>
  <div class="run-list">
    {#each runs as run}
      <button type="button" class:active={run.name === selectedName} onclick={() => onSelect(run.name)}>
        <span>{runLabel(run)}</span>
        <small class="pill {typeTone(run.artifact_type)}">{typeLabel(run.artifact_type)}</small>
      </button>
    {/each}
  </div>
</section>
