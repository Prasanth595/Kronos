import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from stom_rl import daily_registry  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _synthetic_source_runs(tmp_path: Path) -> tuple[Path, Path]:
    portfolio = tmp_path / "portfolio" / "portfolio_000250"
    walk_forward = tmp_path / "walk_forward" / "walk_forward_000250"
    _write_json(
        portfolio / "rl_manifest.json",
        {
            "schema_version": 1,
            "run_id": "portfolio_000250",
            "prediction_manifest_sha": "pred-sha-000250",
            "price_basis": "unknown",
            "universe_review_status": "WATCH_HEURISTIC_UNIVERSE",
            "score_column": "score",
            "cost_assumption_round_trip_bp": 23,
            "guardrail": "RESEARCH_ONLY no live/broker/orders",
        },
    )
    _write_json(
        portfolio / "verdict.json",
        {
            "status": "RESEARCH_ONLY",
            "implementation_unlocked": False,
            "go_summary_allowed": False,
            "gate_dependency": "D3_WATCH_D5_NOT_RUN",
        },
    )
    _write_json(
        portfolio / "baseline_comparison.json",
        {
            "policy_strategy": "tabular_q_constrained_daily_portfolio_rl",
            "delta_vs_best_d3_total_net_return": -0.62,
            "cost_round_trip_bp": 23,
        },
    )
    _write_json(
        portfolio / "policy_evaluation_manifest.json",
        {
            "policy_baseline_comparison_rows": 6,
            "model_build_allowed": False,
            "no_live_broker_order_readiness": True,
        },
    )
    _write_csv(
        portfolio / "policy_nav.csv",
        [
            {"split": "val", "date": "2026-01-02", "policy_nav": 1.0, "policy_reward": 0.0, "policy_turnover": 0.0, "policy_concentration": 0.0, "policy_current_drawdown": 0.0},
            {"split": "test", "date": "2026-01-03", "policy_nav": 0.98, "policy_reward": -0.02, "policy_turnover": 0.0, "policy_concentration": 0.0, "policy_current_drawdown": -0.02},
        ],
        ["split", "date", "policy_nav", "policy_reward", "policy_turnover", "policy_concentration", "policy_current_drawdown"],
    )
    _write_json(
        walk_forward / "walk_forward_manifest.json",
        {
            "schema_version": 1,
            "run_id": "walk_forward_000250",
            "no_oos_retuning": True,
            "guardrail": "NO-GO no live/broker/orders",
        },
    )
    _write_json(
        walk_forward / "gate_verdict.json",
        {
            "status": "NO-GO",
            "model_build_allowed": False,
            "go_summary_allowed": False,
            "selected_strategy": "equal_weight_topk_momentum",
            "price_basis": "unknown",
            "universe_review_status": "WATCH_HEURISTIC_UNIVERSE",
            "cost_round_trip_bp": 23,
            "reasons": ["RL_POLICY_UNDERPERFORMS_D3_BASELINE"],
        },
    )
    _write_csv(
        walk_forward / "fold_metrics.csv",
        [{"fold_id": "F01", "strategy": "equal_weight_topk_momentum", "total_net_return": 0.01}],
        ["fold_id", "strategy", "total_net_return"],
    )
    return portfolio, walk_forward
