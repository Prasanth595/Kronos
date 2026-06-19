"""Unit tests for stom_rl.gap_up_dashboard_publish.

All tests use synthetic instances data (no real DB / filesystem dependencies
beyond tmp_path) and a monkeypatched RL_RUN_ROOTS so the dashboard loader
finds the test output without touching the production webui/rl_runs directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from stom_rl.gap_up_dashboard_publish import (
    _apply_filter,
    _build_equity_curve,
    _net_at_cost,
    publish_gap_up_run,
)


# ---------------------------------------------------------------------------
# Synthetic fixture data
# ---------------------------------------------------------------------------

def _make_record(
    *,
    session: str,
    symbol: str,
    net_pct_25bps: float,
    pass_ts: bool = True,
    pass_ts_imb: bool = True,
    entry_price: float = 10000.0,
    entry_change_rate: float = 3.0,
    entry_trade_strength: float = 120.0,
    entry_bid_ask_imbalance: float = 0.6,
) -> Dict[str, Any]:
    """Create a minimal synthetic instance record."""
    return {
        "symbol": symbol,
        "session": session,
        "split": "in_sample",
        "entry_change_rate": entry_change_rate,
        "entry_price": entry_price,
        "entry_trade_strength": entry_trade_strength,
        "entry_sec_amount": 100.0,
        "entry_bid_ask_imbalance": entry_bid_ask_imbalance,
        "pass_ts": pass_ts,
        "pass_ts_imb": pass_ts_imb,
        "tp5_sl1_net_pct": net_pct_25bps,
        "tp5_sl1_reason": "tp" if net_pct_25bps > 0 else "sl",
    }


# Five synthetic records: varied net, varied filter flags
SYNTHETIC_RECORDS: List[Dict[str, Any]] = [
    # A: pass_ts=True, pass_ts_imb=True, gain
    _make_record(session="20240101", symbol="000010", net_pct_25bps=2.0),
    # B: pass_ts=True, pass_ts_imb=False, loss
    _make_record(session="20240102", symbol="000020", net_pct_25bps=-0.5,
                 pass_ts=True, pass_ts_imb=False),
    # C: pass_ts=True, pass_ts_imb=True, gain
    _make_record(session="20240103", symbol="000030", net_pct_25bps=1.0),
    # D: pass_ts=False, pass_ts_imb=False, small gain
    _make_record(session="20240104", symbol="000040", net_pct_25bps=0.5,
                 pass_ts=False, pass_ts_imb=False),
    # E: pass_ts=True, pass_ts_imb=True, gain
    _make_record(session="20240105", symbol="000050", net_pct_25bps=3.0),
]


@pytest.fixture()
def instances_file(tmp_path: Path) -> Path:
    """Write synthetic records to a BOM-prefixed UTF-8 JSON file."""
    path = tmp_path / "instances.json"
    path.write_text(
        json.dumps(SYNTHETIC_RECORDS, ensure_ascii=False),
        encoding="utf-8-sig",
    )
    return path


# ---------------------------------------------------------------------------
# 1. test_equity_curve_non_compounded_matches_cumsum
# ---------------------------------------------------------------------------

def test_equity_curve_non_compounded_matches_cumsum() -> None:
    """NAV at each step equals initial_cash*(1+cumsum/100) within 1e-6."""
    records = [
        _make_record(session="20240101", symbol="A", net_pct_25bps=2.0),
        _make_record(session="20240102", symbol="B", net_pct_25bps=-0.5),
        _make_record(session="20240103", symbol="C", net_pct_25bps=1.5),
    ]
    initial_cash = 1_000_000.0
    cost_bps = 25.0  # same as base → no shift

    net_series, nav_series, final_cum = _build_equity_curve(
        records,
        tp_sl_key="tp5_sl1",
        cost_bps=cost_bps,
        initial_cash=initial_cash,
    )

    assert len(net_series) == 3
    assert len(nav_series) == 3

    # Verify each NAV step matches cumulative sum formula
    cum = 0.0
    for i, (net_i, nav_i) in enumerate(zip(net_series, nav_series)):
        cum += net_i
        expected_nav = initial_cash * (1.0 + cum / 100.0)
        assert abs(nav_i - expected_nav) < 1e-6, (
            f"Step {i}: nav={nav_i}, expected={expected_nav}"
        )

    # Final cumulative pct returned correctly
    assert abs(final_cum - (2.0 - 0.5 + 1.5)) < 1e-9

    # Final NAV
    expected_final = initial_cash * (1.0 + final_cum / 100.0)
    assert abs(nav_series[-1] - expected_final) < 1e-6


# ---------------------------------------------------------------------------
# 2. test_cost_shift_additive
# ---------------------------------------------------------------------------

def test_cost_shift_additive() -> None:
    """Changing cost_bps 25→23 shifts each net by +0.02; final cum increases by 0.02*N."""
    records = [
        _make_record(session="20240101", symbol="A", net_pct_25bps=1.0),
        _make_record(session="20240102", symbol="B", net_pct_25bps=-0.25),
        _make_record(session="20240103", symbol="C", net_pct_25bps=2.0),
        _make_record(session="20240104", symbol="D", net_pct_25bps=0.75),
    ]
    initial_cash = 500_000.0
    n = len(records)

    net_25, nav_25, cum_25 = _build_equity_curve(
        records, tp_sl_key="tp5_sl1", cost_bps=25.0, initial_cash=initial_cash
    )
    net_23, nav_23, cum_23 = _build_equity_curve(
        records, tp_sl_key="tp5_sl1", cost_bps=23.0, initial_cash=initial_cash
    )

    # Each individual net shifted by +0.02
    for i in range(n):
        assert abs(net_23[i] - net_25[i] - 0.02) < 1e-9, (
            f"Step {i}: net_23={net_23[i]}, net_25={net_25[i]}"
        )

    # Final cum increases by 0.02 * N
    assert abs(cum_23 - cum_25 - 0.02 * n) < 1e-9

    # Helper also confirms the shift
    assert abs(_net_at_cost(1.0, 23.0) - 1.02) < 1e-9
    assert abs(_net_at_cost(-0.5, 23.0) - (-0.48)) < 1e-9


# ---------------------------------------------------------------------------
# 3. test_filter_selection
# ---------------------------------------------------------------------------

def test_filter_selection() -> None:
    """ts_imb selects only pass_ts_imb; none selects all; ts selects pass_ts."""
    # none: all 5
    none_result = _apply_filter(SYNTHETIC_RECORDS, "none")
    assert len(none_result) == 5

    # ts: records A, B, C, E (pass_ts=True); D has pass_ts=False
    ts_result = _apply_filter(SYNTHETIC_RECORDS, "ts")
    assert len(ts_result) == 4
    assert all(r["pass_ts"] for r in ts_result)

    # ts_imb: records A, C, E (pass_ts_imb=True); B and D excluded
    ts_imb_result = _apply_filter(SYNTHETIC_RECORDS, "ts_imb")
    assert len(ts_imb_result) == 3
    assert all(r["pass_ts_imb"] for r in ts_imb_result)

    # Invalid filter raises
    with pytest.raises(ValueError, match="Invalid filter"):
        _apply_filter(SYNTHETIC_RECORDS, "bad_filter")


# ---------------------------------------------------------------------------
# 4. test_outputs_written_and_detected
# ---------------------------------------------------------------------------

def test_outputs_written_and_detected(
    instances_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After publish, run dir has 3 files; dashboard load_rl_run detects it correctly."""
    output_root = tmp_path / "rl_runs"
    run_name = "gap_up_ts_imb_equity"

    # Monkeypatch RL_RUN_ROOTS so dashboard finds our tmp output
    import webui.rl_dashboard as dashboard
    monkeypatch.setattr(dashboard, "RL_RUN_ROOTS", [output_root])

    result = publish_gap_up_run(
        instances_path=instances_file,
        filter_name="ts_imb",
        cost_bps=23.0,
        tp_sl_key="tp5_sl1",
        run_name=run_name,
        output_root=output_root,
        initial_cash=1_000_000.0,
    )

    run_dir = output_root / run_name

    # Three expected files present
    assert (run_dir / "portfolio_paper_summary.json").is_file()
    assert (run_dir / "rl_live_summary.json").is_file()
    assert (run_dir / "rl_live_events.jsonl").is_file()

    # Dashboard detects correct artifact type
    loaded = dashboard.load_rl_run(run_name)
    assert loaded["artifact_type"] == "portfolio_paper"
    assert "final_nav" in loaded["summary"]

    # JSONL has exactly 3 lines (ts_imb: records A, C, E)
    lines = [
        line for line in
        (run_dir / "rl_live_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 3

    # Each line has an equity field
    for line in lines:
        event = json.loads(line)
        assert "equity" in event
        assert event["equity"] is not None

    # Return value matches expected structure
    assert result["artifact_type"] == "portfolio_paper"
    assert result["summary"]["final_nav"] is not None
    assert result["config"]["is_reinforcement_learning"] is False


# ---------------------------------------------------------------------------
# 5. test_event_schema_honest
# ---------------------------------------------------------------------------

def test_event_schema_honest(
    instances_file: Path, tmp_path: Path
) -> None:
    """Each event algorithm starts with 'rule:'; info.note mentions 'RULE';
    config is_reinforcement_learning is False."""
    output_root = tmp_path / "rl_runs"
    run_name = "gap_up_none_equity"

    result = publish_gap_up_run(
        instances_path=instances_file,
        filter_name="none",
        cost_bps=23.0,
        tp_sl_key="tp5_sl1",
        run_name=run_name,
        output_root=output_root,
        initial_cash=1_000_000.0,
    )

    run_dir = output_root / run_name
    lines = [
        line for line in
        (run_dir / "rl_live_events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # All 5 records with filter=none
    assert len(lines) == 5

    for line in lines:
        event = json.loads(line)
        # algorithm must start with "rule:"
        assert event["algorithm"].startswith("rule:"), (
            f"Expected algorithm starting with 'rule:', got {event['algorithm']!r}"
        )
        # info.note mentions RULE
        note = event.get("info", {}).get("note", "")
        assert "RULE" in note, f"Expected 'RULE' in note, got {note!r}"

    # Config is_reinforcement_learning is False
    assert result["config"]["is_reinforcement_learning"] is False

    # portfolio_paper_summary.json also has is_reinforcement_learning=False
    summary_path = run_dir / "portfolio_paper_summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    assert payload["config"]["is_reinforcement_learning"] is False
    assert payload["artifact_type"] == "portfolio_paper"


# ---------------------------------------------------------------------------
# 6. test_main_cli_encoding_safe
# ---------------------------------------------------------------------------

def test_main_cli_encoding_safe(
    instances_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """main() returns 0 and prints valid JSON even when the strategy string
    contains non-ASCII characters (em-dash, Korean) that cp949 cannot encode."""
    from stom_rl.gap_up_dashboard_publish import main

    output_root = tmp_path / "rl_runs_cli"
    exit_code = main([
        "--instances", str(instances_file),
        "--filter", "ts_imb",
        "--cost-bps", "23.0",
        "--output-root", str(output_root),
        "--run-name", "cli_test_run",
    ])

    assert exit_code == 0

    captured = capsys.readouterr()
    # stdout must be non-empty and parse as valid JSON
    assert captured.out.strip(), "Expected non-empty stdout"
    parsed = json.loads(captured.out)

    # The em-dash in strategy must survive the round-trip
    strategy = parsed["summary"]["strategy"]
    assert "—" in strategy, f"em-dash missing in strategy: {strategy!r}"
    assert parsed["config"]["is_reinforcement_learning"] is False
