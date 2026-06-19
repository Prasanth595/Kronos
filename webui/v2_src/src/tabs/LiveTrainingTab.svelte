<script lang="ts">
  import { metricsLatest, lossPoints, trainingStatus, systemStatus } from '$lib/stores';
  import { fmt } from '$lib/format';
  import type { DatasetSplitSummary, TrainingStatus } from '$lib/api';
  import W3LossCurve from '$widgets/W3_LossCurve.svelte';
  import W4EtaTimeline from '$widgets/W4_EtaTimeline.svelte';
  import W5GpuSparkline from '$widgets/W5_GpuSparkline.svelte';
  import W6LossVolatility from '$widgets/W6_LossVolatility.svelte';
  import W9LogTail from '$widgets/W9_LogTail.svelte';

  type SplitRow = {
    key: 'train' | 'val' | 'test';
    label: string;
    tone: 'accent' | 'info' | 'warn';
    summary: DatasetSplitSummary;
  };

  type ProgressSegment = {
    key: string;
    label: string;
    stageIndex: number;
    start: number;
    end: number;
    stagePercent: number;
    overallContribution: number;
    active: boolean;
    complete: boolean;
    status?: string;
  };

  type HealthLevel = 'ok' | 'watch' | 'bad' | 'info';
  type HealthCheck = {
    key: string;
    label: string;
    value: string;
    normal: string;
    level: HealthLevel;
    message: string;
  };

  let m = $state<any>({});
  metricsLatest.subscribe((v) => (m = v));

  let pts = $state<{ step: number; loss: number }[]>([]);
  lossPoints.subscribe((v) => (pts = v));

  let status = $state<TrainingStatus | null>(null);
  trainingStatus.subscribe((v) => (status = v));

  let system = $state<any>(null);
  systemStatus.subscribe((v) => (system = v));

  const stats = $derived.by(() => {
    const window = pts.slice(-200);
    if (window.length === 0) return { mean: null, std: null, min: null, max: null, n: 0 };
    const losses = window.map((p) => p.loss);
    const mean = losses.reduce((a, b) => a + b, 0) / losses.length;
    const variance = losses.reduce((a, b) => a + (b - mean) ** 2, 0) / losses.length;
    const std = Math.sqrt(variance);
    return {
      mean,
      std,
      min: Math.min(...losses),
      max: Math.max(...losses),
      n: window.length,
    };
  });

  const trend = $derived.by(() => {
    if (pts.length < 100) return { dir: 'flat' as const, pct: 0 };
    const recent = pts.slice(-50).map((p) => p.loss);
    const prev = pts.slice(-100, -50).map((p) => p.loss);
    const rAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
    const pAvg = prev.reduce((a, b) => a + b, 0) / prev.length;
    if (Math.abs(rAvg - pAvg) < 1e-6) return { dir: 'flat' as const, pct: 0 };
    const pct = pAvg !== 0 ? Math.abs((rAvg - pAvg) / pAvg) * 100 : 0;
    return { dir: rAvg < pAvg ? ('down' as const) : ('up' as const), pct };
  });

  let lr = $derived(m.learningRate);
  const dataset = $derived(status?.dataset_summary ?? null);
  const latestStage = $derived(status?.latest_stage ?? null);
  const cpu = $derived(system?.cpu ?? null);
  const cpuPct = $derived(cpu?.utilization_percent ?? null);
  const cpuTempC = $derived(cpu?.temperature_c ?? null);
  const cpuTempPct = $derived(cpu?.temperature_percent ?? null);
  const overallPercent = $derived.by(() =>
    clampPercent(status?.overall_percent ?? latestStage?.overall_percent ?? 0),
  );
  const stageCount = $derived.by(() => Math.max(1, Number(latestStage?.stage_count ?? status?.stage_count ?? 2) || 2));
  const currentStagePercent = $derived.by(() => clampPercent(latestStage?.stage_percent ?? 0));
  const currentStageLabel = $derived(stageLabel(latestStage?.train_stage));
  const latestLossPoint = $derived(pts.length ? pts[pts.length - 1] : null);
  const recentAnchorPoint = $derived(pts.length > 1 ? pts[Math.max(0, pts.length - 30)] : null);
  const recentStepDelta = $derived.by(() => {
    if (!latestLossPoint || !recentAnchorPoint) return null;
    return latestLossPoint.step - recentAnchorPoint.step;
  });

  const splitRows = $derived.by<SplitRow[]>(() => {
    const splits = dataset?.splits ?? {};
    const rows: Array<{ key: 'train' | 'val' | 'test'; label: string; tone: 'accent' | 'info' | 'warn' }> = [
      { key: 'train', label: '학습', tone: 'accent' },
      { key: 'val', label: '검증', tone: 'info' },
      { key: 'test', label: '테스트', tone: 'warn' },
    ];
    return rows
      .map((row) => ({ ...row, summary: splits[row.key] }))
      .filter((row): row is SplitRow => Boolean(row.summary));
  });

  function ymd(value?: string | null): string {
    if (!value || value.length !== 8) return value ?? '-';
    return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
  }

  function hms(value?: string | null): string {
    if (!value || value.length < 6) return value ?? '-';
    return `${value.slice(0, 2)}:${value.slice(2, 4)}:${value.slice(4, 6)}`;
  }

  function featureLabel(value: string): string {
    const labels: Record<string, string> = {
      open: '시가',
      high: '고가',
      low: '저가',
      close: '종가/현재가',
      vol: '거래량',
      amt: '거래대금',
      minute: '분',
      hour: '시',
      weekday: '요일',
      day: '일',
      month: '월',
    };
    return labels[value] ?? value;
  }

  function clampPercent(value: unknown): number {
    const numeric = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(numeric)) return 0;
    return Math.max(0, Math.min(100, numeric));
  }

  function stageLabel(value?: string | null): string {
    if (value === 'tokenizer') return '토크나이저';
    if (value === 'predictor') return '프리딕터';
    if (!value) return '대기';
    return value;
  }

  function defaultStageName(index: number, count: number): string {
    if (count === 2 && index === 1) return 'tokenizer';
    if (count === 2 && index === 2) return 'predictor';
    return `stage-${index}`;
  }

  function fmtMaybePct(value: unknown, digits = 1): string {
    if (value == null) return '—';
    const numeric = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(numeric) ? `${fmt.num(numeric, digits)}%` : '—';
  }

  function fmtMaybeTemp(value: unknown): string {
    if (value == null) return '미측정';
    const numeric = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(numeric) ? `${fmt.num(numeric, 1)}°C` : '미측정';
  }

  function healthLabel(level: HealthLevel): string {
    if (level === 'ok') return '정상';
    if (level === 'watch') return '주의';
    if (level === 'bad') return '위험';
    return '정보';
  }

  const progressSegments = $derived.by<ProgressSegment[]>(() => {
    const latest = latestStage;
    const count = stageCount;
    const latestIndex = Number(latest?.stage_index ?? 1) || 1;
    const stages = Array.isArray(status?.stages) ? status.stages : [];
    const byName = new Map(stages.map((stage) => [stage.train_stage, stage]));

    return Array.from({ length: count }, (_, idx) => {
      const stageIndex = idx + 1;
      const key = defaultStageName(stageIndex, count);
      const stage = byName.get(key);
      const active = stageIndex === latestIndex || latest?.train_stage === key;
      const inferredPercent =
        stage?.stage_percent ??
        (active ? latest?.stage_percent : stageIndex < latestIndex ? 100 : 0);
      const stagePercent = clampPercent(inferredPercent);
      const start = (idx / count) * 100;
      const end = ((idx + 1) / count) * 100;
      return {
        key,
        label: stageLabel(key),
        stageIndex,
        start,
        end,
        stagePercent,
        overallContribution: stagePercent / count,
        active,
        complete: stagePercent >= 99.95 || ['ok', 'recovered'].includes(stage?.status),
        status: stage?.status ?? (active ? latest?.status : undefined),
      };
    });
  });

  const progressFormula = $derived.by(() => {
    const count = stageCount;
    const latest = latestStage;
    if (!latest) return '전체 진행률 = 단계별 진행률을 동일 구간으로 합산';
    return `전체 ${fmt.num(overallPercent, 1)}% = 완료 구간 + ${currentStageLabel} ${fmt.num(currentStagePercent, 1)}% × 1/${count}`;
  });

  const healthChecks = $derived.by<HealthCheck[]>(() => {
    const currentLoss = m.loss ?? latestLossPoint?.loss ?? null;
    const lossUpper = stats.mean != null && stats.std != null ? stats.mean + stats.std * 2 : null;
    const lossLower = stats.mean != null && stats.std != null ? Math.max(0, stats.mean - stats.std * 2) : null;
    const lossLevel: HealthLevel =
      currentLoss == null || lossUpper == null
        ? 'info'
        : currentLoss <= lossUpper
          ? 'ok'
          : currentLoss <= lossUpper * 1.25
            ? 'watch'
            : 'bad';
    const stepMoving = (recentStepDelta ?? 0) > 0 || (m.samplesPerSec ?? 0) > 0;
    const stepLevel: HealthLevel = latestStage?.status === 'running' && !stepMoving ? 'watch' : 'ok';
    const lrLevel: HealthLevel =
      lr == null ? 'info' : lr > 0 && lr <= 1e-3 ? 'ok' : lr > 0 && lr <= 1e-2 ? 'watch' : 'bad';
    const progressLevel: HealthLevel =
      overallPercent >= 0 && overallPercent <= 100 && currentStagePercent >= 0 && currentStagePercent <= 100
        ? 'ok'
        : 'bad';
    const cpuLevel: HealthLevel =
      cpuPct == null && cpuTempC == null
        ? 'info'
        : (cpuTempC != null && cpuTempC >= 92) || (cpuPct != null && cpuPct >= 98)
          ? 'bad'
          : (cpuTempC != null && cpuTempC >= 85) || (cpuPct != null && cpuPct >= 95)
            ? 'watch'
            : 'ok';

    return [
      {
        key: 'progress',
        label: '진행률',
        value: `전체 ${fmt.num(overallPercent, 1)}% · 단계 ${fmt.num(currentStagePercent, 1)}%`,
        normal: '0~100%, 현재 단계 안에서 증가',
        level: progressLevel,
        message: progressLevel === 'ok' ? '단계/전체 진행률 산식이 정상 범위입니다.' : '진행률 값이 정상 범위를 벗어났습니다.',
      },
      {
        key: 'lr',
        label: '학습률(LR)',
        value: lr != null ? lr.toExponential(2) : '—',
        normal: '0 < LR ≤ 1e-3 참고',
        level: lrLevel,
        message:
          lrLevel === 'ok'
            ? '현재 LR은 보수적인 미세조정 범위입니다.'
            : lrLevel === 'info'
              ? '최근 history에서 LR을 아직 읽지 못했습니다.'
              : 'LR이 일반 참고 범위보다 큽니다. 손실 급등 여부를 함께 보세요.',
      },
      {
        key: 'loss',
        label: 'Rolling avg loss',
        value:
          currentLoss != null
            ? `현재 ${currentLoss.toFixed(4)} · 평균 ${stats.mean != null ? stats.mean.toFixed(4) : '—'}`
            : '—',
        normal:
          lossLower != null && lossUpper != null
            ? `${lossLower.toFixed(4)} ~ ${lossUpper.toFixed(4)}`
            : '최근 200포인트 평균 ± 2σ',
        level: lossLevel,
        message:
          lossLevel === 'ok'
            ? '현재 손실이 최근 rolling 범위 안에 있습니다.'
            : lossLevel === 'info'
              ? 'rolling loss 포인트가 더 필요합니다.'
              : '현재 손실이 rolling 평균 대비 높습니다. 다음 몇 분 추세 확인이 필요합니다.',
      },
      {
        key: 'step',
        label: 'Step/Loss 수신',
        value: `step ${fmt.int(latestStage?.step)} · Δ${fmt.int(recentStepDelta ?? 0)}`,
        normal: '최근 30포인트에서 step 증가',
        level: stepLevel,
        message: stepLevel === 'ok' ? 'step과 loss 로그가 계속 갱신되고 있습니다.' : 'running 상태지만 최근 step 증가가 약합니다.',
      },
      {
        key: 'cpu',
        label: 'Host CPU 상태',
        value: `${fmtMaybePct(cpuPct)} · ${fmtMaybeTemp(cpuTempC)}${cpuTempPct != null ? ` (${fmt.num(cpuTempPct, 0)}%)` : ''}`,
        normal: 'CPU < 95%, 온도 < 85°C 권장',
        level: cpuLevel,
        message:
          cpuLevel === 'ok'
            ? 'CPU 사용률/온도는 학습 감시에 무리가 없는 범위입니다.'
            : cpuLevel === 'info'
              ? 'CPU 온도 센서가 OS에서 노출되지 않을 수 있습니다.'
              : 'CPU 부하 또는 온도가 높습니다. 냉각/백그라운드 작업을 확인하세요.',
      },
    ];
  });

  const healthSummary = $derived.by(() => {
    const bad = healthChecks.filter((item) => item.level === 'bad').length;
    const watch = healthChecks.filter((item) => item.level === 'watch').length;
    if (bad > 0) return { level: 'bad' as HealthLevel, label: '학습 상태 위험', message: `${bad}개 항목이 위험 범위입니다.` };
    if (watch > 0) return { level: 'watch' as HealthLevel, label: '학습 상태 주의', message: `${watch}개 항목을 관찰하세요.` };
    return { level: 'ok' as HealthLevel, label: '학습 정상 진행', message: '진행률·LR·loss·step·CPU 기준이 정상입니다.' };
  });