def _write_clean_pass_gates(portfolio: Path, walk_forward: Path) -> None:
    _write_json(
        portfolio / "rl_manifest.json",
        {
            "schema_version": 1,
            "run_id": "portfolio_000250",
            "prediction_manifest_sha": "pred-sha-000250",
            "price_basis": "adjusted",
            "price_basis_status": "ADJUSTED_VERIFIED",
            "decision_grade_return_status": "READY",
            "verdict": "OFFICIAL_OR_MANUAL_REVIEWED",
            "universe_review_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "official_metadata_status": "OFFICIAL_VERIFIED",
            "official_metadata_coverage_status": "COMPLETE",
            "universe_certification_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "score_column": "score",
            "cost_assumption_round_trip_bp": 23,
            "guardrail": "RESEARCH_ONLY no live/broker/orders",
        },
    )
    _write_json(
        portfolio / "verdict.json",
        {
            "status": "PASS",
            "implementation_unlocked": True,
            "go_summary_allowed": True,
            "gate_dependency": "D5_PASS_SYNTHETIC",
        },
    )
    _write_json(
        walk_forward / "gate_verdict.json",
        {
            "status": "PASS",
            "model_build_allowed": True,
            "go_summary_allowed": True,
            "selected_strategy": "optimistic_daily_portfolio_rl",
            "price_basis": "adjusted",
            "price_basis_status": "ADJUSTED_VERIFIED",
            "decision_grade_return_status": "READY",
            "verdict": "OFFICIAL_OR_MANUAL_REVIEWED",
            "universe_review_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "official_metadata_status": "OFFICIAL_VERIFIED",
            "official_metadata_coverage_status": "COMPLETE",
            "universe_certification_status": "OFFICIAL_OR_MANUAL_REVIEWED",
            "cost_round_trip_bp": 23,
            "reasons": [],
        },
    )




def test_daily_registry_builds_blocked_research_only_payload(tmp_path: Path):
    portfolio, walk_forward = _synthetic_source_runs(tmp_path)

    result = daily_registry.build_daily_registry(portfolio_run_dir=portfolio, walk_forward_run_dir=walk_forward)

    manifest = result["manifest"]
    candidate = result["candidate_registry"]["candidates"][0]
    assert manifest["status"] == "RESEARCH_ONLY_BLOCKED"
    assert manifest["model_build_allowed"] is False
    assert manifest["live_broker_order_allowed"] is False
    assert "no live/broker/orders" in manifest["guardrail"]
    assert manifest["no_live_broker_order_readiness"] is True
    assert candidate["candidate_id"] == "portfolio_000250"
    assert candidate["promotion_status"] == "BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER"
    assert candidate["model_build_allowed"] is False
    assert candidate["paper_forward_allowed"] is False
    assert candidate["live_broker_order_allowed"] is False
    assert candidate["no_live_broker_order_readiness"] is True
    assert candidate["cost_round_trip_bp"] == 23
    assert "PRICE_BASIS_UNKNOWN" in candidate["reasons"]
    assert "UNIVERSE_WATCH_HEURISTIC" in candidate["reasons"]
    assert len(candidate["config_hash"]) == 64
    assert len(candidate["data_hash"]) == 64
    assert len(candidate["code_hash"]) == 64
    assert "webui/daily_ohlcv_dashboard.py" in candidate["source_hashes"]
    assert "webui/app.py" in candidate["source_hashes"]
    assert "webui/v2_src/src/lib/dailyOhlcvApi.ts" in candidate["source_hashes"]
    assert "webui/v2_src/src/tabs/DailyOhlcvTab.svelte" in candidate["source_hashes"]
    assert "webui/v2_src/src/tabs/dailyOhlcv/DailyProgressTimeline.svelte" in candidate["source_hashes"]
    assert "webui/v2_src/src/tabs/dailyOhlcv/DailyVisualLabCard.svelte" in candidate["source_hashes"]
    assert result["paper_selected"][0]["selection_status"] == "BLOCKED_BY_D5_NO_GO"
    assert result["paper_selected"][0]["paper_only_selected"] is False
    assert result["realized_returns"][1]["realized_return"] == pytest.approx(-0.02)
    assert result["drawdown"][1]["paper_forward_drawdown"] == pytest.approx(-0.02)
    drift_status = {row["metric"]: row["status"] for row in result["drift"]}
    assert drift_status["price_basis"] == "BLOCKED"
    assert drift_status["d5_gate_status"] == "BLOCKED"
    assert result["decision_log"][2]["event"] == "live_broker_order_blocked"
    assert drift_status["effective_model_gate"] == "BLOCKED"



