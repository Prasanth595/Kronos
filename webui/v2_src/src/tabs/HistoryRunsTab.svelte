<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { activeTab } from '$lib/stores';
  import { fmt } from '$lib/format';

  interface TrainingRun {
    name: string;
    path: string;
    overall_percent: number;
    status: string;
    stage_count: number;
    updated_at: string;
    updated_at_epoch?: number;
  }

  let runs = $state<TrainingRun[]>([]);
  let loaded = $state(false);
  let loading = $state(false);
  let error = $state<string | null>(null);

  let filter = $state<'all' | 'completed' | 'running' | 'failed'>('all');
  let sortBy = $state<'recent' | 'name' | 'progress'>('recent');

  async function load() {
    if (loading) return;
    loading = true;
    error = null;
    try {
      const r = await fetch('/api/training/runs');
      if (!r.ok) {
        error = `HTTP ${r.status}`;
        return;
      }
      const d = await r.json();
      runs = Array.isArray(d.runs) ? d.runs : [];
      loaded = true;
    } catch (e: any) {
      error = e?.message ?? '네트워크 오류';
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    load();
  });

  // 폴링 (60초마다 갱신)
  let timer: number | undefined;
  $effect(() => {
    if (timer != null) clearInterval(timer);
    timer = window.setInterval(load, 60000);
    return () => {
      if (timer != null) clearInterval(timer);
    };
  });

  // 필터링
  let filtered = $derived.by(() => {
    let list = runs.slice();
    if (filter !== 'all') {
      list = list.filter((r) => {
        if (filter === 'completed') return r.status === 'completed' || r.status === 'complete' || r.status === 'success';
        if (filter === 'failed') return r.status === 'failed' || r.status === 'error';
        if (filter === 'running') return r.status === 'running' || r.status === 'active';
        return true;
      });
    }
    if (sortBy === 'name') {
      list.sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortBy === 'progress') {
      list.sort((a, b) => (b.overall_percent ?? 0) - (a.overall_percent ?? 0));
    } else {
      list.sort((a, b) => (b.updated_at_epoch ?? 0) - (a.updated_at_epoch ?? 0));
    }
    return list;
  });

  // 카운트
  let counts = $derived.by(() => {
    let completed = 0, failed = 0, running = 0;
    for (const r of runs) {
      const s = r.status;
      if (s === 'completed' || s === 'complete' || s === 'success') completed++;
      else if (s === 'failed' || s === 'error') failed++;
      else if (s === 'running' || s === 'active') running++;
    }
    return { total: runs.length, completed, failed, running };
  });

  function statusKind(s: string): 'success' | 'danger' | 'accent' | '' {
    if (s === 'completed' || s === 'complete' || s === 'success') return 'success';
    if (s === 'failed' || s === 'error') return 'danger';
    if (s === 'running' || s === 'active') return 'accent';
    return '';
  }

  function statusLabel(s: string): string {
    if (s === 'completed' || s === 'complete' || s === 'success') return '완료';
    if (s === 'failed' || s === 'error') return '실패';
    if (s === 'running' || s === 'active') return '진행 중';
    return s || '미상';
  }
</script>

<section class="page-hero">
  <div class="row" style="gap:10px">
    <span class="text-eyebrow">정식</span>
    <span class="pill"><span class="dot" style="background:var(--info)"></span>/api/training/runs · 60초 폴링</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">기록 & 런</h1>
  <p class="text-muted" style="margin-top:6px">
    finetune/outputs 디렉터리의 모든 학습 run 목록. 상태별 필터·정렬을 지원하며, 실시간 학습 탭의 손실 곡선은
    <button class="text-accent text-link" onclick={() => activeTab.set('live-training')}>실시간 학습</button>
    에서 현재 진행 중인 run 만 표시합니다.
  </p>
</section>

<!-- ===== Summary KPI ===== -->
<section class="grid-4-summary">
  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">총 RUN</span>
    </div>
    <div class="metric-value tnum">{counts.total}<span class="metric-unit">개</span></div>
    <div class="metric-foot">finetune/outputs 스캔 결과</div>
  </div>
  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">완료</span>
      <span class="pill success" style="padding:2px 8px"><span class="dot"></span>{counts.completed}</span>
    </div>
    <div class="metric-value tnum" style="color:var(--success)">{counts.completed}<span class="metric-unit">개</span></div>
    <div class="metric-foot">overall_percent = 100% + status=completed</div>
  </div>
  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">실패</span>
      <span class="pill danger" style="padding:2px 8px"><span class="dot"></span>{counts.failed}</span>
    </div>
    <div class="metric-value tnum" style="color:var(--danger)">{counts.failed}<span class="metric-unit">개</span></div>
    <div class="metric-foot">OOM / interrupted 등</div>
  </div>
  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">진행 중</span>
      <span class="pill accent" style="padding:2px 8px"><span class="dot"></span>{counts.running}</span>
    </div>
    <div class="metric-value tnum" style="color:var(--accent-strong)">{counts.running}<span class="metric-unit">개</span></div>
    <div class="metric-foot">live 폴링 대상</div>
  </div>
