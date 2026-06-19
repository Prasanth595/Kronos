from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SRC = REPO_ROOT / "webui" / "v2_src" / "src"
RL_COMPONENT_DIR = DASHBOARD_SRC / "tabs" / "rlTrading"


def _opening_source_text() -> str:
    files = [
        DASHBOARD_SRC / "lib" / "rlApi.ts",
        DASHBOARD_SRC / "tabs" / "RLTradingTab.svelte",
    ]
    files.extend(sorted(RL_COMPONENT_DIR.glob("OpeningWorkflowCard.svelte")))
    return "\n".join(path.read_text(encoding="utf-8") for path in files if path.is_file())


def test_rl_tab_contains_opening_workflow_guardrails():
    source = _opening_source_text()

    for marker in [
        "opening_30m_rl_workflow",
        "OPENING 30M RL WORKFLOW",
        "RL EXPERIMENT",
        "NO-GO",
        "not live-ready",
        "23bp",
        "ts_imb RULE baseline",
        "CUMULATIVE REWARD EVIDENCE",
        "data-rl-opening-workflow-card",
    ]:
        assert marker in source
    for forbidden in ["Cumulative profit curve", "start training", "broker action", "live order"]:
        assert forbidden not in source


def test_rl_tab_bundle_contains_opening_workflow_guardrails_when_built():
    dist = REPO_ROOT / "webui" / "static" / "v2" / "dist"
    if not dist.is_dir():
        return

    bundle_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (dist / "assets").glob("index-*.js")
    )
    for marker in [
        "OPENING 30M RL WORKFLOW",
        "RL EXPERIMENT",
        "NO-GO",
        "not live-ready",
        "23bp",
        "ts_imb RULE baseline",
    ]:
        assert marker in bundle_text
    assert "Cumulative profit curve" not in bundle_text