def test_daily_registry_effective_gate_blocks_optimistic_d5_with_research_blockers(tmp_path: Path):
    portfolio, walk_forward = _synthetic_source_runs(tmp_path)
    _write_json(
        portfolio / "verdict.json",
        {
            "status": "PASS",
            "implementation_unlocked": True,
            "go_summary_allowed": True,
            "gate_dependency": "D5_PASS_SYNTHETIC",
        },
    )
    _write_json(
        portfolio / "baseline_comparison.json",
        {
            "policy_strategy": "optimistic_daily_portfolio_rl",
            "delta_vs_best_d3_total_net_return": 0.01,
            "cost_round_trip_bp": 23,
        },
    )
    _write_json(
        walk_forward / "gate_verdict.json",
        {
            "status": "PASS",
            "model_build_allowed": True,
            "go_summary_allowed": True,
            "selected_strategy": "optimistic_daily_portfolio_rl",
            "price_basis": "unknown",
            "universe_review_status": "WATCH_HEURISTIC_UNIVERSE",
            "cost_round_trip_bp": 23,
            "reasons": [],
        },
    )

    result = daily_registry.build_daily_registry(portfolio_run_dir=portfolio, walk_forward_run_dir=walk_forward)

    manifest = result["manifest"]
    candidate = result["candidate_registry"]["candidates"][0]
    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert candidate["model_build_allowed"] is False
    assert candidate["paper_forward_allowed"] is False
    assert candidate["promotion_status"] == "BLOCKED_RESEARCH_ONLY_NO_LIVE_BROKER_ORDER"
    assert candidate["effective_gate_blockers"] == [
        "D0_PRICE_BASIS_NOT_VERIFIED",
        "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED",
    ]
    assert result["paper_selected"][0]["selection_status"] == "BLOCKED_BY_EFFECTIVE_RESEARCH_GATE"
    assert "D0_PRICE_BASIS_NOT_VERIFIED" in result["paper_selected"][0]["reason"]
    drift_status = {row["metric"]: row["status"] for row in result["drift"]}
    assert drift_status["effective_model_gate"] == "BLOCKED"



def test_daily_registry_blocks_noncanonical_d0_d1_even_when_other_gates_pass(tmp_path: Path):
    portfolio, walk_forward = _synthetic_source_runs(tmp_path)
    _write_clean_pass_gates(portfolio, walk_forward)
    _write_json(
        portfolio / "rl_manifest.json",
        {
            "schema_version": 1,
            "run_id": "portfolio_000250",
            "prediction_manifest_sha": "pred-sha-000250",
            "price_basis": "adjusted_verified",
            "price_basis_status": "READY",
            "decision_grade_return_status": "READY",
            "verdict": "OFFICIAL_COMMON_EQUITY_REVIEWED",
            "universe_review_status": "OFFICIAL_COMMON_EQUITY_REVIEWED",
            "official_metadata_status": "OFFICIAL_VERIFIED",
            "official_metadata_coverage_status": "COMPLETE",
            "universe_certification_status": "OFFICIAL_COMMON_EQUITY_REVIEWED",
            "score_column": "score",
            "cost_assumption_round_trip_bp": 23,
            "guardrail": "RESEARCH_ONLY no live/broker/orders no profit claim",
        },
    )
    _write_json(
        portfolio / "baseline_comparison.json",
        {
            "policy_strategy": "optimistic_daily_portfolio_rl",
            "delta_vs_best_d3_total_net_return": 0.01,
            "cost_round_trip_bp": 23,
        },
    )

    result = daily_registry.build_daily_registry(portfolio_run_dir=portfolio, walk_forward_run_dir=walk_forward)

    candidate = result["candidate_registry"]["candidates"][0]
    assert candidate["effective_gate_blockers"] == [
        "D0_PRICE_BASIS_NOT_VERIFIED",
        "D1_UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED",
    ]
    assert candidate["model_build_allowed"] is False
    assert "PRICE_BASIS_NOT_VERIFIED" in candidate["reasons"]
    assert "UNIVERSE_NOT_OFFICIAL_OR_MANUAL_REVIEWED" in candidate["reasons"]
    drift_status = {row["metric"]: row["status"] for row in result["drift"]}
    assert drift_status["price_basis"] == "BLOCKED"
    assert drift_status["universe_review_status"] == "WATCH"

