<script lang="ts">
  import { artifacts } from '$lib/stores';
  import { fmt } from '$lib/format';
  import { ICONS } from '$lib/icons';

  let a = $state<any>(null);
  artifacts.subscribe((v) => (a = v));

  let loaded = $derived(a != null);
  let ckCount = $derived(a?.checkpoint_file_count ?? 0);
  let mwCount = $derived(a?.model_weight_file_count ?? 0);
  let ckReady = $derived(!!a?.checkpoint_ready);
  let pStarted = $derived(!!a?.predictor_started);
  let pComplete = $derived(!!a?.stages?.predictor?.checkpoint_ready);
  let recentCk = $derived<any[]>(Array.isArray(a?.recent_checkpoint_files) ? a.recent_checkpoint_files : []);
  let recentMw = $derived<any[]>(Array.isArray(a?.recent_model_weight_files) ? a.recent_model_weight_files : []);

  function fileName(f: any): string {
    return typeof f === 'string' ? f : (f?.path ?? f?.name ?? '-');
  }
  function fileSize(f: any): string | null {
    if (typeof f === 'object' && f?.size_mib != null) return fmt.bytes(f.size_mib);
    if (typeof f === 'object' && f?.size != null) return fmt.bytes(f.size / (1024 * 1024));
    return null;
  }
  function fileModified(f: any): string | null {
    if (typeof f === 'object' && f?.modified) return fmt.relative(f.modified);
    if (typeof f === 'object' && f?.mtime) return fmt.relative(f.mtime);
    return null;
  }

  let view = $state<'ckpt' | 'weight'>('ckpt');
</script>

<section class="page-hero">
  <div class="row" style="gap:10px">
    <span class="text-eyebrow">공식 기능</span>
    <span class="pill"><span class="dot" style="background:var(--info)"></span>/api/training/artifacts · read-only</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">아티팩트 & 모델</h1>
  <p class="text-muted" style="margin-top:6px">
    현재 학습 단계에서 생성된 checkpoint와 사전학습 모델 weight 파일을 표시합니다.
    Predictor 단계 시작 전에는 tokenizer checkpoint만 누적되며 모든 표시는 읽기 전용입니다.
  </p>
</section>

