<script lang="ts">
  import type { DailyModelChartResponse, DailyPortfolioResponse, DailyPredictionResponse, DailyWalkForwardResponse } from '$lib/dailyOhlcvApi';

  interface Props {
    prediction: DailyPredictionResponse | null;
    portfolio: DailyPortfolioResponse | null;
    walkForward: DailyWalkForwardResponse | null;
    predictionChart: DailyModelChartResponse | null;
    portfolioChart: DailyModelChartResponse | null;
    walkForwardChart: DailyModelChartResponse | null;
  }

  let { prediction, portfolio, walkForward, predictionChart, portfolioChart, walkForwardChart }: Props = $props();

  const num = (value: unknown) => typeof value === 'number' ? value.toLocaleString('ko-KR', { maximumFractionDigits: 4 }) : (value ?? '—');
  const pct = (value: unknown) => typeof value === 'number' ? `${(value * 100).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}%` : (value ?? '—');
  const rows = (items: readonly Record<string, unknown>[] | undefined, limit = 8) => (items ?? []).slice(0, limit);
  const d3GateBlockerFallback = ['D0_PRICE_BASIS_NOT_VERIFIED', 'D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED', 'D5_WALK_FORWARD_NOT_PASS', 'D3_BASELINE_WATCH_RESEARCH_ONLY'];
  const d3BlockedUseFallback = ['model_build_or_candidate_promotion', 'go_summary_or_profit_claim', 'paper_forward_or_live_readiness_claims'];
  const listValue = (value: readonly string[] | undefined) => value?.length ? value : ['—'];
  const guidanceValue = (row: Readonly<Record<string, unknown>>, key: string) => typeof row[key] === 'string' ? row[key] : String(row[key] ?? '—');
  const uniqueStrings = (...groups: readonly (readonly string[] | undefined)[]) => Array.from(new Set(groups.flatMap((group) => group ?? [])));
  const hashValue = (value: unknown) => typeof value === 'string' && value.length ? value : '—';
  const flagText = (value: unknown) => value === true ? 'true' : value === false ? 'false' : 'MISSING';
  const joinedFlagText = (chartValue: unknown, latestValue: unknown) => {
    const chart = flagText(chartValue);
    const latest = flagText(latestValue);
    return chart === latest ? chart : `chart=${chart} latest=${latest} MISMATCH`;
  };
  const statusText = (chartValue: unknown, latestValue: unknown) => {
    const chart = typeof chartValue === 'string' && chartValue.length ? chartValue : 'MISSING';
    const latest = typeof latestValue === 'string' && latestValue.length ? latestValue : 'MISSING';
    if (chart === latest) return chart;
    if (chart === 'MISSING' && latest !== 'MISSING') return latest;
    if (latest === 'MISSING' && chart !== 'MISSING') return chart;
    if (chart === 'NOT_STARTED' || latest === 'NOT_STARTED') return 'NOT_STARTED';
    return `${chart}/${latest} MISMATCH`;
  };
  const stringsFrom = (value: unknown): readonly string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.length > 0) : [];
  const positiveNumber = (value: unknown) => typeof value === 'number' && Number.isFinite(value) && value > 0;

  const baselineSummary = $derived((predictionChart?.baseline_delta_summary ?? prediction?.baseline_delta_summary ?? {}) as Record<string, unknown>);
  const d3GateBlockers = $derived((predictionChart?.d3_gate_blockers ?? prediction?.d3_gate_blockers ?? []) as readonly string[]);
  const d3BlockedUses = $derived((predictionChart?.d3_blocked_uses ?? prediction?.d3_blocked_uses ?? []) as readonly string[]);
  const displayedD3GateBlockers = $derived(uniqueStrings(d3GateBlockerFallback, d3GateBlockers));
  const displayedD3BlockedUses = $derived(d3BlockedUses.length ? d3BlockedUses : d3BlockedUseFallback);
  const d3Readiness = $derived(String(baselineSummary.readiness_status ?? predictionChart?.readiness_status ?? prediction?.readiness_status ?? 'D3_WATCH_RESEARCH_ONLY'));
  const d3Guidance = $derived((predictionChart?.d3_user_guidance ?? prediction?.d3_user_guidance ?? []) as readonly Record<string, unknown>[]);
  const baselineFreeze = $derived((predictionChart?.baseline_freeze_contract ?? prediction?.baseline_freeze_contract ?? {}) as Record<string, unknown>);
  const telemetry = $derived((portfolioChart?.telemetry ?? portfolio?.telemetry ?? {}) as Record<string, unknown>);
  const portfolioArtifactHashes = $derived((portfolioChart?.artifact_hashes ?? portfolio?.artifact_hashes ?? {}) as Record<string, unknown>);
  const portfolioPredictionHashes = $derived((portfolioChart?.prediction_artifact_hashes ?? portfolio?.prediction_artifact_hashes ?? {}) as Record<string, unknown>);
  const rewardSummaryRows = $derived((((portfolioChart?.reward_component_summary as Record<string, unknown> | undefined)?.by_split ?? []) as readonly Record<string, unknown>[]));
  const portfolioSamples = $derived((portfolio?.samples ?? {}) as Readonly<Record<string, readonly Record<string, unknown>[]>>);
  const observationManifest = $derived((portfolioChart?.observation_manifest ?? portfolio?.observation_manifest ?? {}) as Record<string, unknown>);
  const observationValidation = $derived((portfolioChart?.observation_manifest_validation ?? portfolio?.observation_manifest_validation ?? {}) as Record<string, unknown>);
  const observationFields = $derived(((observationManifest.observation_fields ?? []) as readonly Record<string, unknown>[]));
  const leakageChecks = $derived(((observationManifest.leakage_checks ?? []) as readonly Record<string, unknown>[]));
  const stateObservationRows = $derived((portfolioChart?.state_observations ?? portfolioSamples.state_observations ?? []) as readonly Record<string, unknown>[]);
  const invalidActionRows = $derived((portfolioChart?.invalid_actions ?? portfolioSamples.invalid_actions ?? []) as readonly Record<string, unknown>[]);
  const rewardRows = $derived((portfolioChart?.reward_sample ?? portfolioSamples.reward_breakdown ?? []) as readonly Record<string, unknown>[]);
  const trajectoryRows = $derived((portfolioChart?.portfolio_trajectory ?? portfolioChart?.policy_nav ?? portfolioSamples.policy_nav ?? []) as readonly Record<string, unknown>[]);
  const rewardStackRows = $derived((portfolioChart?.reward_stack ?? rewardSummaryRows) as readonly Record<string, unknown>[]);
  const d5StateContract = $derived((walkForwardChart?.d4_state_contract ?? walkForward?.d4_state_contract ?? {}) as Record<string, unknown>);
  const d5StateRowCounts = $derived((d5StateContract.row_counts ?? {}) as Record<string, unknown>);
  const d5FoldWindows = $derived((walkForwardChart?.fold_windows ?? []) as readonly Record<string, unknown>[]);
  const d5SelectedFoldRows = $derived((walkForwardChart?.selected_fold_metrics ?? []) as readonly Record<string, unknown>[]);
  const d5NoTradeRows = $derived((walkForwardChart?.no_trade_control ?? []) as readonly Record<string, unknown>[]);
  const d5CostRows = $derived((walkForwardChart?.cost_sensitivity ?? []) as readonly Record<string, unknown>[]);
  const d5RlRows = $derived((walkForwardChart?.rl_fold_metrics ?? []) as readonly Record<string, unknown>[]);
  const d5FoldConsistency = $derived((walkForwardChart?.fold_consistency ?? {}) as Record<string, unknown>);
  const d5Reasons = $derived(uniqueStrings(stringsFrom(walkForwardChart?.reasons), stringsFrom(walkForward?.verdict?.reasons)));
  const displayedD5Reasons = $derived(d5Reasons.length ? d5Reasons : ['D5_REASONS_MISSING_OR_STALE']);
  const d5ArtifactIssues = $derived((walkForwardChart?.d4_artifact_issues ?? []) as readonly unknown[]);
  const d5ContractStatus = $derived(String(walkForwardChart?.d4_state_contract_status ?? d5StateContract.status ?? 'MISSING_D4_STATE_CONTRACT_STATUS'));
  const d5ContractGate = $derived(String(walkForwardChart?.d4_observation_manifest_gate ?? d5StateContract.gate ?? 'MISSING_D4_STATE_CONTRACT_GATE'));
  const d5ContractValidationStatus = $derived(String(walkForwardChart?.d4_observation_manifest_validation_status ?? d5StateContract.observation_manifest_validation_status ?? 'MISSING_D4_OBSERVATION_VALIDATION_STATUS'));
  const d5StateObservationRowCount = $derived(walkForwardChart?.d4_state_observation_rows ?? d5StateRowCounts.state_observations);
  const d5RewardActionAblationRowCount = $derived(walkForwardChart?.d4_reward_action_ablation_rows ?? d5StateRowCounts.reward_action_ablations);
  const d5SourceHashCount = $derived(walkForwardChart?.d4_source_hash_count ?? d5StateRowCounts.source_hashes);
  const d5Consumed = $derived(
    walkForwardChart?.d4_state_contract_artifacts_consumed === true
      && d5ContractStatus === 'PASS'
      && d5ContractGate === 'D4_OBSERVATION_STATE_MANIFEST'
      && d5ContractValidationStatus === 'PASS'
      && positiveNumber(d5StateObservationRowCount)
      && positiveNumber(d5RewardActionAblationRowCount)
      && positiveNumber(d5SourceHashCount)
  );
  const d5ContractMessages = $derived(
    d5Consumed && d5ArtifactIssues.length === 0
      ? ['D4_OBSERVATION_STATE_MANIFEST_CONSUMED']
      : ['D4_STATE_CONTRACT_EVIDENCE_MISSING_OR_STALE', ...d5ArtifactIssues.map((issue) => String(issue))]
  );
  const walkForwardArtifactHashes = $derived((walkForwardChart?.artifact_hashes ?? walkForward?.artifact_hashes ?? {}) as Record<string, unknown>);
  const walkForwardPredictionHashes = $derived((walkForwardChart?.prediction_artifact_hashes ?? walkForward?.prediction_artifact_hashes ?? {}) as Record<string, unknown>);
  const walkForwardPortfolioHashes = $derived((walkForwardChart?.portfolio_artifact_hashes ?? walkForward?.portfolio_artifact_hashes ?? {}) as Record<string, unknown>);
  const d4ModelFlag = $derived(joinedFlagText(portfolioChart?.model_build_allowed, portfolio?.model_build_allowed));
  const d4GoFlag = $derived(joinedFlagText(portfolioChart?.go_summary_allowed, portfolio?.go_summary_allowed));
  const d4PaperFlag = $derived(joinedFlagText(portfolioChart?.paper_forward_allowed, portfolio?.paper_forward_allowed));
  const d4LiveFlag = $derived(joinedFlagText(portfolioChart?.live_broker_order_allowed, portfolio?.live_broker_order_allowed));
  const d5ModelFlag = $derived(joinedFlagText(walkForwardChart?.model_build_allowed, walkForward?.model_build_allowed));
  const d5GoFlag = $derived(joinedFlagText(walkForwardChart?.go_summary_allowed, walkForward?.go_summary_allowed));
  const d5PaperFlag = $derived(joinedFlagText(walkForwardChart?.paper_forward_allowed, walkForward?.paper_forward_allowed));
  const d5LiveFlag = $derived(joinedFlagText(walkForwardChart?.live_broker_order_allowed, walkForward?.live_broker_order_allowed));
  const d5NoLiveReadyFlag = $derived(joinedFlagText(walkForwardChart?.no_live_broker_order_readiness, walkForward?.no_live_broker_order_readiness));
  const d5DisplayStatus = $derived(statusText(walkForwardChart?.status, walkForward?.status));

  function verdictValue(record: Record<string, unknown> | undefined, key: string): unknown {
    return record?.[key] ?? '—';
  }

  function tone(status: string | undefined): string {
    if (status === 'PASS') return 'success';
    if (status === 'WATCH' || status === 'RESEARCH_ONLY') return 'warn';
    if (status === 'NO-GO' || status === 'BLOCKED') return 'danger';
    return '';
  }
