from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / 'webui' / 'v2_src' / 'src'


def test_daily_ohlcv_tab_and_navigation_markers_present():
    app = (SRC / 'App.svelte').read_text(encoding='utf-8')
    sidebar = (SRC / 'layout' / 'Sidebar.svelte').read_text(encoding='utf-8')
    header = (SRC / 'layout' / 'Header.svelte').read_text(encoding='utf-8')
    tab = (SRC / 'tabs' / 'DailyOhlcvTab.svelte').read_text(encoding='utf-8')
    api = (SRC / 'lib' / 'dailyOhlcvApi.ts').read_text(encoding='utf-8')
    guide = (SRC / 'tabs' / 'DailyRlGuideTab.svelte').read_text(encoding='utf-8')

    assert "DailyOhlcvTab" in app
    assert "'/daily-ohlcv'" in app
    assert "daily-ohlcv" in sidebar
    assert "Daily OHLCV" in header
    assert "data-daily-ohlcv-tab" in tab
    assert "READ_ONLY" in tab
    assert "no live/broker/orders" in tab
    assert "/api/daily-ohlcv/db-summary" in api
    assert "/api/daily-ohlcv/universe/preview" in api
    assert "/api/daily-ohlcv/symbol/" in api
    assert "/api/daily-ohlcv/dataset/latest" in api
    assert "/api/daily-ohlcv/charts/dataset" in api
    assert "/api/daily-ohlcv/prediction/latest" in api
    assert "/api/daily-ohlcv/portfolio/latest" in api
    assert "/api/daily-ohlcv/walk-forward/latest" in api
    assert "/api/daily-ohlcv/charts/walk-forward" in api
    assert "/api/daily-ohlcv/registry/latest" in api
    assert "/api/daily-ohlcv/charts/decision-cockpit" in api
    assert "/api/daily-ohlcv/scenarios" in api
    assert "/api/daily-ohlcv/scenario-runs" in api
    assert "/api/daily-ohlcv/rl-env-guide" in api
    assert "/api/daily-ohlcv/research-workflows" in api
    assert "/api/daily-ohlcv/charts/research-diagnostics" in api
    assert "/api/daily-ohlcv/charts/equity-overlay" in api
    assert "/api/daily-ohlcv/charts/walk-forward-heatmap" in api
    assert "/api/daily-ohlcv/charts/run-scatter" in api
    assert "/api/daily-ohlcv/charts/universe-breakdown" in api
    assert "/api/daily-ohlcv/charts/symbol/" in api
    assert "'/daily-rl-guide'" in app
    assert "'/daily-ohlcv/rl-guide'" in app
    assert "DailyModelResultsCard" in tab
    assert "DailyVisualLabCard" in tab
    assert "DailyScenarioLabCard" in tab
    assert "DailyScenarioRunLedgerCard" in tab
    assert "DailyRlGuideTab" in app
    assert "일봉 RL 설명서" in sidebar
    assert "일봉 RL 설명서" in header
    assert "NO-GO/RESEARCH_ONLY" in tab
    assert "data-daily-api-error" in tab
    assert "API_UNAVAILABLE" in tab
    assert "DailyDatasetBuilderCard" in tab
    assert "data-daily-symbol-panel" in tab
    assert "000250" in tab