</script>

<!-- ===== 핵심 실시간 지표 ===== -->
<section class="metric-grid">
  <div class="metric glow">
    <div class="metric-head">
      <span class="metric-label">현재 손실</span>
      {#if trend.dir !== 'flat'}
        <span class="delta {trend.dir === 'down' ? 'down' : 'up'}">
          {trend.dir === 'down' ? '↓ 개선' : '↑ 상승'} {fmt.num(trend.pct, 1)}%
        </span>
      {:else}
        <span class="delta flat">→ 0.0%</span>
      {/if}
    </div>
    <div class="metric-value tnum">
      {m.loss != null ? m.loss.toFixed(4) : '-'}<span class="metric-unit">최근값</span>
    </div>
    <div class="metric-foot">
      평균 <span class="text-mono" style="color:var(--fg)">{stats.mean != null ? stats.mean.toFixed(4) : '-'}</span>
      ± <span class="text-mono" style="color:var(--fg)">{stats.std != null ? stats.std.toFixed(4) : '-'}</span>
    </div>
  </div>

  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">처리 속도</span>
      <span class="pill success" style="padding:2px 8px;font-size:10px">live</span>
    </div>
    <div class="metric-value tnum">
      {fmt.num(m.samplesPerSec, 1)}<span class="metric-unit">samples/s</span>
    </div>
    <div class="metric-foot">
      step <span class="text-mono" style="color:var(--fg)">{fmt.int(status?.latest_stage?.step)}</span>
      / {fmt.int(status?.latest_stage?.total_steps)} · 현재 batch 기준
    </div>
  </div>

  <div class="metric">
    <div class="metric-head">
      <span class="metric-label">Learning Rate</span>
      <span class="pill" style="padding:2px 8px;font-size:10px">scheduled</span>
    </div>
    <div class="metric-value mono tnum">
      {lr != null ? lr.toExponential(2) : '-'}
    </div>
    <div class="metric-foot">
      소수 표기 <span class="text-mono" style="color:var(--fg)">{lr != null ? lr.toFixed(6) : '-'}</span>
    </div>
  </div>
</section>

<!-- ===== 학습 정상 범위 점검 ===== -->
<section class="card training-health-card glow" aria-label="학습 정상 범위와 현재 상태 점검">
  <div class="training-health-head">
    <div>
      <div class="text-eyebrow">TRAINING HEALTH</div>
      <h2>현재 학습이 잘 진행 중인지 기준과 함께 확인합니다</h2>
      <p>
        아래 정상 범위는 수익률 보장이 아니라 실시간 학습 모니터링용 안전 기준입니다.
        손실은 고정 절대값보다 최근 rolling 평균과 표준편차를 기준으로 이상 여부를 판단합니다.
      </p>
    </div>
    <div class="health-summary" data-level={healthSummary.level}>
      <span>{healthLabel(healthSummary.level)}</span>
      <strong>{healthSummary.label}</strong>
      <small>{healthSummary.message}</small>
    </div>
  </div>

  <div class="health-check-grid">
    {#each healthChecks as item (item.key)}
      <div class="health-check" data-level={item.level}>
        <div class="row spread">
          <strong>{item.label}</strong>
          <span class="health-chip">{healthLabel(item.level)}</span>
        </div>
        <div class="health-value text-mono tnum">{item.value}</div>
        <div class="health-normal">정상 범위: {item.normal}</div>
        <p>{item.message}</p>
      </div>
    {/each}
  </div>
</section>

<!-- ===== 단계 구간이 보이는 전체 진행률 가로 바 ===== -->
<section class="card progress-card stage-timeline-card glow" aria-label="단계별 전체 진행률 가로 막대">
  <div class="stage-progress-head">
    <div>
      <div class="text-eyebrow">STAGE-AWARE PROGRESS</div>
      <h2>전체 진행률을 한 줄 단계 바로 봅니다</h2>
      <p>
        전체 100%를 {stageCount}개 단계 구간으로 나누고, 현재 단계의 채움 값은 해당 구간 안에서만 표시합니다.
        중복 표시를 줄이고, 단계별 위치·기여도·현재 속도를 한 화면에서 비교합니다.
      </p>
    </div>
    <div class="stage-progress-kpis" aria-label="전체와 현재 단계 진행 요약">
      <div>
        <span>전체 진행</span>
        <strong class="tnum">{fmt.num(overallPercent, 1)}%</strong>
      </div>
      <div>
        <span>현재 단계</span>
        <strong class="tnum">{currentStageLabel} {fmt.num(currentStagePercent, 1)}%</strong>
      </div>
    </div>
  </div>

  <div class="progress-formula text-mono">{progressFormula}</div>

  <div
    class="stage-track"
    role="img"
    aria-label={`전체 진행률 ${fmt.num(overallPercent, 1)}%, 현재 단계 ${currentStageLabel} ${fmt.num(currentStagePercent, 1)}%`}
  >
    {#each progressSegments as segment (segment.key)}
      <div
        class="stage-track-segment"
        data-active={segment.active ? 'true' : 'false'}
        data-complete={segment.complete ? 'true' : 'false'}
        style:flex-basis={`${100 / stageCount}%`}
        title={`${segment.stageIndex}구간 ${segment.label}: ${fmt.num(segment.stagePercent, 1)}%`}
      >
        <span style:width={`${segment.stagePercent}%`}></span>
        <em>{segment.stageIndex}</em>
      </div>
    {/each}
  </div>

  <div class="stage-scale-row" aria-hidden="true">
    {#each progressSegments as segment (segment.key)}
      <span style:left={`${segment.start}%`}>{fmt.num(segment.start, 0)}%</span>
    {/each}
    <span style:left="100%">100%</span>
  </div>

  <div class="segment-list compact">
    {#each progressSegments as segment (segment.key)}
      <div class="segment-row" data-active={segment.active ? 'true' : 'false'}>
        <div class="segment-main">
          <span class="segment-dot" data-active={segment.active ? 'true' : 'false'} data-complete={segment.complete ? 'true' : 'false'}></span>
          <div>
            <strong>{segment.stageIndex}구간 · {segment.label}</strong>
            <small>전체 {fmt.num(segment.start, 0)}~{fmt.num(segment.end, 0)}%</small>
          </div>
        </div>
        <div class="segment-stat">
          <strong class="tnum">{fmt.num(segment.stagePercent, 1)}%</strong>
          <small>전체 기여 {fmt.num(segment.overallContribution, 1)}%</small>
        </div>
      </div>
    {/each}
  </div>
</section>

<!-- ===== 학습 데이터 범위 / 특징 요약 ===== -->
{#if dataset?.available}
  <section class="card dataset-card glow" aria-label="STOM 학습 데이터 범위 요약">
    <div class="dataset-hero">
      <div>
        <div class="text-eyebrow">DATASET SCOPE</div>
        <h2>STOM 2025 전체 1초봉 · pred{dataset.horizon_seconds ?? dataset.predict_window ?? '-'}</h2>
        <p>
          공식 Kronos OHLCV 입력에 맞춰 <strong>{dataset.features?.map(featureLabel).join(' · ')}</strong>를 사용하고,
          시간 feature는 <strong>{dataset.time_features?.map(featureLabel).join(' · ')}</strong>로 보강합니다.
        </p>
      </div>
      <div class="dataset-badges" aria-label="데이터 설정">
        <span class="pill accent">{dataset.freq ?? '1s'}</span>
        <span class="pill">{hms(dataset.range?.time_start)}~{hms(dataset.range?.time_end)}</span>
        <span class="pill">lookback {fmt.int(dataset.lookback_window)}</span>
        <span class="pill">window {fmt.int(dataset.sample_window)}</span>
        {#if dataset.regularize_1s}<span class="pill success">1초 정규화</span>{/if}
      </div>
    </div>

    <div class="dataset-metrics">
      <div class="dataset-mini">
        <span>학습 samples</span>
        <strong class="tnum">{fmt.int(dataset.current_targets?.train_samples)}</strong>
        <small>검증 {fmt.int(dataset.current_targets?.val_samples)}</small>
      </div>
      <div class="dataset-mini">
        <span>전체 rows</span>
        <strong class="tnum">{fmt.int(dataset.counts?.exported_row_count)}</strong>
        <small>그룹 {fmt.int(dataset.counts?.exported_group_count)}</small>
      </div>
      <div class="dataset-mini">
        <span>종목 테이블</span>
        <strong class="tnum">{fmt.int(dataset.counts?.tables_with_rows)}</strong>
        <small>전체 {fmt.int(dataset.counts?.table_count)} · 0행 {fmt.int(dataset.counts?.tables_zero_rows)}</small>
      </div>
      <div class="dataset-mini">
        <span>실제 거래일</span>
        <strong>{ymd(dataset.range?.actual_start)}</strong>
        <small>~ {ymd(dataset.range?.actual_end)}</small>
      </div>
    </div>

    <div class="dataset-detail-grid">
      <div class="split-table" role="table" aria-label="학습 검증 테스트 분할">
        <div class="split-row split-head" role="row">
          <span>구간</span>
          <span>기간</span>
          <span>세션</span>
          <span>그룹</span>
          <span>rows</span>
          <span>samples</span>
        </div>
        {#each splitRows as row (row.key)}
          <div class="split-row" role="row">
            <span><span class="pill {row.tone}">{row.label}</span></span>
            <span>{ymd(row.summary.first_session)} ~ {ymd(row.summary.last_session)}</span>
            <span class="tnum">{fmt.int(row.summary.sessions)}</span>
            <span class="tnum">{fmt.int(row.summary.groups)}</span>
            <span class="tnum">{fmt.int(row.summary.rows)}</span>
            <span class="tnum">{fmt.int(row.summary.current_target_samples ?? row.summary.possible_samples)}</span>
          </div>
        {/each}
      </div>

      <div class="feature-panel">
        <div>
          <div class="text-eyebrow">FEATURES</div>
          <div class="feature-chips">
            {#each dataset.features ?? [] as feature}
              <span class="feature-chip">{featureLabel(feature)}<em>{feature}</em></span>
            {/each}
          </div>
        </div>
        <div>
          <div class="text-eyebrow">TIME FEATURES</div>
          <div class="feature-chips muted">
            {#each dataset.time_features ?? [] as feature}
              <span class="feature-chip">{featureLabel(feature)}<em>{feature}</em></span>
            {/each}
          </div>
        </div>
        <div class="dataset-note">
          <strong>주의:</strong> price_mode가 <code>{dataset.price_mode ?? '-'}</code>이면 STOM tick DB의 현재가 기반으로 OHLC가 구성됩니다.
          {#if dataset.warnings?.length}
            <br />{dataset.warnings[0]}
          {/if}
        </div>
      </div>
    </div>

    <div class="dataset-source text-caption">
      DB: <span class="text-mono">{dataset.source_db ?? '-'}</span>
      · Report: <span class="text-mono">{dataset.report_path ?? '-'}</span>
    </div>
  </section>
{:else if dataset}
  <section class="card dataset-card dataset-card-warn" aria-label="STOM 학습 데이터 범위 요약 없음">
    <div class="dataset-hero">
      <div>
        <div class="text-eyebrow">DATASET SCOPE</div>
        <h2>데이터 요약을 아직 읽지 못했습니다</h2>
        <p>{dataset.message ?? '현재 run의 Qlib export report를 찾는 중입니다.'}</p>
      </div>
      <span class="pill warn">확인 필요</span>
    </div>
  </section>
{/if}

<!-- ===== 손실 곡선 + 변동성 ===== -->
<section class="grid-3-1">
  <W3LossCurve />
  <W6LossVolatility {stats} {trend} />
</section>

<!-- ===== ETA 타임라인 ===== -->
<W4EtaTimeline />

<!-- ===== GPU 추세 ===== -->
<W5GpuSparkline />

<!-- ===== 로그 tail ===== -->
<W9LogTail />

<style>
  .metric-grid {
    display: grid;
    grid-template-columns: 1.18fr 1fr 0.95fr;
    gap: 16px;
  }
  .grid-3-1 {
    display: grid;
    grid-template-columns: 3fr 1fr;
    gap: 16px;
  }
  .training-health-card {
    overflow: hidden;
  }
  .training-health-card::before {
    content: '';
    position: absolute;
    inset: 0 0 auto 0;
    height: 4px;
    background: linear-gradient(90deg, var(--success), var(--accent), var(--info));
  }
  .training-health-head {
    display: grid;
    grid-template-columns: minmax(0, 1.45fr) minmax(260px, 0.72fr);
    gap: 18px;
    align-items: start;
  }
  .training-health-head h2 {
    margin-top: 4px;
    color: var(--fg-strong);
    font: 700 22px/1.25 var(--font-display);
    letter-spacing: -0.018em;
  }
  .training-health-head p {
    margin-top: 8px;
    color: var(--muted);
    max-width: 920px;
  }
  .health-summary {
    padding: 15px 16px;
    border-radius: var(--r-md);
    border: 1px solid var(--border-faint);
    background: var(--surface-sunken);
  }
  .health-summary[data-level='ok'] {
    border-color: color-mix(in oklab, var(--success) 34%, var(--border-faint));
    background: var(--success-soft);
  }
  .health-summary[data-level='watch'] {
    border-color: color-mix(in oklab, var(--warn) 34%, var(--border-faint));
    background: var(--warn-soft);
  }
  .health-summary[data-level='bad'] {
    border-color: color-mix(in oklab, var(--danger) 34%, var(--border-faint));
    background: var(--danger-soft);
  }
  .health-summary span,
  .health-summary small {
    display: block;
    color: var(--muted);
    font: 700 11px/1.25 var(--font-display);
  }
  .health-summary strong {
    display: block;
    margin: 6px 0 5px;
    color: var(--fg-strong);
    font: 800 24px/1.1 var(--font-display);
    letter-spacing: -0.02em;
  }
  .health-check-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 10px;
  }
  .health-check {
    min-width: 0;
    padding: 13px 14px;
    border: 1px solid var(--border-faint);
    border-radius: var(--r-md);
    background: var(--surface-raised);
  }
  .health-check[data-level='ok'] {
    border-color: color-mix(in oklab, var(--success) 26%, var(--border-faint));
  }
  .health-check[data-level='watch'] {
    border-color: color-mix(in oklab, var(--warn) 34%, var(--border-faint));
    background: color-mix(in oklab, var(--surface-raised) 76%, var(--warn-soft));
  }
  .health-check[data-level='bad'] {
    border-color: color-mix(in oklab, var(--danger) 34%, var(--border-faint));
    background: color-mix(in oklab, var(--surface-raised) 76%, var(--danger-soft));
  }
  .health-check strong {
    color: var(--fg-strong);
    font: 700 13px/1.2 var(--font-display);
  }
  .health-chip {
    padding: 2px 7px;
    border-radius: var(--r-pill);
    color: var(--muted);
    background: var(--surface-sunken);
    font: 800 10px/1.4 var(--font-display);
  }
  .health-check[data-level='ok'] .health-chip {
    color: var(--success);
    background: var(--success-soft);
  }
  .health-check[data-level='watch'] .health-chip {
    color: var(--warn);
    background: var(--warn-soft);
  }
  .health-check[data-level='bad'] .health-chip {
    color: var(--danger);
    background: var(--danger-soft);
  }
  .health-value {
    margin-top: 10px;
    color: var(--fg-strong);
    font-size: 17px;
    font-weight: 800;
    overflow-wrap: anywhere;
  }
  .health-normal {
    margin-top: 7px;
    color: var(--muted);
    font: 700 11px/1.35 var(--font-display);
  }
  .health-check p {
    margin-top: 7px;
    color: var(--muted);
    font-size: 12px;
    line-height: 1.45;
  }

  .progress-card {
    overflow: hidden;
  }
  .progress-card::before {
    content: '';
    position: absolute;
    inset: 0 0 auto 0;
    height: 4px;
    background: linear-gradient(90deg, var(--accent), var(--info), var(--warm));
  }
  .stage-timeline-card {
    gap: 18px;
  }
  .stage-progress-head {
    display: grid;
    grid-template-columns: minmax(0, 1.45fr) minmax(280px, 0.78fr);
    gap: 18px;
    align-items: start;
  }
  .stage-progress-head h2 {
    margin-top: 4px;
    font: 700 22px/1.25 var(--font-display);
    letter-spacing: -0.018em;
    color: var(--fg-strong);
  }
  .stage-progress-head p {
    margin-top: 8px;
    color: var(--muted);
    max-width: 880px;
  }
  .stage-progress-kpis {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  .stage-progress-kpis > div {
    padding: 14px;
    border: 1px solid var(--border-faint);
    border-radius: var(--r-md);
    background: color-mix(in oklab, var(--surface-raised) 84%, var(--accent-soft));
  }
  .stage-progress-kpis span {
    display: block;
    color: var(--muted);
    font: 700 11px/1.2 var(--font-display);
  }
  .stage-progress-kpis strong {
    display: block;
    margin-top: 6px;
    color: var(--fg-strong);
    font: 800 24px/1.05 var(--font-display);
    letter-spacing: -0.02em;
  }
  .progress-formula {
    width: fit-content;
    max-width: 100%;
    padding: 10px 12px;
    border-radius: var(--r-md);
    background: var(--accent-soft);
    color: var(--accent-strong);
    font-weight: 700;
    overflow-wrap: anywhere;
  }
  :global([data-theme='dark']) .progress-formula {
    color: var(--accent);
  }
  .stage-track {
    position: relative;
    display: flex;
    width: 100%;
    height: 34px;
    overflow: hidden;
    border-radius: var(--r-pill);
    border: 1px solid var(--border-faint);
    background: var(--surface-sunken);
    box-shadow: inset 0 1px 0 color-mix(in oklab, white 36%, transparent);
  }
  .stage-track-segment {
    position: relative;
    flex-grow: 0;
    flex-shrink: 0;
    min-width: 0;
    height: 100%;
    background: var(--surface-sunken);
    border-left: 1px solid var(--border-faint);
  }
  .stage-track-segment:first-child {
    border-left: none;
  }
  .stage-track-segment > span {
    position: absolute;
    inset: 0 auto 0 0;
    display: block;
    max-width: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, var(--accent), color-mix(in oklab, var(--accent) 52%, var(--info)));
  }
  .stage-track-segment[data-complete='true'] > span {
    background: linear-gradient(90deg, var(--success), color-mix(in oklab, var(--success) 45%, var(--accent)));
  }
  .stage-track-segment[data-active='true'] {
    background: color-mix(in oklab, var(--accent-soft) 55%, var(--surface-sunken));
  }
  .stage-track-segment em {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    color: var(--fg-strong);
    font: 800 12px/1 var(--font-display);
    font-style: normal;
    text-shadow: 0 1px 2px color-mix(in oklab, black 35%, transparent);
    pointer-events: none;
  }
  .stage-scale-row {
    position: relative;
    height: 20px;
    margin-top: -8px;
  }
  .stage-scale-row span {
    position: absolute;
    transform: translateX(-50%);
    color: var(--muted);
    font: 700 10px/1 var(--font-mono);
    white-space: nowrap;
  }
  .stage-scale-row span:first-child {
    transform: translateX(0);
  }
  .stage-scale-row span:last-child {
    transform: translateX(-100%);
  }
  .segment-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  .segment-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px 12px;
    align-items: center;
    padding: 13px 14px;
    border: 1px solid var(--border-faint);
    border-radius: var(--r-md);
    background: var(--surface-raised);
  }
  .segment-row[data-active='true'] {
    border-color: var(--accent-tint);
    background: color-mix(in oklab, var(--surface-raised) 82%, var(--accent-soft));
  }
  .segment-main {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .segment-main strong {
    display: block;
    color: var(--fg-strong);
    font: 700 13px/1.2 var(--font-display);
  }
  .segment-main small,
  .segment-stat small {
    color: var(--muted);
    font: 600 11px/1.25 var(--font-mono);
  }
  .segment-dot {
    width: 11px;
    height: 11px;
    border-radius: 50%;
    background: var(--border-strong);
    box-shadow: 0 0 0 4px color-mix(in oklab, var(--border-strong) 18%, transparent);
    flex-shrink: 0;
  }
  .segment-dot[data-active='true'] {
    background: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-glow);
  }
  .segment-dot[data-complete='true'] {
    background: var(--success);
    box-shadow: 0 0 0 4px color-mix(in oklab, var(--success) 18%, transparent);
  }
  .segment-stat {
    text-align: right;
  }
  .segment-stat strong {
    display: block;
    color: var(--fg-strong);
    font: 800 18px/1 var(--font-display);
  }
  .dataset-card {
    overflow: hidden;
  }
  .dataset-card::before {
    content: '';
    position: absolute;
    inset: 0 0 auto 0;
    height: 4px;
    background: linear-gradient(90deg, var(--accent), color-mix(in oklab, var(--accent) 45%, var(--warm)));
  }
  .dataset-card-warn::before {
    background: linear-gradient(90deg, var(--warn), var(--warm));
  }
  .dataset-hero {
    display: flex;
    justify-content: space-between;
    gap: 18px;
    align-items: flex-start;
  }
  .dataset-hero h2 {
    margin-top: 4px;
    font: 700 22px/1.25 var(--font-display);
    letter-spacing: -0.018em;
    color: var(--fg-strong);
  }
  .dataset-hero p {
    margin-top: 8px;
    max-width: 780px;
    color: var(--muted);
  }
  .dataset-hero strong {
    color: var(--fg-strong);
    font-weight: 700;
  }
  .dataset-badges {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
    min-width: min(360px, 100%);
  }
  .dataset-metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }
  .dataset-mini {
    padding: 14px 16px;
    border: 1px solid var(--border-faint);
    border-radius: var(--r-md);
    background: color-mix(in oklab, var(--surface-raised) 82%, var(--accent-soft));
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .dataset-mini span,
  .dataset-mini small {
    color: var(--muted);
    font: 600 11px/1.35 var(--font-display);
  }
  .dataset-mini strong {
    color: var(--fg-strong);
    font: 700 21px/1.15 var(--font-display);
    letter-spacing: -0.012em;
    word-break: keep-all;
  }
  .dataset-detail-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.6fr) minmax(300px, 0.9fr);
    gap: 16px;
  }
  .split-table {
    border: 1px solid var(--border-faint);
    border-radius: var(--r-md);
    overflow: hidden;
    background: var(--surface);
  }
  .split-row {
    display: grid;
    grid-template-columns: 74px 1.25fr 0.55fr 0.65fr 0.8fr 0.9fr;
    align-items: center;
    gap: 10px;
    padding: 11px 14px;
    border-top: 1px solid var(--border-faint);
    font: 500 12px/1.35 var(--font-mono);
  }
  .split-row:first-child {
    border-top: none;
  }
  .split-head {
    background: var(--surface-sunken);
    color: var(--muted);
    font: 700 11px/1.2 var(--font-display);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .feature-panel {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 16px;
    border-radius: var(--r-md);
    border: 1px solid var(--border-faint);
    background: var(--surface-raised);
  }
  .feature-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
  }
  .feature-chip {
    display: inline-flex;
    align-items: baseline;
    gap: 6px;
    padding: 7px 10px;
    border-radius: var(--r-pill);
    background: var(--accent-soft);
    color: var(--accent-strong);
    font: 700 12px/1 var(--font-display);
  }
  :global([data-theme='dark']) .feature-chip {
    color: var(--accent);
  }
  .feature-chips.muted .feature-chip {
    background: var(--surface-sunken);
    color: var(--muted);
  }
  .feature-chip em {
    font: 600 10px/1 var(--font-mono);
    opacity: 0.72;
    font-style: normal;
  }
  .dataset-note {
    padding: 12px;
    border-radius: var(--r-md);
    background: var(--warm-soft);
    color: var(--fg);
    font-size: 12px;
    line-height: 1.55;
  }
  .dataset-note code {
    font-family: var(--font-mono);
    color: var(--accent-strong);
  }
  .dataset-source {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding-top: 2px;
    word-break: break-all;
  }

  @media (max-width: 1200px) {
    .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .grid-3-1 { grid-template-columns: 1fr; }
    .training-health-head { grid-template-columns: 1fr; }
    .health-check-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .stage-progress-head { grid-template-columns: 1fr; }
    .dataset-metrics { grid-template-columns: repeat(2, 1fr); }
    .dataset-detail-grid { grid-template-columns: 1fr; }
  }
  @media (max-width: 760px) {
    .health-check-grid { grid-template-columns: 1fr; }
    .segment-list { grid-template-columns: 1fr; }
    .dataset-hero { flex-direction: column; }
    .dataset-badges { justify-content: flex-start; min-width: 0; }
    .split-table { overflow-x: auto; }
    .split-row { min-width: 740px; }
  }
  @media (max-width: 560px) {
    .metric-grid { grid-template-columns: 1fr; }
    .dataset-metrics { grid-template-columns: 1fr; }
  }
</style>