</section>

<!-- ===== Toolbar ===== -->
<section class="row" style="gap:10px;flex-wrap:wrap;align-items:center">
  <div class="tabs">
    <button data-active={filter === 'all' ? 'true' : 'false'} onclick={() => (filter = 'all')}>전체 ({counts.total})</button>
    <button data-active={filter === 'completed' ? 'true' : 'false'} onclick={() => (filter = 'completed')}>완료 ({counts.completed})</button>
    <button data-active={filter === 'failed' ? 'true' : 'false'} onclick={() => (filter = 'failed')}>실패 ({counts.failed})</button>
    <button data-active={filter === 'running' ? 'true' : 'false'} onclick={() => (filter = 'running')}>진행 중 ({counts.running})</button>
  </div>
  <div class="seg" style="margin-left:auto">
    <button data-active={sortBy === 'recent' ? 'true' : 'false'} onclick={() => (sortBy = 'recent')}>최신순</button>
    <button data-active={sortBy === 'name' ? 'true' : 'false'} onclick={() => (sortBy = 'name')}>이름순</button>
    <button data-active={sortBy === 'progress' ? 'true' : 'false'} onclick={() => (sortBy = 'progress')}>진척순</button>
  </div>
  <button class="btn ghost sm" onclick={load} disabled={loading}>
    {loading ? '갱신 중…' : '새로고침'}
  </button>
</section>

<!-- ===== Runs grid ===== -->
{#if !loaded && loading}
  <div class="card"><div class="text-muted">run 목록을 불러오는 중...</div></div>
{:else if error}
  <div class="card" style="border-color:var(--danger-soft)">
    <div class="card-header">
      <div class="card-title" style="color:var(--danger)">불러오기 실패</div>
      <span class="pill danger"><span class="dot"></span>{error}</span>
    </div>
    <button class="btn" onclick={load} style="margin-top:8px">다시 시도</button>
  </div>
{:else if filtered.length === 0}
  <div class="card">
    <div class="text-muted">
      {filter === 'all' ? 'run 이 없습니다' : `필터 "${filter}" 조건에 맞는 run 이 없습니다`}
    </div>
  </div>
{:else}
  <section class="runs-grid">
    {#each filtered as run}
      <div class="card run-card" data-status={run.status}>
        <div class="card-header">
          <div style="min-width:0;flex:1">
            <div class="card-eyebrow">RUN</div>
            <div class="text-mono" style="font-weight:700;color:var(--fg-strong);font-size:13px;word-break:break-all;line-height:1.3">
              {run.name}
            </div>
          </div>
          <span class="pill {statusKind(run.status)}" style="flex-shrink:0">
            <span class="dot"></span>{statusLabel(run.status)}
          </span>
        </div>

        <div style="margin-top:8px">
          <div class="row spread" style="margin-bottom:6px">
            <span class="text-eyebrow">전체 진행률</span>
            <span class="text-mono tnum" style="font-weight:600;color:var(--fg-strong)">{fmt.pct(run.overall_percent, 1)}</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" data-status={statusKind(run.status)} style:width={`${run.overall_percent}%`}></div>
          </div>
        </div>

        <div class="row spread" style="border-top:1px solid var(--border-faint);padding-top:10px;margin-top:12px;flex-wrap:wrap;gap:8px">
          <span class="text-caption">stages <span class="text-mono" style="color:var(--fg);font-weight:600">{run.stage_count}</span></span>
          <span class="text-caption">{fmt.relative(run.updated_at)}</span>
        </div>
        <div class="text-caption" style="font-size:10px;color:var(--dim);margin-top:4px;word-break:break-all">
          {run.path}
        </div>
      </div>
    {/each}
  </section>
{/if}

<style>
  .page-hero { padding: 8px 0; }
  .grid-4-summary {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
  }
  @media (max-width: 1100px) {
    .grid-4-summary { grid-template-columns: repeat(2, 1fr); }
  }
  @media (max-width: 560px) {
    .grid-4-summary { grid-template-columns: 1fr; }
  }
  .runs-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 16px;
  }
  .text-link {
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    text-decoration: underline;
    font: inherit;
    color: var(--accent-strong);
  }
  .progress-track {
    height: 8px;
    border-radius: var(--r-pill);
    background: var(--surface-sunken);
    overflow: hidden;
    border: 1px solid var(--border-faint);
  }
  .progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: var(--r-pill);
    transition: width 400ms ease;
  }
  .progress-fill[data-status="success"] {
    background: linear-gradient(90deg, var(--success), oklch(70% 0.16 150));
  }
  .progress-fill[data-status="danger"] {
    background: linear-gradient(90deg, var(--danger), oklch(70% 0.21 25));
  }
  .progress-fill[data-status="accent"] {
    background: linear-gradient(90deg, var(--accent-strong), var(--accent));
  }
  .run-card {
    transition: transform var(--d-fast), box-shadow var(--d-fast);
  }
  .run-card:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }
</style>
