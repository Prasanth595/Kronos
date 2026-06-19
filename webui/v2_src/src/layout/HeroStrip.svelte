<script lang="ts">
  import { trainingStatus, metricsLatest, lastUpdatedAt } from '$lib/stores';
  import { fmt } from '$lib/format';

  let status = $state<any>(null);
  trainingStatus.subscribe((v) => (status = v));

  let m = $state<any>({});
  metricsLatest.subscribe((v) => (m = v));

  let last = $state('-');
  lastUpdatedAt.subscribe((v) => (last = v));

  let latest = $derived(status?.latest_stage ?? {});
  let stagePct = $derived(latest.stage_percent ?? 0);
  let overallPct = $derived(latest.overall_percent ?? status?.overall_percent ?? 0);
  let sps = $derived(latest.samples_per_second ?? m.samplesPerSec ?? null);
  let etaSeconds = $derived(latest.eta_seconds ?? null);
  let etaCompact = $derived(fmt.durationCompact(etaSeconds));
  let etaFinish = $derived(fmt.finishKst(etaSeconds, latest.updated_at));
  let stageName = $derived(latest.train_stage ?? '-');
  let runName = $derived(m.runName ?? status?.run_name ?? '-');
  let readinessLevel = $derived(status?.readiness?.level ?? 'waiting');
  let readinessLabel = $derived(
    readinessLevel === 'ready' ? 'Predictor 완료' :
    readinessLevel === 'training' ? '학습 진행 중' :
    'Predictor 대기'
  );
</script>

<section class="hero">
  <div class="hero-left">
    <div class="hero-eyebrow">
      <span>실시간 학습 모니터 · /api/training/status</span>
      <span class="header-stat" style="padding:4px 10px;font-size:11px">
        <span class="header-stat-dot live"></span>live
      </span>
    </div>

    <h1 class="hero-title">
      <span class="text-mono" style="font-size:18px;font-weight:600;letter-spacing:0;color:var(--muted);display:block;margin-bottom:6px">
        {runName}
      </span>
      {stageName} 학습 중 <span class="accent">전체 {fmt.pct(overallPct, 1)}</span>
    </h1>

    <p class="hero-sub">
      Hero 영역은 실행 핵심만 요약합니다. 전체 진행률과 단계 구간은 아래 긴 단계 바에서 확인하고,
      손실 곡선·GPU·데이터 범위는 각 전용 카드에서 분리해 확인합니다.
    </p>

    <div class="hero-status-strip" aria-label="실시간 학습 핵심 상태">
      <div>
        <span>현재 단계</span>
        <strong class="text-mono">{stageName}</strong>
      </div>
      <div>
        <span>Step</span>
        <strong class="text-mono tnum">{fmt.int(latest.step)} / {fmt.int(latest.total_steps)}</strong>
      </div>
      <div>
        <span>Epoch</span>
        <strong class="text-mono tnum">{m.epoch ?? '-'} / {m.epochs ?? '-'}</strong>
      </div>
      <div>
        <span>Loss</span>
        <strong class="text-mono tnum">{m.loss != null ? m.loss.toFixed(4) : '—'}</strong>
      </div>
    </div>
  </div>

  <div class="hero-right">
    <div class="card glow" style="padding:20px;gap:16px;align-items:center">
      <div class="row spread" style="width:100%">
        <span class="card-eyebrow">실행 요약</span>
        <span class="signal" data-level={readinessLevel === 'ready' ? 'ready' : readinessLevel === 'training' ? 'ready' : 'waiting'}>
          <span class="light"></span>
          <span>{readinessLabel}</span>
        </span>
      </div>

      <div class="hero-summary">
        <div>
          <div class="text-eyebrow">전체 진행</div>
          <strong class="text-mono tnum">{fmt.pct(overallPct, 1)}</strong>
          <span>단계 구간은 아래 가로 진행 바로 확인</span>
        </div>
        <div>
          <div class="text-eyebrow">현재 단계 진행</div>
          <strong class="text-mono tnum">{fmt.pct(stagePct, 1)}</strong>
          <span>{stageName}</span>
        </div>
      </div>

      <div class="grid-2" style="width:100%">
        <div>
          <div class="text-eyebrow">완료 예상</div>
          <div class="text-mono tnum" style="font-size:22px;font-weight:600;color:var(--fg-strong);margin-top:4px">{etaCompact}</div>
          <div class="text-caption" style="margin-top:2px">{etaFinish}</div>
        </div>
        <div>
          <div class="text-eyebrow">처리 속도</div>
          <div class="text-mono tnum" style="font-size:22px;font-weight:600;color:var(--fg-strong);margin-top:4px">{fmt.num(sps, 1)}</div>
          <div class="text-caption" style="margin-top:2px">samples / second</div>
        </div>
      </div>

      <div style="width:100%;padding-top:8px;border-top:1px solid var(--border-faint);display:flex;align-items:center;justify-content:space-between;gap:8px">
        <span class="text-caption">Polling <span class="text-mono" style="color:var(--fg)">5초</span></span>
        <span class="text-caption">마지막 업데이트 <span class="text-mono" style="color:var(--fg)">{last}</span></span>
      </div>
    </div>
  </div>
</section>

<style>
  .hero-status-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
    margin-top: 16px;
  }
  .hero-status-strip > div {
    min-width: 0;
    padding: 13px 14px;
    border: 1px solid var(--border-faint);
    border-radius: var(--r-md);
    background: color-mix(in oklab, var(--surface-raised) 84%, var(--accent-soft));
  }
  .hero-status-strip span {
    display: block;
    color: var(--muted);
    font: 700 11px/1.2 var(--font-display);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .hero-status-strip strong {
    display: block;
    margin-top: 6px;
    color: var(--fg-strong);
    font-size: 15px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .hero-summary {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  .hero-summary > div {
    padding: 14px;
    border-radius: var(--r-md);
    background: var(--surface-sunken);
    border: 1px solid var(--border-faint);
  }
  .hero-summary strong {
    display: block;
    margin-top: 5px;
    font-size: 24px;
    font-weight: 800;
    color: var(--fg-strong);
  }
  .hero-summary span {
    display: block;
    margin-top: 3px;
    color: var(--muted);
    font: 600 11px/1.3 var(--font-display);
  }
  @media (max-width: 980px) {
    .hero-status-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 560px) {
    .hero-status-strip { grid-template-columns: 1fr; }
    .hero-summary { grid-template-columns: 1fr; }
  }
</style>
