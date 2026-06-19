import json
import hashlib
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from webui.app import app as flask_app  # noqa: E402


def test_daily_ohlcv_db_summary_api_is_read_only_and_bounded():
    client = flask_app.test_client()
    response = client.get('/api/daily-ohlcv/db-summary?table_limit=2&flag_limit=2&window_limit=2')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['read_only'] is True
    assert payload['query_only'] is True
    assert payload['table_count'] == 4727
    assert payload['total_rows'] == 14691020
    assert payload['prefix_counts']['A'] == 4166
    assert payload['prefix_counts']['Q'] == 561
    assert payload['price_basis'] == 'unknown'
    assert payload['price_basis_status'] == 'UNKNOWN_CONFIRMED'
    assert payload['decision_grade_return_status'] == 'BLOCKED_UNTIL_PRICE_BASIS_VERIFIED'
    assert payload['price_basis_audit']['status'] == 'UNKNOWN_CONFIRMED'
    assert set(payload['price_basis_audit']['component_status']) == {
        'adjusted_price',
        'raw_price',
        'split_adjustment',
        'dividend_adjustment',
    }
    assert payload['price_basis_audit']['blocking_implications']
    assert 'model_build_or_candidate_promotion' in payload['price_basis_blocked_uses']
    assert payload['price_basis_user_guidance'][0]['section'] == 'D0 summary'
    assert payload['quality_scan_scope'] == 'all_tables'
    assert len(payload['table_summaries']) <= 2
    assert len(payload['quality_flags']) <= 2
    assert len(payload['material_unknown_adjustment_windows']) <= 2
    assert 'no live/broker/orders' in payload['guardrail']