</script>

<section class="panel" data-daily-model-results-card>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">D3-D5 Model Evidence</div>
      <h2 class="text-h3">예측·포트폴리오 RL·워크포워드 게이트</h2>
    </div>
    <span class="pill {tone(d5DisplayStatus)}"><span class="dot"></span>{d5DisplayStatus}</span>
  </div>

  <p class="text-muted" style="margin-top:8px">
    이 영역은 결과를 좋게 포장하는 화면이 아니라 실패/잠금 근거와 RESEARCH_ONLY diagnostics를 표시하는 읽기 전용 패널입니다. RESEARCH_ONLY, WATCH, NO-GO, PRICE_BASIS_UNKNOWN, UNIVERSE_WATCH_HEURISTIC, no live/broker/orders.
  </p>

  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">D3 status</div><div class="metric-value">{prediction?.status ?? 'NOT_STARTED'}</div></div>
    <div class="metric"><div class="metric-label">D4 badge</div><div class="metric-value">{String(verdictValue(portfolio?.verdict, 'ui_badge'))}</div></div>
    <div class="metric"><div class="metric-label">D5 gate</div><div class="metric-value">{d5DisplayStatus}</div></div>
    <div class="metric"><div class="metric-label">model_build_allowed</div><div class="metric-value">{d5ModelFlag}</div></div>
  </div>

  <div class="notice danger" data-daily-decision-panel style="margin-top:12px">
    결정 패널: model_build_allowed={d5ModelFlag} · go_summary_allowed={d5GoFlag} · paper_forward_allowed={d5PaperFlag} · live_broker_order_allowed={d5LiveFlag} · 현재 결론은 수익 모델 생성 GO가 아니라 NO-GO/RESEARCH_ONLY 증거입니다.
  </div>

  <div class="evidence-grid" style="margin-top:16px">
    <div class="evidence-box" data-daily-prediction-chart>
      <div class="text-eyebrow">D3 baseline/ranker</div>
      <div class="mini-kv"><span>run</span><strong class="tnum">{prediction?.run_id ?? '—'}</strong></div>
      <div class="mini-kv"><span>best_strategy</span><strong>{String(verdictValue(prediction?.verdict, 'best_strategy_by_total_net_return'))}</strong></div>
      <div class="mini-kv"><span>price_basis</span><strong>{prediction?.price_basis ?? 'unknown'}</strong></div>
      <div class="mini-kv"><span>go_summary_allowed</span><strong>{String(verdictValue(prediction?.verdict, 'go_summary_allowed'))}</strong></div>
      <div class="mini-kv" data-daily-d3-cost-assumption><span>cost</span><strong>{num(verdictValue(baselineSummary, 'cost_round_trip_bp'))}bp round trip</strong></div>
      <div class="mini-kv"><span>control</span><strong>{String(verdictValue(baselineSummary, 'shuffle_control_strategy'))}</strong></div>
      <div class="mini-kv"><span>best_rule</span><strong>{String(verdictValue(baselineSummary, 'best_rule_baseline_strategy'))}</strong></div>
      <div class="mini-kv"><span>best_supervised</span><strong>{String(verdictValue(baselineSummary, 'best_supervised_strategy'))}</strong></div>
      <div class="mini-kv"><span>supervised vs shuffle</span><strong>{pct(verdictValue(baselineSummary, 'best_supervised_delta_vs_shuffle_control'))}</strong></div>
      <div class="mini-kv"><span>readiness</span><strong>{d3Readiness}</strong></div>
      <div class="mini-kv"><span>freeze</span><strong>{String(baselineFreeze.deterministic_shuffle_method ?? 'sha256(date:code)_ascending')} · fit={String(baselineFreeze.fit_split ?? 'train')} · eval={String((baselineFreeze.evaluation_splits as string[] | undefined)?.join('+') ?? 'val+test')}</strong></div>
      <div class="mini-list" data-daily-d3-gate-blockers>
        <div><span>D3 blockers</span><strong>{listValue(displayedD3GateBlockers).join(', ')}</strong></div>
        <div><span>blocked uses</span><strong>{listValue(displayedD3BlockedUses).join(', ')}</strong></div>
      </div>
      <div class="mini-list" data-daily-d3-user-guidance>
        {#each rows(d3Guidance, 3) as row}
          <div><span>{guidanceValue(row, 'section')}</span><strong>{guidanceValue(row, 'action')}</strong></div>
        {/each}
      </div>
      <div class="mini-list">
        {#each rows(predictionChart?.baseline_series, 5) as row}
          <div><span>{row.strategy} · {row.strategy_family ?? '—'}</span><strong>{pct(row.total_net_return)} · vs shuffle {pct(row.delta_vs_shuffle_control_total_net_return)} · DD {pct(row.max_drawdown)}</strong></div>
        {/each}
      </div>
    </div>

    <div class="evidence-box" data-daily-portfolio-chart>
      <div class="text-eyebrow">D4 constrained portfolio RL</div>
      <div class="mini-kv"><span>run</span><strong class="tnum">{portfolio?.run_id ?? '—'}</strong></div>
      <div class="mini-kv"><span>gate_dependency</span><strong>{String(verdictValue(portfolio?.verdict, 'gate_dependency'))}</strong></div>
      <div class="mini-kv"><span>implementation_unlocked</span><strong>{String(verdictValue(portfolio?.verdict, 'implementation_unlocked'))}</strong></div>
      <div class="mini-kv" data-daily-rl-readiness><span>readiness/model</span><strong>{String(portfolioChart?.readiness_status ?? portfolio?.verdict?.readiness_status ?? portfolio?.readiness_status ?? 'D4_RESEARCH_ONLY_DIAGNOSTICS')} · model={d4ModelFlag} · go={d4GoFlag} · paper={d4PaperFlag} · live={d4LiveFlag}</strong></div>
      <div class="mini-list" data-daily-rl-provenance-hashes>
        <div><span>prediction_manifest_sha</span><strong class="tnum">{hashValue(portfolioChart?.prediction_manifest_sha ?? portfolio?.prediction_manifest_sha)}</strong></div>
        <div><span>D4 artifact hashes</span><strong class="tnum">policy_metrics={hashValue(portfolioArtifactHashes.policy_metrics)} · policy_nav={hashValue(portfolioArtifactHashes.policy_nav)} · policy_baseline={hashValue(portfolioArtifactHashes.policy_baseline_comparison)}</strong></div>
        <div><span>upstream hashes</span><strong class="tnum">predictions={hashValue(portfolioPredictionHashes.predictions)} · baseline={hashValue(portfolioPredictionHashes.baseline_metrics)} · verdict={hashValue(portfolioPredictionHashes.verdict)}</strong></div>
      </div>
      <div class="mini-kv"><span>delta_vs_best_d3</span><strong>{pct(portfolio?.baseline_comparison?.delta_vs_best_d3_total_net_return)}</strong></div>
      <div class="mini-kv" data-daily-rl-invalid-action-rate><span>invalid_action_rate</span><strong>{pct(verdictValue(portfolio?.verdict, 'invalid_action_rate'))}</strong></div>
      <div class="mini-kv" data-daily-rl-training-status><span>training_status</span><strong>{String(portfolioChart?.training_status ?? telemetry.training_status ?? '—')}</strong></div>
      <div class="mini-kv" data-daily-rl-telemetry-stack><span>telemetry_stack</span><strong>{String((telemetry.visualization_stack as string[] | undefined)?.join(' · ') ?? 'csv/dashboard')}</strong></div>
      <div class="mini-list" data-daily-rl-state-contract>
        <div><span>state_contract</span><strong>{String(observationManifest.gate ?? 'MISSING_D4_OBSERVATION_STATE_MANIFEST_GATE')} · validation={String(observationValidation.status ?? 'MISSING_D4_OBSERVATION_VALIDATION_STATUS')}</strong></div>
        <div><span>model/go/telemetry</span><strong>model={String(observationManifest.model_build_allowed)} · go={String(observationManifest.go_summary_allowed)} · telemetry_sufficient={String(observationManifest.reward_action_telemetry_sufficient_for_d4)}</strong></div>
        {#each rows(observationFields, 4) as field}
          <div><span>{field.name} · {field.timing ?? '—'}</span><strong>{field.source ?? field.leakage_status ?? '—'}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-state-observations>
        <div><span>state_observations</span><strong>cash · exposure · top candidate · future label exposed</strong></div>
        {#each rows(stateObservationRows, 4) as row}
          <div><span>{row.date} · pos {row.observation_position_count}</span><strong>cash {num(row.cash_fraction)} · exp {num(row.exposure_fraction)} · top {row.top_candidate_code ?? '—'} · future={String(row.future_label_exposed)}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-leakage-checks>
        <div><span>leakage_checks</span><strong>required missing/duplicate/failing checks must fail closed</strong></div>
        {#each rows(leakageChecks, 5) as check}
          <div><span>{check.check}</span><strong>{String(check.status)} · {String(check.evidence ?? '—')}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-learning-curve>
        <div><span>learning_curve</span><strong>episode · total_reward · rolling_mean</strong></div>
        {#each rows(portfolioChart?.learning_curve, 5) as row}
          <div><span>EP {row.episode}</span><strong>{num(row.total_reward)} · roll {num(row.rolling_mean_reward)} · best {num(row.best_total_reward)}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-reward-return-curve>
        <div><span>reward_return_curve</span><strong>date · gross return · reward · equity · missing labels</strong></div>
        {#each rows(rewardRows, 5) as row}
          <div><span>{row.split} · {row.date} · {row.action}</span><strong>gross {pct(row.gross_return)} · reward {num(row.reward)} · equity {num(row.equity)} · missing {num(row.missing_reward_label_count)}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-action-distribution>
        <div><span>action_distribution</span><strong>split · action · invalid · rate</strong></div>
        {#each rows(portfolioChart?.action_distribution, 5) as row}
          <div><span>{row.split} · {row.action} · invalid={String(row.invalid_action)}</span><strong>{num(row.count)} · {pct(row.action_rate)}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-invalid-actions>
        <div><span>invalid_actions</span><strong>date · action · invalid · mask</strong></div>
        {#each rows(invalidActionRows, 4) as row}
          <div><span>{row.split} · {row.date}</span><strong>{row.action} · invalid={String(row.invalid_action)} · mask {row.action_mask_hold_buy_add_sell_reduce ?? '—'}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-reward-components>
        <div><span>reward_components</span><strong>gross/cost/exposure/concentration/invalid/churn/drawdown/reward</strong></div>
        {#each rows(rewardStackRows, 4) as row}
          <div><span>{row.split}</span><strong>{num(row.gross_return)} / cost {num(row.cost)} / exp {num(row.exposure_penalty)} / conc {num(row.concentration_penalty)} / invalid {num(row.invalid_action_penalty)} / churn {num(row.churn_penalty)} / DD {num(row.drawdown_penalty)} / reward {num(row.reward)}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-turnover-drawdown>
        <div><span>turnover_drawdown</span><strong>date · turnover · drawdown</strong></div>
        {#each rows(portfolioChart?.turnover_series, 3) as row, index}
          <div><span>{row.split} · {row.date}</span><strong>turn {num(row.turnover)} · DD {pct((portfolioChart?.drawdown_series ?? [])[index]?.current_drawdown)}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-policy-baseline-comparison>
        <div><span>frozen_baseline_delta</span><strong>policy NAV/MDD/turnover vs D3 baselines</strong></div>
        {#each rows(portfolioChart?.policy_baseline_comparison, 6) as row}
          <div><span>{row.baseline_strategy}</span><strong>NAV {num(row.policy_nav)} vs {num(row.baseline_nav)} · Δ {pct(row.baseline_delta_total_net_return)} · DD {pct(row.policy_max_drawdown)}</strong></div>
        {/each}
      </div>
      <div class="mini-list" data-daily-rl-portfolio-trajectory>
        <div><span>portfolio_trajectory</span><strong>date · NAV · MDD · concentration · turnover</strong></div>
        {#each rows(trajectoryRows, 4) as row}
          <div><span>{row.date}</span><strong>NAV {num(row.policy_nav)} · MDD {pct(row.policy_current_drawdown)} · conc {num(row.policy_concentration)} · turn {num(row.policy_turnover)}</strong></div>
        {/each}
      </div>
    </div>

    <div class="evidence-box" data-daily-walk-forward-chart>
      <div class="text-eyebrow">D5 walk-forward gate</div>
      <div class="mini-kv"><span>run</span><strong class="tnum">{walkForward?.run_id ?? '—'}</strong></div>
      <div class="mini-kv"><span>strategy</span><strong>{String(walkForwardChart?.selected_strategy ?? walkForward?.selected_strategy ?? verdictValue(walkForward?.verdict, 'selected_strategy'))}</strong></div>
      <div class="mini-kv"><span>n_folds</span><strong>{num(walkForwardChart?.n_folds)} / {num(walkForwardChart?.required_min_folds)}</strong></div>
      <div class="mini-kv"><span>purge/embargo</span><strong>{num(walkForwardChart?.purge_days)}d / {num(walkForwardChart?.embargo_days)}d · min {num(walkForwardChart?.min_required_purge_days)}d / {num(walkForwardChart?.min_required_embargo_days)}d</strong></div>
      <div class="mini-kv"><span>no_oos_retuning</span><strong>{String(walkForwardChart?.no_oos_retuning)}</strong></div>
      <div class="mini-kv"><span>policy</span><strong>{String(walkForwardChart?.strategy_selection_policy ?? walkForward?.strategy_selection_policy ?? verdictValue(walkForward?.verdict, 'strategy_selection_policy'))}</strong></div>
      <div class="mini-kv" data-daily-walk-forward-readiness><span>readiness/model</span><strong>{String(walkForwardChart?.readiness_status ?? walkForward?.readiness_status ?? 'D5_NO_GO_RESEARCH_ONLY_GATE')} · model={d5ModelFlag} · go={d5GoFlag} · paper={d5PaperFlag} · live={d5LiveFlag} · no_live_ready={d5NoLiveReadyFlag}</strong></div>
      <div class="mini-list" data-daily-walk-forward-provenance-hashes>
        <div><span>manifest sha</span><strong class="tnum">prediction={hashValue(walkForwardChart?.prediction_manifest_sha ?? walkForward?.prediction_manifest_sha)} · portfolio={hashValue(walkForwardChart?.portfolio_manifest_sha ?? walkForward?.portfolio_manifest_sha)}</strong></div>
        <div><span>D5 artifact hashes</span><strong class="tnum">fold_metrics={hashValue(walkForwardArtifactHashes.fold_metrics)} · cost={hashValue(walkForwardArtifactHashes.cost_sensitivity)} · rl={hashValue(walkForwardArtifactHashes.rl_fold_metrics)} · gate={hashValue(walkForwardArtifactHashes.gate_verdict)}</strong></div>
        <div><span>upstream hashes</span><strong class="tnum">predictions={hashValue(walkForwardPredictionHashes.predictions)} · D4={hashValue(walkForwardPortfolioHashes.rl_manifest)} · state={hashValue(walkForwardPortfolioHashes.state_observations)}</strong></div>
      </div>
      <ul>
        {#each displayedD5Reasons.slice(0, 8) as reason}
          <li>{reason}</li>
        {/each}
      </ul>
    </div>

    <div class="evidence-box" data-daily-walk-forward-d4-state-contract>
      <div class="text-eyebrow">D5 consumes D4 state contract</div>
      <div class="mini-kv"><span>status</span><strong>{d5ContractStatus}</strong></div>
      <div class="mini-kv"><span>gate</span><strong>{d5ContractGate}</strong></div>
      <div class="mini-kv"><span>validation</span><strong>{d5ContractValidationStatus}</strong></div>
      <div class="mini-kv"><span>state rows</span><strong>{num(d5StateObservationRowCount)}</strong></div>
      <div class="mini-kv"><span>D4 ablations/source hashes</span><strong>{num(d5RewardActionAblationRowCount)} / {num(d5SourceHashCount)}</strong></div>
      <div class="mini-kv"><span>telemetry sufficient</span><strong>{String(walkForwardChart?.d4_reward_action_telemetry_sufficient_for_d4 ?? d5StateContract.reward_action_telemetry_sufficient_for_d4)}</strong></div>
      <ul>
        {#each d5ContractMessages.slice(0, 5) as issue}
          <li>{String(issue)}</li>
        {/each}
      </ul>
    </div>

    <div class="evidence-box" data-daily-walk-forward-controls>
      <div class="text-eyebrow">Controls · fold consistency</div>
      <div class="mini-kv"><span>price/universe</span><strong>{String(walkForwardChart?.price_basis)} · {String(walkForwardChart?.universe_review_status)}</strong></div>
      <div class="mini-kv"><span>positive folds</span><strong>{num(verdictValue(d5FoldConsistency, 'positive_folds'))}</strong></div>
      <div class="mini-kv"><span>beats no-trade/shuffle</span><strong>{num(verdictValue(d5FoldConsistency, 'folds_beating_no_trade'))} / {num(verdictValue(d5FoldConsistency, 'folds_beating_shuffle'))}</strong></div>
      <div class="mini-kv"><span>worst DD / mean turnover</span><strong>{pct(verdictValue(d5FoldConsistency, 'worst_fold_max_drawdown'))} / {num(verdictValue(d5FoldConsistency, 'mean_fold_turnover'))}</strong></div>
      <div class="mini-list">
        {#each rows(d5SelectedFoldRows, 3) as row}
          <div><span>{row.fold_id} selected</span><strong>{pct(row.total_net_return)} · vs shuffle {pct(row.delta_vs_shuffled_total_net_return)}</strong></div>
        {/each}
        {#each rows(d5NoTradeRows, 3) as row}
          <div><span>{row.fold_id} no-trade</span><strong>{pct(row.total_net_return)} · DD {pct(row.max_drawdown)}</strong></div>
        {/each}
      </div>
    </div>

    <div class="evidence-box" data-daily-walk-forward-cost-sensitivity>
      <div class="text-eyebrow">0/23/46bp sensitivity · RL folds</div>
      <div class="mini-kv"><span>bp ladder</span><strong>{(walkForwardChart?.cost_sensitivity_bp ?? []).join(' / ')}</strong></div>
      <div class="mini-list">
        {#each rows(d5CostRows, 6) as row}
          <div><span>{row.fold_id} · {num(row.cost_bp)}bp</span><strong>{pct(row.total_net_return)} · DD {pct(row.max_drawdown)}</strong></div>
        {/each}
        {#each rows(d5RlRows, 3) as row}
          <div><span>{row.fold_id} RL</span><strong>{pct(row.total_net_return)} · invalid {pct(row.invalid_action_rate)}</strong></div>
        {/each}
      </div>
    </div>

    <div class="evidence-box" data-daily-walk-forward-fold-windows>
      <div class="text-eyebrow">Forward-only fold windows</div>
      <div class="mini-list">
        {#each rows(d5FoldWindows, 5) as row}
          <div><span>{row.fold_id} test {row.test_start_date}→{row.test_end_date}</span><strong>purge {row.purge_start_date || '—'}→{row.purge_end_date || '—'} · embargo {row.embargo_start_date || '—'}→{row.embargo_end_date || '—'} · retune={String(row.retuned_on_oos)}</strong></div>
        {/each}
      </div>
    </div>
  </div>

  <div class="table-wrap" style="margin-top:16px; max-height:260px; overflow:auto">
    <table>
      <thead><tr><th>fold</th><th>strategy</th><th>control</th><th>net</th><th>vs no-trade</th><th>vs shuffled</th><th>DD</th><th>turnover</th></tr></thead>
      <tbody>
        {#each rows(walkForwardChart?.fold_metrics, 12) as row}
          <tr>
            <td>{row.fold_id}</td>
            <td>{row.strategy}</td>
            <td>{row.control}</td>
            <td class="tnum">{pct(row.total_net_return)}</td>
            <td class="tnum">{pct(row.delta_vs_no_trade_total_net_return)}</td>
            <td class="tnum">{pct(row.delta_vs_shuffled_total_net_return)}</td>
            <td class="tnum">{pct(row.max_drawdown)}</td>
            <td class="tnum">{num(row.mean_turnover)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</section>

<style>
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th, td { border-bottom:1px solid var(--border-faint); padding:7px; text-align:left; vertical-align:top; }
  .evidence-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:12px; }
  .evidence-box { border:1px solid var(--border); border-radius:var(--r-lg); padding:12px; background:var(--surface); }
  .evidence-box ul { margin:8px 0 0; padding-left:18px; color:var(--muted); font-size:12px; }
  .mini-kv, .mini-list div { display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid var(--border-faint); padding:6px 0; font-size:12px; }
  .mini-kv span, .mini-list span { color:var(--muted); }
</style>
