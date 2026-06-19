import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DASHBOARD_SRC = REPO_ROOT / "webui" / "v2_src" / "src"
RL_COMPONENT_DIR = DASHBOARD_SRC / "tabs" / "rlTrading"

from webui import rl_dashboard  # noqa: E402
from webui.app import app as flask_app  # noqa: E402


def _write_csv(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8-sig")


def _write_participant_run(root: Path) -> None:
    run = root / "opening_participant_run"
    run.mkdir()
    (run / "opening_30m_rl_workflow_summary.json").write_text(
        json.dumps(
            {
                "artifact_type": "opening_30m_rl_workflow",
                "mode": "opening_30m_rl_workflow",
                "run_id": "opening_participant_run",
                "verdict": "NO-GO",
                "config": {"cost_bps": 23.0, "time_start": "090000", "time_end": "093000"},
                "proxy_availability": {"trade_strength": "available", "foreign_net_buy": "missing"},
                "missing_proxy_columns": ["외국인순매수"],
                "feature_ablation_results": {
                    "no_participant_pressure": {"verdict": "NO-GO", "baseline_delta_pct": -0.2}
                },
                "stages": [{"name": "controls", "status": "failed", "reason": "NO-GO"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )
    (run / "participant_pressure_readiness_summary.json").write_text(
        json.dumps(
            {
                "artifact_type": "participant_pressure_readiness",
                "proxy_availability": {"trade_strength": "available", "foreign_net_buy": "missing"},
                "missing_proxy_columns": ["외국인순매수"],
                "feature_schema": [
                    {"name": "trade_strength", "feature_group": "participant_pressure", "source_column": "체결강도"},
                    {"name": "foreign_net_buy", "feature_group": "participant_flow_optional", "source_column": "외국인순매수"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )
    (run / "orderbook_persistence_score_summary.json").write_text(
        json.dumps(
            {
                "artifact_type": "orderbook_persistence_score",
                "score": 0.62,
                "components": {"bid_depth_persistence": 0.8, "overheat_penalty": 0.3},
            }
        ),
        encoding="utf-8-sig",
    )
    _write_csv(
        run / "market_participant_study_groups.csv",
        "group,episode_count,verdict",
        ["absolute_ge_100b_krw,3,NO-GO_SAMPLE"],
    )
    _write_csv(
        run / "market_participant_study_episodes.csv",
        "episode_id,symbol,upper_wick_signal",
        ["000250_20250103,000250,True"],
    )


def _participant_source_text() -> str:
    files = [
        DASHBOARD_SRC / "lib" / "rlApi.ts",
        DASHBOARD_SRC / "tabs" / "RLTradingTab.svelte",
    ]
    files.extend(sorted(RL_COMPONENT_DIR.glob("ParticipantProxyCard.svelte")))
    return "\n".join(path.read_text(encoding="utf-8") for path in files if path.is_file())


def test_dashboard_displays_participant_proxy_evidence_guardrails(tmp_path, monkeypatch):
    _write_participant_run(tmp_path)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    proxy = rl_dashboard.load_rl_table("opening_participant_run", "proxy_availability", limit=10)
    orderbook = rl_dashboard.load_rl_table("opening_participant_run", "orderbook_persistence", limit=10)
    studies = rl_dashboard.load_rl_table("opening_participant_run", "participant_study_groups", limit=10)
    ablation = rl_dashboard.load_rl_table("opening_participant_run", "feature_ablation", limit=10)
    client = flask_app.test_client()
    response = client.get("/api/rl/runs/opening_participant_run/table/proxy_availability")
    source = _participant_source_text()

    assert response.status_code == 200
    assert proxy["rows"][0]["proxy"] == "trade_strength"
    assert proxy["rows"][1]["status"] == "missing"
    assert orderbook["rows"][0]["component"] == "bid_depth_persistence"
    assert studies["rows"][0]["group"] == "absolute_ge_100b_krw"
    assert ablation["rows"][0]["feature_ablation"] == "no_participant_pressure"
    for marker in ["PARTICIPANT PROXY EVIDENCE", "ORDERBOOK PERSISTENCE", "PROXY AVAILABILITY", "FEATURE ABLATION", "NO-GO", "not live-ready"]:
        assert marker in source


def test_dashboard_rejects_identity_and_profit_claim_copy(tmp_path, monkeypatch):
    _write_participant_run(tmp_path)
    monkeypatch.setattr(rl_dashboard, "RL_RUN_ROOTS", [tmp_path])

    with pytest.raises(ValueError, match="direct child|Invalid"):
        rl_dashboard.load_rl_table("../opening_participant_run", "proxy_availability")
    source = _participant_source_text()

    for forbidden in ["actual foreign buyer detected", "big-money actor identified", "profit model"]:
        assert forbidden not in source
