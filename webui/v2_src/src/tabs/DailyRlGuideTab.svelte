<script lang="ts">
  import { onMount } from 'svelte';
  import { dailyOhlcvApi, type DailyRlEnvGuideResponse } from '$lib/dailyOhlcvApi';

  let guide = $state<DailyRlEnvGuideResponse | null>(null);
  let loading = $state(false);

  let visualFrame = $state(0);
  let selectedLaneId = $state('D4_RL_RISK_OVERLAY');
  let selectedTemplateId = $state('D3_D4_SIGNAL_QUALITY_AUDIT');
  let selectedWorkflowId = $state('PAST_ONLY_MARKET_REGIME_AUDIT');

  const rows = (items: unknown): readonly Record<string, unknown>[] => {
    if (!Array.isArray(items)) return [];
    return items.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
  };
  const listText = (value: unknown): string => Array.isArray(value) ? value.join(' · ') : String(value ?? '—');
  const stringItems = (value: unknown): string[] => Array.isArray(value) ? value.map((item) => String(item)) : [];
  const safeJson = (value: unknown): string => JSON.stringify(value ?? {}, null, 2);
  const boolText = (value: unknown): string => value === true ? 'true' : value === false ? 'false' : '—';
  const asRecord = (value: unknown): Record<string, unknown> => (
    value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
  );
  const field = (value: unknown, key: string): unknown => asRecord(value)[key];
  const nestedRecord = (value: unknown, key: string): Record<string, unknown> => asRecord(field(value, key));
  const numberValue = (value: unknown): number | null => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  };
  const formatPercent = (value: unknown, digits = 2): string => {
    const numeric = numberValue(value);
    if (numeric === null) return '—';
    const prefix = numeric > 0 ? '+' : '';
    return `${prefix}${numeric.toFixed(digits)}%`;
  };
  const formatKrw = (value: unknown): string => {
    const numeric = numberValue(value);
    if (numeric === null) return '—';
    return new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW', maximumFractionDigits: 0 }).format(numeric);
  };
  const formatNumber = (value: unknown, digits = 3): string => {
    const numeric = numberValue(value);
    return numeric === null ? '—' : numeric.toFixed(digits);
  };
  const formatScore = (value: unknown): string => {
    const numeric = numberValue(value);
    return numeric === null ? '—' : `${numeric.toFixed(0)}%`;
  };
  const barWidthStyle = (value: unknown, multiplier = 100): string => {
    const numeric = numberValue(value);
    const width = numeric === null ? 0 : Math.max(4, Math.min(100, Math.abs(numeric) * multiplier));
    return `--bar-width:${width}%`;
  };
  const probabilityBarStyle = (value: unknown): string => {
    const numeric = numberValue(value);
    const width = numeric === null ? 0 : Math.max(3, Math.min(100, numeric * 100));
    return `--bar-width:${width}%`;
  };
  const formatProbability = (value: unknown): string => {
    const numeric = numberValue(value);
    return numeric === null ? '—' : `${Math.round(numeric * 100)}%`;
  };
  const recordEntries = (value: unknown): [string, unknown][] => Object.entries(asRecord(value));
  const hasRows = (value: unknown): boolean => rows(value).length > 0;
  const laneRows = (): readonly Record<string, unknown>[] => rows(field(guide?.research_process_catalog, 'lanes'));
  const selectedResearchLane = (): Record<string, unknown> => {
    const lanes = laneRows();
    return lanes.find((lane) => String(field(lane, 'id')) === selectedLaneId) ?? lanes[0] ?? {};
  };
  const replayFrames = (): readonly Record<string, unknown>[] => rows(field(guide?.active_replay, 'frames'));
  const currentReplayFrame = (): Record<string, unknown> => {
    const frames = replayFrames();
    return frames.length > 0 ? (frames[visualFrame % frames.length] ?? {}) : {};
  };
  const frameState = (): Record<string, unknown> => nestedRecord(currentReplayFrame(), 'state');
  const frameAction = (): Record<string, unknown> => nestedRecord(currentReplayFrame(), 'action');
  const frameReward = (): Record<string, unknown> => nestedRecord(currentReplayFrame(), 'reward');
  const frameLearning = (): Record<string, unknown> => nestedRecord(currentReplayFrame(), 'learning');
  const frameNav = (): Record<string, unknown> => nestedRecord(currentReplayFrame(), 'nav');
  const actionDistributionRows = (): readonly Record<string, unknown>[] => rows(field(guide?.active_replay, 'action_distribution'));
  const activeActionDistributionRows = (): readonly Record<string, unknown>[] => {
    const currentAction = String(field(frameAction(), 'executed') ?? '');
    const allRows = actionDistributionRows();
    const matching = allRows.filter((row) => String(field(row, 'action')) === currentAction);
    return matching.length > 0 ? matching : allRows.slice(0, 5);
  };
  const listRecordItems = (value: unknown, key: string): string[] => stringItems(field(value, key));
  const selectedLaneJson = (): string => safeJson(field(selectedResearchLane(), 'ai_guidance_format'));
  const scenarioTemplateRows = (): readonly Record<string, unknown>[] => rows(field(guide?.scenario_generator, 'templates'));
  const selectedScenarioTemplate = (): Record<string, unknown> => {
    const templates = scenarioTemplateRows();
    return templates.find((template) => String(field(template, 'template_id')) === selectedTemplateId) ?? templates[0] ?? {};
  };
  const selectedScenarioPlanJson = (): string => safeJson(field(selectedScenarioTemplate(), 'plan_json_draft'));
  const signalQualityRowCounts = (): [string, unknown][] => recordEntries(field(guide?.signal_quality_audit_summary, 'row_counts'));
  const signalQualityArtifacts = (): [string, unknown][] => recordEntries(field(guide?.signal_quality_audit_summary, 'required_artifacts'));
  const scenarioComparisonRows = (): readonly Record<string, unknown>[] => rows(field(guide?.scenario_comparison, 'cards'));
  const marketRegimeReadinessRows = (): readonly Record<string, unknown>[] => rows(field(guide?.market_regime_audit_readiness, 'readiness_checks'));
  const improvementQueueRows = (): readonly Record<string, unknown>[] => rows(field(guide?.improvement_queue, 'items'));
  const maturityRows = (): readonly Record<string, unknown>[] => rows(field(guide?.page_maturity_report, 'priority_completion'));
  const researchWorkflowRows = (): readonly Record<string, unknown>[] => rows(field(guide?.research_workflow_catalog, 'workflows'));
  const researchIntentRows = (): readonly Record<string, unknown>[] => rows(field(guide?.research_job_intent_ledger, 'intents'));
  const rejectionFunnelRows = (): readonly Record<string, unknown>[] => rows(field(guide?.rejection_analytics, 'gate_funnel_metrics'));
  const rejectionReasonRows = (): readonly Record<string, unknown>[] => rows(field(guide?.rejection_analytics, 'rejection_reason_taxonomy'));
  const falseNegativeRows = (): readonly Record<string, unknown>[] => rows(field(guide?.rejection_analytics, 'false_negative_candidates'));
  const completionSurfaceRows = (): readonly Record<string, unknown>[] => rows(field(guide?.dashboard_first_completion_report, 'completed_surfaces'));
  const selectedResearchWorkflow = (): Record<string, unknown> => {
    const workflows = researchWorkflowRows();
    return workflows.find((workflow) => String(field(workflow, 'workflow_id')) === selectedWorkflowId) ?? workflows[0] ?? {};
  };
  const selectedWorkflowBlockers = (): string[] => stringItems(field(selectedResearchWorkflow(), 'blocked_by'));
  const selectedWorkflowArtifacts = (): string[] => stringItems(field(selectedResearchWorkflow(), 'artifact_dependencies'));
  const tone = (status: unknown): string => {
    const normalized = String(status ?? '').toUpperCase();
    if (normalized === 'PASS' || normalized === 'INPUT') return 'pass';
    if (normalized.includes('NO-GO') || normalized.includes('FAIL') || normalized.includes('BLOCK')) return 'danger';
    if (normalized.includes('WATCH') || normalized.includes('RESEARCH')) return 'warn';
    return 'neutral';
  };


  const processSteps = [
    {
      no: '01',
      title: '데이터 준비',
      detail: 'D2 일봉 feature/label/split과 D3 후보 점수를 입력으로 고정합니다.',
      tone: 'input',
    },
    {
      no: '02',
      title: 'State 생성',
      detail: '미래 수익률 없이 position_count와 top_score_bucket만 관측합니다.',
      tone: 'pass',
    },
    {
      no: '03',
      title: 'Agent 판단',
      detail: '정책 모델이 현재 상태를 보고 hold/buy/add/sell/reduce 중 하나를 고릅니다.',
      tone: 'warn',
    },
    {
      no: '04',
      title: 'Action Mask',
      detail: '보유/미보유/최대 포지션 조건으로 불가능한 행동을 차단합니다.',
      tone: 'pass',
    },
    {
      no: '05',
      title: 'Reward 계산',
      detail: '다음날 연구용 future_return_1d에서 23bp 비용과 위험 벌점을 뺍니다.',
      tone: 'warn',
    },
    {
      no: '06',
      title: 'D5 검증',
      detail: '5-fold walk-forward, cost sensitivity, no-retune 조건으로 GO/NO-GO를 냅니다.',
      tone: 'danger',
    },
  ] as const;

  async function loadGuide(): Promise<void> {
    loading = true;
    try {
      guide = await dailyOhlcvApi.rlEnvGuide();
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    void loadGuide();
    const timer = window.setInterval(() => {
      visualFrame = (visualFrame + 1) % 240;
    }, 1600);
    return () => window.clearInterval(timer);
  });
</script>

