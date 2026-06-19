<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { trainingStatus, refreshSeconds } from '$lib/stores';
  import { fmt } from '$lib/format';

  let status = $state<any>(null);
  trainingStatus.subscribe((v) => (status = v));

  let refresh = $state(5);
  refreshSeconds.subscribe((v) => (refresh = v));

  let lines = $state<string[]>([]);
  let lastFetchedAt = $state<string>('-');
  let error = $state<string | null>(null);
  let loading = $state(false);
  let tailCount = $state<10 | 20 | 50>(10);

  let stage = $derived(status?.latest_stage?.train_stage ?? null);

  async function fetchLogs() {
    if (loading) return;
    loading = true;
    error = null;
    try {
      const url = stage
        ? `/api/training/logs?stage=${encodeURIComponent(stage)}&lines=${tailCount}`
        : `/api/training/logs?lines=${tailCount}`;
      const r = await fetch(url);
      if (!r.ok) {
        error = `HTTP ${r.status}`;
        return;
      }
      const d = await r.json();
      if (d.error) {
        error = d.error;
        return;
      }
      lines = Array.isArray(d.lines) ? d.lines : [];
      lastFetchedAt = fmt.kstTime(Date.now());
    } catch (e: any) {
      error = e?.message ?? '로그 조회 실패';
    } finally {
      loading = false;
    }
  }

  let timer: number | undefined;
  onMount(() => {
    fetchLogs();
    // 로그는 10초 주기로 충분 (학습 step 갱신은 1000 step 마다)
    timer = window.setInterval(fetchLogs, 10000);
  });

  onDestroy(() => {
    if (timer != null) clearInterval(timer);
  });

  $effect(() => {
    void tailCount;
    fetchLogs();
  });

  // 색상 분기 — loss/lr/sps/step/AMP/compile/error 키워드별 강조
  function colorize(line: string): string {
    if (!line) return '';
    // HTML escape 먼저
    let safe = line
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    safe = safe.replace(/Loss:\s*(-?[0-9.]+(?:e[-+]?\d+)?)/gi,
      (_, v) => `Loss: <span style="color:var(--accent);font-weight:600">${v}</span>`);
    safe = safe.replace(/LR\s+(-?[0-9.]+(?:e[-+]?\d+)?)/gi,
      (_, v) => `LR <span style="color:var(--warn);font-weight:600">${v}</span>`);
    safe = safe.replace(/(samples\/?s|sps)\s*[:=]\s*(-?[0-9.]+(?:e[-+]?\d+)?)/gi,
      (_, k, v) => `${k}=<span style="color:var(--success);font-weight:600">${v}</span>`);
    safe = safe.replace(/(Step\s+)(\d+(?:\/\d+)?)/gi,
      (_, p, v) => `${p}<span style="color:var(--fg-strong);font-weight:600">${v}</span>`);
    safe = safe.replace(/(AMP\s+enabled\s*—\s*dtype=\w+\s+scaler=\w+)/gi,
      (_, v) => `<span style="color:var(--success);font-weight:600">${v}</span>`);
    safe = safe.replace(/(torch\.compile\s+enabled\s*—\s*mode=\S+\s+fullgraph=\w+)/gi,
      (_, v) => `<span style="color:var(--accent-strong);font-weight:600">${v}</span>`);
    safe = safe.replace(/(torch\.compile\s+failed[^\n]*)/gi,
      (_, v) => `<span style="color:var(--warn);font-weight:600">${v}</span>`);
    safe = safe.replace(/(out\s+of\s+memory|OOM|CUDA error|Traceback|Error|Exception)/gi,
      (_, v) => `<span style="color:var(--danger);font-weight:700">${v}</span>`);
    safe = safe.replace(/(checkpoint saved|saved checkpoint|pre-validation\s+epoch\s+\d+)/gi,
      (_, v) => `<span style="color:var(--success);font-weight:600">${v}</span>`);
    return safe;
  }
</script>

<div class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">W9 · /api/training/logs · stdout tail</div>
      <div class="card-title">학습 로그 실시간 tail{stage ? ` · ${stage}` : ''}</div>
    </div>
    <div class="row" style="gap:8px;flex-wrap:wrap">
      <div class="seg">
        <button data-active={tailCount === 10 ? 'true' : 'false'} onclick={() => (tailCount = 10)}>10</button>
        <button data-active={tailCount === 20 ? 'true' : 'false'} onclick={() => (tailCount = 20)}>20</button>
        <button data-active={tailCount === 50 ? 'true' : 'false'} onclick={() => (tailCount = 50)}>50</button>
      </div>
      <span class="pill"><span class="dot" style="background:var(--success)"></span>tail -f · 10초 주기</span>
    </div>
  </div>

  {#if error}
    <div class="text-caption" style="color:var(--danger);padding:12px 0">⚠ {error}</div>
  {:else if lines.length === 0 && !loading}
    <div class="text-caption" style="color:var(--muted);padding:12px 0">로그가 없습니다.</div>
  {:else if loading && lines.length === 0}
    <div class="text-caption" style="color:var(--muted);padding:12px 0">로그를 불러오는 중...</div>
  {:else}
    <div class="log-pane">
      {#each lines as line, i (i)}
        <div class="log-line">{@html colorize(line)}</div>
      {/each}
    </div>
  {/if}

  <div class="row spread" style="border-top:1px solid var(--border-faint);padding-top:10px;margin-top:8px;flex-wrap:wrap;gap:8px">
    <div class="row" style="gap:18px;flex-wrap:wrap">
      <span class="legend"><span class="swatch" style="background:var(--accent)"></span>Loss</span>
      <span class="legend"><span class="swatch" style="background:var(--warn)"></span>LR</span>
      <span class="legend"><span class="swatch" style="background:var(--success)"></span>sps · checkpoint</span>
      <span class="legend"><span class="swatch" style="background:var(--accent-strong)"></span>compile</span>
      <span class="legend"><span class="swatch" style="background:var(--danger)"></span>error · OOM</span>
    </div>
    <span class="text-caption">마지막 갱신 <span class="text-mono">{lastFetchedAt}</span></span>
  </div>
</div>

<style>
  .log-pane {
    background: var(--surface-sunken);
    border: 1px solid var(--border-faint);
    border-radius: var(--r-sm);
    padding: 12px 14px;
    max-height: 240px;
    overflow-y: auto;
    font: 500 11.5px/1.55 var(--font-mono);
    color: var(--muted);
    margin-top: 8px;
  }
  .log-line {
    padding: 2px 0;
    word-break: break-all;
    white-space: pre-wrap;
  }
</style>
