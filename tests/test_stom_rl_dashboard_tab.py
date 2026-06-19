from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SRC = REPO_ROOT / "webui" / "v2_src" / "src"
DASHBOARD_PACKAGE = REPO_ROOT / "webui" / "v2_src" / "package.json"
RL_COMPONENT_DIR = DASHBOARD_SRC / "tabs" / "rlTrading"


def _rl_source_text() -> str:
    files = [DASHBOARD_SRC / "tabs" / "RLTradingTab.svelte", DASHBOARD_SRC / "lib" / "rlApi.ts"]
    files.extend(sorted(RL_COMPONENT_DIR.glob("*")))
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def _public_copy_source_text() -> str:
    files = [
        DASHBOARD_PACKAGE,
        DASHBOARD_SRC / "app.css",
        DASHBOARD_SRC / "layout" / "Header.svelte",
        DASHBOARD_SRC / "layout" / "Sidebar.svelte",
        DASHBOARD_SRC / "tabs" / "ArtifactsModelsTab.svelte",
        DASHBOARD_SRC / "tabs" / "DocsTab.svelte",
        DASHBOARD_SRC / "tabs" / "SettingsTab.svelte",
        DASHBOARD_SRC / "tabs" / "SystemHealthTab.svelte",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def test_official_dashboard_sources_register_stom_rl_trading_tab():
    app = (DASHBOARD_SRC / "App.svelte").read_text(encoding="utf-8")
    sidebar = (DASHBOARD_SRC / "layout" / "Sidebar.svelte").read_text(encoding="utf-8")
    header = (DASHBOARD_SRC / "layout" / "Header.svelte").read_text(encoding="utf-8")
    source = _rl_source_text()

    assert "RLTradingTab" in app
    assert "tab === 'rl'" in app
    assert "path === '/rl'" in app
    assert "requested === 'rl-lab' || requested === 'rl-trading'" in app
    assert "id: 'rl'" in sidebar
    assert "label: 'RL Trading'" in sidebar
    assert "rl: 'RL Trading'" in header
    assert "data-rl-trading-tab" in source
    assert "data-rl-orderbook-readiness-card" in source
    assert "orderbook_rl_readiness" in source


def test_official_dashboard_public_copy_has_no_version_or_lab_labels():
    source = _public_copy_source_text()

    assert '"name": "kronos-dashboard"' in source
    assert "Kronos official dashboard" in source
    assert "Kronos \ub300\uc2dc\ubcf4\ub4dc" in source
    assert "RL Trading" in source
    for old_public_label in [
        "Kronos v2",
        "P1 \ubbf8\ub9ac\ubcf4\uae30",
        "P1.5",
        "RL Lab",
        "\uac15\ud654\ud559\uc2b5 \uc2e4\ud5d8\uc2e4",
        "\uc2e4\ud5d8\uc2e4",
        "KRONOS_V2_DIST",
    ]:
        assert old_public_label not in source


def test_rl_trading_tab_uses_read_only_rl_api_contracts():
    api = (DASHBOARD_SRC / "lib" / "rlApi.ts").read_text(encoding="utf-8")
    source = _rl_source_text()

    for marker in [
        "/api/rl/runs",
        "rlRuns",
        "rlRun",
        "rlActions",
        "rlTrades",
        "rlEquity",
        "rlEpisodes",
        "rlTable",
        "rlCostGate",
    ]:
        assert marker in api

    for marker in [
        "leaderboardChartOption",
        "costGateChartOption",
        "equityChartOption",
        "actionPnlChartOption",
        "tradeChartOption",
        "data-rl-leaderboard-table",
        "data-rl-leaderboard-chart",
        "data-rl-cost-gate-table",
        "data-rl-trade-table",
        "Kronos",
        "DQN/PPO",
        "25bp cost gate",
        "RULE MAINLINE",
        "RL EXPERIMENT",
        "ts_imb RULE baseline",
        "NO-GO",
        "not live-ready",
        "23bp",
        "ORDERBOOK RL READINESS",
        "market_buy",
        "market_exit",
        "readiness artifact",
        "CUMULATIVE REWARD EVIDENCE",
        "cumulative reward evidence",
        "ts_imb baseline",
        "markLine",
        "tooltipLines",
        "tooltipTitle",
    ]:
        assert marker in source
    assert "Cumulative profit curve" not in source


def test_rl_trading_tab_escapes_artifact_strings_in_chart_tooltips():
    source = _rl_source_text()
    helper = (DASHBOARD_SRC / "lib" / "safeHtml.ts").read_text(encoding="utf-8")

    assert "function escapeHtml" in helper
    assert ".replace(/</g, '&lt;')" in helper
    assert "from '$lib/safeHtml'" in source
    assert "tooltipTitle(" in source
    assert "tooltipText(" in source
    assert "`<strong>${row" not in source
    assert "`<strong>#${row" not in source
    assert "].filter(Boolean).join('<br/>')" not in source


def test_v2_dist_contains_rl_trading_bundle_marker_when_built():
    dist = REPO_ROOT / "webui" / "static" / "v2" / "dist"
    if not dist.is_dir():
        return

    bundle_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (dist / "assets").glob("index-*.js")
    )
    assert "RULE / RL EVIDENCE" in bundle_text
    assert "RULE MAINLINE" in bundle_text
    assert "RL EXPERIMENT" in bundle_text
    assert "ts_imb RULE baseline" in bundle_text
    assert "NO-GO" in bundle_text
    assert "not live-ready" in bundle_text
    assert "23bp" in bundle_text
    assert "data-rl-trading-tab" in bundle_text
    assert "data-rl-orderbook-readiness-card" in bundle_text
    assert "CUMULATIVE REWARD EVIDENCE" in bundle_text
    assert "Cumulative profit curve" not in bundle_text
    assert "ts_imb baseline" in bundle_text
    assert "/api/rl/runs" in bundle_text


def test_participant_proxy_card_uses_rule_filter_non_rl_label():
    source = (RL_COMPONENT_DIR / "ParticipantProxyCard.svelte").read_text(encoding="utf-8")

    assert "RULE FILTER EVIDENCE" in source
    assert "run?.strategy_context?.label" in source
    assert "run?.artifact_type === 'opening_30m_rule_filter'" in source
    assert "RL EXPERIMENT" not in source


def test_opening_workflow_card_uses_rule_filter_non_rl_label():
    source = (RL_COMPONENT_DIR / "OpeningWorkflowCard.svelte").read_text(encoding="utf-8")

    assert "isRuleFilterRun" in source
    assert "RULE FILTER evidence panel" in source
    assert "rule/meta-label evidence" in source
    assert "run?.artifact_type === 'opening_30m_rule_filter'" in source
