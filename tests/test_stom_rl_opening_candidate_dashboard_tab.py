from pathlib import Path


def test_rl_tab_renders_candidate_history_guardrails():
    source = Path("webui/v2_src/src/tabs/rlTrading/OpeningWorkflowCard.svelte").read_text(encoding="utf-8")

    assert "OPENING 30M RL CANDIDATES" in source
    assert "OOS" in source
    assert "negative controls" in source
    assert "feature ablation" in source
    assert "FEATURE ABLATION" in source
    assert "OOS BASELINE" in source
    assert "CONTEXT FEATURE SAMPLE" in source
    assert "FAILURE REASONS" in source
    assert "NO-GO" in source
    assert "23bp" in source
    assert "not live-ready" in source
    assert "ts_imb RULE baseline" in source
    assert "cumulative equity curve" in source
    assert "time-bucket" in source