{#if !loaded}
  <div class="card"><div class="text-muted">아티팩트 상태를 불러오는 중...</div></div>
{:else}
  <!-- Summary cards -->
  <section class="grid-3-summary">
    <div class="card" class:glow={ckReady}>
      <div class="card-header">
        <div>
          <div class="card-eyebrow">CHECKPOINTS · Tokenizer</div>
          <div class="card-title">학습 중 누적</div>
        </div>
        {#if ckReady}
          <span class="pill accent"><span class="dot"></span>활성</span>
        {:else}
          <span class="pill warn"><span class="dot"></span>대기</span>
        {/if}
      </div>
      <div class="row" style="gap:18px;align-items:baseline;margin-top:8px">
        <span class="text-display tnum" style="font-size:56px;letter-spacing:-0.03em;color:{ckCount > 0 ? 'var(--fg-strong)' : 'var(--dim)'};line-height:1">{ckCount}</span>
        <span class="text-mono" style="color:var(--muted)">개</span>
      </div>
      {#if recentCk.length > 0}
        <div class="row" style="gap:6px;flex-wrap:wrap;margin-top:8px">
          {#each recentCk.slice(0, 5) as f, i}
            <span class="pill {i === 0 ? 'accent' : ''}">{fileName(f).split(/[/\\]/).pop()}</span>
          {/each}
        </div>
      {/if}
      <div class="text-caption" style="border-top:1px solid var(--border-faint);padding-top:10px;margin-top:8px">
        {a?.message ?? 'checkpoint 자동 저장 정책 적용 중'}
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-eyebrow">MODEL WEIGHTS · 사전학습</div>
          <div class="card-title">로컬 baseline</div>
        </div>
        <span class="pill"><span class="dot" style="background:var(--info)"></span>read-only</span>
      </div>
      <div class="row" style="gap:18px;align-items:baseline;margin-top:8px">
        <span class="text-display tnum" style="font-size:56px;letter-spacing:-0.03em;color:{mwCount > 0 ? 'var(--fg-strong)' : 'var(--dim)'};line-height:1">{mwCount}</span>
        <span class="text-mono" style="color:var(--muted)">개</span>
      </div>
      {#if recentMw.length > 0}
        <div class="stack" style="gap:6px;margin-top:8px">
          {#each recentMw.slice(0, 3) as f}
            {@const size = fileSize(f)}
            <div class="row spread">
              <span class="text-mono" style="font-weight:600;font-size:12px">{fileName(f).split(/[/\\]/).pop()}</span>
              {#if size}<span class="text-mono" style="color:var(--muted);font-size:11px">{size}</span>{/if}
            </div>
          {/each}
        </div>
      {:else}
        <div class="text-caption" style="margin-top:8px">사전학습 weight 파일 없음</div>
      {/if}
      <div class="text-caption" style="border-top:1px solid var(--border-faint);padding-top:10px;margin-top:8px">
        finetune 시작점 · 학습 결과와 무관
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-eyebrow">PREDICTOR · 결과물</div>
          <div class="card-title">{pComplete ? '완료' : pStarted ? '학습 중' : '대기 중'}</div>
        </div>
        {#if pComplete}
          <span class="pill success"><span class="dot"></span>완료</span>
        {:else if pStarted}
          <span class="pill accent"><span class="dot"></span>학습 중</span>
        {:else}
          <span class="pill warn"><span class="dot"></span>미시작</span>
        {/if}
      </div>
      <div class="row" style="gap:18px;align-items:baseline;margin-top:8px">
        <span class="text-display tnum" style="font-size:56px;letter-spacing:-0.03em;color:{pStarted ? 'var(--fg-strong)' : 'var(--dim)'};line-height:1">0</span>
        <span class="text-mono" style="color:var(--muted)">개</span>
      </div>
      <div class="card compact flat" style="background:var(--surface-sunken);border:none;padding:12px;gap:8px;margin-top:8px;border-radius:12px">
        <div class="row" style="gap:8px">
          {#if pComplete}
            <span class="pill success" style="padding:2px 8px"><span class="dot"></span>완료</span>
            <span class="text-caption">예측기 학습이 완료되었습니다</span>
          {:else if pStarted}
            <span class="pill accent" style="padding:2px 8px"><span class="dot"></span>진행</span>
            <span class="text-caption">예측기 학습 중</span>
          {:else}
            <span class="pill warn" style="padding:2px 8px"><span class="dot"></span>대기</span>
            <span class="text-caption">Tokenizer 100% 도달 시 자동 시작</span>
          {/if}
        </div>
        <p class="text-caption" style="line-height:1.5;margin:0">
          Predictor 단계가 시작되면 약 4.7M step에 걸쳐 모델 weight 와 평가 metrics 가 이 영역에 누적됩니다.
        </p>
      </div>
    </div>
  </section>

  <!-- Toolbar -->
  <section class="row" style="gap:10px;flex-wrap:wrap">
    <div class="tabs" data-tab-group="art">
      <button data-active={view === 'ckpt' ? 'true' : 'false'} onclick={() => (view = 'ckpt')}>Checkpoints</button>
      <button data-active={view === 'weight' ? 'true' : 'false'} onclick={() => (view = 'weight')}>Model Weights</button>
    </div>
    <span class="text-caption" style="margin-left:auto">
      총 {view === 'ckpt' ? recentCk.length : recentMw.length}개 표시 · 정렬 최신순
    </span>
  </section>

  <!-- File list -->
  <section class="card" style="padding:0">
    <div class="row spread" style="padding:18px 20px 8px">
      <div>
        <div class="card-eyebrow">{view === 'ckpt' ? 'RECENT_CHECKPOINT_FILES' : 'RECENT_MODEL_WEIGHT_FILES'} ({view === 'ckpt' ? recentCk.length : recentMw.length})</div>
        <div class="card-title">
          {view === 'ckpt' ? 'Tokenizer/Predictor step별 체크포인트' : '사전학습 weight 파일'}
        </div>
      </div>
      <span class="text-caption">{view === 'ckpt' ? '정렬 · 최신순' : 'read-only · 학습 시작점'}</span>
    </div>
    <div style="padding:0 12px 16px">
      {#if view === 'ckpt'}
        {#if recentCk.length === 0}
          <div class="text-caption" style="padding:24px 20px;text-align:center">
            아직 생성된 checkpoint 파일이 없습니다. tokenizer 또는 predictor 진행 시 자동으로 표시됩니다.
          </div>
        {:else}
          {#each recentCk as f, i}
            {@const size = fileSize(f)}
            {@const mod = fileModified(f)}
            {@const name = fileName(f)}
            <div class="file-row">
              <span class="file-icon">
                <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">{@html ICONS.package}</svg>
              </span>
              <div class="file-info">
                <div class="text-mono" style="font-weight:600;color:var(--fg-strong);font-size:13px">
                  {name.split(/[/\\]/).pop()}
                </div>
                <div class="text-caption">{name}</div>
              </div>
              <div class="file-meta">
                {#if size}<span class="text-mono" style="font-size:11px;color:var(--muted)">{size}</span>{/if}
                {#if mod}<span class="text-mono" style="font-size:11px;color:var(--dim)">{mod}</span>{/if}
                {#if i === 0}<span class="pill accent" style="padding:2px 8px">최신</span>{/if}
              </div>
            </div>
          {/each}
        {/if}
      {:else}
        {#if recentMw.length === 0}
          <div class="text-caption" style="padding:24px 20px;text-align:center">
            사전학습 weight 파일이 없습니다.
          </div>
        {:else}
          {#each recentMw as f, i}
            {@const size = fileSize(f)}
            {@const name = fileName(f)}
            <div class="file-row">
              <span class="file-icon">
                <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">{@html ICONS.chip}</svg>
              </span>
              <div class="file-info">
                <div class="text-mono" style="font-weight:600;color:var(--fg-strong);font-size:13px">
                  {name.split(/[/\\]/).pop()}
                </div>
                <div class="text-caption">{name}</div>
              </div>
              <div class="file-meta">
                {#if size}<span class="text-mono" style="font-size:11px;color:var(--muted)">{size}</span>{/if}
                <span class="pill"><span class="dot" style="background:var(--info)"></span>read-only</span>
              </div>
            </div>
          {/each}
        {/if}
      {/if}
    </div>
  </section>
{/if}

<style>
  .page-hero {
    padding: 8px 0 8px;
  }
  .grid-3-summary {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }
  @media (max-width: 1100px) {
    .grid-3-summary { grid-template-columns: 1fr; }
  }
  .file-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: var(--r-sm);
    transition: background var(--d-fast) var(--ease-out);
  }
  .file-row:hover {
    background: var(--surface-sunken);
  }
  .file-icon {
    width: 36px;
    height: 36px;
    border-radius: var(--r-sm);
    background: var(--accent-soft);
    color: var(--accent-strong);
    display: grid;
    place-items: center;
    flex-shrink: 0;
  }
  .file-info {
    flex: 1;
    min-width: 0;
  }
  .file-info .text-caption {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .file-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }
</style>