def test_daily_ohlcv_db_summary_stale_artifact_fails_closed(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / 'db_summary'
    run_dir = root / 'stale'
    run_dir.mkdir(parents=True)
    (run_dir / 'db_summary.json').write_text(
        json.dumps({
            'schema_version': 1,
            'table_count': 1,
            'total_rows': 1,
            'read_only': False,
            'query_only': False,
            'guardrail': 'unsafe optimistic stale artifact',
            'price_basis': 'raw',
            'price_basis_status': 'RAW_VERIFIED',
            'decision_grade_return_status': 'READY',
            'price_basis_audit': {
                'status': 'RAW_VERIFIED',
                'blocked_uses': [],
            },
        }),
        encoding='utf-8',
    )
    monkeypatch.setattr(daily_dashboard, 'DB_SUMMARY_ROOT', root)

    payload = daily_dashboard.load_daily_db_summary(run='stale', table_limit=0, flag_limit=0, window_limit=0)

    assert payload['price_basis'] == 'unknown'
    assert payload['price_basis_status'] == 'UNKNOWN_CONFIRMED'
    assert payload['decision_grade_return_status'] == 'BLOCKED_UNTIL_PRICE_BASIS_VERIFIED'
    assert payload['price_basis_audit']['status'] == 'UNKNOWN_CONFIRMED'
    assert payload['price_basis_audit']['normalized_from_artifact']['price_basis'] == 'raw'
    assert payload['price_basis_audit']['blocked_uses'] == [
        'decision_grade_return_labels',
        'model_build_or_candidate_promotion',
        'paper_forward_or_live_readiness_claims',
    ]
    assert payload['read_only'] is True
    assert payload['query_only'] is True
    assert 'no DB mutation' in payload['guardrail']
    assert 'no live/broker/orders' in payload['guardrail']
    assert 'no DB mutation' in payload['read_only_dashboard_note']
    assert payload['artifact_status'] == 'LOADED_GENERATED_ARTIFACT'


def test_daily_ohlcv_symbol_preserves_leading_zero_and_rejects_unsafe_code():
    client = flask_app.test_client()
    ok = client.get('/api/daily-ohlcv/symbol/000250?limit=1')
    assert ok.status_code == 200
    payload = ok.get_json()
    assert payload['table'] == 'A000250'
    assert payload['code'] == '000250'
    assert payload['price_basis'] == 'unknown'
    assert len(payload['sample_rows_desc']) == 1

    bad = client.get('/api/daily-ohlcv/symbol/..%2FA000250')
    assert bad.status_code == 400


def test_daily_ohlcv_universe_preview_api_exposes_watch_counts_and_required_fields():
    client = flask_app.test_client()
    response = client.get('/api/daily-ohlcv/universe/preview?limit=3')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['verdict'] == 'WATCH_HEURISTIC_UNIVERSE'
    assert payload['table_count'] == 4727
    assert payload['stockinfo_matched_table_count'] == 4229
    assert payload['stockinfo_unmatched_table_count'] == 498
    assert payload['unmatched_quarantine_count'] == 498
    assert payload['q_product_count'] == 561
    assert payload['official_metadata_status'] == 'MISSING'
    assert payload['official_metadata_coverage_status'] == 'MISSING'
    assert payload['universe_certification_status'] == 'BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW'
    assert 'model_build_or_candidate_promotion' in payload['universe_blocked_uses']
    assert payload['universe_user_guidance'][0]['section'] == 'D1 summary'
    assert 'official_metadata_required_columns' in payload
    assert 'official_metadata_unmatched_table_count' in payload
    assert len(payload['symbols']) <= 3
    assert set(payload['required_fields']) == {
        'classification_source',
        'classification_confidence',
        'exclusion_reason',
        'metadata_sha',
        'review_status',
        'official_metadata_status',
        'official_metadata_coverage_status',
        'universe_certification_status',
    }
    assert 'no live/broker/orders' in payload['guardrail']
def test_daily_ohlcv_universe_preview_no_artifact_keeps_full_counts(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    monkeypatch.setattr(daily_dashboard, "DEFAULT_UNIVERSE_ROOT", tmp_path / "empty_universe_root")
    payload = daily_dashboard.load_universe_preview(limit=0)
    assert payload["artifact_status"] == "GENERATED_ON_DEMAND_READ_ONLY"
    assert payload["table_count"] == 4727
    assert payload["stockinfo_unmatched_table_count"] == 498
    assert payload["official_metadata_status"] == "MISSING"
    assert payload["official_metadata_coverage_status"] == "MISSING"
    assert payload["universe_certification_status"] == "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW"
    assert payload["symbols_total"] == 4727
    assert payload["symbols"] == []
def test_daily_ohlcv_universe_preview_stale_artifact_fails_closed(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / "universe"
    run_dir = root / "optimistic"
    run_dir.mkdir(parents=True)
    (run_dir / "universe.json").write_text(
        json.dumps({
            "verdict": "OFFICIAL_OR_MANUAL_REVIEWED",
            "review_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "universe_review_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "official_metadata_status": "OFFICIAL_VERIFIED",
            "official_metadata_coverage_status": "COMPLETE",
            "universe_certification_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "official_metadata_path": str(tmp_path / "missing_krx.csv"),
            "table_count": 7,
            "symbols": [],
            "exclusions": [],
            "required_fields": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(daily_dashboard, "DEFAULT_UNIVERSE_ROOT", root)

    payload = daily_dashboard.load_universe_preview(run="optimistic", limit=0)

    assert payload["verdict"] == "WATCH_HEURISTIC_UNIVERSE"
    assert payload["review_status"] == "WATCH_REQUIRES_OFFICIAL_OR_MANUAL_REVIEW"
    assert payload["official_metadata_status"] == "MISSING"
    assert payload["official_metadata_coverage_status"] == "MISSING"
    assert payload["universe_certification_status"] == "BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW"
    assert payload["official_metadata_matched_table_count"] == 0
    assert payload["official_metadata_unmatched_table_count"] == 7
    assert "model_build_or_candidate_promotion" in payload["universe_blocked_uses"]





def test_daily_ohlcv_artifacts_api_is_bounded():
    client = flask_app.test_client()
    response = client.get('/api/daily-ohlcv/artifacts?limit=1')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['read_only'] is True
    assert payload['limit'] == 1
    assert len(payload['artifacts']) <= 1
    assert 'artifacts_total' in payload
    assert 'artifacts_truncated' in payload

def test_daily_ohlcv_dataset_api_exposes_d2_guardrails_and_samples():
    client = flask_app.test_client()
    latest = client.get('/api/daily-ohlcv/dataset/latest?limit=2')
    assert latest.status_code == 200
    payload = latest.get_json()
    assert payload['status'] == 'PASS'
    assert payload['artifact_scope'] == 'BOUNDED_PREVIEW'
    assert payload['price_basis'] == 'unknown'
    assert payload['universe_verdict'] == 'WATCH_HEURISTIC_UNIVERSE'
    assert payload['price_basis_status'] == 'UNKNOWN_CONFIRMED'
    assert payload['decision_grade_return_status'] == 'BLOCKED_UNTIL_PRICE_BASIS_VERIFIED'
    assert payload['official_metadata_status'] == 'MISSING'
    assert payload['official_metadata_coverage_status'] == 'MISSING'
    assert payload['universe_certification_status'] == 'BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW'
    assert payload['upstream_gate_blockers'] == [
        'D0_PRICE_BASIS_NOT_VERIFIED',
        'D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED',
    ]
    assert payload['model_readiness'] == 'DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS'
    assert 'model_build_or_candidate_promotion' in payload['dataset_blocked_uses']
    assert payload['dataset_user_guidance'][0]['section'] == 'D2 summary'
    assert payload['leakage_status'] == 'PASS'
    assert payload['split_chronology_status'] == 'PASS'
    assert payload['row_counts']['feature_rows'] == 80000
    assert len(payload['samples']['split_assignments']) <= 2
    assert 'no training/order/live/profit' in payload['read_only_dashboard_note']

    chart = client.get('/api/daily-ohlcv/charts/dataset').get_json()
    assert chart['status'] == 'PASS'
    assert chart['split_chronology_status'] == 'PASS'
    assert chart['upstream_gate_blockers'] == [
        'D0_PRICE_BASIS_NOT_VERIFIED',
        'D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED',
    ]
    assert chart['model_readiness'] == 'DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS'
    assert 'not a profit' in chart['guardrail']

    artifacts = client.get('/api/daily-ohlcv/dataset/artifacts?limit=1').get_json()
    assert artifacts['runs'][0]['kind'] == 'daily_ohlcv_dataset'

def test_daily_ohlcv_dataset_stale_artifact_fails_closed(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / "dataset"
    run_dir = root / "stale_optimistic"
    run_dir.mkdir(parents=True)
    (run_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "stale_optimistic",
                "artifact_scope": "BOUNDED_PREVIEW",
                "price_basis": "raw",
                "price_basis_status": "RAW_VERIFIED",
                "decision_grade_return_status": "READY",
                "universe_verdict": "OFFICIAL_OR_MANUAL_REVIEWED",
                "universe_review_status": "OFFICIAL_OR_MANUAL_REVIEWED",
                "official_metadata_status": "OFFICIAL_VERIFIED",
                "official_metadata_coverage_status": "COMPLETE",
                "universe_certification_status": "OFFICIAL_OR_MANUAL_REVIEWED",
                "upstream_gate_blockers": [],
                "dataset_blocked_uses": [],
                "model_readiness": "DATASET_RESEARCH_READY_FOR_BASELINE_ONLY",
                "decision_grade_status": "PASS",
                "leakage_status": "PASS",
                "split_chronology_status": "PASS",
                "row_counts": {"feature_rows": 3, "eligible_rows": 3},
                "split_summary": {"row_counts": {"train": 1, "val": 1, "test": 1}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(daily_dashboard, "DEFAULT_DATASET_ROOT", root)

    latest = daily_dashboard.load_dataset_latest(run="stale_optimistic", sample_limit=0)
    assert latest["upstream_gate_blockers"] == [
        "D0_PRICE_BASIS_NOT_VERIFIED",
        "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED",
    ]
    assert latest["model_readiness"] == "DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS"
    assert latest["decision_grade_status"] == "BLOCKED_BY_UPSTREAM_D0_D1_GUARDRAILS"
    assert latest["price_basis"] == "unknown"
    assert latest["universe_verdict"] == "WATCH_HEURISTIC_UNIVERSE"
    assert {
        "decision_grade_return_labels",
        "model_build_or_candidate_promotion",
        "paper_forward_or_live_readiness_claims",
    } <= set(latest["dataset_blocked_uses"])
    assert latest["dataset_user_guidance"][0]["section"] == "D2 summary"

    chart = daily_dashboard.load_dataset_chart(run="stale_optimistic")
    assert chart["upstream_gate_blockers"] == [
        "D0_PRICE_BASIS_NOT_VERIFIED",
        "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED",
    ]
    assert chart["model_readiness"] == "DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS"

    artifacts = daily_dashboard.list_dataset_artifacts(limit=1)
    row = artifacts["runs"][0]
    assert row["model_readiness"] == "DATASET_RESEARCH_PREVIEW_BLOCKED_BY_UPSTREAM_GUARDRAILS"
    assert row["upstream_gate_blockers"] == [
        "D0_PRICE_BASIS_NOT_VERIFIED",
        "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED",
    ]
    assert "model_build_or_candidate_promotion" in row["dataset_blocked_uses"]

def test_daily_ohlcv_scenario_lab_generates_research_only_assumptions():
    client = flask_app.test_client()

    response = client.get('/api/daily-ohlcv/scenarios')
    assert response.status_code == 200
    payload = response.get_json()

    assert payload['mode'] == 'daily_ohlcv_scenario_lab'
    assert payload['platform_stage'] == 'SCENARIO_GENERATOR_MVP'
    assert payload['read_only'] is True
    assert payload['scenario_generation_available'] is True
    assert payload['model_run_generation_available'] is False
    assert payload['status'] == 'RESEARCH_ONLY'
    assert payload['assumption_dimensions']['cost_bps'] == [0, 23, 46]
    assert payload['assumption_dimensions']['purge_days_min'] == 5
    assert payload['assumption_dimensions']['embargo_days_min'] == 5
    assert payload['current_evidence']['d5_status'] == 'NO-GO'
    assert 'D5_WALK_FORWARD_NOT_PASS' in payload['current_evidence']['effective_gate_blockers']
    assert payload['model_input_contract']['required_outputs'] == [
        'scenario_manifest.json',
        'candidate_generation_config.json',
        'fresh_oos_walk_forward_manifest.json',
        'gate_verdict.json',
    ]
    rows = payload['scenario_rows']
    assert payload['scenario_count'] == len(rows) >= 7
    by_id = {row['scenario_id']: row for row in rows}
    assert by_id['cost_23bp_current_evidence']['cost_bps'] == 23
    assert by_id['cost_23bp_current_evidence']['status'] == 'NO-GO'
    assert by_id['cost_23bp_current_evidence']['model_build_allowed'] is False
    assert by_id['cost_23bp_data_repaired_hypothesis']['status'] == 'HYPOTHESIS_ONLY'
    assert 'D0_PRICE_BASIS_NOT_VERIFIED' not in by_id['cost_23bp_data_repaired_hypothesis']['blocking_reasons']
    assert by_id['model_generated_candidate_contract']['readiness_status'] == 'MODEL_SCENARIO_GENERATION_CONTRACT_ONLY'
    assert 'MODEL_CANDIDATE_NOT_GENERATED' in by_id['model_generated_candidate_contract']['blocking_reasons']
    assert all(row['paper_forward_allowed'] is False for row in rows)
    assert all(row['live_broker_order_allowed'] is False for row in rows)
    assert 'not a profit/live/broker/order' in payload['guardrail']


def test_daily_ohlcv_scenario_run_ledger_api_lists_research_only_batches(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    scenario_root = tmp_path / "scenarios"
    batch_root = tmp_path / "batches"
    scenario_dir = scenario_root / "batch_unit__seed7"
    batch_dir = batch_root / "batch_unit"
    scenario_dir.mkdir(parents=True)
    batch_dir.mkdir(parents=True)
    (scenario_dir / "scenario_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "batch_unit__seed7",
                "generated_at": "2026-06-15T00:00:00Z",
                "status": "NO-GO",
                "readiness_status": "D5_NO_GO_RESEARCH_ONLY_GATE",
                "guardrail": "Research-only scenario/model experiment; no profit guarantee, no live/broker/orders.",
                "config": {"n_folds": 5, "purge_days": 5, "embargo_days": 5},
                "artifact_paths": {"scenario_manifest": "scenario_manifest.json"},
                "gate_verdict_summary": {
                    "selected_strategy": "equal_weight_topk_momentum",
                    "n_folds": 5,
                    "purge_days": 5,
                    "embargo_days": 5,
                    "cost_sensitivity_bp": [0, 23, 46],
                    "reasons": ["RESEARCH_ONLY_NO_PROFIT_LIVE_BROKER_ORDER_CLAIM"],
                },
            }
        ),
        encoding="utf-8",
    )
    (batch_dir / "scenario_batch_manifest.json").write_text(
        json.dumps(
            {
                "batch_id": "batch_unit",
                "generated_at": "2026-06-15T00:01:00Z",
                "mode": "daily_ohlcv_model_scenario_batch",
                "platform_stage": "SCENARIO_BATCH_RUNNER_MVP",
                "status": "COMPLETED_RESEARCH_ONLY",
                "scenario_count": 1,
                "completed_count": 1,
                "failed_count": 0,
                "gate_status_counts": {"NO-GO": 1},
                "artifact_paths": {"scenario_batch_manifest": "scenario_batch_manifest.json"},
                "comparison_rows": [
                    {
                        "scenario_id": "seed7",
                        "run_id": "batch_unit__seed7",
                        "status": "NO-GO",
                        "cost_sensitivity_bp": [0, 23, 46],
                        "model_build_allowed": False,
                        "paper_forward_allowed": False,
                        "live_broker_order_allowed": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(daily_dashboard, "DEFAULT_SCENARIO_ROOT", scenario_root)
    monkeypatch.setattr(daily_dashboard, "DEFAULT_SCENARIO_BATCH_ROOT", batch_root)

    response = flask_app.test_client().get("/api/daily-ohlcv/scenario-runs?limit=5")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["mode"] == "daily_ohlcv_scenario_run_ledger"
    assert payload["platform_stage"] == "SCENARIO_BATCH_RUNNER_MVP"
    assert payload["read_only"] is True
    assert payload["dashboard_mutation_available"] is False
    assert payload["cli_model_run_generation_available"] is True
    assert payload["scenario_run_count"] == 1
    assert payload["batch_count"] == 1
    assert payload["runs"][0]["run_id"] == "batch_unit__seed7"
    assert payload["runs"][0]["cost_sensitivity_bp"] == [0, 23, 46]
    assert payload["runs"][0]["model_build_allowed"] is False
    assert payload["batches"][0]["batch_id"] == "batch_unit"
    assert payload["batches"][0]["gate_status_counts"] == {"NO-GO": 1}
    assert payload["batches"][0]["comparison_rows"][0]["paper_forward_allowed"] is False
    assert "stom_rl.daily_scenario_batch" in payload["quick_start_commands"][0]
    assert "no profit/live/broker/order" in payload["guardrail"]


def test_daily_ohlcv_rl_env_guide_explains_research_only_environment():
    response = flask_app.test_client().get("/api/daily-ohlcv/rl-env-guide")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["mode"] == "daily_ohlcv_rl_environment_guide"
    assert payload["platform_stage"] == "RL_ENV_VISUAL_GUIDE_MVP"
    assert payload["read_only"] is True
    assert payload["schema_version"] == "daily_rl_env_guide.v2"
    assert payload["source_run_id"]
    assert payload["policy_type"] == "tabular_q"
    assert payload["model_build_allowed"] is False
    assert payload["paper_forward_allowed"] is False
    assert payload["live_broker_order_allowed"] is False
    assert "BLOCKED_MODEL_BUILD_LOCKED" in payload["blockers"]
    assert payload["environment_built"] is True
    assert payload["maturity"] == "RESEARCH_ONLY_ENV_BUILT_NOT_PROFIT_READY"
    assert payload["state_contract"]["fields"] == ["position_count", "top_score_bucket"]
    assert payload["action_space"] == {"0": "hold", "1": "buy", "2": "add", "3": "sell", "4": "reduce"}
    assert "future_return_1d" in payload["what_rl_means_here"]["reward"]
    assert payload["cost_round_trip_bp"] == 23
    assert payload["observation_manifest_validation"]["status"] == "PASS"
    assert payload["current_artifact_evidence"]["d4_observation_manifest_validation_status"] == "PASS"
    performance = payload["learning_performance"]
    assert performance["status"] == "RESEARCH_ONLY_PERFORMANCE_DIAGNOSTIC"
    assert performance["display_capital_krw"] == 10_000_000
    assert performance["policy"]["label"] == "D4 RL 정책"
    assert "total_return_pct" in performance["policy"]
    assert "simulated_profit_krw" in performance["policy"]
    assert performance["best_d3_baseline"]["split"] == "best_d3_baseline"
    assert performance["delta_vs_best_d3"]["label"] == "D4 RL - best D3 baseline"
    assert "수익금" in {item["metric"] for item in performance["metric_definitions"]}
    assert "no profit guarantee" in performance["guardrail"]
    replay = payload["active_replay"]
    assert replay["schema_version"] == "daily_rl_active_replay.v1"
    assert replay["policy_type"] == "tabular_q"
    assert replay["policy_network_available"] is False
    assert replay["policy_network_status"] == "MISSING_POLICY_ARTIFACT"
    assert replay["frames"][0]["status"] == "LOADED_GENERATED_ARTIFACT"
    assert replay["frames"][0]["state"]["future_label_exposed"] == "False"
    assert "fake neural/probability fallback" in replay["guardrail"]
    catalog = payload["research_process_catalog"]
    assert catalog["schema_version"] == "daily_rl_research_process_catalog.v1"
    lane_ids = {lane["id"] for lane in catalog["lanes"]}
    assert {"D3_BASELINE_FREEZE", "D4_RL_RISK_OVERLAY", "REWARD_ABLATION_LAB", "REGIME_DIAGNOSTICS", "SCENARIO_AUTOMATION"} <= lane_ids
    d4_lane = next(lane for lane in catalog["lanes"] if lane["id"] == "D4_RL_RISK_OVERLAY")
    assert "tabular Q" in d4_lane["current_limitations"][0]
    assert d4_lane["ai_guidance_format"]["baseline"] == catalog["headline"]["best_d3_strategy"]
    assert "D5_NO_GO" in d4_lane["ai_guidance_format"]["stop_conditions"]
    generator = payload["scenario_generator"]
    assert generator["schema_version"] == "daily_rl_scenario_generator.v1"
    assert generator["read_only"] is True
    assert generator["execution_allowed"] is False
    template_ids = {template["template_id"] for template in generator["templates"]}
    assert {"D3_D4_SIGNAL_QUALITY_AUDIT", "PAST_ONLY_MARKET_REGIME_AUDIT", "D4_RL_OVERLAY_ABLATION"} <= template_ids
    signal_template = next(template for template in generator["templates"] if template["template_id"] == "D3_D4_SIGNAL_QUALITY_AUDIT")
    assert signal_template["plan_json_draft"]["draft_only"] is True
    assert signal_template["plan_json_draft"]["default_cost_bp"] == 23
    assert "no_live_broker_orders" in signal_template["plan_json_draft"]["guardrails"]
    workflow_catalog = payload["research_workflow_catalog"]
    assert workflow_catalog["schema_version"] == "daily_ohlcv_research_workflow_catalog.v1"
    assert workflow_catalog["read_only"] is True
    assert workflow_catalog["execution_allowed_from_browser"] is False
    assert workflow_catalog["job_intent_mode"] == "APPROVAL_GATED_INTENT_RECORD_ONLY"
    assert workflow_catalog["workflow_count"] == 6
    workflow_ids = {workflow["workflow_id"] for workflow in workflow_catalog["workflows"]}
    assert {"PAST_ONLY_MARKET_REGIME_AUDIT", "HYPOTHESIS_REJECTION_AUDIT", "D4_RL_OVERLAY_ABLATION"} <= workflow_ids
    rejection_workflow = next(workflow for workflow in workflow_catalog["workflows"] if workflow["workflow_id"] == "HYPOTHESIS_REJECTION_AUDIT")
    assert rejection_workflow["execution_allowed_from_browser"] is False
    assert "false_negative_candidates.csv" in rejection_workflow["artifact_dependencies"]
    assert "command" in workflow_catalog["forbidden_fields"]
    assert "paper_forward" in workflow_catalog["forbidden_fields"]
    intent_ledger = payload["research_job_intent_ledger"]
    assert intent_ledger["schema_version"] == "daily_ohlcv_research_job_intent_ledger.v1"
    assert intent_ledger["execution_allowed_from_browser"] is False
    assert intent_ledger["model_build_allowed"] is False
    rejection_analytics = payload["rejection_analytics"]
    assert rejection_analytics["schema_version"] == "daily_ohlcv_rejection_analytics.v1"
    assert rejection_analytics["status"] == "COMPLETED_RESEARCH_ONLY"
    assert rejection_analytics["promotion_allowed"] is False
    assert rejection_analytics["summary"]["false_negative_candidate_count"] >= 1
    assert rejection_analytics["false_negative_candidates"][0]["review_status"] == "REVIEW_ONLY"
    assert rejection_analytics["false_negative_candidates"][0]["promotion_allowed"] is False
    assert "no_no_go_reversal" in rejection_analytics["audit_manifest"]["guardrails"]
    completion_report = payload["dashboard_first_completion_report"]
    assert completion_report["schema_version"] == "daily_ohlcv_dashboard_first_completion_report.v1"
    assert completion_report["status"] == "NON_LIVE_RESEARCH_PLATFORM_COMPLETE"
    assert completion_report["non_live_goal_completion_pct"] == 100
    assert completion_report["live_trading_readiness_pct"] == 0
    assert completion_report["model_build_readiness_pct"] == 0
    assert completion_report["paper_forward_readiness_pct"] == 0
    assert completion_report["execution_allowed_from_browser"] is False
    assert completion_report["model_build_allowed"] is False
    assert completion_report["paper_forward_allowed"] is False
    assert completion_report["live_broker_order_allowed"] is False
    completion_surfaces = {surface["id"] for surface in completion_report["completed_surfaces"]}
    assert {"workflow_center", "workflow_inspector", "intent_ledger", "rejection_analytics", "docs_governance"} <= completion_surfaces


    signal_summary = payload["signal_quality_audit_summary"]
    assert signal_summary["schema_version"] == "daily_rl_signal_quality_summary.v1"
    assert signal_summary["run_id"] == "signal_quality_audit_2026_06_18_001"
    assert signal_summary["promotion_status"] == "NO-GO_RESEARCH_ONLY"
    assert signal_summary["row_counts"]["risk_proxy_metrics"] == 219
    assert signal_summary["batch_manifest"]["gate_status_counts"] == {"WATCH": 5}
    assert signal_summary["batch_manifest"]["failed_count"] == 0
    assert "future_return_1d is evaluation_label_only" in signal_summary["no_future_label_policy"]

    regime_readiness = payload["market_regime_audit_readiness"]
    assert regime_readiness["schema_version"] == "daily_rl_market_regime_readiness.v1"
    assert regime_readiness["maturity_score_pct"] == 72
    assert "D0_PRICE_BASIS" in regime_readiness["blocked_gates"]
    assert regime_readiness["ai_guidance_format"]["next_research_lane"] == "past_only_market_regime_data_quality_audit"

    improvement_queue = payload["improvement_queue"]
    assert improvement_queue["schema_version"] == "daily_rl_ai_improvement_queue.v1"
    assert len(improvement_queue["items"]) == 5
    assert improvement_queue["items"][0]["blocker_status"] == "BLOCKED_D0_D1_DATA_GOVERNANCE"
    assert "profit_claim" in improvement_queue["ai_guidance_format"]["blocked_actions"]

    comparison = payload["scenario_comparison"]
    assert comparison["schema_version"] == "daily_rl_scenario_comparison.v1"
    assert comparison["scenario_count"] == 5
    assert comparison["completed_count"] == 5
    assert comparison["failed_count"] == 0
    assert len(comparison["cards"]) >= 5

    maturity = payload["page_maturity_report"]
    assert maturity["schema_version"] == "daily_rl_page_maturity_report.v1"
    assert maturity["implementation_completion_pct"] == 100
    assert maturity["page_maturity_pct"] == 88
    assert maturity["scenario_platform_maturity_pct"] == 86
    assert maturity["live_trading_readiness_pct"] == 0
    assert len(maturity["priority_completion"]) == 5
    assert replay["frames"][0]["join_key"]["date"] == replay["frames"][0]["date"]
    checks = {row["check"]: row for row in payload["well_built_checks"]}
    assert checks["state_has_no_future_label"]["status"] == "PASS"
    assert checks["action_mask_available"]["status"] == "PASS"
    assert checks["d5_consumes_d4_state_contract"]["status"] in {"PASS", "WATCH"}
    assert "수익성 주장" in payload["not_good_enough_for"]
    assert "no profit guarantee" in payload["guardrail"]
    assert "no live/broker/orders" in payload["guardrail"]



def test_daily_ohlcv_research_workflow_catalog_and_detail_are_read_only():
    client = flask_app.test_client()

    catalog_response = client.get("/api/daily-ohlcv/research-workflows")
    assert catalog_response.status_code == 200
    catalog = catalog_response.get_json()
    assert catalog["schema_version"] == "daily_ohlcv_research_workflow_catalog.v1"
    assert catalog["read_only"] is True
    assert catalog["execution_allowed_from_browser"] is False
    assert catalog["job_intent_mode"] == "APPROVAL_GATED_INTENT_RECORD_ONLY"
    assert catalog["workflow_count"] == 6
    assert "command" in catalog["forbidden_fields"]
    assert "broker" in catalog["forbidden_fields"]
    assert "paper_forward" in catalog["forbidden_fields"]
    assert "HYPOTHESIS_REJECTION_AUDIT" in catalog["allowed_workflow_ids"]

    detail_response = client.get("/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT")
    assert detail_response.status_code == 200
    detail = detail_response.get_json()
    assert detail["schema_version"] == "daily_ohlcv_research_workflow_detail.v1"
    assert detail["read_only"] is True
    assert detail["execution_allowed_from_browser"] is False
    assert detail["workflow"]["live_broker_order_allowed"] is False
    assert detail["config_preview_contract"]["status"] == "INTENT_CREATION_AVAILABLE_G003"
    assert "false_negative_candidates.csv" in detail["workflow"]["artifact_dependencies"]

    unknown = client.get("/api/daily-ohlcv/research-workflows/UNKNOWN_WORKFLOW")
    assert unknown.status_code == 404
    assert unknown.get_json()["status"] == "UNKNOWN_WORKFLOW_ID"


def test_daily_ohlcv_research_job_intents_are_approval_gated_and_idempotent(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    intent_root = tmp_path / "research_intents"
    monkeypatch.setattr(daily_dashboard, "DEFAULT_RESEARCH_INTENT_ROOT", intent_root)
    approval_ref = ".gjc/plans/ralplan/2026-06-11-0158-38ea/pending-approval.md"
    approval_path = REPO_ROOT / approval_ref
    approval_sha = hashlib.sha256(approval_path.read_bytes()).hexdigest()
    client = flask_app.test_client()

    def payload(**overrides):
        base = {
            "workflow_id": "HYPOTHESIS_REJECTION_AUDIT",
            "approval_ref": approval_ref,
            "approval_ref_sha256": approval_sha,
            "approval_status": "APPROVED_FOR_RESEARCH_INTENT",
            "idempotency_key": "unit-intent-001",
            "requested_by": "pytest-local-dashboard",
            "config": {
                "workflow_id": "HYPOTHESIS_REJECTION_AUDIT",
                "hypothesis_id": "reject-audit-unit",
                "default_cost_bp": 23,
                "cost_sensitivity_bp": [0, 23, 46],
                "controls": ["no_trade", "shuffle_control", "frozen_d3_baseline"],
                "artifact_dependencies": ["gate_funnel_metrics.csv", "audit_manifest.json"],
            },
        }
        base.update(overrides)
        return base

    created = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json=payload(),
    )
    assert created.status_code == 201
    intent = created.get_json()
    assert intent["schema_version"] == "daily_ohlcv_research_job_intent.v1"
    assert intent["status"] == "INTENT_RECORDED"
    assert intent["idempotency_result"] == "created"
    assert intent["model_build_allowed"] is False
    assert intent["paper_forward_allowed"] is False
    assert intent["live_broker_order_allowed"] is False
    assert intent["authz_decision"] == "ALLOW_RESEARCH_INTENT_RECORD_ONLY"
    assert "no_arbitrary_shell" in intent["guardrails"]
    assert (intent_root / intent["intent_id"] / "intent.json").is_file()
    assert sorted(path.name for path in (intent_root / intent["intent_id"]).iterdir()) == ["intent.json"]

    duplicate = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json=payload(),
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["idempotency_result"] == "existing_intent_returned"

    conflict_payload = payload(config={**payload()["config"], "reviewer_notes": "different plan"})
    conflict = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json=conflict_payload,
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["status"] == "IDEMPOTENCY_CONFLICT"

    ledger = client.get("/api/daily-ohlcv/research-jobs?limit=5")
    assert ledger.status_code == 200
    ledger_payload = ledger.get_json()
    assert ledger_payload["schema_version"] == "daily_ohlcv_research_job_intent_ledger.v1"
    assert ledger_payload["count"] == 1
    assert ledger_payload["execution_allowed_from_browser"] is False
    assert ledger_payload["intents"][0]["intent_id"] == intent["intent_id"]

    detail = client.get(f"/api/daily-ohlcv/research-jobs/{intent['intent_id']}")
    assert detail.status_code == 200
    assert detail.get_json()["status"] == "INTENT_RECORDED"


def test_daily_ohlcv_research_job_intents_fail_closed_for_unsafe_payloads(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    monkeypatch.setattr(daily_dashboard, "DEFAULT_RESEARCH_INTENT_ROOT", tmp_path / "research_intents")
    approval_ref = ".gjc/plans/ralplan/2026-06-11-0158-38ea/pending-approval.md"
    approval_path = REPO_ROOT / approval_ref
    approval_sha = hashlib.sha256(approval_path.read_bytes()).hexdigest()
    client = flask_app.test_client()

    base_payload = {
        "workflow_id": "HYPOTHESIS_REJECTION_AUDIT",
        "approval_ref": approval_ref,
        "approval_ref_sha256": approval_sha,
        "approval_status": "APPROVED_FOR_RESEARCH_INTENT",
        "idempotency_key": "unsafe-unit",
        "config": {
            "workflow_id": "HYPOTHESIS_REJECTION_AUDIT",
            "default_cost_bp": 23,
            "cost_sensitivity_bp": [0, 23, 46],
        },
    }

    forbidden = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json={**base_payload, "command": "python train.py"},
    )
    assert forbidden.status_code == 400
    assert "FORBIDDEN_FIELDS:command" in forbidden.get_json()["errors"]

    forbidden_variants = {
        "shell": {"shell": "py -3.11 -m pytest"},
        "argv": {"argv": ["py", "-3.11"]},
        "env": {"env": {"TOKEN": "x"}},
        "cwd": {"cwd": "webui"},
        "broker": {"broker": {"name": "demo"}},
        "order": {"order": {"code": "000250", "side": "buy"}},
        "live": {"live": True},
        "paper_forward": {"paper_forward": {"unlock": True}},
        "model_build": {"model_build": {"unlock": True}},
        "model_build_allowed": {"model_build_allowed": True},
        "paper_forward_allowed": {"paper_forward_allowed": True},
        "live_broker_order_allowed": {"live_broker_order_allowed": True},
    }
    for key, extra in forbidden_variants.items():
        response = client.post(
            "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
            json={**base_payload, **extra, "idempotency_key": f"unsafe-unit-{key}"},
        )
        assert response.status_code == 400
        assert any(key in error for error in response.get_json()["errors"])

    pending_status = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json={**base_payload, "approval_status": "PENDING_APPROVAL_ACCEPTED", "idempotency_key": "unsafe-pending"},
    )
    assert pending_status.status_code == 400
    assert "APPROVAL_STATUS_NOT_APPROVED" in pending_status.get_json()["errors"]
    stale = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json={**base_payload, "approval_ref_sha256": "0" * 64},
    )
    assert stale.status_code == 400
    assert "APPROVAL_REF_SHA_MISMATCH" in stale.get_json()["errors"]

    traversal = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json={**base_payload, "approval_ref": "../secrets.md"},
    )
    assert traversal.status_code == 400
    assert any(error.startswith("UNSAFE_PATH") for error in traversal.get_json()["errors"])

    unknown = client.post(
        "/api/daily-ohlcv/research-workflows/UNKNOWN_WORKFLOW/job-intents",
        json={**base_payload, "workflow_id": "UNKNOWN_WORKFLOW", "config": {"workflow_id": "UNKNOWN_WORKFLOW"}},
    )
    assert unknown.status_code == 400
    assert "UNKNOWN_WORKFLOW_ID" in unknown.get_json()["errors"]

    artifact_traversal = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json={**base_payload, "config": {**base_payload["config"], "artifact_dependencies": ["../escape.csv"]}},
    )
    assert artifact_traversal.status_code == 400
    assert any(error.startswith("UNSAFE_ARTIFACT_DEPENDENCY") for error in artifact_traversal.get_json()["errors"])


def test_daily_ohlcv_research_job_intents_conflict_when_approval_hash_changes(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    intent_root = tmp_path / "research_intents"
    approval_path = tmp_path / "approval.md"
    approval_path.write_text("approved revision one", encoding="utf-8")
    monkeypatch.setattr(daily_dashboard, "DEFAULT_RESEARCH_INTENT_ROOT", intent_root)
    monkeypatch.setattr(daily_dashboard, "_safe_relative_repo_path", lambda value: approval_path)
    monkeypatch.setattr(daily_dashboard, "_approval_path_allowed", lambda path: True)
    client = flask_app.test_client()

    first_sha = hashlib.sha256(approval_path.read_bytes()).hexdigest()
    base_payload = {
        "workflow_id": "HYPOTHESIS_REJECTION_AUDIT",
        "approval_ref": "approval.md",
        "approval_ref_sha256": first_sha,
        "approval_status": "APPROVED_FOR_RESEARCH_INTENT",
        "idempotency_key": "approval-hash-conflict",
        "config": {
            "workflow_id": "HYPOTHESIS_REJECTION_AUDIT",
            "default_cost_bp": 23,
            "cost_sensitivity_bp": [0, 23, 46],
        },
    }

    first = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json=base_payload,
    )
    assert first.status_code == 201

    approval_path.write_text("approved revision two", encoding="utf-8")
    second_sha = hashlib.sha256(approval_path.read_bytes()).hexdigest()
    second = client.post(
        "/api/daily-ohlcv/research-workflows/HYPOTHESIS_REJECTION_AUDIT/job-intents",
        json={**base_payload, "approval_ref_sha256": second_sha},
    )
    assert second.status_code == 409
    assert second.get_json()["status"] == "IDEMPOTENCY_CONFLICT"


def test_daily_ohlcv_rejection_analytics_api_is_research_only():
    client = flask_app.test_client()

    response = client.get("/api/daily-ohlcv/rejection-analytics?limit=10")
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["schema_version"] == "daily_ohlcv_rejection_analytics.v1"
    assert payload["status"] == "COMPLETED_RESEARCH_ONLY"
    assert payload["run_id"] == "hypothesis_rejection_audit_2026_06_18_001"
    assert payload["read_only"] is True
    assert payload["promotion_allowed"] is False
    assert payload["model_build_allowed"] is False
    assert payload["paper_forward_allowed"] is False
    assert payload["live_broker_order_allowed"] is False
    assert payload["row_counts"] == {
        "gate_funnel_metrics": 3,
        "rejection_reason_taxonomy": 3,
        "calibration_metrics": 3,
        "threshold_sensitivity": 4,
        "false_negative_candidates": 1,
    }
    assert payload["summary"]["rejected_total"] == 5
    assert payload["summary"]["early_dropout_total"] == 3
    assert payload["denominator_policy"].startswith("denominator_count is preregistered")
    assert "decision_time_utc" in payload["timing_policy"]
    assert "separately timestamped follow-up review evidence manifest" in payload["independent_evidence_policy"]
    assert len(payload["artifact_hashes"]["gate_funnel_metrics.csv"]) == 64
    assert payload["false_negative_candidates"][0]["review_status"] == "REVIEW_ONLY"
    assert payload["false_negative_candidates"][0]["promotion_allowed"] is False
    assert payload["false_negative_candidates"][0]["requires_new_preregistration"] is True
    assert "cannot reverse NO-GO" in payload["guardrail"]
    assert len(payload["false_negative_candidates"][0]["later_independent_evidence_sha256"]) == 64
    limited = client.get("/api/daily-ohlcv/rejection-analytics?limit=1").get_json()
    assert limited["status"] == "COMPLETED_RESEARCH_ONLY"
    assert limited["row_counts"]["gate_funnel_metrics"] == 3
    assert len(limited["gate_funnel_metrics"]) == 1

    invalid = client.get("/api/daily-ohlcv/rejection-analytics?run=../escape")
    assert invalid.status_code == 200
    assert invalid.get_json()["status"] == "INVALID_RUN_ID"


def test_daily_ohlcv_rejection_analytics_invalid_artifacts_fail_closed(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / "rejection_audit"
    run_dir = root / "optimistic"
    run_dir.mkdir(parents=True)
    (run_dir / "audit_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "daily_ohlcv_rejection_audit_manifest.v1",
                "status": "COMPLETED_RESEARCH_ONLY",
                "audit_run_id": "optimistic",
                "artifact_hashes": {},
                "row_counts": {},
                "guardrails": ["research_only"],
                "promotion_allowed": True,
                "model_build_allowed": True,
                "paper_forward_allowed": True,
                "live_broker_order_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(daily_dashboard, "DEFAULT_REJECTION_AUDIT_ROOT", root)

    payload = daily_dashboard.load_rejection_analytics(run="optimistic")

    assert payload["status"] == "INVALID_REJECTION_AUDIT_ARTIFACTS"
    assert payload["promotion_allowed"] is False
    assert payload["model_build_allowed"] is False
    assert "MISSING_REQUIRED_ARTIFACT:gate_funnel_metrics.csv" in payload["errors"]
    assert "PROMOTION_ALLOWED_NOT_FALSE" in payload["errors"]


def test_daily_ohlcv_rejection_analytics_manifest_status_required(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / "rejection_audit"
    run_dir = root / "missing_status"
    run_dir.mkdir(parents=True)
    csv_specs = {
        "gate_funnel_metrics.csv": ["run_id", "entered_count", "rejected_count", "early_dropout_count"],
        "rejection_reason_taxonomy.csv": ["reason_id"],
        "calibration_metrics.csv": ["run_id"],
        "threshold_sensitivity.csv": ["run_id"],
        "false_negative_candidates.csv": ["candidate_id"],
    }
    for name, fieldnames in csv_specs.items():
        with (run_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
    artifact_hashes = {
        name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
        for name in csv_specs
    }
    (run_dir / "audit_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "daily_ohlcv_rejection_audit_manifest.v1",
                "audit_run_id": "missing_status",
                "artifact_hashes": artifact_hashes,
                "row_counts": {
                    "gate_funnel_metrics": 0,
                    "rejection_reason_taxonomy": 0,
                    "calibration_metrics": 0,
                    "threshold_sensitivity": 0,
                    "false_negative_candidates": 0,
                },
                "guardrails": [
                    "research_only",
                    "review_only_false_negatives",
                    "no_no_go_reversal",
                    "no_model_build",
                    "no_paper_forward",
                    "no_live_broker_orders",
                ],
                "promotion_allowed": False,
                "model_build_allowed": False,
                "paper_forward_allowed": False,
                "live_broker_order_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(daily_dashboard, "DEFAULT_REJECTION_AUDIT_ROOT", root)

    payload = daily_dashboard.load_rejection_analytics(run="missing_status")

    assert payload["status"] == "INVALID_REJECTION_AUDIT_ARTIFACTS"
    assert "INVALID_MANIFEST_STATUS" in payload["errors"]


def test_daily_ohlcv_rejection_analytics_false_negative_rows_fail_closed(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / "rejection_audit"
    run_dir = root / "optimistic_false_negative"
    run_dir.mkdir(parents=True)

    def write_csv_file(name, fieldnames, rows):
        with (run_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    write_csv_file(
        "gate_funnel_metrics.csv",
        ["run_id", "entered_count", "rejected_count", "early_dropout_count"],
        [{"run_id": "optimistic_false_negative", "entered_count": 1, "rejected_count": 1, "early_dropout_count": 0}],
    )
    write_csv_file("rejection_reason_taxonomy.csv", ["reason_id"], [{"reason_id": "R001"}])
    write_csv_file("calibration_metrics.csv", ["run_id"], [{"run_id": "optimistic_false_negative"}])
    write_csv_file("threshold_sensitivity.csv", ["run_id"], [{"run_id": "optimistic_false_negative"}])
    follow_up = {
        "schema_version": "daily_ohlcv_false_negative_followup_evidence.v1",
        "status": "FOLLOW_UP_PREREGISTRATION_REQUIRED_REVIEW_ONLY",
        "candidate_ids": ["FN_BAD"],
        "promotion_allowed": False,
        "requires_new_preregistration": True,
        "guardrails": [
            "review_only_false_negatives",
            "no_no_go_reversal",
            "no_model_build",
            "no_paper_forward",
            "no_live_broker_orders",
        ],
    }
    follow_up_path = run_dir / "follow_up_review_evidence_manifest.json"
    follow_up_path.write_text(json.dumps(follow_up), encoding="utf-8")
    follow_up_sha = hashlib.sha256(follow_up_path.read_bytes()).hexdigest()
    write_csv_file(
        "false_negative_candidates.csv",
        [
            "candidate_id",
            "review_status",
            "promotion_allowed",
            "requires_new_preregistration",
            "later_independent_evidence_manifest_path",
            "later_independent_evidence_sha256",
        ],
        [
            {
                "candidate_id": "FN_BAD",
                "review_status": "REVIEW_ONLY",
                "promotion_allowed": "true",
                "requires_new_preregistration": "true",
                "later_independent_evidence_manifest_path": "follow_up_review_evidence_manifest.json",
                "later_independent_evidence_sha256": follow_up_sha,
            }
        ],
    )
    artifact_hashes = {
        name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
        for name in [
            "gate_funnel_metrics.csv",
            "rejection_reason_taxonomy.csv",
            "calibration_metrics.csv",
            "threshold_sensitivity.csv",
            "false_negative_candidates.csv",
            "follow_up_review_evidence_manifest.json",
        ]
    }
    (run_dir / "audit_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "daily_ohlcv_rejection_audit_manifest.v1",
                "status": "COMPLETED_RESEARCH_ONLY",
                "audit_run_id": "optimistic_false_negative",
                "artifact_hashes": artifact_hashes,
                "row_counts": {
                    "gate_funnel_metrics": 1,
                    "rejection_reason_taxonomy": 1,
                    "calibration_metrics": 1,
                    "threshold_sensitivity": 1,
                    "false_negative_candidates": 1,
                },
                "guardrails": [
                    "research_only",
                    "review_only_false_negatives",
                    "no_no_go_reversal",
                    "no_model_build",
                    "no_paper_forward",
                    "no_live_broker_orders",
                ],
                "promotion_allowed": False,
                "model_build_allowed": False,
                "paper_forward_allowed": False,
                "live_broker_order_allowed": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(daily_dashboard, "DEFAULT_REJECTION_AUDIT_ROOT", root)
    monkeypatch.setattr(daily_dashboard, "_safe_relative_repo_path", lambda value: follow_up_path)

    payload = daily_dashboard.load_rejection_analytics(run="optimistic_false_negative")

    assert payload["status"] == "INVALID_REJECTION_AUDIT_ARTIFACTS"
    assert "FALSE_NEGATIVE_PROMOTION_ALLOWED" in payload["errors"]
def test_daily_rl_market_regime_readiness_fails_closed_without_signal_artifacts():
    import webui.daily_ohlcv_dashboard as daily_dashboard

    missing_signal = {
        "status": "MISSING_SIGNAL_QUALITY_AUDIT",
        "run_id": "MISSING_SIGNAL_QUALITY_AUDIT",
        "manifest_path": None,
        "promotion_status": "NO-GO_RESEARCH_ONLY",
        "batch_manifest": {"scenario_count": 0, "completed_count": 0, "failed_count": 0},
        "scenario_cards": [],
    }

    readiness = daily_dashboard._build_rl_guide_market_regime_readiness(missing_signal)
    assert readiness["status"] == "BLOCKED_MISSING_SIGNAL_QUALITY_AUDIT"
    assert readiness["source_signal_quality_run_id"] is None
    checks = {row["check"]: row for row in readiness["readiness_checks"]}
    assert checks["signal_quality_artifacts_available"]["status"] == "BLOCKED"
    assert checks["signal_quality_artifacts_available"]["completion_pct"] == 0
    assert checks["past_only_proxy_contract"]["status"] == "BLOCKED"

    generator = daily_dashboard._build_rl_guide_scenario_generator(missing_signal)
    queue = daily_dashboard._build_rl_guide_improvement_queue(missing_signal)
    comparison = daily_dashboard._build_rl_guide_scenario_comparison(missing_signal)
    maturity = daily_dashboard._build_rl_guide_page_maturity_report(
        scenario_generator=generator,
        signal_summary=missing_signal,
        market_regime_readiness=readiness,
        improvement_queue=queue,
        scenario_comparison=comparison,
    )
    assert maturity["implementation_completion_pct"] < 100
    assert maturity["priority_completion"][1]["status"] == "MISSING_SIGNAL_QUALITY_ARTIFACT"
    assert maturity["score_inputs"]["raw_research_readiness_pct"] < 74

def test_daily_rl_active_replay_fails_closed_on_mismatched_join_keys():
    import webui.daily_ohlcv_dashboard as daily_dashboard

    replay = daily_dashboard._build_rl_guide_active_replay(
        {
            "run_id": "unit_replay_mismatch",
            "artifact_hashes": {"state_observations": "abc"},
            "baseline_comparison": {"policy_strategy": "pretend_policy_network"},
            "samples": {
                "state_observations": [
                    {
                        "split": "train",
                        "date": "20250102",
                        "observation_position_count": "0",
                        "observation_top_score_bucket": "1",
                        "future_label_exposed": "False",
                    }
                ],
                "reward_breakdown": [
                    {
                        "split": "train",
                        "date": "20250103",
                        "action": "buy",
                        "reward": "0.1",
                    }
                ],
            },
        },
        {"schema_version": 1},
    )

    assert replay["status"] == "MISSING_REPLAY_ARTIFACT"
    assert replay["frames"][0]["status"] == "MISSING_REPLAY_JOIN_KEY"
    assert replay["policy_type"] == "tabular_q"
    assert replay["policy_network_status"] == "MISSING_POLICY_ARTIFACT"


def test_daily_rl_active_replay_never_promotes_non_tabular_policy_without_artifact():
    import webui.daily_ohlcv_dashboard as daily_dashboard

    replay = daily_dashboard._build_rl_guide_active_replay(
        {
            "run_id": "unit_non_tabular_policy",
            "artifact_hashes": {"state_observations": "abc", "reward_breakdown": "def"},
            "baseline_comparison": {"policy_strategy": "policy_network_candidate"},
            "samples": {
                "state_observations": [
                    {
                        "split": "test",
                        "date": "20250102",
                        "observation_position_count": "1",
                        "observation_top_score_bucket": "1",
                        "future_label_exposed": "False",
                    }
                ],
                "reward_breakdown": [
                    {
                        "split": "test",
                        "date": "20250102",
                        "action": "hold",
                        "executed_action": "hold",
                        "reward": "0.0",
                    }
                ],
            },
        },
        {"schema_version": 1},
    )

    assert replay["status"] == "LOADED_GENERATED_ARTIFACT"
    assert replay["policy_strategy"] == "policy_network_candidate"
    assert replay["policy_type"] == "tabular_q"
    assert replay["policy_network_available"] is False
    assert replay["policy_network_status"] == "MISSING_POLICY_ARTIFACT"


def test_daily_rl_active_replay_does_not_attach_mismatched_nav_rows():
    import webui.daily_ohlcv_dashboard as daily_dashboard

    replay = daily_dashboard._build_rl_guide_active_replay(
        {
            "run_id": "unit_nav_mismatch",
            "artifact_hashes": {"state_observations": "abc", "reward_breakdown": "def", "policy_nav": "ghi"},
            "baseline_comparison": {"policy_strategy": "tabular_q_constrained_daily_portfolio_rl"},
            "samples": {
                "state_observations": [
                    {
                        "split": "test",
                        "date": "20250102",
                        "observation_position_count": "1",
                        "observation_top_score_bucket": "1",
                        "future_label_exposed": "False",
                    }
                ],
                "reward_breakdown": [
                    {
                        "split": "test",
                        "date": "20250102",
                        "action": "hold",
                        "executed_action": "hold",
                        "reward": "0.0",
                    }
                ],
                "policy_nav": [
                    {
                        "split": "test",
                        "date": "20250103",
                        "policy_nav": "1.23",
                    }
                ],
            },
        },
        {"schema_version": 1},
    )

    assert replay["status"] == "LOADED_GENERATED_ARTIFACT"
    assert replay["frames"][0]["join_key"] == {"split": "test", "date": "20250102"}
    assert replay["frames"][0]["nav"]["policy_nav"] is None

def test_daily_ohlcv_model_result_apis_expose_d3_d5_guardrails():
    client = flask_app.test_client()

    prediction = client.get('/api/daily-ohlcv/prediction/latest?limit=2')
    assert prediction.status_code == 200
    prediction_payload = prediction.get_json()
    assert prediction_payload['status'] == 'WATCH'
    assert prediction_payload['verdict']['go_summary_allowed'] is False
    assert prediction_payload['price_basis'] == 'unknown'
    assert 1 <= len(prediction_payload['baseline_metrics']) <= 2
    assert prediction_payload['baseline_delta_summary']['shuffle_control_strategy'] == 'shuffle_control'
    assert prediction_payload['baseline_delta_summary']['model_build_allowed'] is False
    assert prediction_payload['baseline_delta_summary']['go_summary_allowed'] is False
    assert prediction_payload['baseline_delta_summary']['readiness_status'] == 'D3_WATCH_RESEARCH_ONLY'
    assert prediction_payload['d3_gate_blockers'] == [
        'D0_PRICE_BASIS_NOT_VERIFIED',
        'D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED',
        'D5_WALK_FORWARD_NOT_PASS',
        'D3_BASELINE_WATCH_RESEARCH_ONLY',
    ]
    assert 'model_build_or_candidate_promotion' in prediction_payload['d3_blocked_uses']
    assert {row['strategy'] for row in prediction_payload['baseline_metrics']} == {'no_trade_cash', 'shuffle_control'}
    assert len(prediction_payload['samples']['predictions']) <= 2
    prediction_full = client.get('/api/daily-ohlcv/prediction/latest?limit=25').get_json()
    families = {row['strategy_family'] for row in prediction_full['baseline_metrics']}
    assert {'control', 'rule_baseline', 'supervised'} <= families
    assert {'equal_weight_topk_momentum', 'vol_adjusted_momentum', 'supervised_direction_classifier'} <= {
        row['strategy'] for row in prediction_full['baseline_metrics']
    }
    assert all('delta_vs_shuffle_control_total_net_return' in row for row in prediction_full['baseline_metrics'])
    assert prediction_full['baseline_delta_summary']['best_supervised_delta_vs_best_rule_baseline'] < 0


    portfolio = client.get('/api/daily-ohlcv/portfolio/latest?limit=2')
    assert portfolio.status_code == 200
    portfolio_payload = portfolio.get_json()
    assert portfolio_payload['status'] == 'RESEARCH_ONLY'
    assert portfolio_payload['verdict']['implementation_unlocked'] is False
    assert portfolio_payload['verdict']['go_summary_allowed'] is False
    assert portfolio_payload['verdict']['model_build_allowed'] is False
    assert portfolio_payload['verdict']['readiness_status'] == 'D4_RESEARCH_ONLY_DIAGNOSTICS'
    assert portfolio_payload['model_build_allowed'] is False
    assert portfolio_payload['paper_forward_allowed'] is False
    assert portfolio_payload['live_broker_order_allowed'] is False
    assert portfolio_payload['readiness_status'] == 'D4_RESEARCH_ONLY_DIAGNOSTICS'
    assert len(portfolio_payload['prediction_manifest_sha']) == 64
    assert portfolio_payload['prediction_artifact_hashes']['prediction_manifest'] == portfolio_payload['prediction_manifest_sha']
    assert portfolio_payload['go_summary_allowed'] is False
    assert portfolio_payload['prediction_artifact_hashes']['predictions']
    assert portfolio_payload['prediction_artifact_hashes']['baseline_metrics']
    assert portfolio_payload['prediction_artifact_hashes']['verdict']
    assert portfolio_payload['baseline_comparison']['delta_vs_best_d3_total_net_return'] < 0
    assert len(portfolio_payload['samples']['reward_breakdown']) <= 2
    assert len(portfolio_payload['samples']['invalid_actions']) <= 2
    assert portfolio_payload['telemetry']['status'] == 'READY_RESEARCH_ONLY'
    assert 'learning_curve.csv' in portfolio_payload['telemetry']['canonical_artifacts']
    assert 'observation_manifest.json' in portfolio_payload['telemetry']['canonical_artifacts']
    assert 'state_observations.csv' in portfolio_payload['telemetry']['canonical_artifacts']
    assert portfolio_payload['observation_manifest']['gate'] == 'D4_OBSERVATION_STATE_MANIFEST'
    assert portfolio_payload['observation_manifest']['reward_action_telemetry_sufficient_for_d4'] is False
    assert len(portfolio_payload['samples']['learning_curve']) <= 2
    assert len(portfolio_payload['samples']['action_distribution']) <= 2
    assert len(portfolio_payload['samples']['turnover']) <= 2
    assert len(portfolio_payload['samples']['drawdown']) <= 2
    assert len(portfolio_payload['samples']['policy_baseline_comparison']) <= 2
    assert len(portfolio_payload['samples']['policy_nav']) <= 2
    assert len(portfolio_payload['samples']['state_observations']) <= 2
    assert portfolio_payload['policy_evaluation']['required_frozen_baselines'] == [
        'no_trade_cash',
        'shuffle_control',
        'equal_weight_topk_momentum',
        'vol_adjusted_momentum',
        'supervised_linear_ranker',
        'supervised_direction_classifier',
    ]
    assert portfolio_payload['reward_component_summary']['by_split']
    assert 'policy_baseline_comparison.csv' in portfolio_payload['telemetry']['canonical_artifacts']
    assert 'policy_nav.csv' in portfolio_payload['telemetry']['canonical_artifacts']

    gate = client.get('/api/daily-ohlcv/walk-forward/latest?limit=2')
    assert gate.status_code == 200
    gate_payload = gate.get_json()
    assert gate_payload['status'] == 'NO-GO'
    assert gate_payload['verdict']['model_build_allowed'] is False
    assert gate_payload['verdict']['go_summary_allowed'] is False
    assert gate_payload['model_build_allowed'] is False
    assert gate_payload['go_summary_allowed'] is False
    assert gate_payload['paper_forward_allowed'] is False
    assert gate_payload['live_broker_order_allowed'] is False
    assert gate_payload['no_live_broker_order_readiness'] is True
    assert gate_payload['readiness_status'] == 'D5_NO_GO_RESEARCH_ONLY_GATE'
    assert gate_payload['verdict']['paper_forward_allowed'] is False
    assert gate_payload['verdict']['live_broker_order_allowed'] is False
    assert len(gate_payload['prediction_manifest_sha']) == 64
    assert gate_payload['prediction_artifact_hashes']['prediction_manifest'] == gate_payload['prediction_manifest_sha']
    assert len(gate_payload['portfolio_manifest_sha']) == 64
    assert gate_payload['portfolio_artifact_hashes']['rl_manifest'] == gate_payload['portfolio_manifest_sha']
    assert 'RL_POLICY_UNDERPERFORMS_D3_BASELINE' in gate_payload['verdict']['reasons']
    assert len(gate_payload['samples']['fold_metrics']) <= 2
    assert gate_payload['d4_state_contract']['status'] == 'PASS'
    assert gate_payload['verdict']['d4_state_contract_artifacts_consumed'] is True
    assert gate_payload['verdict']['d4_observation_manifest_gate'] == 'D4_OBSERVATION_STATE_MANIFEST'

    registry = client.get('/api/daily-ohlcv/registry/latest?limit=2')
    assert registry.status_code == 200
    registry_payload = registry.get_json()
    assert registry_payload['status'] == 'RESEARCH_ONLY_BLOCKED'
    assert registry_payload['promotion_status'] == 'BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER'
    assert registry_payload['model_build_allowed'] is False
    assert registry_payload['paper_forward_allowed'] is False
    assert registry_payload['live_broker_order_allowed'] is False
    assert 'no live/broker/orders' in registry_payload['guardrail']
    assert len(registry_payload['config_hash']) == 64
    assert len(registry_payload['data_hash']) == 64
    assert len(registry_payload['code_hash']) == 64
    assert registry_payload['candidate_registry']['candidates'][0]['promotion_status'] == 'BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER'
    assert registry_payload['candidate_registry']['candidates'][0]['model_build_allowed'] is False
    assert registry_payload['candidate_registry']['candidates'][0]['paper_forward_allowed'] is False
    assert registry_payload['candidate_registry']['candidates'][0]['live_broker_order_allowed'] is False
    assert registry_payload['candidate_registry']['candidates'][0]['no_live_broker_order_readiness'] is True
    assert 'D5_WALK_FORWARD_NOT_PASS' in registry_payload['effective_gate_blockers']
    assert registry_payload['samples']['drawdown'][0]['source'] == 'research_policy_nav_not_live_account'
    assert registry_payload['read_only_dashboard_note'].startswith('GET-only D8/D9')
    assert len(registry_payload['samples']['paper_selected']) <= 2
    assert registry_payload['samples']['paper_selected'][0]['selection_status'] == 'BLOCKED_BY_D5_NO_GO'
    assert len(registry_payload['samples']['realized_returns']) <= 2
    assert len(registry_payload['samples']['drift']) <= 2
    assert len(registry_payload['samples']['drawdown']) <= 2
    assert len(registry_payload['samples']['decision_log']) <= 2

    chart = client.get('/api/daily-ohlcv/charts/walk-forward').get_json()
    prediction_chart = client.get('/api/daily-ohlcv/charts/prediction').get_json()
    assert prediction_chart['baseline_delta_summary']['shuffle_control_strategy'] == 'shuffle_control'
    assert any(row['strategy'] == 'shuffle_control' for row in prediction_chart['baseline_series'])
    chart_families = {row['strategy_family'] for row in prediction_chart['baseline_series']}
    assert {'control', 'rule_baseline', 'supervised'} <= chart_families
    assert prediction_chart['baseline_delta_summary']['cost_round_trip_bp'] == 23
    assert prediction_chart['d3_gate_blockers'] == [
        'D0_PRICE_BASIS_NOT_VERIFIED',
        'D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED',
        'D5_WALK_FORWARD_NOT_PASS',
        'D3_BASELINE_WATCH_RESEARCH_ONLY',
    ]
    assert prediction_chart['baseline_freeze_contract']['deterministic_shuffle_method'] == 'sha256(date:code)_ascending'
    portfolio_chart = client.get('/api/daily-ohlcv/charts/portfolio').get_json()
    assert portfolio_chart['training_status'] == 'TABULAR_Q_TELEMETRY_RECORDED'
    assert portfolio_chart['model_build_allowed'] is False
    assert portfolio_chart['readiness_status'] == 'D4_RESEARCH_ONLY_DIAGNOSTICS'
    assert portfolio_chart['paper_forward_allowed'] is False
    assert portfolio_chart['live_broker_order_allowed'] is False
    assert portfolio_chart['learning_curve']
    assert portfolio_chart['action_distribution']
    assert portfolio_chart['reward_component_summary']['by_split']
    assert portfolio_chart['observation_manifest']['gate'] == 'D4_OBSERVATION_STATE_MANIFEST'
    assert portfolio_chart['observation_manifest']['reward_action_telemetry_sufficient_for_d4'] is False
    assert portfolio_chart['state_observations']
    assert portfolio_chart['invalid_actions']
    assert portfolio_chart['portfolio_trajectory']
    assert portfolio_chart['reward_stack']
    assert portfolio_chart['turnover_series']
    assert portfolio_chart['drawdown_series']
    assert 'invalid_action' in portfolio_chart['action_distribution'][0]
    reward_row = portfolio_chart['reward_component_summary']['by_split'][0]
    assert {'exposure_penalty', 'concentration_penalty', 'invalid_action_penalty', 'churn_penalty', 'drawdown_penalty'} <= set(reward_row)
    assert 'turnover_cost' in portfolio_chart['turnover_series'][0]
    assert 'current_drawdown' in portfolio_chart['drawdown_series'][0]
    assert portfolio_chart['policy_baseline_comparison']
    assert portfolio_chart['policy_nav']
    assert portfolio_chart['policy_nav'] == portfolio_chart['portfolio_trajectory']
    assert portfolio_chart['policy_evaluation']['policy_baseline_comparison_rows'] >= 6
    assert len(portfolio_chart['prediction_manifest_sha']) == 64
    assert portfolio_chart['prediction_artifact_hashes']['predictions']
    assert portfolio_chart['artifact_hashes']['policy_nav']
    assert portfolio_chart['go_summary_allowed'] is False
    assert {'baseline_strategy', 'policy_nav', 'baseline_nav', 'baseline_delta_total_net_return'} <= set(portfolio_chart['policy_baseline_comparison'][0])
    assert 'RESEARCH_ONLY diagnostics' in portfolio_chart['guardrail']
    assert chart['status'] == 'NO-GO'
    assert chart['model_build_allowed'] is False
    assert 'NO-GO/WATCH reasons' in chart['guardrail']
    assert chart['readiness_status'] == 'D5_NO_GO_RESEARCH_ONLY_GATE'
    assert chart['go_summary_allowed'] is False
    assert chart['paper_forward_allowed'] is False
    assert chart['live_broker_order_allowed'] is False
    assert chart['no_live_broker_order_readiness'] is True
    assert len(chart['prediction_manifest_sha']) == 64
    assert chart['prediction_artifact_hashes']['predictions']
    assert len(chart['portfolio_manifest_sha']) == 64
    assert chart['portfolio_artifact_hashes']['state_observations']
    assert chart['artifact_hashes']['fold_metrics']
    assert chart['artifact_hashes']['gate_verdict']
    assert chart['d4_state_contract']['status'] == 'PASS'
    assert chart['d4_state_contract_artifacts_consumed'] is True
    assert chart['d4_state_observation_rows'] > 0
    assert chart['d4_observation_manifest_gate'] == 'D4_OBSERVATION_STATE_MANIFEST'
    assert chart['d4_observation_manifest_validation_status'] == 'PASS'
    assert chart['d4_reward_action_telemetry_sufficient_for_d4'] is False
    assert chart['d4_reward_action_ablation_rows'] > 0
    assert chart['d4_source_hash_count'] > 0
    assert chart['fold_windows']
    assert chart['no_trade_control']
    assert chart['selected_fold_metrics']
    assert chart['cost_sensitivity_bp'] == [0, 23, 46]
    assert chart['purge_days'] == 5
    assert chart['embargo_days'] == 5
    assert chart['min_required_purge_days'] == 5
    assert chart['min_required_embargo_days'] == 5
    assert chart['no_oos_retuning'] is True
    assert 'worst_fold_max_drawdown' in chart['fold_consistency']
    assert 'mean_fold_turnover' in chart['fold_consistency']



def test_daily_walk_forward_stale_optimistic_artifact_fails_closed(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / "walk_forward"
    run_dir = root / "optimistic_d5"
    run_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "run_id": "optimistic_d5",
        "status": "READY",
        "readiness_status": "D5_GO_READY",
        "model_build_allowed": True,
        "go_summary_allowed": True,
        "paper_forward_allowed": True,
        "live_broker_order_allowed": True,
        "no_live_broker_order_readiness": False,
        "d4_state_contract_artifacts_consumed": True,
        "d4_state_contract_status": "PASS",
        "d4_observation_manifest_gate": "D4_OBSERVATION_STATE_MANIFEST",
        "d4_observation_manifest_validation_status": "PASS",
        "d4_state_observation_rows": 100,
        "d4_reward_action_ablation_rows": 10,
        "d4_source_hash_count": 3,
        "d4_artifact_issues": [],
        "verdict": {
            "status": "LIVE_READY",
            "ui_badge": "GO",
            "implementation_unlocked": True,
            "model_build_allowed": True,
            "go_summary_allowed": True,
            "paper_forward_allowed": True,
            "live_broker_order_allowed": True,
            "no_live_broker_order_readiness": False,
            "readiness_status": "D5_GO_READY",
            "selected_strategy": "selected_rl",
            "no_oos_retuning": False,
            "purge_days": 0,
            "embargo_days": 0,
            "min_required_purge_days": -10,
            "min_required_embargo_days": -10,
            "d4_state_contract_artifacts_consumed": True,
            "d4_state_contract_status": "PASS",
            "d4_observation_manifest_gate": "D4_OBSERVATION_STATE_MANIFEST",
            "d4_observation_manifest_validation_status": "PASS",
            "d4_state_observation_rows": 100,
            "d4_reward_action_ablation_rows": 10,
            "d4_source_hash_count": 3,
            "d4_artifact_issues": [],
            "reasons": ["OPTIMISTIC_STALE", "D4_OBSERVATION_STATE_MANIFEST_CONSUMED"],
        },
    }
    (run_dir / "walk_forward_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "gate_verdict.json").write_text(json.dumps(manifest["verdict"]), encoding="utf-8")
    (run_dir / "d4_state_contract.json").write_text(json.dumps({}), encoding="utf-8")
    (run_dir / "cost_sensitivity.csv").write_text(
        "fold_id,strategy,cost_bp,total_net_return,max_drawdown\n"
        "F01,other_strategy,0,0.01,-0.01\n"
        "F01,other_strategy,23,0.01,-0.01\n"
        "F01,other_strategy,46,0.01,-0.01\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(daily_dashboard, "DEFAULT_WALK_FORWARD_ROOT", root)
    monkeypatch.setattr(
        daily_dashboard,
        "load_daily_db_summary",
        lambda **_: {
            "price_basis": "unknown",
            "price_basis_status": "UNKNOWN_CONFIRMED",
            "decision_grade_return_status": "BLOCKED_UNTIL_PRICE_BASIS_VERIFIED",
        },
    )
    monkeypatch.setattr(
        daily_dashboard,
        "load_universe_preview",
        lambda **_: {"verdict": "WATCH_HEURISTIC_UNIVERSE", "official_metadata_status": "MISSING"},
    )
    monkeypatch.setattr(
        daily_dashboard,
        "load_prediction_latest",
        lambda **_: {
            "baseline_delta_summary": {"model_build_allowed": False},
            "verdict": {"go_summary_allowed": False},
        },
    )

    latest = daily_dashboard.load_walk_forward_latest(run="optimistic_d5", sample_limit=0)
    chart = daily_dashboard.load_walk_forward_chart(run="optimistic_d5")

    for payload in (latest, chart):
        assert payload["status"] == "NO-GO"
        assert payload["readiness_status"] == "D5_NO_GO_RESEARCH_ONLY_GATE"
        assert payload["model_build_allowed"] is False
        assert payload["go_summary_allowed"] is False
        assert payload["paper_forward_allowed"] is False
        assert payload["live_broker_order_allowed"] is False
        assert payload["no_live_broker_order_readiness"] is True
    assert latest["verdict"]["ui_badge"] == "NO-GO"
    assert latest["verdict"]["implementation_unlocked"] is False
    assert latest["verdict"]["no_live_broker_order_readiness"] is True
    assert latest["verdict"]["d4_state_contract_artifacts_consumed"] is False
    assert latest["verdict"]["d4_state_contract_status"] is None
    assert "D4_STATE_CONTRACT_EVIDENCE_MISSING_OR_STALE" in latest["verdict"]["d4_artifact_issues"]
    assert latest["d4_state_contract_artifacts_consumed"] is False
    assert latest["d4_state_contract_status"] is None
    assert "D4_STATE_CONTRACT_EVIDENCE_MISSING_OR_STALE" in latest["d4_artifact_issues"]
    assert "D4_OBSERVATION_STATE_MANIFEST_CONSUMED" not in latest["verdict"]["reasons"]
    assert "D5_EFFECTIVE_MODEL_BUILD_LOCK" in latest["verdict"]["reasons"]
    assert chart["cost_sensitivity_bp"] == []
    assert chart["no_oos_retuning"] is False
    assert chart["purge_days"] == 0
    assert chart["embargo_days"] == 0
    assert chart["min_required_purge_days"] == 5
    assert chart["min_required_embargo_days"] == 5
    assert chart["d4_state_contract_artifacts_consumed"] is False
    assert "D5_COST_SENSITIVITY_INCOMPLETE" in chart["reasons"]
    assert "D5_NO_OOS_RETUNING_NOT_PROVEN" in chart["reasons"]
    assert "PURGE_DAYS_BELOW_REQUIRED_MIN" in chart["reasons"]
    assert "EMBARGO_DAYS_BELOW_REQUIRED_MIN" in chart["reasons"]
    assert "D4_STATE_CONTRACT_EVIDENCE_MISSING_OR_STALE" in chart["d4_artifact_issues"]
    assert "D4_OBSERVATION_STATE_MANIFEST_CONSUMED" not in chart["reasons"]


def test_daily_ohlcv_portfolio_stale_optimistic_artifact_fails_closed(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / "portfolio"
    run_dir = root / "optimistic"
    run_dir.mkdir(parents=True)
    stale_manifest = {
        "schema_version": 1,
        "run_id": "optimistic",
        "status": "PASS",
        "readiness_status": "D4_GO_READY",
        "model_build_allowed": True,
        "go_summary_allowed": True,
        "paper_forward_allowed": True,
        "live_broker_order_allowed": True,
        "no_live_broker_order_readiness": False,
        "verdict": {
            "status": "GO",
            "ui_badge": "GO",
            "implementation_unlocked": True,
            "model_build_allowed": True,
            "go_summary_allowed": True,
            "paper_forward_allowed": True,
            "live_broker_order_allowed": True,
            "readiness_status": "D4_GO_READY",
        },
        "telemetry": {"status": "READY_RESEARCH_ONLY"},
    }
    (run_dir / "rl_manifest.json").write_text(json.dumps(stale_manifest), encoding="utf-8")
    (run_dir / "verdict.json").write_text(
        json.dumps(
            {
                "status": "GO",
                "ui_badge": "GO",
                "implementation_unlocked": True,
                "model_build_allowed": True,
                "go_summary_allowed": True,
                "paper_forward_allowed": True,
                "live_broker_order_allowed": True,
                "readiness_status": "D4_GO_READY",
                "no_live_broker_order_readiness": False,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "policy_evaluation_manifest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "model_build_allowed": True,
                "go_summary_allowed": True,
                "paper_forward_allowed": True,
                "live_broker_order_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "training_manifest.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "readiness_status": "D4_GO_READY",
                "model_build_allowed": True,
                "go_summary_allowed": True,
                "paper_forward_allowed": True,
                "live_broker_order_allowed": True,
                "verdict": {
                    "status": "GO",
                    "ui_badge": "GO",
                    "implementation_unlocked": True,
                    "model_build_allowed": True,
                    "go_summary_allowed": True,
                    "paper_forward_allowed": True,
                    "live_broker_order_allowed": True,
                    "readiness_status": "D4_GO_READY",
                    "no_live_broker_order_readiness": False,
                },
                "telemetry": {"canonical_artifacts": []},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(daily_dashboard, "DEFAULT_PORTFOLIO_ROOT", root)

    latest = daily_dashboard.load_portfolio_latest(run="optimistic", sample_limit=0)
    chart = daily_dashboard.load_portfolio_chart(run="optimistic")

    assert latest["status"] == "RESEARCH_ONLY"
    assert latest["readiness_status"] == "D4_RESEARCH_ONLY_DIAGNOSTICS"
    assert latest["model_build_allowed"] is False
    assert latest["go_summary_allowed"] is False
    assert latest["paper_forward_allowed"] is False
    assert latest["live_broker_order_allowed"] is False
    assert latest["no_live_broker_order_readiness"] is True
    assert latest["verdict"]["status"] == "RESEARCH_ONLY"
    assert latest["verdict"]["ui_badge"] == "RESEARCH_ONLY"
    assert latest["verdict"]["implementation_unlocked"] is False
    assert latest["verdict"]["model_build_allowed"] is False
    assert latest["verdict"]["go_summary_allowed"] is False
    assert latest["verdict"]["paper_forward_allowed"] is False
    assert latest["verdict"]["live_broker_order_allowed"] is False
    assert latest["verdict"]["no_live_broker_order_readiness"] is True
    assert latest["policy_evaluation"]["model_build_allowed"] is False
    assert latest["policy_evaluation"]["paper_forward_allowed"] is False
    assert latest["training_manifest"]["status"] == "RESEARCH_ONLY"
    assert latest["training_manifest"]["readiness_status"] == "D4_RESEARCH_ONLY_DIAGNOSTICS"
    assert latest["training_manifest"]["model_build_allowed"] is False
    assert latest["training_manifest"]["go_summary_allowed"] is False
    assert latest["training_manifest"]["paper_forward_allowed"] is False
    assert latest["training_manifest"]["live_broker_order_allowed"] is False
    assert latest["training_manifest"]["verdict"]["implementation_unlocked"] is False
    assert latest["training_manifest"]["verdict"]["no_live_broker_order_readiness"] is True
    assert chart["status"] == "RESEARCH_ONLY"
    assert chart["readiness_status"] == "D4_RESEARCH_ONLY_DIAGNOSTICS"
    assert chart["model_build_allowed"] is False
    assert chart["go_summary_allowed"] is False
    assert chart["paper_forward_allowed"] is False
    assert chart["live_broker_order_allowed"] is False

def test_daily_ohlcv_prediction_stale_artifact_fails_closed(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / 'prediction'
    run_dir = root / 'stale_go'
    run_dir.mkdir(parents=True)
    (run_dir / 'prediction_manifest.json').write_text(
        json.dumps({
            'schema_version': 1,
            'run_id': 'stale_go',
            'status': 'MODEL_READY',
            'readiness_status': 'PRODUCTION_READY',
            'model_build_allowed': True,
            'go_summary_allowed': True,
            'price_basis': 'raw',
            'price_basis_status': 'RAW_VERIFIED',
            'decision_grade_return_status': 'READY',
            'universe_verdict': 'OFFICIAL_OR_MANUAL_REVIEWED',
            'universe_review_status': 'OFFICIAL_OR_MANUAL_REVIEWED',
            'official_metadata_status': 'OFFICIAL_VERIFIED',
            'official_metadata_coverage_status': 'COMPLETE',
            'universe_certification_status': 'OFFICIAL_OR_MANUAL_REVIEWED',
            'baseline_delta_summary': {
                'status': 'LIVE_READY',
                'readiness_status': 'PRODUCTION_READY',
                'model_build_allowed': True,
                'go_summary_allowed': True,
                'shuffle_control_strategy': 'shuffle_control',
            },
            'verdict': {
                'status': 'READY',
                'readiness_status': 'PRODUCTION_READY',
                'go_summary_allowed': True,
                'model_build_allowed': True,
                'reasons': [],
            },
        }),
        encoding='utf-8',
    )
    (run_dir / 'baseline_delta_summary.json').write_text(
        json.dumps({
            'status': 'MODEL_READY',
            'readiness_status': 'PRODUCTION_READY',
            'model_build_allowed': True,
            'go_summary_allowed': True,
            'shuffle_control_strategy': 'shuffle_control',
        }),
        encoding='utf-8',
    )
    (run_dir / 'verdict.json').write_text(
        json.dumps({'status': 'LIVE_READY', 'readiness_status': 'PRODUCTION_READY', 'go_summary_allowed': True, 'model_build_allowed': True, 'reasons': []}),
        encoding='utf-8',
    )
    monkeypatch.setattr(daily_dashboard, 'DEFAULT_PREDICTION_ROOT', root)

    payload = daily_dashboard.load_prediction_latest(run='stale_go', sample_limit=0)
    chart = daily_dashboard.load_prediction_chart(run='stale_go')

    assert payload['status'] == 'WATCH'
    assert payload['readiness_status'] == 'D3_WATCH_RESEARCH_ONLY'
    assert payload['model_build_allowed'] is False
    assert payload['go_summary_allowed'] is False
    assert payload['verdict']['go_summary_allowed'] is False
    assert payload['verdict']['model_build_allowed'] is False
    assert payload['verdict']['status'] == 'WATCH'
    assert payload['verdict']['readiness_status'] == 'D3_WATCH_RESEARCH_ONLY'
    assert payload['price_basis'] == 'unknown'
    assert payload['universe_verdict'] == 'WATCH_HEURISTIC_UNIVERSE'
    assert payload['baseline_delta_summary']['model_build_allowed'] is False
    assert payload['baseline_delta_summary']['go_summary_allowed'] is False
    assert payload['baseline_delta_summary']['status'] == 'WATCH'
    assert payload['baseline_delta_summary']['readiness_status'] == 'D3_WATCH_RESEARCH_ONLY'
    assert payload['d3_gate_blockers'] == [
        'D0_PRICE_BASIS_NOT_VERIFIED',
        'D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED',
        'D5_WALK_FORWARD_NOT_PASS',
        'D3_BASELINE_WATCH_RESEARCH_ONLY',
    ]
    assert 'model_build_or_candidate_promotion' in payload['d3_blocked_uses']
    assert chart['go_summary_allowed'] is False
    assert chart['model_build_allowed'] is False
    assert chart['readiness_status'] == 'D3_WATCH_RESEARCH_ONLY'
    assert chart['baseline_delta_summary']['status'] == 'WATCH'
    assert chart['baseline_delta_summary']['readiness_status'] == 'D3_WATCH_RESEARCH_ONLY'
    assert chart['d3_gate_blockers'] == payload['d3_gate_blockers']


def test_daily_ohlcv_visual_chart_apis_expose_read_only_gate_payloads():
    client = flask_app.test_client()

    decision = client.get('/api/daily-ohlcv/charts/decision-cockpit')
    assert decision.status_code == 200
    decision_payload = decision.get_json()
    assert decision_payload['model_build_allowed'] is False
    assert decision_payload['go_summary_allowed'] is False
    blocker_ids = {row['id'] for row in decision_payload['blockers']}
    assert 'RL_POLICY_UNDERPERFORMS_D3_BASELINE' in blocker_ids
    assert 'PRICE_BASIS_UNKNOWN' in blocker_ids
    assert 'not a profit/live/broker/order readiness claim' in decision_payload['guardrail']
    assert decision_payload['usage_guide'][0]['stage'] == 'D6'
    assert decision_payload['usage_guide'][1]['stage'] == 'D7'
    assert 'Decision Cockpit' in decision_payload['usage_guide'][0]['can_do']

    flow = client.get('/api/daily-ohlcv/charts/flow').get_json()
    assert [node['id'] for node in flow['nodes']] == ['D0', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8', 'D9']
    assert len(flow['edges']) == 9
    assert flow['model_build_allowed'] is False
    assert flow['nodes'][6]['usage_guide']['stage'] == 'D6'
    assert flow['nodes'][7]['usage_guide']['stage'] == 'D7'
    assert flow['nodes'][8]['severity'] == 'block'
    assert flow['nodes'][9]['severity'] == 'block'

    glossary = client.get('/api/daily-ohlcv/charts/glossary').get_json()
    terms = {row['term'] for row in glossary['items']}
    assert {'NO-GO', 'RESEARCH_ONLY', 'Shuffle control', 'model_build_allowed'} <= terms
    assert {'Learning curve', 'Action distribution', 'Portfolio trajectory', 'Symbol drilldown'} <= terms

    diagnostics = client.get('/api/daily-ohlcv/charts/research-diagnostics').get_json()
    assert diagnostics['status'] == 'WATCH'
    assert diagnostics['model_build_allowed'] is False
    assert diagnostics['go_summary_allowed'] is False
    diagnostic_ids = {row['id'] for row in diagnostics['cards']}
    assert {
        'D7_FEATURE_DIAGNOSTICS',
        'D7_REGIME_DIAGNOSTICS',
        'D7_CORRELATION_RISK',
        'D7_FAILURE_ANALYSIS',
    } <= diagnostic_ids
    assert '읽기 전용' in diagnostics['summary']['korean']
    assert 'no profit, live, broker, order' in diagnostics['guardrail']
    assert diagnostics['usage_guide'][0]['stage'] == 'D7'
    assert all(row['allowed_use'] for row in diagnostics['cards'])
    assert all(row['blocked_use'] for row in diagnostics['cards'])
    assert all(row['how_to_read_ko'] for row in diagnostics['cards'])
    assert all(row['current_gap'] for row in diagnostics['cards'])
    next_artifacts = {row['next_artifact'] for row in diagnostics['cards']}
    assert {
        'feature_importance_by_fold.csv',
        'regime_bucket_metrics.csv',
        'correlation_cluster_summary.csv',
        'failure_reason_attribution.csv',
    } <= next_artifacts
    assert '연구 노트' in diagnostics['summary']['how_to_use']

    equity = client.get('/api/daily-ohlcv/charts/equity-overlay').get_json()
    assert equity['status'] == 'NO-GO'
    assert any(curve['kind'] == 'daily_baseline' for curve in equity['curves'])
    assert any(curve['kind'] == 'rl_research_only' for curve in equity['curves'])
    assert 'not a profit' in equity['guardrail']

    heatmap = client.get('/api/daily-ohlcv/charts/walk-forward-heatmap').get_json()
    assert heatmap['status'] == 'NO-GO'
    assert heatmap['model_build_allowed'] is False
    assert heatmap['cells']
    assert any(row['cost_bp'] == 23 for row in heatmap['cost_series'])

    scatter = client.get('/api/daily-ohlcv/charts/run-scatter').get_json()
    kinds = {row['kind'] for row in scatter['points']}
    assert {'daily_baseline', 'daily_rl', 'walk_forward_gate'} <= kinds

    universe = client.get('/api/daily-ohlcv/charts/universe-breakdown').get_json()
    assert universe['status'] == 'WATCH_HEURISTIC_UNIVERSE'
    assert universe['summary']['include_count'] == 2599
    assert universe['summary']['exclude_count'] == 2128
    assert universe['summary']['universe_certification_status'] == 'BLOCKED_UNTIL_OFFICIAL_OR_MANUAL_REVIEW'

    symbol = client.get('/api/daily-ohlcv/charts/symbol/000250?limit=5').get_json()
    assert symbol['code'] == '000250'
    assert symbol['table'] == 'A000250'
    assert len(symbol['ohlcv']) <= 5
    assert 'not a prediction' in symbol['guardrail']
    assert symbol['usage_guide'][0]['section'] == 'symbol_ohlcv_preview'
    assert '매수/매도 추천' in symbol['usage_guide'][0]['must_not']


def test_daily_effective_model_gate_blocks_optimistic_d5_artifact(monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    monkeypatch.setattr(
        daily_dashboard,
        'load_daily_db_summary',
        lambda **_: {
            'table_count': 1,
            'total_rows': 10,
            'price_basis': 'unknown',
            'price_basis_status': 'UNKNOWN_CONFIRMED',
            'decision_grade_return_status': 'BLOCKED_UNTIL_PRICE_BASIS_VERIFIED',
            'quality_scan_scope': 'synthetic',
        },
    )
    monkeypatch.setattr(
        daily_dashboard,
        'load_universe_preview',
        lambda **_: {
            'verdict': 'WATCH_HEURISTIC_UNIVERSE',
            'official_metadata_status': 'MISSING',
            'include_count': 1,
            'exclude_count': 0,
            'stockinfo_matched_table_count': 1,
            'stockinfo_unmatched_table_count': 0,
        },
    )
    monkeypatch.setattr(
        daily_dashboard,
        'load_dataset_latest',
        lambda **_: {
            'status': 'PASS',
            'price_basis': 'unknown',
            'universe_verdict': 'WATCH_HEURISTIC_UNIVERSE',
            'leakage_status': 'PASS',
            'split_chronology_status': 'PASS',
            'row_counts': {'feature_rows': 10, 'eligible_rows': 10},
            'artifact_scope': 'synthetic',
        },
    )
    monkeypatch.setattr(
        daily_dashboard,
        'load_prediction_latest',
        lambda **_: {
            'status': 'WATCH',
            'price_basis': 'unknown',
            'verdict': {
                'best_strategy_by_total_net_return': 'optimistic',
                'go_summary_allowed': False,
            },
            'baseline_delta_summary': {
                'model_build_allowed': False,
                'shuffle_control_strategy': 'shuffle_control',
                'best_rule_baseline_strategy': 'equal_weight_topk_momentum',
                'cost_round_trip_bp': 23,
            },
        },
    )
    monkeypatch.setattr(
        daily_dashboard,
        'load_portfolio_latest',
        lambda **_: {
            'status': 'RESEARCH_ONLY',
            'verdict': {'implementation_unlocked': False, 'gate_dependency': 'D3'},
            'baseline_comparison': {'delta_vs_best_d3_total_net_return': -0.1},
            'observation_manifest_validation': {'status': 'PASS'},
            'samples': {},
        },
    )
    monkeypatch.setattr(
        daily_dashboard,
        'load_walk_forward_latest',
        lambda **_: {
            'status': 'PASS',
            'run_id': 'optimistic_d5',
            'verdict': {
                'model_build_allowed': True,
                'go_summary_allowed': True,
                'n_folds': 5,
                'no_oos_retuning': True,
                'd4_state_contract_status': 'PASS',
                'selected_strategy': 'optimistic',
                'strategy_selection_policy': 'synthetic',
                'reasons': [],
            },
            'samples': {'fold_metrics': []},
            'd4_state_contract': {'status': 'PASS'},
        },
    )
    monkeypatch.setattr(
        daily_dashboard,
        'load_registry_latest',
        lambda **_: {
            'status': 'RESEARCH_ONLY_BLOCKED',
            'promotion_status': 'BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER',
            'model_build_allowed': False,
            'paper_forward_allowed': False,
            'live_broker_order_allowed': False,
            'no_live_broker_order_readiness': True,
            'code_hash': 'synthetic',
            'candidate_registry': {},
        },
    )

    client = flask_app.test_client()
    progress = client.get('/api/daily-ohlcv/progress').get_json()
    gate = client.get('/api/daily-ohlcv/gate/latest').get_json()
    flow = client.get('/api/daily-ohlcv/charts/flow').get_json()
    decision = client.get('/api/daily-ohlcv/charts/decision-cockpit').get_json()
    diagnostics = client.get('/api/daily-ohlcv/charts/research-diagnostics').get_json()

    for payload in (progress, gate, flow, decision, diagnostics):
        assert payload['model_build_allowed'] is False
        assert payload['go_summary_allowed'] is False
    assert progress['effective_gate_blockers'] == [
        'D0_PRICE_BASIS_NOT_VERIFIED',
        'D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED',
        'D3_BASELINE_NOT_PROMOTABLE',
    ]
    assert gate['effective_gate_blockers'] == progress['effective_gate_blockers']
    blocker_ids = {row['id'] for row in decision['blockers']}
    assert set(progress['effective_gate_blockers']) <= blocker_ids


def test_daily_effective_model_gate_fails_closed_on_missing_d0_fields():
    import webui.daily_ohlcv_dashboard as daily_dashboard

    gate = daily_dashboard._effective_daily_model_gate(
        db={},
        universe={'verdict': 'PASS', 'official_metadata_status': 'OFFICIAL_VERIFIED'},
        prediction={
            'baseline_delta_summary': {'model_build_allowed': True},
            'verdict': {'go_summary_allowed': True},
        },
        gate_verdict={'model_build_allowed': True, 'go_summary_allowed': True},
        gate_status='PASS',
    )

    assert gate['model_build_allowed'] is False
    assert 'D0_PRICE_BASIS_NOT_VERIFIED' in gate['effective_gate_blockers']


def test_daily_effective_model_gate_rejects_unverified_substrings():
    import webui.daily_ohlcv_dashboard as daily_dashboard

    gate = daily_dashboard._effective_daily_model_gate(
        db={
            'price_basis': 'raw',
            'price_basis_status': 'UNVERIFIED',
            'decision_grade_return_status': 'READY',
        },
        universe={'verdict': 'UNOFFICIAL_VERIFIED', 'official_metadata_status': 'UNVERIFIED'},
        prediction={
            'baseline_delta_summary': {'model_build_allowed': True},
            'verdict': {'go_summary_allowed': True},
        },
        gate_verdict={'model_build_allowed': True, 'go_summary_allowed': True},
        gate_status='PASS',
    )

    assert gate['model_build_allowed'] is False
    assert gate['effective_gate_blockers'] == [
        'D0_PRICE_BASIS_NOT_VERIFIED',
        'D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED',
    ]

def test_daily_effective_model_gate_requires_exact_d1_statuses_and_complete_coverage():
    import webui.daily_ohlcv_dashboard as daily_dashboard

    common_kwargs = {
        'db': {
            'price_basis': 'raw',
            'price_basis_status': 'RAW_VERIFIED',
            'decision_grade_return_status': 'READY',
        },
        'prediction': {
            'baseline_delta_summary': {'model_build_allowed': True},
            'verdict': {'go_summary_allowed': True},
        },
        'gate_verdict': {'model_build_allowed': True, 'go_summary_allowed': True},
        'gate_status': 'PASS',
    }
    generic = daily_dashboard._effective_daily_model_gate(
        universe={
            'verdict': 'PASS',
            'universe_review_status': 'PASS',
            'official_metadata_status': 'PASS',
            'official_metadata_coverage_status': 'COMPLETE',
            'universe_certification_status': 'PASS',
        },
        **common_kwargs,
    )
    partial = daily_dashboard._effective_daily_model_gate(
        universe={
            'verdict': 'OFFICIAL_OR_MANUAL_REVIEWED',
            'universe_review_status': 'OFFICIAL_OR_MANUAL_REVIEWED',
            'official_metadata_status': 'OFFICIAL_VERIFIED',
            'official_metadata_coverage_status': 'PARTIAL',
            'universe_certification_status': 'OFFICIAL_OR_MANUAL_REVIEWED',
        },
        **common_kwargs,
    )

    assert generic['model_build_allowed'] is False
    assert generic['effective_gate_blockers'] == ['D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED']
    assert partial['model_build_allowed'] is False
    assert partial['effective_gate_blockers'] == ['D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED']



def test_daily_effective_model_gate_accepts_explicit_verified_d0_d1():
    import webui.daily_ohlcv_dashboard as daily_dashboard

    gate = daily_dashboard._effective_daily_model_gate(
        db={
            'price_basis': 'raw',
            'price_basis_status': 'RAW_VERIFIED',
            'decision_grade_return_status': 'READY',
        },
        universe={'verdict': 'OFFICIAL_OR_MANUAL_REVIEWED', 'universe_review_status': 'OFFICIAL_OR_MANUAL_REVIEWED', 'official_metadata_status': 'OFFICIAL_VERIFIED', 'official_metadata_coverage_status': 'COMPLETE', 'universe_certification_status': 'OFFICIAL_OR_MANUAL_REVIEWED'},
        prediction={
            'baseline_delta_summary': {'model_build_allowed': True},
            'verdict': {'go_summary_allowed': True},
        },
        gate_verdict={'model_build_allowed': True, 'go_summary_allowed': True},
        gate_status='PASS',
    )

    assert gate['model_build_allowed'] is True
    assert gate['effective_gate_blockers'] == []


def test_daily_registry_invariants_require_explicit_effective_gate_and_verified_d0_d1():
    import webui.daily_ohlcv_dashboard as daily_dashboard

    errors = daily_dashboard._registry_artifact_invariant_errors(
        {
            'guardrail': 'research-only no live/broker/orders no profit',
            'model_build_allowed': True,
            'paper_forward_allowed': True,
            'live_broker_order_allowed': False,
            'no_live_broker_order_readiness': True,
        },
        {
            'candidates': [
                {
                    'config_hash': 'a' * 64,
                    'data_hash': 'b' * 64,
                    'code_hash': 'c' * 64,
                    'source_hashes': {
                        'stom_rl/daily_rl_train.py': 'd' * 64,
                        'stom_rl/daily_walk_forward.py': 'e' * 64,
                        'stom_rl/daily_registry.py': 'f' * 64,
                        'webui/daily_ohlcv_dashboard.py': '1' * 64,
                        'webui/app.py': '2' * 64,
                        'webui/v2_src/src/lib/dailyOhlcvApi.ts': '3' * 64,
                        'webui/v2_src/src/tabs/DailyOhlcvTab.svelte': '4' * 64,
                        'webui/v2_src/src/tabs/dailyOhlcv/DailyProgressTimeline.svelte': '5' * 64,
                        'webui/v2_src/src/tabs/dailyOhlcv/DailyVisualLabCard.svelte': '6' * 64,
                    },
                    'live_broker_order_allowed': False,
                    'no_live_broker_order_readiness': True,
                    'd4_status': 'PASS',
                    'd5_status': 'PASS',
                    'baseline_delta_vs_best_d3': 0.1,
                    'model_build_allowed': True,
                    'paper_forward_allowed': True,
                }
            ]
        },
    )

    assert 'REGISTRY_CANDIDATE_0_EFFECTIVE_GATE_BLOCKERS_MISSING' in errors
    assert 'REGISTRY_MANIFEST_MODEL_BUILD_TRUE_WITHOUT_SAFE_CANDIDATE' in errors
    assert 'REGISTRY_MANIFEST_PAPER_FORWARD_TRUE_WITHOUT_SAFE_CANDIDATE' in errors


def test_daily_walk_forward_heatmap_applies_effective_gate(monkeypatch, tmp_path):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / 'walk_forward'
    run_dir = root / 'optimistic_heatmap'
    run_dir.mkdir(parents=True)
    (run_dir / 'walk_forward_manifest.json').write_text(
        json.dumps({'run_id': 'optimistic_heatmap', 'verdict': {'status': 'PASS'}}),
        encoding='utf-8',
    )
    (run_dir / 'gate_verdict.json').write_text(
        json.dumps({
            'status': 'PASS',
            'selected_strategy': 'optimistic',
            'model_build_allowed': True,
            'go_summary_allowed': True,
            'n_folds': 5,
            'no_oos_retuning': True,
        }),
        encoding='utf-8',
    )
    (run_dir / 'fold_metrics.csv').write_text(
        'fold_id,strategy,control,total_net_return,max_drawdown,delta_vs_no_trade_total_net_return,delta_vs_shuffled_total_net_return,mean_turnover,hit_rate\n'
        'F01,optimistic,actual,0.1,-0.02,0.1,0.1,0.1,0.6\n',
        encoding='utf-8',
    )
    (run_dir / 'cost_sensitivity.csv').write_text(
        'fold_id,strategy,cost_bp,total_net_return,max_drawdown\n'
        'F01,optimistic,23,0.1,-0.02\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(daily_dashboard, 'DEFAULT_WALK_FORWARD_ROOT', root)
    monkeypatch.setattr(
        daily_dashboard,
        'load_daily_db_summary',
        lambda **_: {
            'price_basis': 'unknown',
            'price_basis_status': 'UNKNOWN_CONFIRMED',
            'decision_grade_return_status': 'BLOCKED_UNTIL_PRICE_BASIS_VERIFIED',
        },
    )
    monkeypatch.setattr(
        daily_dashboard,
        'load_universe_preview',
        lambda **_: {'verdict': 'WATCH_HEURISTIC_UNIVERSE', 'official_metadata_status': 'MISSING'},
    )
    monkeypatch.setattr(
        daily_dashboard,
        'load_prediction_latest',
        lambda **_: {
            'baseline_delta_summary': {'model_build_allowed': True},
            'verdict': {'go_summary_allowed': True},
        },
    )

    payload = daily_dashboard.load_walk_forward_heatmap_chart(run='optimistic_heatmap')

    assert payload['status'] == 'NO-GO'
    assert payload['readiness_status'] == 'D5_NO_GO_RESEARCH_ONLY_GATE'
    assert payload['model_build_allowed'] is False
    assert payload['go_summary_allowed'] is False
    assert payload['paper_forward_allowed'] is False
    assert payload['live_broker_order_allowed'] is False
    assert payload['effective_gate_blockers'] == [
        'D0_PRICE_BASIS_NOT_VERIFIED',
        'D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED',
        'D5_WALK_FORWARD_NOT_PASS',
    ]


def _registry_required_sources(fake_hash: str) -> dict[str, str]:
    return {
        'stom_rl/daily_rl_train.py': fake_hash,
        'stom_rl/daily_walk_forward.py': fake_hash,
        'stom_rl/daily_registry.py': fake_hash,
        'webui/daily_ohlcv_dashboard.py': fake_hash,
        'webui/app.py': fake_hash,
        'webui/v2_src/src/lib/dailyOhlcvApi.ts': fake_hash,
        'webui/v2_src/src/tabs/DailyOhlcvTab.svelte': fake_hash,
        'webui/v2_src/src/tabs/dailyOhlcv/DailyProgressTimeline.svelte': fake_hash,
        'webui/v2_src/src/tabs/dailyOhlcv/DailyVisualLabCard.svelte': fake_hash,
    }


def _write_registry_safe_manifest_and_candidate(run_dir: Path, fake_hash: str) -> None:
    (run_dir / 'registry_manifest.json').write_text(
        json.dumps(
            {
                'schema_version': 1,
                'run_id': run_dir.name,
                'status': 'RESEARCH_ONLY_BLOCKED',
                'guardrail': 'Research-only no live/broker/orders no profit claim evidence',
                'model_build_allowed': False,
                'paper_forward_allowed': False,
                'live_broker_order_allowed': False,
                'no_live_broker_order_readiness': True,
                'config_hash': fake_hash,
                'data_hash': fake_hash,
                'code_hash': fake_hash,
                'effective_gate_blockers': ['D5_WALK_FORWARD_NOT_PASS'],
            }
        ),
        encoding='utf-8',
    )
    (run_dir / 'candidate_registry.json').write_text(
        json.dumps(
            {
                'candidates': [
                    {
                        'candidate_id': 'blocked-candidate',
                        'd4_status': 'RESEARCH_ONLY',
                        'd5_status': 'NO-GO',
                        'model_build_allowed': False,
                        'paper_forward_allowed': False,
                        'live_broker_order_allowed': False,
                        'no_live_broker_order_readiness': True,
                        'config_hash': fake_hash,
                        'data_hash': fake_hash,
                        'code_hash': fake_hash,
                        'source_hashes': _registry_required_sources(fake_hash),
                        'effective_gate_blockers': ['D5_WALK_FORWARD_NOT_PASS'],
                    }
                ]
            }
        ),
        encoding='utf-8',
    )


def _write_registry_nonempty_evidence(run_dir: Path) -> None:
    (run_dir / 'paper_selected.csv').write_text(
        'date,code,rank,paper_weight,paper_only_selected,selection_status,strategy,reason\n'
        '20260614,000250,1,0,false,BLOCKED_BY_D5_NO_GO,equal_weight_topk_momentum,D5_WALK_FORWARD_NOT_PASS\n',
        encoding='utf-8',
    )
    (run_dir / 'realized_returns.csv').write_text(
        'date,split,paper_nav,realized_return,policy_reward,current_drawdown,evidence_status,numeric_error,source\n'
        '20260614,test,1.0,0.0,0.0,0.0,COMPLETE_NUMERIC_EVIDENCE,,policy_nav_research_artifact_not_live_trade\n',
        encoding='utf-8',
    )
    (run_dir / 'drift.csv').write_text(
        'metric,value,reference,status,action\n'
        'd5_gate_status,NO-GO,NO-GO blocks model build,BLOCKED,block promotion when D5 is not PASS\n',
        encoding='utf-8',
    )
    (run_dir / 'drawdown.csv').write_text(
        'date,split,paper_nav,paper_forward_drawdown,computed_drawdown,evidence_status,numeric_error,source\n'
        '20260614,test,1.0,0.0,0.0,COMPLETE_NUMERIC_EVIDENCE,,research_policy_nav_not_live_account\n',
        encoding='utf-8',
    )
    (run_dir / 'decision_log.jsonl').write_text(
        json.dumps({'event': 'live_broker_order_blocked', 'status': 'BLOCKED'}) + '\n',
        encoding='utf-8',
    )


def test_daily_registry_api_blocks_unsafe_generated_artifact(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    root = tmp_path / "registry"
    run_dir = root / "unsafe_registry"
    run_dir.mkdir(parents=True)
    (run_dir / "registry_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "unsafe_registry",
                "status": "PAPER_ONLY_REVIEW_REQUIRED",
                "guardrail": "unsafe optimistic artifact",
                "model_build_allowed": True,
                "paper_forward_allowed": True,
                "live_broker_order_allowed": True,
                "no_live_broker_order_readiness": False,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "candidate_registry.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "unsafe",
                        "d4_status": "RESEARCH_ONLY",
                        "d5_status": "NO-GO",
                        "model_build_allowed": True,
                        "paper_forward_allowed": True,
                        "live_broker_order_allowed": True,
                        "no_live_broker_order_readiness": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for name in ["paper_selected.csv", "realized_returns.csv", "drift.csv", "drawdown.csv"]:
        (run_dir / name).write_text("\n", encoding="utf-8")
    (run_dir / "decision_log.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(daily_dashboard, "DEFAULT_DAILY_REGISTRY_ROOT", root)

    client = flask_app.test_client()
    response = client.get("/api/daily-ohlcv/registry/latest?run=unsafe_registry")
    assert response.status_code == 200
    payload = response.get_json()
    candidate = payload["candidate_registry"]["candidates"][0]
    assert payload["status"] == "BLOCKED_UNSAFE_REGISTRY_ARTIFACT"
    assert payload["model_build_allowed"] is False
    assert payload["paper_forward_allowed"] is False
    assert payload["live_broker_order_allowed"] is False
    assert payload["no_live_broker_order_readiness"] is True
    assert candidate["model_build_allowed"] is False
    assert candidate["paper_forward_allowed"] is False
    assert candidate["live_broker_order_allowed"] is False
    assert candidate["no_live_broker_order_readiness"] is True
    assert "REGISTRY_MANIFEST_LIVE_BROKER_ORDER_NOT_FALSE" in payload["invariant_errors"]
    assert "no live/broker/orders" in payload["guardrail"]



def test_daily_registry_api_blocks_malformed_json_artifacts(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    fake_hash = 'e' * 64
    root = tmp_path / 'registry'
    run_dir = root / 'malformed_registry'
    run_dir.mkdir(parents=True)
    (run_dir / 'registry_manifest.json').write_text('{not-json', encoding='utf-8')
    (run_dir / 'candidate_registry.json').write_text(
        json.dumps({'candidates': [{'candidate_id': 'blocked', 'model_build_allowed': False, 'paper_forward_allowed': False, 'live_broker_order_allowed': False, 'no_live_broker_order_readiness': True, 'config_hash': fake_hash, 'data_hash': fake_hash, 'code_hash': fake_hash, 'source_hashes': _registry_required_sources(fake_hash), 'effective_gate_blockers': ['D5_WALK_FORWARD_NOT_PASS']}]}),
        encoding='utf-8',
    )
    _write_registry_nonempty_evidence(run_dir)
    monkeypatch.setattr(daily_dashboard, 'DEFAULT_DAILY_REGISTRY_ROOT', root)

    payload = flask_app.test_client().get('/api/daily-ohlcv/registry/latest?run=malformed_registry').get_json()

    assert payload['status'] == 'BLOCKED_UNSAFE_REGISTRY_ARTIFACT'
    assert payload['model_build_allowed'] is False
    assert payload['paper_forward_allowed'] is False
    assert 'REGISTRY_MANIFEST_JSON_INVALID' in payload['invariant_errors']


def test_daily_registry_api_blocks_malformed_decision_log_jsonl(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    fake_hash = 'f' * 64
    root = tmp_path / 'registry'
    run_dir = root / 'malformed_decision_log'
    run_dir.mkdir(parents=True)
    _write_registry_safe_manifest_and_candidate(run_dir, fake_hash)
    _write_registry_nonempty_evidence(run_dir)
    (run_dir / 'decision_log.jsonl').write_text('{not-json\n', encoding='utf-8')
    monkeypatch.setattr(daily_dashboard, 'DEFAULT_DAILY_REGISTRY_ROOT', root)

    payload = flask_app.test_client().get('/api/daily-ohlcv/registry/latest?run=malformed_decision_log').get_json()

    assert payload['status'] == 'BLOCKED_UNSAFE_REGISTRY_ARTIFACT'
    assert 'REGISTRY_DECISION_LOG_JSONL_INVALID' in payload['invariant_errors']
    assert payload['samples']['decision_log'] == []


def test_daily_registry_api_blocks_missing_or_empty_evidence_files(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    fake_hash = '0' * 64
    root = tmp_path / 'registry'
    run_dir = root / 'empty_evidence_registry'
    run_dir.mkdir(parents=True)
    _write_registry_safe_manifest_and_candidate(run_dir, fake_hash)
    (run_dir / 'paper_selected.csv').write_text('date,selection_status\n', encoding='utf-8')
    (run_dir / 'realized_returns.csv').write_text('', encoding='utf-8')
    (run_dir / 'drift.csv').write_text('metric,value\nprice_basis,unknown\n', encoding='utf-8')
    (run_dir / 'decision_log.jsonl').write_text('', encoding='utf-8')
    monkeypatch.setattr(daily_dashboard, 'DEFAULT_DAILY_REGISTRY_ROOT', root)

    payload = flask_app.test_client().get('/api/daily-ohlcv/registry/latest?run=empty_evidence_registry').get_json()

    assert payload['status'] == 'BLOCKED_UNSAFE_REGISTRY_ARTIFACT'
    assert 'REGISTRY_EVIDENCE_PAPER_SELECTED_EMPTY' in payload['invariant_errors']
    assert 'REGISTRY_EVIDENCE_REALIZED_RETURNS_HEADER_MISSING' in payload['invariant_errors']
    assert 'REGISTRY_EVIDENCE_DRAWDOWN_MISSING' in payload['invariant_errors']
    assert 'REGISTRY_EVIDENCE_DECISION_LOG_EMPTY' in payload['invariant_errors']


def test_daily_registry_api_blocks_wrong_column_and_invalid_csv_evidence(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    fake_hash = '1' * 64
    root = tmp_path / 'registry'
    run_dir = root / 'bad_csv_registry'
    run_dir.mkdir(parents=True)
    _write_registry_safe_manifest_and_candidate(run_dir, fake_hash)
    (run_dir / 'paper_selected.csv').write_text('foo\nbar\n', encoding='utf-8')
    (run_dir / 'realized_returns.csv').write_bytes(b'\xff\xfe\x00\x00')
    (run_dir / 'drift.csv').write_text('metric,value,reference,status,action\nprice_basis,unknown,required,BLOCKED,keep locked\n', encoding='utf-8')
    (run_dir / 'drawdown.csv').write_text(
        'date,split,paper_nav,paper_forward_drawdown,computed_drawdown,evidence_status,numeric_error,source\n'
        '20260614,test,1.0,0.0,0.0,COMPLETE_NUMERIC_EVIDENCE,,research_policy_nav_not_live_account\n',
        encoding='utf-8',
    )
    (run_dir / 'decision_log.jsonl').write_text(json.dumps({'event': 'registry_created', 'status': 'RESEARCH_ONLY'}) + '\n', encoding='utf-8')
    monkeypatch.setattr(daily_dashboard, 'DEFAULT_DAILY_REGISTRY_ROOT', root)

    payload = flask_app.test_client().get('/api/daily-ohlcv/registry/latest?run=bad_csv_registry').get_json()

    assert payload['status'] == 'BLOCKED_UNSAFE_REGISTRY_ARTIFACT'
    assert 'REGISTRY_EVIDENCE_PAPER_SELECTED_COLUMNS_INVALID' in payload['invariant_errors']
    assert 'REGISTRY_EVIDENCE_REALIZED_RETURNS_INVALID' in payload['invariant_errors']
    assert payload['samples']['realized_returns'] == []

def test_daily_registry_api_blocks_missing_hash_evidence(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    fake_hash = "a" * 64
    root = tmp_path / "registry"
    run_dir = root / "missing_hash_registry"
    run_dir.mkdir(parents=True)
    (run_dir / "registry_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "missing_hash_registry",
                "status": "RESEARCH_ONLY_BLOCKED",
                "guardrail": "Research-only no live/broker/orders evidence",
                "model_build_allowed": False,
                "paper_forward_allowed": False,
                "live_broker_order_allowed": False,
                "no_live_broker_order_readiness": True,
                "config_hash": fake_hash,
                "data_hash": fake_hash,
                "code_hash": "not-a-sha",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "candidate_registry.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "missing-hash",
                        "d4_status": "RESEARCH_ONLY",
                        "d5_status": "NO-GO",
                        "model_build_allowed": False,
                        "paper_forward_allowed": False,
                        "live_broker_order_allowed": False,
                        "no_live_broker_order_readiness": True,
                        "config_hash": fake_hash,
                        "data_hash": fake_hash,
                        "code_hash": fake_hash,
                        "source_hashes": {"stom_rl/daily_registry.py": fake_hash},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for name in ["paper_selected.csv", "realized_returns.csv", "drift.csv", "drawdown.csv"]:
        (run_dir / name).write_text("\n", encoding="utf-8")
    (run_dir / "decision_log.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(daily_dashboard, "DEFAULT_DAILY_REGISTRY_ROOT", root)

    client = flask_app.test_client()
    payload = client.get("/api/daily-ohlcv/registry/latest?run=missing_hash_registry").get_json()
    assert payload["status"] == "BLOCKED_UNSAFE_REGISTRY_ARTIFACT"
    assert "REGISTRY_MANIFEST_CODE_HASH_INVALID" in payload["invariant_errors"]
    assert any(error.startswith("REGISTRY_CANDIDATE_0_SOURCE_HASH_INVALID_webui/app.py") for error in payload["invariant_errors"])


def test_daily_registry_api_blocks_manifest_only_optimistic_flags(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    fake_hash = "b" * 64
    required_sources = {
        "stom_rl/daily_rl_train.py": fake_hash,
        "stom_rl/daily_walk_forward.py": fake_hash,
        "stom_rl/daily_registry.py": fake_hash,
        "webui/daily_ohlcv_dashboard.py": fake_hash,
        "webui/app.py": fake_hash,
    }
    root = tmp_path / "registry"
    run_dir = root / "manifest_optimistic_registry"
    run_dir.mkdir(parents=True)
    (run_dir / "registry_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "manifest_optimistic_registry",
                "status": "PAPER_ONLY_REVIEW_REQUIRED",
                "guardrail": "Research-only no live/broker/orders evidence",
                "model_build_allowed": True,
                "paper_forward_allowed": True,
                "live_broker_order_allowed": False,
                "no_live_broker_order_readiness": True,
                "config_hash": fake_hash,
                "data_hash": fake_hash,
                "code_hash": fake_hash,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "candidate_registry.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "blocked-candidate",
                        "d4_status": "RESEARCH_ONLY",
                        "d5_status": "NO-GO",
                        "model_build_allowed": False,
                        "paper_forward_allowed": False,
                        "live_broker_order_allowed": False,
                        "no_live_broker_order_readiness": True,
                        "config_hash": fake_hash,
                        "data_hash": fake_hash,
                        "code_hash": fake_hash,
                        "source_hashes": required_sources,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for name in ["paper_selected.csv", "realized_returns.csv", "drift.csv", "drawdown.csv"]:
        (run_dir / name).write_text("\n", encoding="utf-8")
    (run_dir / "decision_log.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(daily_dashboard, "DEFAULT_DAILY_REGISTRY_ROOT", root)

    client = flask_app.test_client()
    payload = client.get("/api/daily-ohlcv/registry/latest?run=manifest_optimistic_registry").get_json()
    assert payload["status"] == "BLOCKED_UNSAFE_REGISTRY_ARTIFACT"
    assert payload["model_build_allowed"] is False
    assert payload["paper_forward_allowed"] is False
    assert "REGISTRY_MANIFEST_MODEL_BUILD_TRUE_WITHOUT_SAFE_CANDIDATE" in payload["invariant_errors"]
    assert "REGISTRY_MANIFEST_PAPER_FORWARD_TRUE_WITHOUT_SAFE_CANDIDATE" in payload["invariant_errors"]


def test_daily_registry_api_blocks_candidate_optimistic_without_d4_pass(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    fake_hash = "c" * 64
    required_sources = {
        "stom_rl/daily_rl_train.py": fake_hash,
        "stom_rl/daily_walk_forward.py": fake_hash,
        "stom_rl/daily_registry.py": fake_hash,
        "webui/daily_ohlcv_dashboard.py": fake_hash,
        "webui/app.py": fake_hash,
    }
    root = tmp_path / "registry"
    run_dir = root / "candidate_optimistic_registry"
    run_dir.mkdir(parents=True)
    (run_dir / "registry_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "candidate_optimistic_registry",
                "status": "PAPER_ONLY_REVIEW_REQUIRED",
                "guardrail": "Research-only no live/broker/orders evidence",
                "model_build_allowed": True,
                "paper_forward_allowed": True,
                "live_broker_order_allowed": False,
                "no_live_broker_order_readiness": True,
                "config_hash": fake_hash,
                "data_hash": fake_hash,
                "code_hash": fake_hash,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "candidate_registry.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "unsafe-d4-watch",
                        "d4_status": "WATCH",
                        "d5_status": "PASS",
                        "model_build_allowed": True,
                        "paper_forward_allowed": True,
                        "live_broker_order_allowed": False,
                        "no_live_broker_order_readiness": True,
                        "config_hash": fake_hash,
                        "data_hash": fake_hash,
                        "code_hash": fake_hash,
                        "source_hashes": required_sources,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for name in ["paper_selected.csv", "realized_returns.csv", "drift.csv", "drawdown.csv"]:
        (run_dir / name).write_text("\n", encoding="utf-8")
    (run_dir / "decision_log.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(daily_dashboard, "DEFAULT_DAILY_REGISTRY_ROOT", root)

    client = flask_app.test_client()
    payload = client.get("/api/daily-ohlcv/registry/latest?run=candidate_optimistic_registry").get_json()
    assert payload["status"] == "BLOCKED_UNSAFE_REGISTRY_ARTIFACT"
    assert payload["model_build_allowed"] is False
    assert payload["paper_forward_allowed"] is False
    assert "REGISTRY_CANDIDATE_0_MODEL_BUILD_TRUE_WITH_LOCKED_GATES" in payload["invariant_errors"]
    assert "REGISTRY_CANDIDATE_0_PAPER_FORWARD_TRUE_WITH_LOCKED_GATES" in payload["invariant_errors"]

def test_daily_registry_api_blocks_candidate_optimistic_with_missing_baseline_delta(tmp_path, monkeypatch):
    import webui.daily_ohlcv_dashboard as daily_dashboard

    fake_hash = "d" * 64
    required_sources = {
        "stom_rl/daily_rl_train.py": fake_hash,
        "stom_rl/daily_walk_forward.py": fake_hash,
        "stom_rl/daily_registry.py": fake_hash,
        "webui/daily_ohlcv_dashboard.py": fake_hash,
        "webui/app.py": fake_hash,
        "webui/v2_src/src/lib/dailyOhlcvApi.ts": fake_hash,
        "webui/v2_src/src/tabs/DailyOhlcvTab.svelte": fake_hash,
        "webui/v2_src/src/tabs/dailyOhlcv/DailyProgressTimeline.svelte": fake_hash,
        "webui/v2_src/src/tabs/dailyOhlcv/DailyVisualLabCard.svelte": fake_hash,
    }
    root = tmp_path / "registry"
    run_dir = root / "candidate_missing_baseline_delta"
    run_dir.mkdir(parents=True)
    (run_dir / "registry_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "candidate_missing_baseline_delta",
                "status": "PAPER_ONLY_REVIEW_REQUIRED",
                "guardrail": "Research-only no live/broker/orders evidence",
                "model_build_allowed": True,
                "paper_forward_allowed": True,
                "live_broker_order_allowed": False,
                "no_live_broker_order_readiness": True,
                "config_hash": fake_hash,
                "data_hash": fake_hash,
                "code_hash": fake_hash,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "candidate_registry.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "unsafe-missing-d3",
                        "d4_status": "PASS",
                        "d5_status": "PASS",
                        "model_build_allowed": True,
                        "paper_forward_allowed": True,
                        "live_broker_order_allowed": False,
                        "no_live_broker_order_readiness": True,
                        "price_basis": "adjusted_verified",
                        "universe_review_status": "OFFICIAL_COMMON_EQUITY_REVIEWED",
                        "config_hash": fake_hash,
                        "data_hash": fake_hash,
                        "code_hash": fake_hash,
                        "source_hashes": required_sources,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for name in ["paper_selected.csv", "realized_returns.csv", "drift.csv", "drawdown.csv"]:
        (run_dir / name).write_text("\n", encoding="utf-8")
    (run_dir / "decision_log.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(daily_dashboard, "DEFAULT_DAILY_REGISTRY_ROOT", root)

    client = flask_app.test_client()
    payload = client.get("/api/daily-ohlcv/registry/latest?run=candidate_missing_baseline_delta").get_json()
    assert payload["status"] == "BLOCKED_UNSAFE_REGISTRY_ARTIFACT"
    assert payload["model_build_allowed"] is False
    assert payload["paper_forward_allowed"] is False
    assert "REGISTRY_CANDIDATE_0_MODEL_BUILD_TRUE_WITH_LOCKED_GATES" in payload["invariant_errors"]
    assert "REGISTRY_CANDIDATE_0_PAPER_FORWARD_TRUE_WITH_LOCKED_GATES" in payload["invariant_errors"]



def test_daily_ohlcv_unsafe_run_and_mutating_methods_rejected():
    client = flask_app.test_client()
    assert client.get('/api/daily-ohlcv/db-summary?run=..').status_code == 400
    assert client.get('/api/daily-ohlcv/universe/preview?run=..').status_code == 400
    assert client.get('/api/daily-ohlcv/dataset/latest?run=..').status_code == 400
    assert client.get('/api/daily-ohlcv/prediction/latest?run=..').status_code == 400
    assert client.get('/api/daily-ohlcv/portfolio/latest?run=..').status_code == 400
    assert client.get('/api/daily-ohlcv/walk-forward/latest?run=..').status_code == 400
    assert client.get('/api/daily-ohlcv/registry/latest?run=..').status_code == 400
    assert client.get('/api/daily-ohlcv/charts/equity-overlay?run=..').status_code == 400
    assert client.get('/api/daily-ohlcv/charts/walk-forward-heatmap?run=..').status_code == 400
    for path in [
        '/api/daily-ohlcv/db-summary',
        '/api/daily-ohlcv/universe/preview',
        '/api/daily-ohlcv/progress',
        '/api/daily-ohlcv/dataset/latest',
        '/api/daily-ohlcv/prediction/latest',
        '/api/daily-ohlcv/portfolio/latest',
        '/api/daily-ohlcv/walk-forward/latest',
        '/api/daily-ohlcv/registry/latest',
        '/api/daily-ohlcv/gate/latest',
        '/api/daily-ohlcv/charts/dataset',
        '/api/daily-ohlcv/charts/prediction',
        '/api/daily-ohlcv/charts/portfolio',
        '/api/daily-ohlcv/charts/walk-forward',
        '/api/daily-ohlcv/charts/decision-cockpit',
        '/api/daily-ohlcv/charts/flow',
        '/api/daily-ohlcv/charts/glossary',
        '/api/daily-ohlcv/charts/research-diagnostics',
        '/api/daily-ohlcv/charts/equity-overlay',
        '/api/daily-ohlcv/charts/walk-forward-heatmap',
        '/api/daily-ohlcv/charts/run-scatter',
        '/api/daily-ohlcv/charts/universe-breakdown',
        '/api/daily-ohlcv/charts/symbol/000250',
    ]:
        assert client.post(path).status_code == 405
        assert client.put(path).status_code == 405
        assert client.patch(path).status_code == 405
        assert client.delete(path).status_code == 405


def test_daily_ohlcv_progress_and_model_surfaces_are_locked():
    client = flask_app.test_client()
    progress = client.get('/api/daily-ohlcv/progress').get_json()
    assert progress['overall_status'] == 'D0_D9_EVIDENCE_VISIBLE_MODEL_BUILD_NO_GO'
    assert progress['model_build_allowed'] is False
    assert progress['go_summary_allowed'] is False
    statuses = {stage['id']: stage['status'] for stage in progress['stages']}
    assert statuses['D0'] == 'PASS'
    assert statuses['D1'] == 'WATCH'
    assert statuses['D2'] == 'PASS'
    assert statuses['D3'] == 'WATCH'
    assert statuses['D4'] == 'RESEARCH_ONLY'
    assert statuses['D5'] == 'NO-GO'
    assert statuses['D6'] == 'PASS'
    assert statuses['D7'] == 'WATCH'
    assert statuses['D8'] == 'RESEARCH_ONLY_BLOCKED'
    assert statuses['D9'] == 'BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER'
    assert 'no live/broker/orders' in progress['guardrail']
    assert len(progress['page_usage_guide']) == 10
    assert progress['stages'][6]['usage_guide']['stage'] == 'D6'
    assert progress['stages'][7]['usage_guide']['stage'] == 'D7'
    assert '시각화 곡선을 수익 보장' in progress['stages'][6]['must_not']
    flow = client.get('/api/daily-ohlcv/charts/flow').get_json()
    assert flow['nodes'][8]['severity'] == 'block'
    assert flow['nodes'][9]['severity'] == 'block'
    provenance = {row['id']: row for row in progress['provenance_matrix']}
    assert {'D0', 'D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8', 'D9'} <= set(provenance)
    assert 'UNKNOWN_CONFIRMED' in provenance['D0']['lock_labels']
    assert 'WATCH_HEURISTIC_UNIVERSE' in provenance['D1']['lock_labels']
    assert 'NO_FUTURE_LEAKAGE' in provenance['D2']['lock_labels']
    assert 'SHUFFLE_CONTROL' in provenance['D3']['lock_labels']
    assert 'RESEARCH_DIAGNOSTICS' in provenance['D7']['lock_labels']
    assert 'REGISTRY_HASHES' in provenance['D8']['lock_labels']
    assert 'PAPER_FORWARD_BLOCKED' in provenance['D9']['lock_labels']
    assert 'tests/test_stom_rl_daily_ohlcv_db.py' in progress['verification_commands']['D0'][0]
    assert 'tests/test_stom_rl_daily_prediction.py' in progress['verification_commands']['D3'][0]
    assert 'price_basis=unknown' in progress['stages'][0]['evidence']
    assert 'control=shuffle_control' in progress['stages'][3]['evidence']

    gate = client.get('/api/daily-ohlcv/gate/latest').get_json()
    assert gate['status'] == 'NO-GO'
    assert gate['model_build_allowed'] is False
    assert 'NO-GO/WATCH reasons' in gate['guardrail']