<section class="page-hero" data-daily-rl-guide-tab>
  <div class="row" style="gap:10px; flex-wrap:wrap">
    <span class="text-eyebrow">Daily RL Environment Guide</span>
    <span class="pill warn"><span class="dot"></span>RL_ENV_VISUAL_GUIDE_MVP</span>
    <span class="pill"><span class="dot"></span>read-only · no live/broker/orders</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">일봉 강화학습 환경 설명서</h1>
  <p class="text-muted" style="margin-top:6px">
    강화학습을 모르는 상태에서도 “무엇을 보고(state), 무엇을 할 수 있고(action), 어떤 점수를 받는지(reward), 왜 아직 실거래가 아닌지”를 한 화면에서 이미지처럼 읽도록 만든 설명서입니다.
  </p>
  <p class="text-muted" style="margin-top:6px">
    핵심 상태 필드 marker: position_count · top_score_bucket. 행동 marker: hold · buy · add · sell · reduce. 보상 label marker: future_return_1d.
  </p>
  <div style="margin-top:12px">
    <button type="button" class="btn" onclick={() => void loadGuide()} disabled={loading}>{loading ? '갱신 중…' : '새로고침'}</button>
  </div>
</section>

<section class="panel" data-daily-rl-env-verdict>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">현재 구축 상태</div>
      <h2 class="text-h3">환경은 구축되어 있지만 연구 전용입니다</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{guide?.maturity ?? 'RESEARCH_ONLY_ENV_BUILT_NOT_PROFIT_READY'}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">{guide?.plain_language_verdict ?? '환경 상태를 불러오는 중입니다.'}</p>
  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">environment_built</div><div class="metric-value">{boolText(guide?.environment_built)}</div></div>
    <div class="metric"><div class="metric-label">cost</div><div class="metric-value tnum">{guide?.cost_round_trip_bp ?? 23}bp</div></div>
    <div class="metric"><div class="metric-label">state shape</div><div class="metric-value">{listText(guide?.state_contract?.shape)}</div></div>
    <div class="metric"><div class="metric-label">status</div><div class="metric-value">{guide?.status ?? 'RESEARCH_ONLY'}</div></div>
  </div>
</section>