def test_daily_registry_blocks_missing_d3_baseline_evidence(tmp_path: Path):
    portfolio, walk_forward = _synthetic_source_runs(tmp_path)
    _write_clean_pass_gates(portfolio, walk_forward)
    (portfolio / "baseline_comparison.json").unlink()

    result = daily_registry.build_daily_registry(portfolio_run_dir=portfolio, walk_forward_run_dir=walk_forward)

    manifest = result["manifest"]
    candidate = result["candidate_registry"]["candidates"][0]
    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert candidate["effective_gate_blockers"] == ["D3_BASELINE_EVIDENCE_MISSING"]
    assert "D3_BASELINE_EVIDENCE_MISSING" in candidate["reasons"]
    assert result["paper_selected"][0]["selection_status"] == "BLOCKED_BY_EFFECTIVE_RESEARCH_GATE"
    drift = {row["metric"]: row["value"] for row in result["drift"]}
    assert "D3_BASELINE_EVIDENCE_MISSING" in drift["effective_model_gate"]


def test_daily_registry_blocks_missing_policy_nav_evidence(tmp_path: Path):
    portfolio, walk_forward = _synthetic_source_runs(tmp_path)
    _write_clean_pass_gates(portfolio, walk_forward)
    _write_json(
        portfolio / "baseline_comparison.json",
        {
            "policy_strategy": "optimistic_daily_portfolio_rl",
            "delta_vs_best_d3_total_net_return": 0.01,
            "cost_round_trip_bp": 23,
        },
    )
    (portfolio / "policy_nav.csv").unlink()

    result = daily_registry.build_daily_registry(portfolio_run_dir=portfolio, walk_forward_run_dir=walk_forward)

    manifest = result["manifest"]
    candidate = result["candidate_registry"]["candidates"][0]
    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert candidate["effective_gate_blockers"] == ["D9_POLICY_NAV_EVIDENCE_MISSING"]
    assert result["realized_returns"][0]["evidence_status"] == "BLOCKED_MISSING_POLICY_NAV"
    assert result["realized_returns"][0]["numeric_error"] == "POLICY_NAV_CSV_MISSING"
    assert result["drawdown"][0]["evidence_status"] == "BLOCKED_MISSING_POLICY_NAV"
    assert result["paper_selected"][0]["selection_status"] == "BLOCKED_BY_EFFECTIVE_RESEARCH_GATE"


def test_daily_registry_blocks_empty_policy_nav_evidence(tmp_path: Path):
    portfolio, walk_forward = _synthetic_source_runs(tmp_path)
    _write_clean_pass_gates(portfolio, walk_forward)
    _write_json(
        portfolio / "baseline_comparison.json",
        {
            "policy_strategy": "optimistic_daily_portfolio_rl",
            "delta_vs_best_d3_total_net_return": 0.01,
            "cost_round_trip_bp": 23,
        },
    )
    _write_csv(
        portfolio / "policy_nav.csv",
        [],
        ["split", "date", "policy_nav", "policy_reward", "policy_turnover", "policy_concentration", "policy_current_drawdown"],
    )

    result = daily_registry.build_daily_registry(portfolio_run_dir=portfolio, walk_forward_run_dir=walk_forward)

    manifest = result["manifest"]
    candidate = result["candidate_registry"]["candidates"][0]
    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert candidate["effective_gate_blockers"] == ["D9_POLICY_NAV_EVIDENCE_MISSING"]
    assert result["realized_returns"][0]["evidence_status"] == "BLOCKED_MISSING_POLICY_NAV"
    assert result["realized_returns"][0]["numeric_error"] == "POLICY_NAV_CSV_EMPTY"
    assert result["drawdown"][0]["evidence_status"] == "BLOCKED_MISSING_POLICY_NAV"
    assert result["drawdown"][0]["numeric_error"] == "POLICY_NAV_CSV_EMPTY"
    assert result["paper_selected"][0]["selection_status"] == "BLOCKED_BY_EFFECTIVE_RESEARCH_GATE"