def test_daily_ohlcv_cards_expose_guardrail_markers():
    progress = (SRC / 'tabs' / 'dailyOhlcv' / 'DailyProgressTimeline.svelte').read_text(encoding='utf-8')
    guide = (SRC / 'tabs' / 'DailyRlGuideTab.svelte').read_text(encoding='utf-8')
    api = (SRC / 'lib' / 'dailyOhlcvApi.ts').read_text(encoding='utf-8')
    db_card = (SRC / 'tabs' / 'dailyOhlcv' / 'DailyDbQualityCard.svelte').read_text(encoding='utf-8')
    universe_card = (SRC / 'tabs' / 'dailyOhlcv' / 'DailyUniverseCard.svelte').read_text(encoding='utf-8')
    dataset_card = (SRC / 'tabs' / 'dailyOhlcv' / 'DailyDatasetBuilderCard.svelte').read_text(encoding='utf-8')
    model_card = (SRC / 'tabs' / 'dailyOhlcv' / 'DailyModelResultsCard.svelte').read_text(encoding='utf-8')
    visual_card = (SRC / 'tabs' / 'dailyOhlcv' / 'DailyVisualLabCard.svelte').read_text(encoding='utf-8')
    scenario_card = (SRC / 'tabs' / 'dailyOhlcv' / 'DailyScenarioLabCard.svelte').read_text(encoding='utf-8')
    scenario_run_card = (SRC / 'tabs' / 'dailyOhlcv' / 'DailyScenarioRunLedgerCard.svelte').read_text(encoding='utf-8')
    progress_without_comments = progress.replace("<!-- Status vocabulary marker: NOT_STARTED RUNNING PASS WATCH RESEARCH_ONLY NO-GO BLOCKED -->", "")

    assert "data-daily-ohlcv-progress" in progress
    assert "NOT_STARTED" in progress_without_comments
    assert "D0-D9 Progress" in progress
    assert "data-daily-progress-empty" in progress
    assert "data-daily-d0-d9-provenance-matrix" in progress
    assert "lock_labels" in progress
    assert "verification_commands" in progress
    assert "D0-D9 provenance" in progress
    assert "command-list" in progress
    assert "slice(0, 4)" not in progress
    assert "data-daily-ohlcv-db-card" in db_card
    assert "price_basis" in db_card
    assert "price_basis_status" in db_card
    assert "decision_grade_return_status" in db_card
    assert "UNKNOWN_CONFIRMED" in db_card
    assert "material_unknown_adjustment_windows" in db_card
    assert "data-daily-price-basis-usage" in db_card
    assert "price_basis_user_guidance" in db_card
    assert "price_basis_required_evidence" in db_card
    assert "data-daily-ohlcv-universe-card" in universe_card
    assert "WATCH_HEURISTIC_UNIVERSE" in universe_card
    assert "unmatched_quarantine_count" in universe_card
    assert "official_metadata_status" in universe_card
    assert "official_metadata_coverage_status" in universe_card
    assert "universe_certification_status" in universe_card
    assert "quarantine_artifact_count" in universe_card
    assert "code,name,market,instrument_type" in universe_card
    assert "data-daily-universe-review-contract" in universe_card
    assert "data-daily-universe-user-guidance" in universe_card
    assert "model_build_or_candidate_promotion" in universe_card
    assert "data-daily-symbol-drilldown" in universe_card
    assert "data-daily-ohlcv-dataset-card" in dataset_card
    assert "leakage_status" in dataset_card
    assert "split_chronology_status" in dataset_card
    assert "no training/order/live/profit" in dataset_card
    assert "data-daily-dataset-upstream-blockers" in dataset_card
    assert "data-daily-dataset-user-guidance" in dataset_card
    assert "upstream_gate_blockers" in dataset_card
    assert "dataset_blocked_uses" in dataset_card
    assert "universe_certification_status" in dataset_card
    assert "DATASET_RESEARCH_PREVIEW_BLOCKED_BY_MISSING_READINESS_EVIDENCE" in dataset_card
    assert "DATASET_RESEARCH_READY_WITH_WATCH_GUARDRAILS" not in dataset_card
    assert "data-daily-dataset-leakage-detail" in dataset_card
    assert "data-daily-dataset-normalization-detail" in dataset_card
    assert "forbidden_feature_columns" in dataset_card
    assert "fit_split" in dataset_card
    assert "fit_row_count" in dataset_card
    assert "data-daily-dataset-manifest-detail" in dataset_card
    assert "data-daily-dataset-split-intervals" in dataset_card
    assert "data-daily-dataset-blocked-windows" in dataset_card
    assert "manifest_sha" in dataset_card
    assert "universe_manifest_sha" in dataset_card
    assert "purge_days" in dataset_card
    assert "embargo_days" in dataset_card
    assert "data-daily-model-results-card" in model_card
    assert "data-daily-prediction-chart" in model_card
    assert "data-daily-portfolio-chart" in model_card
    assert "data-daily-walk-forward-chart" in model_card
    assert "data-daily-decision-panel" in model_card
    assert "RESEARCH_ONLY" in model_card
    assert "NO-GO" in model_card
    assert "PRICE_BASIS_UNKNOWN" in model_card
    assert "UNIVERSE_WATCH_HEURISTIC" in model_card
    assert "model_build_allowed" in model_card
    assert "go_summary_allowed" in model_card
    assert "shuffle_control_strategy" in model_card
    assert "best_rule_baseline_strategy" in model_card
    assert "best_supervised_delta_vs_shuffle_control" in model_card
    assert "data-daily-d3-cost-assumption" in model_card
    assert "data-daily-d3-gate-blockers" in model_card
    assert "data-daily-d3-user-guidance" in model_card
    assert "D3_BASELINE_WATCH_RESEARCH_ONLY" in model_card
    assert "D0_PRICE_BASIS_NOT_VERIFIED" in model_card
    assert "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED" in model_card
    assert "D5_WALK_FORWARD_NOT_PASS" in model_card
    assert "D3_WATCH_RESEARCH_ONLY" in model_card
    assert "model_build_allowed" in model_card
    assert "paper_forward_allowed" in model_card
    assert "live_broker_order_allowed" in model_card
    assert "data-daily-walk-forward-readiness" in model_card
    assert "D5_NO_GO_RESEARCH_ONLY_GATE" in model_card
    assert "data-daily-walk-forward-provenance-hashes" in model_card
    assert "fold_metrics=" in model_card
    assert "predictions=" in model_card
    assert "D4=" in model_card
    assert "model_build_or_candidate_promotion" in model_card
    assert "sha256(date:code)_ascending" in model_card
    assert "data-daily-rl-readiness" in model_card
    assert "D4_RESEARCH_ONLY_DIAGNOSTICS" in model_card
    assert "joinedFlagText" in model_card
    assert "d4ModelFlag" in model_card
    assert "d4GoFlag" in model_card
    assert "d5ModelFlag" in model_card
    assert "D5_REASONS_MISSING_OR_STALE" in model_card
    assert "D4_STATE_CONTRACT_EVIDENCE_MISSING_OR_STALE" in model_card
    assert "MISSING_D4_OBSERVATION_STATE_MANIFEST_GATE" in model_card
    assert "D3-D5 Model Evidence" in model_card
    assert "data-daily-rl-provenance-hashes" in model_card
    assert "prediction_manifest_sha" in model_card
    assert "portfolioPredictionHashes.predictions" in model_card
    assert "portfolioArtifactHashes.policy_nav" in model_card
    assert "data-daily-rl-training-status" in model_card
    assert "data-daily-rl-invalid-action-rate" in model_card
    assert "invalid_action_rate" in model_card
    assert "data-daily-rl-learning-curve" in model_card
    assert "data-daily-rl-state-contract" in model_card
    assert "data-daily-rl-state-observations" in model_card
    assert "data-daily-rl-leakage-checks" in model_card
    assert "D4_OBSERVATION_STATE_MANIFEST" in model_card
    assert "reward_action_telemetry_sufficient_for_d4" in model_card
    assert "future_label_exposed" in model_card
    assert "data-daily-rl-reward-return-curve" in model_card
    assert "data-daily-rl-action-distribution" in model_card
    assert "data-daily-rl-invalid-actions" in model_card
    assert "data-daily-rl-reward-components" in model_card
    assert "data-daily-rl-turnover-drawdown" in model_card
    assert "invalid_action_penalty" in model_card
    assert "exposure_penalty" in model_card
    assert "concentration_penalty" in model_card
    assert "invalid={String(row.invalid_action)}" in model_card
    assert "data-daily-rl-policy-baseline-comparison" in model_card
    assert "data-daily-rl-portfolio-trajectory" in model_card
    assert "frozen_baseline_delta" in model_card
    assert "baseline_delta_total_net_return" in model_card
    assert "RESEARCH_ONLY diagnostics" in model_card
    assert "data-daily-walk-forward-d4-state-contract" in model_card
    assert "data-daily-walk-forward-controls" in model_card
    assert "d4_reward_action_ablation_rows" in model_card
    assert "d4_source_hash_count" in model_card
    assert "min_required_purge_days" in model_card
    assert "data-daily-walk-forward-cost-sensitivity" in model_card
    assert "data-daily-walk-forward-fold-windows" in model_card
    assert "D4_OBSERVATION_STATE_MANIFEST_CONSUMED" in model_card
    assert "walkForwardChart?.d4_state_contract_artifacts_consumed === true" in model_card
    assert "positiveNumber(d5StateObservationRowCount)" in model_card
    assert "positiveNumber(d5RewardActionAblationRowCount)" in model_card
    assert "positiveNumber(d5SourceHashCount)" in model_card
    assert "D4_STATE_CONTRACT_EVIDENCE_MISSING_OR_STALE', ...d5ArtifactIssues.map" in model_card
    assert "no_oos_retuning" in model_card
    assert "purge/embargo" in model_card
    assert "0/23/46bp sensitivity" in model_card
    assert "data-daily-scenario-lab-card" in scenario_card
    assert "SCENARIO_GENERATOR_MVP" in scenario_card
    assert "model_run_generation_available" in scenario_card
    assert "data-daily-scenario-grid" in scenario_card
    assert "data-daily-scenario-model-contract" in scenario_card
    assert "cost_23bp_current_evidence" in scenario_card
    assert "scenario_manifest.json" in scenario_card
    assert "fresh_oos_walk_forward_manifest.json" in scenario_card
    assert "no live/broker/orders" in scenario_card
    assert "data-daily-scenario-run-ledger" in scenario_run_card
    assert "SCENARIO_BATCH_RUNNER_MVP" in scenario_run_card
    assert "stom_rl.daily_scenario_batch" in scenario_run_card
    assert "scenario_batch_manifest.json" in scenario_run_card
    assert "data-daily-scenario-batch-grid" in scenario_run_card
    assert "data-daily-scenario-run-grid" in scenario_run_card
    assert "comparison_rows" in scenario_run_card
    assert "model_run_generation_available" in scenario_run_card
    assert "no live/broker/orders" in scenario_run_card
    assert "data-daily-rl-guide-tab" in guide
    assert "RL_ENV_VISUAL_GUIDE_MVP" in guide
    assert "data-daily-rl-env-visual-map" in guide
    assert "data-daily-rl-loop-diagram" in guide
    assert "data-daily-rl-process-storyboard" in guide
    assert "일봉 강화학습 환경 순환 다이어그램" in guide
    assert "Agent ↔ Environment ↔ Reward" in guide
    assert "상태 → 행동 → 보상 → 검증" in guide
    assert "data-daily-rl-performance-example" in guide
    assert "data-daily-rl-performance-pnl" in guide
    assert "data-daily-rl-learning-curve-visual" in guide
    assert "data-daily-rl-nav-preview" in guide
    assert "학습 성과 예시: 수익금" in guide
    assert "RESEARCH_ONLY_PERFORMANCE_DIAGNOSTIC" in guide
    assert "data-daily-rl-research-process-selector" in guide
    assert "data-daily-rl-process-lane-picker" in guide
    assert "data-daily-rl-selected-process-detail" in guide
    assert "data-daily-rl-research-limitations" in guide
    assert "data-daily-rl-ai-guidance-format" in guide
    assert "D4_RL_RISK_OVERLAY" in guide
    assert "AI-readable / AI 개선 지시 고정 포맷" in guide
    assert "AI Agent" in guide
    assert "data-daily-rl-scenario-generator" in guide
    assert "data-daily-rl-workflow-center" in guide
    assert "data-daily-rl-workflow-picker" in guide
    assert "data-daily-rl-workflow-inspector" in guide
    assert "data-daily-rl-workflow-safe-config-preview" in guide
    assert "APPROVAL_GATED_INTENT_RECORD_ONLY" in guide
    assert "data-daily-rl-approval-trigger-surface" in guide
    assert "data-daily-rl-intent-ledger" in guide
    assert "researchJobIntents" in api
    assert "/api/daily-ohlcv/research-jobs" in api
    assert "data-daily-rl-rejection-analytics" in guide
    assert "rejectionAnalytics" in api
    assert "/api/daily-ohlcv/rejection-analytics" in api
    assert "False-negative review queue" in guide
    assert "promotion_allowed" in guide
    assert "HYPOTHESIS_REJECTION_AUDIT" in guide
    assert "data-daily-rl-final-completion-report" in guide
    assert "NON_LIVE_RESEARCH_PLATFORM_COMPLETE" in guide
    assert "non_live_goal_completion_pct" in guide
    assert "live_trading_readiness_pct" in guide
    assert "model_build_readiness_pct" in guide
    assert "paper_forward_readiness_pct" in guide
    assert "비실거래 연구 플랫폼 완료 성과" in guide
    assert "실거래·브로커 주문·페이퍼 포워드·모델 빌드·수익성 주장은 계속 0%/blocked" in guide
    assert "data-daily-rl-scenario-plan-json" in guide
    assert "D3_D4_SIGNAL_QUALITY_AUDIT" in guide
    assert "PAST_ONLY_MARKET_REGIME_AUDIT" in guide
    assert "data-daily-rl-signal-quality-integration" in guide
    assert "MISSING_SIGNAL_QUALITY_AUDIT" in guide
    assert "data-daily-rl-scenario-comparison" in guide
    assert "data-daily-rl-market-regime-readiness" in guide
    assert "data-daily-rl-improvement-queue" in guide
    assert "data-daily-rl-page-maturity-report" in guide
    assert "scenario_platform_maturity_pct" in guide
    assert "live_trading_readiness_pct" in guide
    assert "MISSING_POLICY_ARTIFACT" in guide
    assert "data-daily-rl-realtime-visualizer" in guide
    assert "data-daily-rl-policy-network-visual" in guide
    assert "data-daily-rl-action-probability-bars" in guide
    assert "저장된 산출물로 움직이는 강화학습 리플레이" in guide
    assert "Artifact-backed RL Replay" in guide
    assert "fake" not in guide.lower()
    assert "data-daily-rl-env-elements" in guide
    assert "data-daily-rl-state-action-reward" in guide
    assert "data-daily-rl-env-checks" in guide
    assert "position_count" in guide
    assert "top_score_bucket" in guide
    assert "hold · buy · add · sell · reduce" in guide
    assert "future_return_1d" in guide
    assert "no live/broker/orders" in guide
    assert "data-daily-visual-lab-card" in visual_card
    assert "data-daily-d6-d7-usage-guide" in visual_card
    assert "data-daily-page-progress-guide" in visual_card
    assert "D6는 증거를 읽는 화면" in visual_card
    assert "D7은 실패 원인과 다음 가설" in visual_card
    assert "data-daily-decision-cockpit" in visual_card
    assert "data-daily-flow-map" in visual_card
    assert "data-daily-metric-glossary" in visual_card
    assert "data-daily-research-diagnostics" in visual_card
    assert "D7 Research Diagnostics" in visual_card
    assert "D7_FEATURE_DIAGNOSTICS" in visual_card
    assert "D7_REGIME_DIAGNOSTICS" in visual_card
    assert "D7_CORRELATION_RISK" in visual_card
    assert "D7_FAILURE_ANALYSIS" in visual_card
    assert "PLACEHOLDER_READY" in visual_card
    assert "D7_FALLBACK_DIAGNOSTICS" in visual_card
    assert "feature_importance_by_fold.csv" in visual_card
    assert "failure_reason_attribution.csv" in visual_card
    assert "allowed_use" in visual_card
    assert "blocked_use" in visual_card
    assert "how_to_read_ko" in visual_card
    assert "current_gap" in visual_card
    assert "feature별 fold 기여도와 drift" in visual_card
    assert "실패 fold를 숨기거나 성공 fold만 골라" in visual_card
    assert "correlation_cluster_summary.csv가 생성되기 전까지 PLACEHOLDER_READY" in visual_card
    assert "mergeD7DiagnosticCard" in visual_card
    assert "allowed_use: card.allowed_use || fallback.allowed_use" in visual_card
    assert "blocked_use: card.blocked_use || fallback.blocked_use" in visual_card
    assert "how_to_read_ko: card.how_to_read_ko || fallback.how_to_read_ko" in visual_card
    assert "current_gap: card.current_gap || fallback.current_gap" in visual_card
    assert "next_artifact: card.next_artifact || fallback.next_artifact" in visual_card
    assert "guardrail: card.guardrail || fallback.guardrail" in visual_card
    assert "summary: card.summary || fallback.summary" in visual_card
    assert "rows(decision?.blockers, 4)" not in visual_card
    assert "data-daily-equity-overlay" in visual_card
    assert "data-daily-walk-forward-heatmap" in visual_card
    assert "data-daily-run-scatter" in visual_card
    assert "data-daily-universe-breakdown" in visual_card
    assert "data-daily-symbol-chart" in visual_card
    assert "data-daily-symbol-usage-guide" in visual_card
    assert "symbolUsageGuideRows" in visual_card
    assert "data-daily-registry-paper-forward" in visual_card
    assert "promotion_status" in visual_card
    assert "paper_forward_allowed" in visual_card
    assert "live_broker_order_allowed" in visual_card
    assert "no_live_broker_order_readiness" in visual_card
    assert "data-daily-registry-effective-gates" in visual_card
    assert "effective_gate_blockers" in visual_card
    assert "invariant_errors" in visual_card
    assert "registryEvidenceText" in visual_card
    assert "MISSING_EFFECTIVE_GATE_EVIDENCE" in visual_card
    assert "MISSING_INVARIANT_EVIDENCE" in visual_card
    assert "registryRows" in visual_card
    assert "registryBlockScore" in visual_card
    assert "data-daily-registry-hidden-counts" in visual_card
    assert "registryFlagText" in visual_card
    assert "MISSING_REGISTRY_FLAG_UNSAFE" in visual_card
    assert "MISSING_SAMPLE_EVIDENCE" in visual_card
    assert "items.length === 0" in visual_card
    assert "drift_hidden" in visual_card
    assert "registryRows(registry?.samples?.drift" in visual_card
    assert "row.metric ?? row.evidence_status" in visual_card
    assert "registry?.model_build_allowed ?? false" not in visual_card
    assert "paper_forward_drawdown" in visual_card
    assert "research_policy_nav_not_live_account" in visual_card
    assert "INCOMPLETE_NUMERIC_EVIDENCE" in visual_card
    assert "finiteNumber" in visual_card
    assert "const asNumber" not in visual_card
    assert "config_hash" in visual_card
    assert "STOM-inspired Visual Lab" in visual_card
    assert "수익 보장·실거래·브로커·주문 준비 상태가 아닙니다" in visual_card