<section class="panel visual-panel" data-daily-rl-loop-diagram>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Image-like Process</div>
      <h2 class="text-h3">Agent가 하루씩 배우는 순환 구조</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>Agent ↔ Environment ↔ Reward</span>
  </div>

  <div class="rl-loop-figure" aria-label="일봉 강화학습 순환 구조 이미지">
    <svg class="rl-loop-svg" viewBox="0 0 980 520" role="img" aria-labelledby="rl-loop-title rl-loop-desc">
      <title id="rl-loop-title">일봉 강화학습 환경 순환 다이어그램</title>
      <desc id="rl-loop-desc">D2/D3 데이터가 상태를 만들고, 에이전트가 행동을 고르면 환경이 마스크와 비용을 적용해 보상을 돌려주고 D5가 검증합니다.</desc>
      <defs>
        <marker id="rlArrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L0,6 L9,3 z" class="svg-arrow-head" />
        </marker>
        <linearGradient id="stateGlow" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="rgba(20,184,166,0.22)" />
          <stop offset="100%" stop-color="rgba(59,130,246,0.12)" />
        </linearGradient>
        <linearGradient id="rewardGlow" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="rgba(245,158,11,0.22)" />
          <stop offset="100%" stop-color="rgba(239,68,68,0.10)" />
        </linearGradient>
      </defs>

      <rect class="svg-backdrop" x="20" y="20" width="940" height="480" rx="30" />
      <text class="svg-section-label" x="55" y="64">RESEARCH-ONLY DAILY RL PROCESS</text>

      <rect class="svg-card data-card" x="55" y="102" width="180" height="120" rx="18" />
      <text class="svg-kicker" x="78" y="138">INPUT</text>
      <text class="svg-title" x="78" y="166">D2/D3 데이터</text>
      <text class="svg-body" x="78" y="192">feature · split · rank</text>

      <rect class="svg-card state-card" x="320" y="78" width="200" height="145" rx="20" />
      <text class="svg-kicker" x="346" y="116">STATE</text>
      <text class="svg-title" x="346" y="145">현재 관측</text>
      <text class="svg-body" x="346" y="174">position_count</text>
      <text class="svg-body" x="346" y="198">top_score_bucket</text>

      <rect class="svg-card agent-card" x="610" y="78" width="230" height="145" rx="20" />
      <text class="svg-kicker" x="638" y="116">AGENT / POLICY</text>
      <text class="svg-title" x="638" y="145">행동 선택</text>
      <text class="svg-body" x="638" y="174">hold · buy · add</text>
      <text class="svg-body" x="638" y="198">sell · reduce</text>

      <rect class="svg-card mask-card" x="610" y="290" width="230" height="135" rx="20" />
      <text class="svg-kicker" x="638" y="328">ENVIRONMENT</text>
      <text class="svg-title" x="638" y="357">Action Mask</text>
      <text class="svg-body" x="638" y="386">불가능한 행동 차단</text>

      <rect class="svg-card reward-card" x="320" y="292" width="230" height="135" rx="20" />
      <text class="svg-kicker" x="348" y="330">REWARD</text>
      <text class="svg-title" x="348" y="359">점수 계산</text>
      <text class="svg-body" x="348" y="388">future_return_1d</text>
      <text class="svg-body" x="348" y="412">- 23bp - penalties</text>

      <rect class="svg-card gate-card" x="55" y="292" width="180" height="135" rx="20" />
      <text class="svg-kicker" x="78" y="330">D5 GATE</text>
      <text class="svg-title" x="78" y="359">워크포워드</text>
      <text class="svg-body" x="78" y="388">5-fold · no retune</text>
      <text class="svg-status" x="78" y="414">NO-GO면 승격 금지</text>

      <path class="svg-arrow" d="M235 162 C270 162 285 150 320 150" marker-end="url(#rlArrow)" />
      <path class="svg-arrow" d="M520 150 C555 150 575 150 610 150" marker-end="url(#rlArrow)" />
      <path class="svg-arrow warn" d="M725 223 C725 250 725 263 725 290" marker-end="url(#rlArrow)" />
      <path class="svg-arrow warn" d="M610 360 C590 360 570 360 550 360" marker-end="url(#rlArrow)" />
      <path class="svg-arrow" d="M320 360 C280 360 260 360 235 360" marker-end="url(#rlArrow)" />
      <path class="svg-arrow loop" d="M435 292 C435 250 420 245 420 223" marker-end="url(#rlArrow)" />
      <path class="svg-arrow loop" d="M550 330 C585 265 595 235 625 205" marker-end="url(#rlArrow)" />

      <text class="svg-annotation" x="560" y="276">mask 적용 후 체결/보유 상태 갱신</text>
      <text class="svg-annotation" x="452" y="265">보상은 다음 state 학습 신호</text>
      <text class="svg-footer" x="55" y="470">실거래 주문이 아니라, 연구용 일봉 데이터로 “상태 → 행동 → 보상 → 검증”을 반복하는 폐쇄 루프입니다.</text>
    </svg>
  </div>

  <div class="process-strip" data-daily-rl-process-storyboard aria-label="일봉 RL 프로세스 스토리보드">
    {#each processSteps as step, index}
      <article class="process-step" data-step-tone={step.tone}>
        <div class="step-badge">{step.no}</div>
        <h3>{step.title}</h3>
        <p>{step.detail}</p>
      </article>
      {#if index < processSteps.length - 1}
        <div class="process-connector" aria-hidden="true">→</div>
      {/if}
    {/each}
  </div>
</section>
<section class="panel process-selector-panel" data-daily-rl-research-process-selector>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Research Process Selector</div>
      <h2 class="text-h3">전체 연구 프로세스를 선택해서 한계와 개선 방향 확인</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{String(field(guide?.research_process_catalog, 'status') ?? 'RESEARCH_ONLY_PROCESS_GUIDE')}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    {String(field(guide?.research_process_catalog, 'selector_help_ko') ?? '연구 lane을 선택하면 환경/상태/행동/보상/한계/개선 방향을 같은 포맷으로 확인합니다.')}
  </p>

  <div class="process-selector-grid" data-daily-rl-process-lane-picker>
    {#each laneRows() as lane}
      <button
        type="button"
        class="lane-select-card"
        data-active={String(field(lane, 'id')) === String(field(selectedResearchLane(), 'id'))}
        onclick={() => { selectedLaneId = String(field(lane, 'id') ?? 'D4_RL_RISK_OVERLAY'); }}
      >
        <span>{String(field(lane, 'stage') ?? 'stage')}</span>
        <b>{String(field(lane, 'title_ko') ?? field(lane, 'id') ?? '연구 lane')}</b>
        <small>{String(field(lane, 'status') ?? 'RESEARCH_ONLY')}</small>
      </button>
    {/each}
  </div>

  <div class="selected-process-grid" data-daily-rl-selected-process-detail>
    <article class="selected-process-main">
      <div class="text-eyebrow">{String(field(selectedResearchLane(), 'id') ?? 'MISSING_PROCESS_LANE')}</div>
      <h3>{String(field(selectedResearchLane(), 'title_ko') ?? '연구 프로세스')}</h3>
      <p>{String(field(selectedResearchLane(), 'goal_ko') ?? '선택된 연구 lane을 불러오는 중입니다.')}</p>

      <div class="lane-visual-chain" aria-label="선택 연구 프로세스 시각 흐름">
        {#each rows(field(selectedResearchLane(), 'visual_nodes')) as node, index}
          <div class="lane-node" data-tone={tone(field(node, 'status'))}>
            <span>{String(field(node, 'label') ?? 'node')}</span>
            <b>{String(field(node, 'detail') ?? '—')}</b>
          </div>
          {#if index < rows(field(selectedResearchLane(), 'visual_nodes')).length - 1}
            <div class="lane-arrow">→</div>
          {/if}
        {/each}
      </div>

      <div class="triple-detail-grid">
        <div><h4>State</h4>{#each listRecordItems(selectedResearchLane(), 'state_setup') as item}<p>{item}</p>{/each}</div>
        <div><h4>Action</h4>{#each listRecordItems(selectedResearchLane(), 'action_setup') as item}<p>{item}</p>{/each}</div>
        <div><h4>Reward</h4>{#each listRecordItems(selectedResearchLane(), 'reward_setup') as item}<p>{item}</p>{/each}</div>
      </div>
    </article>

    <aside class="selected-process-side" data-daily-rl-research-limitations>
      <h3>한계점</h3>
      {#each listRecordItems(selectedResearchLane(), 'current_limitations') as item}
        <p class="limitation-item">{item}</p>
      {/each}
      <h3>개선 방향</h3>
      {#each listRecordItems(selectedResearchLane(), 'improvement_directions') as item}
        <p class="improvement-item">{item}</p>
      {/each}
    </aside>
  </div>

  <div class="ai-guidance-grid" data-daily-rl-ai-guidance-format>
    <div class="mini-chart-card">
      <div class="text-eyebrow">Metrics to watch</div>
      {#each listRecordItems(selectedResearchLane(), 'metrics_to_watch') as metric}
        <span class="chip">{metric}</span>
      {/each}
      <div class="text-eyebrow" style="margin-top:12px">Required artifacts</div>
      {#each listRecordItems(selectedResearchLane(), 'required_artifacts') as artifact}
        <span class="chip">{artifact}</span>
      {/each}
    </div>
    <div class="mini-chart-card">
      <div class="text-eyebrow">AI-readable / AI 개선 지시 고정 포맷</div>
      <p class="text-muted" style="margin-bottom:8px">선택한 연구 lane의 한계·개선 방향을 AI Agent가 그대로 읽고 다음 실험 계획으로 사용할 수 있는 고정 JSON입니다.</p>
      <pre class="ai-format-box">{selectedLaneJson()}</pre>
    </div>
  </div>
</section>

<section class="panel workflow-center-panel" data-daily-rl-workflow-center>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Research Workflow Center · dashboard-first</div>
      <h2 class="text-h3">CLI 대신 대시보드에서 연구 workflow와 blocker를 확인</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{String(field(guide?.research_workflow_catalog, 'job_intent_mode') ?? 'APPROVAL_GATED_INTENT_RECORD_ONLY')}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    이 영역은 연구 workflow를 보고·검사하고·설정 초안을 준비하기 위한 화면입니다. 브라우저 실행은 막혀 있으며 실거래/브로커/주문/모델빌드/수익 주장으로 이어지지 않습니다.
  </p>
  <p class="text-muted" style="margin-top:6px">
    Workflow markers: D0_D1_DATA_GOVERNANCE_REVIEW · D3_D4_SIGNAL_QUALITY_AUDIT · PAST_ONLY_MARKET_REGIME_AUDIT · D4_RL_OVERLAY_ABLATION · SCENARIO_BATCH_RESEARCH_ONLY · HYPOTHESIS_REJECTION_AUDIT.
  </p>

  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">workflows</div><div class="metric-value tnum">{String(field(guide?.research_workflow_catalog, 'workflow_count') ?? '—')}</div></div>
    <div class="metric"><div class="metric-label">completion</div><div class="metric-value tnum">{formatScore(field(guide?.research_workflow_catalog, 'completion_pct'))}</div></div>
    <div class="metric"><div class="metric-label">browser execution</div><div class="metric-value">{boolText(field(guide?.research_workflow_catalog, 'execution_allowed_from_browser'))}</div></div>
    <div class="metric"><div class="metric-label">default cost</div><div class="metric-value tnum">23bp</div></div>
  </div>

  <div class="scenario-template-grid" data-daily-rl-workflow-picker>
    {#each researchWorkflowRows() as workflow}
      <button
        type="button"
        class="template-card"
        data-active={String(field(workflow, 'workflow_id')) === String(field(selectedResearchWorkflow(), 'workflow_id'))}
        onclick={() => { selectedWorkflowId = String(field(workflow, 'workflow_id') ?? 'PAST_ONLY_MARKET_REGIME_AUDIT'); }}
      >
        <span>{String(field(workflow, 'stage') ?? 'stage')}</span>
        <b>{String(field(workflow, 'title_ko') ?? field(workflow, 'workflow_id') ?? 'workflow')}</b>
        <small>{String(field(workflow, 'status') ?? 'WATCH')}</small>
      </button>
    {/each}
  </div>

  <div class="selected-process-grid" data-daily-rl-workflow-inspector>
    <article class="selected-process-main">
      <div class="text-eyebrow">{String(field(selectedResearchWorkflow(), 'workflow_id') ?? 'MISSING_WORKFLOW')}</div>
      <h3>{String(field(selectedResearchWorkflow(), 'title_ko') ?? 'Research workflow')}</h3>
      <p>{String(field(selectedResearchWorkflow(), 'next_allowed_action') ?? '승인된 연구 의도 기록 전 blocker와 artifact를 확인합니다.')}</p>
      <div style="margin-top:10px">
        <span class="chip">{String(field(selectedResearchWorkflow(), 'approval_status') ?? 'APPROVAL_REQUIRED')}</span>
        <span class="chip">{String(field(selectedResearchWorkflow(), 'trigger_status') ?? 'INTENT_ONLY_NOT_EXECUTED_BY_BROWSER')}</span>
        <span class="chip">no live/broker/orders</span>
      </div>
      <div class="triple-detail-grid" style="margin-top:14px">
        <div><h4>Blockers</h4>{#each selectedWorkflowBlockers() as item}<p>{item}</p>{/each}</div>
        <div><h4>Artifacts</h4>{#each selectedWorkflowArtifacts().slice(0, 6) as item}<p>{item}</p>{/each}</div>
        <div><h4>Guardrail</h4><p>{String(field(selectedResearchWorkflow(), 'guardrail') ?? 'research-only intent surface')}</p></div>
      </div>
    </article>
    <aside class="selected-process-side" data-daily-rl-workflow-safe-config-preview>
      <h3>Safe config preview</h3>
      <pre class="ai-format-box">{safeJson({
        workflow_id: field(selectedResearchWorkflow(), 'workflow_id'),
        default_cost_bp: field(selectedResearchWorkflow(), 'default_cost_bp') ?? 23,
        cost_sensitivity_bp: field(selectedResearchWorkflow(), 'cost_sensitivity_bp') ?? [0, 23, 46],
        approval_required: field(selectedResearchWorkflow(), 'approval_required') ?? true,
        execution_allowed_from_browser: field(selectedResearchWorkflow(), 'execution_allowed_from_browser') ?? false,
        forbidden_fields: field(guide?.research_workflow_catalog, 'forbidden_fields')
      })}</pre>
    </aside>
  </div>

  <div class="selected-process-grid" style="margin-top:14px" data-daily-rl-approval-trigger-surface>
    <article class="selected-process-main">
      <div class="text-eyebrow">Approval-aware trigger surface · intent record only</div>
      <h3>승인된 연구 의도만 기록하고 실행은 하지 않음</h3>
      <p>
        POST /api/daily-ohlcv/research-workflows/{String(field(selectedResearchWorkflow(), 'workflow_id') ?? '{workflow_id}')}/job-intents 는
        approval_ref, approval_ref_sha256, approval_status, idempotency_key를 검증한 뒤 immutable intent.json만 생성합니다.
      </p>
      <div style="margin-top:10px">
        <span class="chip">APPROVAL_GATED_INTENT_RECORD_ONLY</span>
        <span class="chip">no shell / no worker spawn</span>
        <span class="chip">model·paper·live locks false</span>
      </div>
    </article>
    <aside class="selected-process-side">
      <h3>Rejected request fields</h3>
      <p class="text-muted">command · shell · argv · env · cwd · broker · account · order · live · paper_forward · model_build · model_build_allowed · paper_forward_allowed · live_broker_order_allowed · arbitrary_path</p>
      <pre class="ai-format-box">{safeJson({
        schema_version: 'daily_ohlcv_research_job_intent.v1',
        approval_status: 'APPROVED_FOR_RESEARCH_INTENT',
        idempotency_key: 'safe-operator-key',
        config: {
          workflow_id: field(selectedResearchWorkflow(), 'workflow_id'),
          default_cost_bp: 23,
          cost_sensitivity_bp: [0, 23, 46],
          controls: ['no_trade', 'shuffle_control', 'frozen_d3_baseline']
        }
      })}</pre>
    </aside>
  </div>

  <div class="table-card" style="margin-top:14px" data-daily-rl-intent-ledger>
    <div class="text-eyebrow">Job / artifact ledger · immutable research intents</div>
    <h3>연구 intent ledger</h3>
    <p class="text-muted">{String(field(guide?.research_job_intent_ledger, 'guardrail') ?? 'Intent ledger records approval-gated research requests only.')}</p>
    <div class="grid-4-kpi" style="margin-top:12px">
      <div class="metric"><div class="metric-label">ledger status</div><div class="metric-value">{String(field(guide?.research_job_intent_ledger, 'status') ?? 'EMPTY')}</div></div>
      <div class="metric"><div class="metric-label">intent count</div><div class="metric-value tnum">{String(field(guide?.research_job_intent_ledger, 'count') ?? 0)}</div></div>
      <div class="metric"><div class="metric-label">browser execution</div><div class="metric-value">{boolText(field(guide?.research_job_intent_ledger, 'execution_allowed_from_browser'))}</div></div>
      <div class="metric"><div class="metric-label">live/model/paper</div><div class="metric-value">0%</div></div>
    </div>
    {#if researchIntentRows().length > 0}
      <div class="compact-table-wrap" style="margin-top:12px">
        <table class="compact-table">
          <thead><tr><th>intent</th><th>workflow</th><th>status</th><th>approval</th><th>hash</th></tr></thead>
          <tbody>
            {#each researchIntentRows().slice(0, 6) as intent}
              <tr>
                <td>{String(field(intent, 'intent_id') ?? '—')}</td>
                <td>{String(field(intent, 'workflow_id') ?? '—')}</td>
                <td>{String(field(intent, 'status') ?? '—')}</td>
                <td>{String(field(intent, 'approval_status') ?? '—')}</td>
                <td class="tnum">{String(field(intent, 'config_hash') ?? '—').slice(0, 12)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else}
      <p class="text-muted" style="margin-top:12px">아직 기록된 intent가 없습니다. 유효한 승인과 SHA가 없으면 생성 요청은 fail-closed 됩니다.</p>
    {/if}
  </div>
  <p class="text-muted" style="margin-top:8px">{String(field(guide?.research_workflow_catalog, 'guardrail') ?? 'workflow catalog is read-only')}</p>
</section>
<section class="panel rejection-analytics-panel" data-daily-rl-rejection-analytics>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Hypothesis rejection analytics · research QA</div>
      <h2 class="text-h3">가설 탈락과 조기 dropout이 과한지 검토</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{String(field(guide?.rejection_analytics, 'status') ?? 'MISSING_REJECTION_AUDIT_ARTIFACTS')}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    gate funnel, rejection taxonomy, calibration, threshold sensitivity, false-negative 후보를 한 화면에서 봅니다. 후보는 REVIEW_ONLY이며 NO-GO를 뒤집거나 모델/페이퍼/실거래를 unlock하지 않습니다.
  </p>
  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">audit run</div><div class="metric-value">{String(field(guide?.rejection_analytics, 'run_id') ?? '—')}</div></div>
    <div class="metric"><div class="metric-label">rejected</div><div class="metric-value tnum">{String(field(field(guide?.rejection_analytics, 'summary'), 'rejected_total') ?? 0)}</div></div>
    <div class="metric"><div class="metric-label">early dropout</div><div class="metric-value tnum">{String(field(field(guide?.rejection_analytics, 'summary'), 'early_dropout_total') ?? 0)}</div></div>
    <div class="metric"><div class="metric-label">promotion allowed</div><div class="metric-value">{boolText(field(guide?.rejection_analytics, 'promotion_allowed'))}</div></div>
  </div>
  <div class="selected-process-grid" style="margin-top:14px">
    <article class="selected-process-main">
      <h3>Gate funnel metrics</h3>
      <div class="compact-table-wrap">
        <table class="compact-table">
          <thead><tr><th>gate</th><th>denominator</th><th>entered</th><th>watch</th><th>reject</th><th>dropout</th></tr></thead>
          <tbody>
            {#each rejectionFunnelRows().slice(0, 6) as row}
              <tr>
                <td>{String(field(row, 'gate_id') ?? '—')}</td>
                <td>{String(field(row, 'denominator_count') ?? '—')}</td>
                <td>{String(field(row, 'entered_count') ?? '—')}</td>
                <td>{String(field(row, 'watch_count') ?? '—')}</td>
                <td>{String(field(row, 'rejected_count') ?? '—')}</td>
                <td>{String(field(row, 'early_dropout_count') ?? '—')}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </article>
    <aside class="selected-process-side">
      <h3>Policies</h3>
      <p><b>Denominator</b> {String(field(guide?.rejection_analytics, 'denominator_policy') ?? 'fail closed')}</p>
      <p><b>Timing</b> {String(field(guide?.rejection_analytics, 'timing_policy') ?? 'decision-time only')}</p>
      <p><b>Independent</b> {String(field(guide?.rejection_analytics, 'independent_evidence_policy') ?? 'later independent evidence only')}</p>
    </aside>
  </div>
  <div class="triple-detail-grid" style="margin-top:14px">
    <div>
      <h4>Rejection taxonomy</h4>
      {#each rejectionReasonRows().slice(0, 4) as row}
        <p><b>{String(field(row, 'reason_id') ?? '—')}</b> {String(field(row, 'reason_family') ?? '—')} · {String(field(row, 'severity') ?? '—')}</p>
      {/each}
    </div>
    <div>
      <h4>False-negative review queue</h4>
      {#each falseNegativeRows().slice(0, 4) as row}
        <p><b>{String(field(row, 'candidate_id') ?? '—')}</b> {String(field(row, 'review_status') ?? 'REVIEW_ONLY')} · promotion_allowed={String(field(row, 'promotion_allowed') ?? false)}</p>
      {/each}
    </div>
    <div>
      <h4>Guardrail</h4>
      <p>{String(field(guide?.rejection_analytics, 'guardrail') ?? 'No NO-GO reversal; new preregistration required.')}</p>
    </div>
  </div>
</section>
<section class="panel final-completion-panel" data-daily-rl-final-completion-report>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Completion report · dashboard-first research platform</div>
      <h2 class="text-h3">비실거래 연구 플랫폼 완료 성과와 남은 lock</h2>
    </div>
    <span class="pill pass"><span class="dot"></span>{String(field(guide?.dashboard_first_completion_report, 'status') ?? 'NON_LIVE_RESEARCH_PLATFORM_INCOMPLETE')}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    {String(field(guide?.dashboard_first_completion_report, 'guardrail') ?? 'Non-live research/dashboard completion can be 100%; live/model/paper readiness remains 0%.')}
  </p>
  <div style="margin-top:10px">
    <span class="chip">NON_LIVE_RESEARCH_PLATFORM_COMPLETE</span>
    <span class="chip">live/model/paper readiness 0%</span>
  </div>
  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">non_live_goal_completion_pct</div><div class="metric-value tnum">{String(field(guide?.dashboard_first_completion_report, 'non_live_goal_completion_pct') ?? 0)}%</div></div>
    <div class="metric"><div class="metric-label">live_trading_readiness_pct</div><div class="metric-value tnum">{String(field(guide?.dashboard_first_completion_report, 'live_trading_readiness_pct') ?? 0)}%</div></div>
    <div class="metric"><div class="metric-label">model_build_readiness_pct</div><div class="metric-value tnum">{String(field(guide?.dashboard_first_completion_report, 'model_build_readiness_pct') ?? 0)}%</div></div>
    <div class="metric"><div class="metric-label">paper_forward_readiness_pct</div><div class="metric-value tnum">{String(field(guide?.dashboard_first_completion_report, 'paper_forward_readiness_pct') ?? 0)}%</div></div>
  </div>
  <div class="selected-process-grid" style="margin-top:14px">
    <article class="selected-process-main">
      <h3>완료된 기능 표면</h3>
      <div class="compact-table-wrap">
        <table class="compact-table">
          <thead><tr><th>surface</th><th>completion</th><th>evidence</th></tr></thead>
          <tbody>
            {#each completionSurfaceRows() as row}
              <tr>
                <td><b>{String(field(row, 'id') ?? 'surface')}</b><br /><span class="text-muted">{String(field(row, 'label_ko') ?? '—')}</span></td>
                <td class="tnum">{String(field(row, 'completion_pct') ?? 0)}%</td>
                <td>{String(field(row, 'evidence') ?? '—')}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </article>
    <aside class="selected-process-side">
      <h3>할 수 있는 것 / 할 수 없는 것</h3>
      <div class="text-eyebrow" style="margin-top:8px">Can do</div>
      {#each stringItems(field(guide?.dashboard_first_completion_report, 'can_do')) as item}
        <span class="chip">{item}</span>
      {/each}
      <div class="text-eyebrow" style="margin-top:14px">Cannot do</div>
      {#each stringItems(field(guide?.dashboard_first_completion_report, 'cannot_do')) as item}
        <span class="chip warn">{item}</span>
      {/each}
    </aside>
  </div>
  <p class="text-muted" style="margin-top:8px">
    이 완료율은 workflow center, inspector, safe config builder, intent ledger, rejection analytics, 문서/검증 표면에만 적용됩니다. 실거래·브로커 주문·페이퍼 포워드·모델 빌드·수익성 주장은 계속 0%/blocked입니다.
  </p>
</section>
<section class="panel scenario-generator-panel" data-daily-rl-scenario-generator>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Scenario Generator · read-only draft</div>
      <h2 class="text-h3">여러 가정/시나리오를 선택하고 고정 JSON 초안 확인</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{String(field(guide?.scenario_generator, 'status') ?? 'READ_ONLY_DRAFT_GENERATOR')}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    이 패널은 실행 버튼이 아니라 <b>시나리오 계획 JSON 초안</b>을 만드는 설명/검토 화면입니다. 실제 연구 실행은 preregistration과 CLI batch manifest로만 진행합니다.
  </p>
  <p class="text-muted" style="margin-top:6px">
    Template markers: D3_D4_SIGNAL_QUALITY_AUDIT · PAST_ONLY_MARKET_REGIME_AUDIT · D4_RL_OVERLAY_ABLATION.
  </p>

  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">templates</div><div class="metric-value tnum">{String(field(guide?.scenario_generator, 'template_count') ?? '—')}</div></div>
    <div class="metric"><div class="metric-label">default cost</div><div class="metric-value tnum">23bp</div></div>
    <div class="metric"><div class="metric-label">execution</div><div class="metric-value">{boolText(field(guide?.scenario_generator, 'execution_allowed'))}</div></div>
    <div class="metric"><div class="metric-label">export</div><div class="metric-value">JSON</div></div>
  </div>

  <div class="scenario-template-grid" data-daily-rl-scenario-template-picker>
    {#each scenarioTemplateRows() as template}
      <button
        type="button"
        class="template-card"
        data-active={String(field(template, 'template_id')) === String(field(selectedScenarioTemplate(), 'template_id'))}
        onclick={() => { selectedTemplateId = String(field(template, 'template_id') ?? 'D3_D4_SIGNAL_QUALITY_AUDIT'); }}
      >
        <span>{String(field(template, 'lane_id') ?? 'lane')}</span>
        <b>{String(field(template, 'title_ko') ?? field(template, 'template_id') ?? 'template')}</b>
        <small>{String(field(template, 'status') ?? 'DRAFT')}</small>
      </button>
    {/each}
  </div>

  <div class="selected-process-grid" data-daily-rl-scenario-plan-json>
    <article class="selected-process-main">
      <div class="text-eyebrow">{String(field(selectedScenarioTemplate(), 'template_id') ?? 'D3_D4_SIGNAL_QUALITY_AUDIT')}</div>
      <h3>{String(field(selectedScenarioTemplate(), 'title_ko') ?? '시나리오 초안')}</h3>
      <p>{String(field(selectedScenarioTemplate(), 'hypothesis_ko') ?? '가설을 불러오는 중입니다.')}</p>
      <div style="margin-top:10px">
        {#each stringItems(field(selectedScenarioTemplate(), 'assumption_tags')) as tag}
          <span class="chip">{tag}</span>
        {/each}
      </div>
      <div class="text-eyebrow" style="margin-top:14px">Required artifacts</div>
      {#each stringItems(field(selectedScenarioTemplate(), 'required_artifacts')) as artifact}
        <span class="chip">{artifact}</span>
      {/each}
    </article>
    <aside class="selected-process-side">
      <h3>Fixed plan JSON draft</h3>
      <pre class="ai-format-box">{selectedScenarioPlanJson()}</pre>
    </aside>
  </div>
  <p class="text-muted" style="margin-top:8px">{String(field(guide?.scenario_generator, 'guardrail') ?? 'read-only scenario generator')}</p>
</section>

<section class="panel" data-daily-rl-signal-quality-integration>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Latest D3/D4 Signal-quality Audit</div>
      <h2 class="text-h3">최신 신호 품질 결과와 시나리오 비교</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{String(field(guide?.signal_quality_audit_summary, 'promotion_status') ?? 'LOADING_OR_MISSING_SIGNAL_QUALITY_AUDIT')}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    Run: <b>{String(field(guide?.signal_quality_audit_summary, 'run_id') ?? 'MISSING_SIGNAL_QUALITY_AUDIT')}</b> · verdict:
    <b>{String(field(guide?.signal_quality_audit_summary, 'result_verdict') ?? 'LOADING_OR_MISSING_SIGNAL_QUALITY_AUDIT')}</b>
  </p>

  <div class="signal-grid">
    <article class="mini-chart-card">
      <div class="text-eyebrow">Row counts</div>
      {#each signalQualityRowCounts() as [name, value]}
        <div class="kv-row"><span>{name}</span><b>{String(value)}</b></div>
      {/each}
    </article>
    <article class="mini-chart-card">
      <div class="text-eyebrow">Baselines / cost</div>
      {#each stringItems(field(guide?.signal_quality_audit_summary, 'baseline_controls')) as control}
        <span class="chip">{control}</span>
      {/each}
      <p class="text-muted" style="margin-top:8px">cost sensitivity: {listText(field(guide?.signal_quality_audit_summary, 'cost_sensitivity_bp'))}bp</p>
    </article>
    <article class="mini-chart-card">
      <div class="text-eyebrow">Artifact links</div>
      {#each signalQualityArtifacts() as [name, path]}
        <div class="artifact-line"><b>{name}</b><span>{String(path)}</span></div>
      {/each}
    </article>
  </div>

  <div class="scenario-comparison-grid" data-daily-rl-scenario-comparison>
    {#each scenarioComparisonRows() as scenario}
      <article class="scenario-card" data-tone={tone(field(scenario, 'status'))}>
        <div class="text-eyebrow">{String(field(scenario, 'scenario_id') ?? 'scenario')}</div>
        <h3>{String(field(scenario, 'diagnostic_focus') ?? 'diagnostic')}</h3>
        <p>{String(field(scenario, 'hypothesis') ?? '—')}</p>
        <div class="scenario-status-line">
          <span>{String(field(scenario, 'status') ?? 'WATCH')}</span>
          <b>{String(field(scenario, 'promotion_status') ?? 'NO-GO_RESEARCH_ONLY')}</b>
        </div>
      </article>
    {/each}
  </div>
  <p class="text-muted" style="margin-top:8px">{String(field(guide?.scenario_comparison, 'guardrail') ?? 'WATCH/NO-GO diagnostics only')}</p>
</section>

<section class="panel" data-daily-rl-market-regime-readiness>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Next research readiness</div>
      <h2 class="text-h3">Past-only 시장 국면 데이터 품질 감사 준비도</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{formatScore(field(guide?.market_regime_audit_readiness, 'maturity_score_pct'))}</span>
  </div>
  <div class="readiness-grid">
    {#each marketRegimeReadinessRows() as check}
      <article class="readiness-card" data-tone={tone(field(check, 'status'))}>
        <div class="text-eyebrow">{String(field(check, 'status') ?? 'WATCH')}</div>
        <h3>{String(field(check, 'check') ?? 'check')}</h3>
        <div class="score-track"><div class="score-fill" style={barWidthStyle(field(check, 'completion_pct'), 1)}></div></div>
        <b>{formatScore(field(check, 'completion_pct'))}</b>
        <p>{String(field(check, 'evidence') ?? '—')}</p>
      </article>
    {/each}
  </div>
  <div class="mini-chart-card" style="margin-top:12px">
    <div class="text-eyebrow">AI-readable next-action guidance</div>
    <pre class="ai-format-box">{safeJson(field(guide?.market_regime_audit_readiness, 'ai_guidance_format'))}</pre>
  </div>
</section>

<section class="panel" data-daily-rl-improvement-queue>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">AI-readable Improvement Queue</div>
      <h2 class="text-h3">한계점 → 다음 행동 → 필요 산출물 → 수락 gate</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{String(field(guide?.improvement_queue, 'status') ?? 'AI_READABLE_QUEUE_AVAILABLE')}</span>
  </div>
  <div class="improvement-grid">
    {#each improvementQueueRows() as item}
      <article class="improvement-card" data-tone={tone(field(item, 'blocker_status'))}>
        <div class="text-eyebrow">P{String(field(item, 'priority') ?? '—')} · {String(field(item, 'id') ?? 'IQ')}</div>
        <h3>{String(field(item, 'title_ko') ?? '개선 항목')}</h3>
        <p><b>한계:</b> {String(field(item, 'source_limitation') ?? '—')}</p>
        <p><b>다음 행동:</b> {String(field(item, 'next_action') ?? '—')}</p>
        <p><b>Gate:</b> {String(field(item, 'acceptance_gate') ?? '—')}</p>
        <small>{String(field(item, 'blocker_status') ?? 'WATCH')}</small>
      </article>
    {/each}
  </div>
  <pre class="ai-format-box" style="margin-top:12px">{safeJson(field(guide?.improvement_queue, 'ai_guidance_format'))}</pre>
</section>

<section class="panel" data-daily-rl-page-maturity-report>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Numeric maturity report</div>
      <h2 class="text-h3">전체 페이지 성숙도와 연구 준비도</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{String(field(guide?.page_maturity_report, 'status') ?? 'FEATURES_IMPLEMENTED_RESEARCH_GATES_BLOCKED')}</span>
  </div>
  <div class="maturity-kpi-grid">
    {#each [
      ['implementation_completion_pct', '구현 완료율'],
      ['page_maturity_pct', '페이지 성숙도'],
      ['scenario_platform_maturity_pct', '시나리오 플랫폼'],
      ['research_readiness_pct', '연구 준비도'],
      ['data_governance_maturity_pct', '데이터 거버넌스'],
      ['live_trading_readiness_pct', '실거래 준비도']
    ] as [key, label]}
      <article class="metric">
        <div class="metric-label">{label}</div>
        <div class="metric-value tnum">{formatScore(field(guide?.page_maturity_report, key))}</div>
        <div class="score-track"><div class="score-fill" style={barWidthStyle(field(guide?.page_maturity_report, key), 1)}></div></div>
      </article>
    {/each}
  </div>
  <div class="table-wrap" style="margin-top:12px; overflow:auto">
    <table>
      <thead><tr><th>priority</th><th>feature</th><th>completion</th><th>status</th><th>evidence</th></tr></thead>
      <tbody>
        {#each maturityRows() as row}
          <tr class={tone(field(row, 'status'))}>
            <td>{String(field(row, 'priority') ?? '—')}</td>
            <td>{String(field(row, 'feature') ?? '—')}</td>
            <td>{formatScore(field(row, 'completion_pct'))}</td>
            <td>{String(field(row, 'status') ?? '—')}</td>
            <td class="mono">{String(field(row, 'evidence') ?? '—')}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p class="text-muted" style="margin-top:8px">{String(field(guide?.page_maturity_report, 'guardrail') ?? 'page maturity is not trading readiness')}</p>
</section>

<section class="panel live-visualizer-panel" data-daily-rl-realtime-visualizer>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Artifact-backed RL Replay</div>
      <h2 class="text-h3">저장된 산출물로 움직이는 강화학습 리플레이</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{String(field(guide?.active_replay, 'status') ?? 'MISSING_REPLAY_ARTIFACT')}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    실제 계좌/주문 실시간 화면이 아니라, 저장된 D4 산출물의 <b>state_observations · reward_breakdown · policy_nav · action_distribution</b>을
    1.6초 단위로 재생합니다. 현재 tabular Q telemetry는 신경망 화면이나 가짜 확률처럼 꾸미지 않고 산출물 action rate와 보상 항목만 보여줍니다.
  </p>

  <div class="live-rl-stage" aria-label="강화학습 산출물 리플레이">
    <article class="live-state-card">
      <div class="text-eyebrow">State input · frame {String(field(currentReplayFrame(), 'frame') ?? '—')}</div>
      <h3>{String(field(currentReplayFrame(), 'date') ?? 'MISSING_REPLAY_ARTIFACT')} · {String(field(currentReplayFrame(), 'split') ?? 'split')}</h3>
      <dl class="state-meter-grid">
        <div><dt>position_count</dt><dd>{String(field(frameState(), 'position_count') ?? '—')}</dd></div>
        <div><dt>top_score_bucket</dt><dd>{String(field(frameState(), 'top_score_bucket') ?? '—')}</dd></div>
        <div><dt>cash_fraction</dt><dd>{formatNumber(field(frameState(), 'cash_fraction'), 2)}</dd></div>
        <div><dt>exposure_fraction</dt><dd>{formatNumber(field(frameState(), 'exposure_fraction'), 2)}</dd></div>
        <div><dt>top_candidate_code</dt><dd>{String(field(frameState(), 'top_candidate_code') ?? '—')}</dd></div>
        <div><dt>future_label_exposed</dt><dd>{String(field(frameState(), 'future_label_exposed') ?? 'UNKNOWN')}</dd></div>
      </dl>
      <p>{String(field(guide?.active_replay, 'policy_representation_ko') ?? '정책 표현 증거를 불러오는 중입니다.')}</p>
    </article>

    <div class="policy-network-card" data-daily-rl-policy-network-visual>
      <div class="text-eyebrow">Policy representation status</div>
      <div class="tabular-policy-visual" aria-label="Tabular Q 정책 표현">
        <div class="policy-status-pill">policy_type: {String(field(guide?.active_replay, 'policy_type') ?? 'tabular_q')}</div>
        <div class="policy-status-pill danger">policy_network_status: {String(field(guide?.active_replay, 'policy_network_status') ?? 'MISSING_POLICY_ARTIFACT')}</div>
        <div class="q-table-grid">
          <div class="q-cell active">state<br />{String(field(frameState(), 'position_count') ?? '—')}:{String(field(frameState(), 'top_score_bucket') ?? '—')}</div>
          <div class="q-arrow">→</div>
          <div class="q-cell">Q-table<br />artifact telemetry</div>
          <div class="q-arrow">→</div>
          <div class="q-cell active">action<br />{String(field(frameAction(), 'executed') ?? 'hold')}</div>
        </div>
      </div>
      <div class="action-probabilities" data-daily-rl-action-probability-bars>
        <div class="text-eyebrow">Action distribution from artifact rows</div>
        {#if hasRows(activeActionDistributionRows())}
          {#each activeActionDistributionRows() as row}
            <div class="action-prob-row" data-selected={String(field(row, 'action')) === String(field(frameAction(), 'executed'))}>
              <span>{String(field(row, 'action') ?? '—')}</span>
              <div class="mini-bar-track"><div class="mini-bar-fill policy" style={probabilityBarStyle(field(row, 'action_rate'))}></div></div>
              <b>{formatProbability(field(row, 'action_rate'))}</b>
            </div>
          {/each}
        {:else}
          <div class="blocked-note">MISSING_POLICY_ARTIFACT · MISSING_REPLAY_ARTIFACT</div>
        {/if}
      </div>
    </div>

    <article class="live-reward-card">
      <div class="text-eyebrow">Action · reward feedback</div>
      <h3>{String(field(frameAction(), 'executed') ?? 'hold')}</h3>
      <div class="selected-action-pill">requested: {String(field(frameAction(), 'requested') ?? '—')}</div>
      <dl>
        <div><dt>Action Mask</dt><dd>{String(field(frameAction(), 'mask') ?? '—')}</dd></div>
        <div><dt>Reward</dt><dd>{formatNumber(field(frameReward(), 'reward'), 4)}</dd></div>
        <div><dt>net_return_after_cost</dt><dd>{formatNumber(field(frameReward(), 'net_return_after_cost'), 4)}</dd></div>
        <div><dt>turnover_cost</dt><dd>{formatNumber(field(frameReward(), 'turnover_cost'), 4)}</dd></div>
        <div><dt>drawdown_penalty</dt><dd>{formatNumber(field(frameReward(), 'drawdown_penalty'), 4)}</dd></div>
        <div><dt>episode reward</dt><dd>{formatNumber(field(frameLearning(), 'total_reward'), 3)}</dd></div>
        <div><dt>policy_nav</dt><dd>{formatNumber(field(frameNav(), 'policy_nav'), 4)}</dd></div>
      </dl>
    </article>
  </div>
</section>

<section class="panel performance-panel" data-daily-rl-performance-example>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Learning Outcome Example</div>
      <h2 class="text-h3">학습 성과 예시: 수익금 · 수익률 · 리스크</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{String(field(guide?.learning_performance, 'status') ?? 'RESEARCH_ONLY_PERFORMANCE_DIAGNOSTIC')}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">
    아래 금액은 실거래 수익이 아니라 <b>가정 원금 {formatKrw(field(guide?.learning_performance, 'display_capital_krw') ?? 10000000)}</b>에
    연구용 평가 수익률을 곱해 이해하기 쉽게 환산한 모의 성과입니다.
  </p>

  <div class="performance-grid" data-daily-rl-performance-pnl>
    {#each [
      nestedRecord(guide?.learning_performance, 'policy'),
      nestedRecord(guide?.learning_performance, 'best_d3_baseline'),
      nestedRecord(guide?.learning_performance, 'delta_vs_best_d3'),
    ] as card}
      <article class="performance-card" data-card-tone={numberValue(field(card, 'total_return_pct')) !== null && Number(field(card, 'total_return_pct')) < 0 ? 'danger' : 'pass'}>
        <div class="text-eyebrow">{String(field(card, 'split') ?? '—')}</div>
        <h3>{String(field(card, 'label') ?? '—')}</h3>
        <div class="performance-main">
          <span>{formatPercent(field(card, 'total_return_pct'))}</span>
          <small>수익률</small>
        </div>
        <div class="performance-bar" style={barWidthStyle(field(card, 'total_return_pct'), 2)}></div>
        <dl>
          <div><dt>수익금</dt><dd>{formatKrw(field(card, 'simulated_profit_krw'))}</dd></div>
          <div><dt>환산 평가금</dt><dd>{formatKrw(field(card, 'simulated_final_capital_krw'))}</dd></div>
          <div><dt>MDD</dt><dd>{formatPercent(field(card, 'max_drawdown_pct'))}</dd></div>
          <div><dt>Turnover</dt><dd>{formatPercent(field(card, 'mean_turnover_pct'))}</dd></div>
        </dl>
      </article>
    {/each}
  </div>

  <div class="outcome-note">{String(field(guide?.learning_performance, 'interpretation_ko') ?? '성과 데이터를 불러오는 중입니다.')}</div>

  <div class="learning-visual-grid">
    <div class="mini-chart-card" data-daily-rl-learning-curve-visual>
      <div class="text-eyebrow">Training curve preview</div>
      <h3>episode별 reward / final equity</h3>
      {#each rows(field(guide?.learning_performance, 'learning_curve_preview')) as row}
        <div class="mini-bar-row" data-tone={numberValue(field(row, 'total_reward')) !== null && Number(field(row, 'total_reward')) < 0 ? 'danger' : 'pass'}>
          <span>EP {String(field(row, 'episode') ?? '—')}</span>
          <div class="mini-bar-track"><div class="mini-bar-fill" style={barWidthStyle(field(row, 'final_equity'), 100)}></div></div>
          <b>{formatNumber(field(row, 'total_reward'), 3)}</b>
        </div>
      {/each}
    </div>

    <div class="mini-chart-card" data-daily-rl-nav-preview>
      <div class="text-eyebrow">Portfolio NAV preview</div>
      <h3>연구용 평가금 흐름</h3>
      {#each rows(field(guide?.learning_performance, 'portfolio_nav_preview')) as row}
        <div class="nav-row">
          <span>{String(field(row, 'date') ?? '—')}</span>
          <div class="mini-bar-track"><div class="mini-bar-fill nav" style={barWidthStyle(field(row, 'nav'), 100)}></div></div>
          <b>{formatKrw(field(row, 'simulated_capital_krw'))}</b>
        </div>
      {/each}
    </div>
  </div>

  <p class="text-muted" style="margin-top:10px">{String(field(guide?.learning_performance, 'guardrail') ?? 'no profit guarantee, no live/broker/orders')}</p>
</section>

<section class="panel" data-daily-rl-env-visual-map>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">Visual Map</div>
      <h2 class="text-h3">D2 → D5 일봉 RL 흐름</h2>
    </div>
    <span class="pill"><span class="dot"></span>state · action · reward · gate</span>
  </div>
  <div class="flow-canvas" aria-label="Daily RL visual environment flow">
    {#each rows(guide?.visual_flow) as node, index}
      <div class="flow-node" data-tone={tone(node.status)}>
        <div class="node-id">{node.id}</div>
        <div class="node-label">{node.label}</div>
        <div class="node-summary">{node.summary}</div>
        <div class="node-status">{node.status}</div>
      </div>
      {#if index < rows(guide?.visual_flow).length - 1}
        <div class="flow-arrow" aria-hidden="true">→</div>
      {/if}
    {/each}
  </div>
</section>

<section class="panel" data-daily-rl-env-elements>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">RL 구성 요소</div>
      <h2 class="text-h3">Agent · State · Action · Reward</h2>
    </div>
  </div>
  <div class="explain-grid">
    {#each recordEntries(guide?.what_rl_means_here) as [key, text]}
      <article class="explain-card">
        <div class="text-eyebrow">{key}</div>
        <p>{text}</p>
      </article>
    {/each}
  </div>
</section>

<section class="panel" data-daily-rl-state-action-reward>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">환경 계약</div>
      <h2 class="text-h3">상태, 행동, 보상 공식</h2>
    </div>
  </div>
  <div class="contract-grid">
    <div class="contract-box">
      <h3>State 관측</h3>
      <p>fields: {listText(guide?.state_contract?.fields)}</p>
      <p>{String(guide?.state_contract?.lookahead_policy ?? 'future_return_1d는 관측에 넣지 않습니다.')}</p>
    </div>
    <div class="contract-box">
      <h3>Action space</h3>
      {#each recordEntries(guide?.action_space) as [id, name]}
        <span class="chip">{id}: {name}</span>
      {/each}
    </div>
    <div class="contract-box">
      <h3>Action mask</h3>
      {#each recordEntries(guide?.action_mask) as [name, rule]}
        <p><b>{name}</b>: {rule}</p>
      {/each}
    </div>
    <div class="contract-box">
      <h3>Reward</h3>
      <p class="mono">{guide?.reward_formula ?? 'net_return_after_cost - penalties'}</p>
      <p>components: {listText(guide?.reward_components)}</p>
      <p>fill: {guide?.fill_assumption ?? 'daily research label only'}</p>
    </div>
  </div>
</section>

<section class="panel" data-daily-rl-env-checks>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">잘 구축되어 있는지 확인</div>
      <h2 class="text-h3">PASS/WATCH 체크리스트</h2>
    </div>
  </div>
  <div class="table-wrap" style="margin-top:12px; overflow:auto">
    <table>
      <thead><tr><th>check</th><th>status</th><th>의미</th></tr></thead>
      <tbody>
        {#each rows(guide?.well_built_checks) as check}
          <tr class={tone(check.status)}>
            <td class="mono">{check.check}</td>
            <td>{check.status}</td>
            <td>{check.meaning_ko}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <div class="contract-grid" style="margin-top:16px">
    <div class="contract-box pass"><h3>가능한 용도</h3><p>{listText(guide?.good_enough_for)}</p></div>
    <div class="contract-box danger"><h3>아직 불가능한 용도</h3><p>{listText(guide?.not_good_enough_for)}</p></div>
  </div>
  <p class="text-muted" style="margin-top:8px">{guide?.guardrail ?? 'no profit guarantee, no live/broker/orders'}</p>
</section>

<style>
  .visual-panel { overflow:hidden; }
  .rl-loop-figure { margin-top:16px; border:1px solid var(--border-faint); border-radius:24px; background:radial-gradient(circle at 22% 28%, rgba(20,184,166,0.16), transparent 34%), radial-gradient(circle at 78% 20%, rgba(59,130,246,0.13), transparent 32%), linear-gradient(135deg, rgba(15,23,42,0.02), rgba(245,158,11,0.05)); overflow:auto; }
  .rl-loop-svg { display:block; width:100%; min-width:900px; height:auto; }
  .svg-backdrop { fill:rgba(255,255,255,0.64); stroke:var(--border-faint); }
  .svg-card { fill:var(--surface); stroke:var(--border-faint); stroke-width:1.5; filter:drop-shadow(0 14px 22px rgba(15,23,42,0.10)); }
  .state-card { fill:url(#stateGlow); stroke:rgba(20,184,166,0.50); }
  .agent-card { stroke:rgba(59,130,246,0.48); }
  .mask-card { stroke:rgba(245,158,11,0.50); }
  .reward-card { fill:url(#rewardGlow); stroke:rgba(245,158,11,0.55); }
  .gate-card { stroke:rgba(239,68,68,0.52); }
  .svg-section-label, .svg-kicker, .svg-status, .svg-footer { font-family:var(--font-mono); letter-spacing:0.03em; }
  .svg-section-label { fill:var(--muted); font-size:13px; font-weight:700; }
  .svg-kicker { fill:var(--muted); font-size:12px; font-weight:700; }
  .svg-title { fill:var(--text); font-size:20px; font-weight:800; }
  .svg-body { fill:var(--muted); font-size:15px; }
  .svg-status { fill:rgb(185,28,28); font-size:13px; font-weight:800; }
  .svg-annotation { fill:var(--muted); font-size:13px; }
  .svg-footer { fill:var(--text); font-size:14px; font-weight:700; }
  .svg-arrow { fill:none; stroke:rgba(20,184,166,0.78); stroke-width:4; stroke-linecap:round; }
  .svg-arrow.warn { stroke:rgba(245,158,11,0.86); }
  .svg-arrow.loop { stroke:rgba(59,130,246,0.78); stroke-dasharray:8 8; }
  .svg-arrow-head { fill:rgba(20,184,166,0.86); }
  .process-strip { margin-top:16px; display:flex; align-items:stretch; gap:8px; overflow-x:auto; padding:4px 0 2px; }
  .process-step { min-width:180px; flex:1; border:1px solid var(--border-faint); border-radius:18px; padding:14px; background:var(--surface); box-shadow:var(--shadow-sm); position:relative; }
  .process-step[data-step-tone='pass'] { border-color:rgba(34,197,94,0.42); background:linear-gradient(180deg, rgba(34,197,94,0.08), var(--surface)); }
  .process-step[data-step-tone='warn'] { border-color:rgba(245,158,11,0.42); background:linear-gradient(180deg, rgba(245,158,11,0.08), var(--surface)); }
  .process-step[data-step-tone='danger'] { border-color:rgba(239,68,68,0.42); background:linear-gradient(180deg, rgba(239,68,68,0.08), var(--surface)); }
  .process-step[data-step-tone='input'] { border-color:rgba(59,130,246,0.42); background:linear-gradient(180deg, rgba(59,130,246,0.08), var(--surface)); }
  .step-badge { width:34px; height:34px; display:grid; place-items:center; border-radius:50%; background:var(--surface-sunken); font-family:var(--font-mono); font-weight:800; margin-bottom:10px; }
  .process-step h3 { margin:0 0 6px; font-size:15px; }
  .process-step p { margin:0; color:var(--muted); font-size:12px; line-height:1.55; }
  .process-connector { align-self:center; color:var(--muted); font-size:24px; font-weight:900; padding:0 2px; }
  .performance-grid { margin-top:16px; display:grid; grid-template-columns:repeat(auto-fit, minmax(250px, 1fr)); gap:12px; }
  .performance-card { border:1px solid var(--border-faint); border-radius:18px; padding:16px; background:var(--surface); box-shadow:var(--shadow-sm); }
  .performance-card[data-card-tone='pass'] { border-color:rgba(34,197,94,0.40); }
  .performance-card[data-card-tone='danger'] { border-color:rgba(239,68,68,0.45); background:linear-gradient(180deg, rgba(239,68,68,0.07), var(--surface)); }
  .performance-card h3 { margin:4px 0 12px; font-size:16px; }
  .performance-main { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; }
  .performance-main span { font-size:30px; font-weight:900; letter-spacing:-0.03em; }
  .performance-main small { color:var(--muted); font-size:12px; }
  .process-selector-panel { overflow:hidden; }
  .process-selector-grid { margin-top:16px; display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:10px; }
  .lane-select-card { text-align:left; border:1px solid var(--border-faint); border-radius:16px; padding:14px; background:var(--surface); color:var(--text); cursor:pointer; box-shadow:var(--shadow-sm); display:grid; gap:6px; }
  .lane-select-card[data-active='true'] { border-color:rgba(20,184,166,0.62); background:linear-gradient(180deg, rgba(20,184,166,0.12), var(--surface)); }
  .lane-select-card span, .lane-select-card small { color:var(--muted); font-family:var(--font-mono); font-size:11px; }
  .lane-select-card b { font-size:14px; }
  .selected-process-grid { margin-top:14px; display:grid; grid-template-columns:minmax(0, 1.4fr) minmax(260px, 0.7fr); gap:12px; }
  .selected-process-main, .selected-process-side { border:1px solid var(--border-faint); border-radius:18px; padding:16px; background:var(--surface); box-shadow:var(--shadow-sm); }
  .selected-process-main h3, .selected-process-side h3 { margin:6px 0 10px; }
  .selected-process-main p, .selected-process-side p { color:var(--muted); line-height:1.55; }
  .lane-visual-chain { display:flex; gap:8px; align-items:stretch; overflow-x:auto; margin:14px 0; padding-bottom:2px; }
  .lane-node { min-width:150px; border:1px solid var(--border-faint); border-radius:14px; padding:12px; background:linear-gradient(180deg, rgba(15,23,42,0.02), var(--surface)); }
  .lane-node[data-tone='pass'] { border-color:rgba(34,197,94,0.42); }
  .lane-node[data-tone='warn'] { border-color:rgba(245,158,11,0.42); }
  .lane-node[data-tone='danger'] { border-color:rgba(239,68,68,0.46); }
  .lane-node span { display:block; color:var(--muted); font-family:var(--font-mono); font-size:11px; margin-bottom:6px; }
  .lane-node b { font-size:12px; line-height:1.45; }
  .lane-arrow { align-self:center; color:var(--muted); font-size:22px; font-weight:900; }
  .triple-detail-grid, .ai-guidance-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr)); gap:10px; margin-top:14px; }
  .triple-detail-grid div { border:1px solid var(--border-faint); border-radius:14px; padding:12px; background:var(--surface-sunken); }
  .triple-detail-grid h4 { margin:0 0 8px; font-size:13px; }
  .triple-detail-grid p, .limitation-item, .improvement-item { margin:6px 0; font-size:12px; }
  .limitation-item { padding:8px 10px; border-radius:12px; background:rgba(239,68,68,0.07); color:var(--text); }
  .improvement-item { padding:8px 10px; border-radius:12px; background:rgba(20,184,166,0.08); color:var(--text); }
  .ai-format-box { max-height:320px; overflow:auto; white-space:pre-wrap; font-family:var(--font-mono); font-size:11px; line-height:1.45; border:1px solid var(--border-faint); border-radius:14px; padding:12px; background:var(--surface-sunken); }
  .tabular-policy-visual { min-height:190px; display:grid; gap:12px; padding:16px; border-radius:18px; background:linear-gradient(135deg, rgba(15,23,42,0.03), rgba(20,184,166,0.06)); }
  .policy-status-pill { display:inline-flex; width:max-content; max-width:100%; padding:7px 10px; border-radius:999px; background:rgba(20,184,166,0.10); color:rgb(15,118,110); font-family:var(--font-mono); font-size:11px; font-weight:800; }
  .policy-status-pill.danger { background:rgba(239,68,68,0.08); color:rgb(185,28,28); }
  .q-table-grid { display:grid; grid-template-columns:1fr 32px 1fr 32px 1fr; gap:8px; align-items:center; }
  .q-cell { min-height:68px; display:grid; place-items:center; text-align:center; border:1px solid var(--border-faint); border-radius:14px; background:var(--surface); font-family:var(--font-mono); font-size:12px; font-weight:800; }
  .q-cell.active { border-color:rgba(20,184,166,0.55); background:rgba(20,184,166,0.08); }
  .q-arrow { color:var(--muted); text-align:center; font-weight:900; }
  .blocked-note { padding:10px 12px; border-radius:12px; background:rgba(239,68,68,0.07); color:rgb(185,28,28); font-family:var(--font-mono); font-size:11px; font-weight:800; }
  .performance-bar { height:8px; margin:12px 0; border-radius:999px; background:var(--surface-sunken); overflow:hidden; }
  .performance-bar::before { content:""; display:block; width:var(--bar-width); height:100%; border-radius:999px; background:linear-gradient(90deg, rgba(20,184,166,0.85), rgba(59,130,246,0.75)); }
  .performance-card dl { display:grid; grid-template-columns:1fr; gap:7px; margin:0; }
  .performance-card dl div { display:flex; justify-content:space-between; gap:12px; border-top:1px solid var(--border-faint); padding-top:7px; }
  .performance-card dt { color:var(--muted); font-size:12px; }
  .performance-card dd { margin:0; font-weight:800; font-family:var(--font-mono); font-size:12px; text-align:right; }
  .outcome-note { margin-top:14px; padding:12px 14px; border-radius:14px; border:1px solid rgba(245,158,11,0.38); background:rgba(245,158,11,0.08); color:var(--text); font-weight:700; line-height:1.55; }
  .learning-visual-grid { margin-top:14px; display:grid; grid-template-columns:repeat(auto-fit, minmax(300px, 1fr)); gap:12px; }
  .mini-chart-card { border:1px solid var(--border-faint); border-radius:18px; padding:14px; background:linear-gradient(180deg, rgba(15,23,42,0.02), var(--surface)); }
  .mini-chart-card h3 { margin:4px 0 12px; font-size:15px; }
  .mini-bar-row, .nav-row { display:grid; grid-template-columns:64px 1fr minmax(72px, auto); gap:10px; align-items:center; padding:6px 0; border-top:1px solid var(--border-faint); font-size:12px; }
  .nav-row { grid-template-columns:78px 1fr minmax(92px, auto); }
  .mini-bar-row span, .nav-row span { color:var(--muted); font-family:var(--font-mono); }
  .mini-bar-row b, .nav-row b { font-family:var(--font-mono); text-align:right; }
  .mini-bar-track { height:8px; border-radius:999px; background:var(--surface-sunken); overflow:hidden; }
  .mini-bar-fill { width:var(--bar-width); height:100%; border-radius:999px; background:linear-gradient(90deg, rgba(245,158,11,0.80), rgba(239,68,68,0.60)); }
  .mini-bar-fill.nav { background:linear-gradient(90deg, rgba(20,184,166,0.85), rgba(59,130,246,0.75)); }
  .mini-bar-row[data-tone='pass'] .mini-bar-fill { background:linear-gradient(90deg, rgba(34,197,94,0.85), rgba(20,184,166,0.72)); }
  .flow-canvas { margin-top:16px; display:flex; align-items:stretch; gap:10px; overflow-x:auto; padding:14px; border:1px solid var(--border-faint); border-radius:18px; background:linear-gradient(135deg, rgba(56,189,248,0.06), rgba(167,139,250,0.06)); }
  .scenario-template-grid, .signal-grid, .scenario-comparison-grid, .readiness-grid, .improvement-grid, .maturity-kpi-grid { margin-top:16px; display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:12px; }
  .template-card { text-align:left; border:1px solid var(--border-faint); border-radius:16px; padding:14px; background:var(--surface); color:var(--text); cursor:pointer; box-shadow:var(--shadow-sm); display:grid; gap:6px; }
  .template-card[data-active='true'] { border-color:rgba(59,130,246,0.58); background:linear-gradient(180deg, rgba(59,130,246,0.10), var(--surface)); }
  .template-card span, .template-card small { color:var(--muted); font-family:var(--font-mono); font-size:11px; }
  .template-card b { font-size:14px; }
  .kv-row { display:flex; justify-content:space-between; gap:12px; border-top:1px solid var(--border-faint); padding:8px 0; font-size:12px; }
  .kv-row span, .kv-row b { font-family:var(--font-mono); }
  .artifact-line { display:grid; gap:3px; padding:8px 0; border-top:1px solid var(--border-faint); font-size:11px; }
  .artifact-line b, .artifact-line span { font-family:var(--font-mono); overflow-wrap:anywhere; }
  .scenario-card, .readiness-card, .improvement-card { border:1px solid var(--border-faint); border-radius:18px; padding:14px; background:var(--surface); box-shadow:var(--shadow-sm); }
  .scenario-card[data-tone='warn'], .readiness-card[data-tone='warn'], .improvement-card[data-tone='warn'] { border-color:rgba(245,158,11,0.42); background:linear-gradient(180deg, rgba(245,158,11,0.07), var(--surface)); }
  .scenario-card[data-tone='danger'], .readiness-card[data-tone='danger'], .improvement-card[data-tone='danger'] { border-color:rgba(239,68,68,0.42); background:linear-gradient(180deg, rgba(239,68,68,0.07), var(--surface)); }
  .scenario-card h3, .readiness-card h3, .improvement-card h3 { margin:6px 0 8px; font-size:15px; }
  .scenario-card p, .readiness-card p, .improvement-card p { margin:7px 0; color:var(--muted); font-size:12px; line-height:1.55; }
  .scenario-status-line { display:flex; justify-content:space-between; gap:8px; margin-top:10px; padding-top:9px; border-top:1px solid var(--border-faint); font-family:var(--font-mono); font-size:11px; }
  .score-track { height:8px; border-radius:999px; background:var(--surface-sunken); overflow:hidden; margin:8px 0; }
  .score-fill { width:var(--bar-width); height:100%; border-radius:999px; background:linear-gradient(90deg, rgba(20,184,166,0.85), rgba(59,130,246,0.78)); }
  .improvement-card small { display:inline-flex; margin-top:8px; padding:5px 8px; border-radius:999px; background:var(--surface-sunken); font-family:var(--font-mono); font-size:11px; font-weight:800; }
  .live-visualizer-panel { overflow:hidden; }
  .live-rl-stage { margin-top:16px; display:grid; grid-template-columns:minmax(240px, 1fr) minmax(320px, 1.25fr) minmax(240px, 1fr); gap:12px; align-items:stretch; }
  .live-state-card, .policy-network-card, .live-reward-card { border:1px solid var(--border-faint); border-radius:20px; padding:16px; background:var(--surface); box-shadow:var(--shadow-sm); }
  .live-state-card { background:linear-gradient(180deg, rgba(20,184,166,0.10), var(--surface)); border-color:rgba(20,184,166,0.34); }
  .policy-network-card { background:radial-gradient(circle at 50% 24%, rgba(59,130,246,0.14), transparent 38%), var(--surface); border-color:rgba(59,130,246,0.34); }
  .live-reward-card { background:linear-gradient(180deg, rgba(245,158,11,0.10), var(--surface)); border-color:rgba(245,158,11,0.38); }
  .live-state-card h3, .live-reward-card h3 { margin:6px 0 12px; font-size:18px; }
  .live-state-card p { margin:12px 0 0; color:var(--muted); font-size:12px; line-height:1.55; }
  .state-meter-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:0; }
  .state-meter-grid div { border:1px solid var(--border-faint); border-radius:12px; padding:10px; background:rgba(255,255,255,0.55); }
  .state-meter-grid dt, .live-reward-card dt { color:var(--muted); font-size:11px; font-family:var(--font-mono); }
  .state-meter-grid dd, .live-reward-card dd { margin:4px 0 0; font-weight:900; font-family:var(--font-mono); }
  .action-probabilities { margin-top:12px; display:grid; gap:7px; }
  .action-prob-row { display:grid; grid-template-columns:54px 1fr 42px; gap:8px; align-items:center; font-size:12px; }
  .action-prob-row span, .action-prob-row b { font-family:var(--font-mono); }
  .action-prob-row[data-selected='true'] { color:rgb(15,118,110); font-weight:900; }
  .mini-bar-fill.policy { background:linear-gradient(90deg, rgba(59,130,246,0.82), rgba(20,184,166,0.85)); transition:width 0.35s ease; }
  .selected-action-pill { display:inline-flex; margin-bottom:12px; padding:7px 12px; border-radius:999px; background:rgba(20,184,166,0.12); color:rgb(15,118,110); font-family:var(--font-mono); font-weight:900; }
  .live-reward-card dl { display:grid; gap:9px; margin:0; }
  .live-reward-card dl div { border-top:1px solid var(--border-faint); padding-top:9px; display:flex; justify-content:space-between; gap:12px; }
  .live-reward-card dd { text-align:right; }
  @media (max-width:1100px) {
    .live-rl-stage { grid-template-columns:1fr; }
    .selected-process-grid { grid-template-columns:1fr; }
  }
  .flow-node { min-width:150px; border:1px solid var(--border-faint); border-radius:16px; padding:12px; background:var(--surface); box-shadow:var(--shadow-sm); }
  .flow-node[data-tone='pass'] { border-color:rgba(34,197,94,0.45); }
  .flow-node[data-tone='warn'] { border-color:rgba(245,158,11,0.45); }
  .flow-node[data-tone='danger'] { border-color:rgba(239,68,68,0.45); }
  .node-id { font-family:var(--font-mono); font-size:12px; color:var(--muted); }
  .node-label { font-weight:700; margin-top:4px; }
  .node-summary { font-size:12px; color:var(--muted); margin-top:6px; min-height:34px; }
  .node-status { margin-top:8px; font-size:11px; font-family:var(--font-mono); }
  .flow-arrow { align-self:center; color:var(--muted); font-size:24px; font-weight:700; }
  .explain-grid, .contract-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(230px, 1fr)); gap:12px; margin-top:16px; }
  .explain-card, .contract-box { border:1px solid var(--border-faint); border-radius:14px; padding:14px; background:var(--surface); }
  .contract-box h3 { margin:0 0 8px; font-size:15px; }
  .chip { display:inline-flex; margin:3px; padding:4px 8px; border-radius:999px; background:var(--surface-sunken); font-family:var(--font-mono); font-size:12px; }
  .mono { font-family:var(--font-mono); font-size:12px; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th, td { border-bottom:1px solid var(--border-faint); padding:8px; text-align:left; vertical-align:top; }
  tr.pass td, .contract-box.pass { background:rgba(34,197,94,0.06); }
  tr.warn td { background:rgba(245,158,11,0.06); }
  tr.danger td, .contract-box.danger { background:rgba(239,68,68,0.06); }
</style>
