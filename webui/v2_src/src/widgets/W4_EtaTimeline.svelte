<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { trainingStatus } from '$lib/stores';
  import { fmt } from '$lib/format';

  let status = $state<any>(null);
  trainingStatus.subscribe((v) => (status = v));

  let latest = $derived(status?.latest_stage ?? {});
  let etaSeconds = $derived(latest?.eta_seconds ?? null);
  let updatedAt = $derived(latest?.updated_at ?? null);
  let stagePct = $derived(latest?.stage_percent ?? 0);
  let overallPct = $derived(latest?.overall_percent ?? 0);

  let now = $state(Date.now());
  let nowTimer: number | undefined;
  onMount(() => {
    nowTimer = window.setInterval(() => (now = Date.now()), 1000);
  });
  onDestroy(() => {
    if (nowTimer != null) clearInterval(nowTimer);
  });

  // 경과 시간 = (updated_at - 학습 시작 가정 시각)
  // updated_at 자체는 최신 step 의 갱신 시각. 학습 시작은 stages[0].started_at 같은 필드가 없어서
  // updated_at - eta_seconds 의 elapsed 추정 (overall_percent 기준)
  let etaFinishMs = $derived.by(() => {
    if (etaSeconds == null) return null;
    const base = updatedAt ? Date.parse(updatedAt) : now;
    if (isNaN(base)) return null;
    return base + etaSeconds * 1000;
  });

  let elapsedSec = $derived.by(() => {
    if (etaSeconds == null || overallPct <= 0) return null;
    // overall_percent 가 N% 면 총 시간의 N% 가 지났다고 추정
    // 총시간 = elapsed + eta = elapsed / (pct/100)
    // → elapsed = eta * (pct / (100 - pct))
    const ratio = overallPct / Math.max(0.01, 100 - overallPct);
    return etaSeconds * ratio;
  });

  let totalSec = $derived.by(() => {
    if (etaSeconds == null || elapsedSec == null) return null;
    return etaSeconds + elapsedSec;
  });

  let startMs = $derived.by(() => {
    if (elapsedSec == null) return null;
    return now - elapsedSec * 1000;
  });

  let remainCompact = $derived(fmt.durationCompact(etaSeconds));
  let elapsedCompact = $derived(fmt.durationCompact(elapsedSec));
  let startKst = $derived(startMs != null ? fmt.kstShort(startMs) : '—');
  let finishKst = $derived(etaFinishMs != null ? fmt.kstShort(etaFinishMs) : '—');

  // 마일스톤 (0%, 50%, 현재, 100%)
  let milestonePct = $derived(overallPct);
</script>

<div class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">W4 · ETA Timeline</div>
      <div class="card-title">학습 시작 → 현재 → 예상 완료</div>
    </div>
    <div class="row" style="gap:8px;flex-wrap:wrap">
      <span class="legend"><span class="swatch" style="background:var(--success)"></span>완료</span>
      <span class="legend"><span class="swatch" style="background:var(--accent-strong)"></span>현재</span>
      <span class="legend"><span class="swatch" style="background:var(--surface-sunken);border:1px solid var(--border-strong)"></span>예정</span>
    </div>
  </div>

  <div class="eta-bar">
    <div class="eta-track">
      <div class="eta-fill" style:width={`${milestonePct}%`}></div>
      <!-- 마일스톤 핀 -->
      <div class="milestone" style:left="0%">
        <span class="pin past"></span>
        <span class="pin-label">시작</span>
      </div>
      <div class="milestone" style:left="50%">
        <span class="pin {milestonePct >= 50 ? 'past' : 'future'}"></span>
        <span class="pin-label">중반</span>
      </div>
      <div class="milestone" style:left={`${milestonePct}%`}>
        <span class="pin now"></span>
        <span class="pin-label" style="color:var(--accent-strong);font-weight:600">현재 {fmt.pct(milestonePct, 1)}</span>
      </div>
      <div class="milestone" style:left="100%">
        <span class="pin future"></span>
        <span class="pin-label">완료</span>
      </div>
    </div>
  </div>

  <div class="row spread" style="border-top:1px solid var(--border-faint);padding-top:12px;margin-top:24px;flex-wrap:wrap;gap:12px">
    <div class="row" style="gap:24px;flex-wrap:wrap">
      <span class="text-caption">학습 시작 <span class="text-mono" style="color:var(--fg)">{startKst}</span></span>
      <span class="text-caption">경과 <span class="text-mono" style="color:var(--fg)">{elapsedCompact}</span></span>
      <span class="text-caption">남은 시간 <span class="text-mono tnum" style="color:var(--accent-strong);font-weight:600">{remainCompact}</span></span>
      <span class="text-caption">완료 예상 <span class="text-mono" style="color:var(--fg)">{finishKst}</span></span>
    </div>
  </div>
</div>

<style>
  .eta-bar {
    padding: 32px 16px 36px;
  }
  .eta-track {
    position: relative;
    height: 8px;
    background: var(--surface-sunken);
    border-radius: var(--r-pill);
    border: 1px solid var(--border-faint);
  }
  .eta-fill {
    position: absolute;
    inset: 0 auto 0 0;
    background: linear-gradient(90deg, var(--success), var(--accent));
    border-radius: var(--r-pill);
    transition: width 400ms ease;
  }
  .milestone {
    position: absolute;
    top: 50%;
    transform: translate(-50%, -50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }
  .pin {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 2px solid var(--surface);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  }
  .pin.past { background: var(--success); }
  .pin.now {
    background: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-glow);
    width: 14px;
    height: 14px;
  }
  .pin.future {
    background: var(--surface-sunken);
    border-color: var(--border-strong);
  }
  .pin-label {
    position: absolute;
    top: 18px;
    font: 500 11px/1 var(--font-mono);
    color: var(--muted);
    white-space: nowrap;
  }
</style>
