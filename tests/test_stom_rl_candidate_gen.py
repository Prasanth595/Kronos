"""Tests for Page 9 candidate generation (panel -> candidate, T+1 fill, top-K).

These tests use a tiny in-memory panel fixture (no 29.7GB DB dependency) and the
real Page 8 rule JSONs.  They verify the panel->candidate seam, the T+1 fill
contract on a multi-symbol panel, cross-symbol rank isolation, last-bar
unfillability, and the top-K distribution report.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stom_rl.candidate_gen import (
    build_topk_report,
    generate_candidates,
    write_topk_report,
)
from stom_rl.condition_screener import ConditionRule, load_rules

RULES_DIR = Path(__file__).resolve().parents[1] / "stom_rl" / "rules"

# Schema the screener guarantees (Page 9 contract); feature_* columns follow.
_BASE_SCHEMA = ["timestamp", "symbol", "condition_id", "passed", "rank_score", "price", "fill_price", "fillable"]


def _panel() -> pd.DataFrame:
    """Tiny long-format panel: 2 symbols x 3 seconds with the columns rules need.

    Symbol 000001 passes buy_widev1 (amount>=100, trade_strength>=100) at every
    bar; 000002 fails (low amount / weak strength).  close values are recognisable
    so the T+1 fill (next bar close) is checkable.
    """

    return pd.DataFrame(
        {
            "timestamp": [
                "2025-07-09 09:00:00",
                "2025-07-09 09:00:00",
                "2025-07-09 09:00:01",
                "2025-07-09 09:00:01",
                "2025-07-09 09:00:02",
                "2025-07-09 09:00:02",
            ],
            "symbol": ["000001", "000002", "000001", "000002", "000001", "000002"],
            "close": [1000.0, 50.0, 1010.0, 51.0, 1025.0, 52.0],
            "amount": [500.0, 10.0, 600.0, 12.0, 700.0, 11.0],
            "trade_strength": [150.0, 80.0, 160.0, 70.0, 155.0, 90.0],
            "buy_qty_1s": [20.0, 1.0, 22.0, 1.0, 25.0, 1.0],
            "sell_qty_1s": [3.0, 5.0, 2.0, 6.0, 4.0, 7.0],
            "net_buy_qty_1s": [17.0, -4.0, 20.0, -5.0, 21.0, -6.0],
            "bid_ask_imbalance": [0.7, 0.3, 0.72, 0.28, 0.75, 0.31],
        }
    )


def test_panel_to_candidate_schema_and_determinism():
    rules = load_rules(RULES_DIR / "buy_widev1.json")
    first = generate_candidates(_panel(), rules)
    second = generate_candidates(_panel(), rules)

    # Schema match: base columns present and in order, plus feature_* columns.
    assert list(first.columns)[: len(_BASE_SCHEMA)] == _BASE_SCHEMA
    assert any(col.startswith("feature_") for col in first.columns)
    # Only 000001 passes the buy_widev1 demand filter.
    assert set(first["symbol"]) == {"000001"}
    # Determinism: identical output on a fresh screen of the same panel.
    pd.testing.assert_frame_equal(first, second)


def test_fill_price_equals_next_bar_close_on_panel():
    rules = load_rules(RULES_DIR / "buy_widev1.json")
    candidates = generate_candidates(_panel(), rules).sort_values("timestamp").reset_index(drop=True)

    # 000001 closes: 1000 (T0) -> 1010 (T1) -> 1025 (T2).
    t0 = candidates[candidates["timestamp"] == "2025-07-09T09:00:00"].iloc[0]
    assert t0["price"] == 1000.0
    assert t0["fill_price"] == 1010.0  # next bar
    t1 = candidates[candidates["timestamp"] == "2025-07-09T09:00:01"].iloc[0]
    assert t1["price"] == 1010.0
    assert t1["fill_price"] == 1025.0
    # Last bar of 000001 has no T+1 -> NaN / unfillable.
    t2 = candidates[candidates["timestamp"] == "2025-07-09T09:00:02"].iloc[0]
    assert pd.isna(t2["fill_price"])
    assert bool(t2["fillable"]) is False


def test_cross_symbol_does_not_change_fill_price():
    """Removing 000002 from the panel must not change 000001's fill_price."""

    rules = load_rules(RULES_DIR / "buy_widev1.json")
    full = generate_candidates(_panel(), rules)
    only_one = generate_candidates(_panel()[_panel()["symbol"] == "000001"], rules)

    full_1 = full[full["symbol"] == "000001"].sort_values("timestamp")["fill_price"].reset_index(drop=True)
    solo_1 = only_one.sort_values("timestamp")["fill_price"].reset_index(drop=True)
    pd.testing.assert_series_equal(full_1, solo_1, check_names=False)


@pytest.mark.parametrize("rule_name", ("buy_widev1", "buy_widev2", "buy_demand_pressure"))
def test_real_rules_run_on_panel(rule_name: str):
    rules = load_rules(RULES_DIR / f"{rule_name}.json")
    candidates = generate_candidates(_panel(), rules)
    # All 3 demand rules select 000001 only on this fixture (000002 always fails).
    assert set(candidates["symbol"]) == {"000001"}
    assert candidates["condition_id"].unique().tolist() == [rule_name]


def test_topk_report_counts_and_distribution(tmp_path: Path):
    # A rule that lets both symbols pass so a timestamp has >1 candidate.
    rule = ConditionRule(
        condition_id="any_buy",
        expression="buy_qty_1s > 0",
        rank_expression="trade_strength",
    )
    candidates = generate_candidates(_panel(), [rule])
    report = build_topk_report(candidates, top_k=2)

    # 3 decision timestamps, each with 2 passing symbols.
    assert len(report) == 3
    first = report.iloc[0]
    assert first["passing_symbols"] == 2
    # Top symbol by trade_strength at T0 is 000001 (150 > 80).
    assert first["top_2_symbols"][0] == "000001"
    assert first["rank_score_max"] >= first["rank_score_min"]

    # JSON round-trip writes a readable report.
    out = tmp_path / "topk.json"
    write_topk_report(out, report)
    loaded = json.loads(out.read_text(encoding="utf-8-sig"))
    assert len(loaded) == 3
    assert loaded[0]["passing_symbols"] == 2


def test_empty_panel_yields_empty_candidates_and_report():
    rules = load_rules(RULES_DIR / "buy_widev1.json")
    empty = pd.DataFrame(columns=["timestamp", "symbol", "close", "amount", "trade_strength"])
    candidates = generate_candidates(empty, rules)
    assert candidates.empty
    report = build_topk_report(candidates, top_k=3)
    assert report.empty
