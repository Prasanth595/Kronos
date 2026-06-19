<script lang="ts">
  import type { DailyProgressResponse } from '$lib/dailyOhlcvApi';

  interface Props { progress: DailyProgressResponse | null }
  let { progress }: Props = $props();

  function tone(status: string | undefined): string {
    if (status === 'PASS') return 'success';
    if (status === 'WATCH' || status === 'RUNNING' || status === 'RESEARCH_ONLY') return 'warn';
    if (status === 'NO-GO' || status === 'BLOCKED') return 'danger';
    return '';
  }
</script>

<!-- Status vocabulary marker: NOT_STARTED RUNNING PASS WATCH RESEARCH_ONLY NO-GO BLOCKED -->
<section class="panel" data-daily-ohlcv-progress>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">D0-D9 Progress</div>
      <h2 class="text-h3">일봉 연구 진행 상태</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{progress?.overall_status ?? 'LOADING'}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">{progress?.guardrail ?? '일봉 대시보드는 읽기 전용 증거 화면입니다.'}</p>
  <div class="timeline">
    {#if (progress?.stages?.length ?? 0) === 0}
      <div class="stage" data-status="NOT_STARTED" data-daily-progress-empty>
        <div class="stage-top">
          <strong>D0-D9</strong>
          <span class="pill"><span class="dot"></span>NOT_STARTED</span>
        </div>
        <div class="stage-label">일봉 연구 진행 상태 대기</div>
        <div class="stage-evidence">API payload가 도착하기 전에는 어떤 GO/수익/실거래 상태도 추론하지 않습니다.</div>
      </div>
    {:else}
      {#each progress?.stages ?? [] as stage}
        <div class="stage" data-status={stage.status}>
          <div class="stage-top">
            <strong>{stage.id}</strong>
            <span class="pill {tone(stage.status)}"><span class="dot"></span>{stage.status}</span>
          </div>
          <div class="stage-label">{stage.label}</div>
          <div class="stage-evidence">{stage.evidence}</div>
          {#if stage.lock_labels?.length}
            <div class="stage-locks">
              {#each stage.lock_labels as lock}
                <span>{lock}</span>
              {/each}
            </div>
          {/if}
          {#if stage.verification_commands?.length}
            <div class="stage-verification">
              <span>검증</span>
              {#each stage.verification_commands as command}
                <code>{command}</code>
              {/each}
            </div>
          {/if}
        </div>
      {/each}
    {/if}
  </div>
  <div class="provenance-table" data-daily-d0-d9-provenance-matrix>
    <div class="text-eyebrow">D0-D9 provenance / exact checks</div>
    {#each progress?.provenance_matrix ?? [] as row}
      <div class="provenance-row">
        <strong>{row.id}</strong>
        <span>{row.status}</span>
        <span>{(row.lock_labels ?? []).join(' · ')}</span>
        <div class="command-list">
          {#each row.verification_commands ?? ['verification pending'] as command}
            <code>{command}</code>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</section>

<style>
  .timeline { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin-top:16px; }
  .stage { border:1px solid var(--border); border-radius:var(--r-lg); padding:12px; background:var(--surface); }
  .stage-top { display:flex; align-items:center; justify-content:space-between; gap:8px; }
  .stage-label { margin-top:8px; font-weight:700; }
  .stage-evidence { margin-top:6px; color:var(--muted); font-size:12px; line-height:1.45; }
  .stage-locks { display:flex; flex-wrap:wrap; gap:4px; margin-top:8px; }
  .stage-locks span { border:1px solid var(--border); border-radius:999px; padding:2px 6px; color:var(--muted); font-size:10px; }
  .stage-verification { margin-top:8px; color:var(--muted); font-size:11px; line-height:1.35; word-break:break-word; display:grid; gap:4px; }
  .provenance-table { margin-top:16px; border:1px solid var(--border); border-radius:var(--r-lg); padding:12px; background:var(--surface); }
  .provenance-row { display:grid; grid-template-columns: 48px 96px minmax(180px, 1fr) minmax(220px, 2fr); gap:8px; align-items:start; border-top:1px solid var(--border-faint); padding:8px 0; font-size:12px; }
  .provenance-row code { white-space:normal; word-break:break-word; color:var(--muted); }
  .command-list { display:grid; gap:4px; }
</style>