def test_daily_registry_default_root_stays_under_webui_rl_runs():
    expected = REPO_ROOT / "webui" / "rl_runs" / "daily_ohlcv_registry"
    assert daily_registry.DEFAULT_DAILY_REGISTRY_ROOT.resolve() == expected.resolve()


def test_daily_registry_marks_invalid_policy_nav_numeric_evidence(tmp_path: Path):
    portfolio, walk_forward = _synthetic_source_runs(tmp_path)
    _write_clean_pass_gates(portfolio, walk_forward)
    _write_json(
        portfolio / "baseline_comparison.json",
        {
            "policy_strategy": "optimistic_daily_portfolio_rl",
            "delta_vs_best_d3_total_net_return": 0.01,
            "cost_round_trip_bp": 23,
        },
    )
    _write_csv(
        portfolio / "policy_nav.csv",
        [
            {"split": "test", "date": "2026-01-02", "policy_nav": "not-a-number", "policy_reward": "nan", "policy_turnover": 0, "policy_concentration": 0, "policy_current_drawdown": "bad"},
        ],
        ["split", "date", "policy_nav", "policy_reward", "policy_turnover", "policy_concentration", "policy_current_drawdown"],
    )

    result = daily_registry.build_daily_registry(portfolio_run_dir=portfolio, walk_forward_run_dir=walk_forward)
    manifest = result["manifest"]
    candidate = result["candidate_registry"]["candidates"][0]

    assert manifest["model_build_allowed"] is False
    assert manifest["paper_forward_allowed"] is False
    assert candidate["effective_gate_blockers"] == ["D9_POLICY_NAV_NUMERIC_EVIDENCE_INVALID"]
    realized = result["realized_returns"][0]
    drawdown = result["drawdown"][0]
    assert realized["paper_nav"] is None
    assert realized["realized_return"] is None
    assert realized["policy_reward"] is None
    assert realized["current_drawdown"] is None
    assert realized["evidence_status"] == "BLOCKED_NUMERIC_EVIDENCE"
    assert "INVALID_POLICY_NAV" in realized["numeric_error"]
    assert "INVALID_POLICY_REWARD" in realized["numeric_error"]
    assert "INVALID_POLICY_CURRENT_DRAWDOWN" in realized["numeric_error"]
    assert drawdown["paper_forward_drawdown"] is None
    assert drawdown["computed_drawdown"] is None
    assert drawdown["evidence_status"] == "BLOCKED_NUMERIC_EVIDENCE"


def test_daily_registry_writer_creates_expected_artifacts_and_rejects_unsafe_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    portfolio, walk_forward = _synthetic_source_runs(tmp_path)
    result = daily_registry.build_daily_registry(portfolio_run_dir=portfolio, walk_forward_run_dir=walk_forward)
    registry_root = tmp_path / "registry_root"
    monkeypatch.setattr(daily_registry, "DEFAULT_DAILY_REGISTRY_ROOT", registry_root)

    receipt = daily_registry.write_registry_artifacts(result, run_id="registry_000250", overwrite=False)
    out_dir = Path(receipt["artifact_dir"])

    assert (out_dir / "registry_manifest.json").exists()
    assert (out_dir / "candidate_registry.json").exists()
    assert (out_dir / "paper_selected.csv").exists()
    assert (out_dir / "realized_returns.csv").exists()
    assert (out_dir / "drift.csv").exists()
    assert (out_dir / "drawdown.csv").exists()
    assert (out_dir / "decision_log.jsonl").exists()
    manifest = json.loads((out_dir / "registry_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == "registry_000250"
    assert manifest["row_counts"]["decision_log_rows"] == 3

    with pytest.raises(FileExistsError):
        daily_registry.write_registry_artifacts(result, run_id="registry_000250", overwrite=False)
    with pytest.raises(ValueError):
        daily_registry.write_registry_artifacts(result, run_id="../bad", overwrite=True)
    with pytest.raises(ValueError):
        daily_registry.write_registry_artifacts(result, run_id="registry_outside", artifact_root=tmp_path / "outside", overwrite=True)
