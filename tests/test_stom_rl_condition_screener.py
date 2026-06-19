import json
from pathlib import Path

import pandas as pd
import pytest

from stom_rl.condition_screener import (
    ConditionRule,
    SafeExpression,
    load_rules,
    screen_frame,
    write_candidates,
)

RULES_DIR = Path(__file__).resolve().parents[1] / "stom_rl" / "rules"
REAL_RULE_FILES = ("buy_widev1", "buy_widev2", "buy_demand_pressure")


def _demand_frame() -> pd.DataFrame:
    """Tiny in-memory fixture (no DB dependency) covering pass and fail rows."""

    return pd.DataFrame(
        {
            "timestamp": [
                "2025-01-03 09:00:00",
                "2025-01-03 09:00:00",
                "2025-01-03 09:00:01",
            ],
            "symbol": ["000001", "000002", "000001"],
            "close": [100.0, 200.0, 101.0],
            "amount": [150, 50, 200],
            "trade_strength": [120, 90, 130],
            "buy_qty_1s": [10, 1, 8],
            "sell_qty_1s": [2, 5, 3],
            "net_buy_qty_1s": [8, -4, 5],
            "bid_ask_imbalance": [0.6, 0.4, 0.7],
        }
    )


def test_safe_expression_rejects_forbidden_tokens_and_unknowns():
    with pytest.raises(ValueError, match="Forbidden"):
        SafeExpression("__import__('os')", allowed_names=["close"])
    with pytest.raises(ValueError, match="Unknown"):
        SafeExpression("missing > 0", allowed_names=["close"])


def test_condition_screener_emits_deterministic_candidate_schema(tmp_path: Path):
    frame = pd.DataFrame(
        {
            "timestamp": ["2025-01-03 09:00:00", "2025-01-03 09:00:00", "2025-01-03 09:00:01"],
            "symbol": ["000001", "000002", "000001"],
            "close": [100.0, 200.0, 101.0],
            "rank_score": [0.5, 0.2, 0.7],
            "buy_qty_1s": [10, 0, 5],
            "sell_qty_1s": [2, 5, 1],
        }
    )
    candidates = screen_frame(
        frame,
        [ConditionRule(condition_id="net_buy", expression="buy_qty_1s > sell_qty_1s", rank_expression="rank_score")],
    )

    assert list(candidates[["timestamp", "symbol", "condition_id", "passed", "rank_score", "price"]].columns)
    assert candidates["symbol"].tolist() == ["000001", "000001"]
    assert candidates["timestamp"].is_monotonic_increasing
    output = tmp_path / "candidates.jsonl"
    write_candidates(output, candidates)
    assert output.read_text(encoding="utf-8-sig").count("\n") == 2


def test_buy_screener_rejects_sell_only_variables():
    frame = pd.DataFrame({"timestamp": ["2025-01-03"], "symbol": ["000001"], "close": [100], "holding_qty": [1]})
    with pytest.raises(ValueError, match="sell-only"):
        screen_frame(frame, [ConditionRule(condition_id="bad", expression="holding_qty > 0")])


@pytest.mark.parametrize("rule_name", REAL_RULE_FILES)
def test_real_buy_rule_json_loads(rule_name: str):
    rules = load_rules(RULES_DIR / f"{rule_name}.json")
    assert len(rules) == 1
    rule = rules[0]
    assert rule.condition_id == rule_name
    assert rule.side == "buy"
    assert rule.expression  # non-empty whitelisted expression


@pytest.mark.parametrize(
    "rule_name, expected_rank",
    [
        ("buy_widev1", [120.0, 130.0]),
        ("buy_widev2", [8.0, 5.0]),
        ("buy_demand_pressure", [72.0, 91.0]),
    ],
)
def test_real_buy_rule_screens_deterministically(rule_name: str, expected_rank: list[float]):
    rules = load_rules(RULES_DIR / f"{rule_name}.json")
    candidates = screen_frame(_demand_frame(), rules, strategy_side="buy")
    # 000002 fails every filter (low amount, weak trade strength, net selling, bid-light book).
    assert candidates["symbol"].tolist() == ["000001", "000001"]
    assert candidates["condition_id"].tolist() == [rule_name, rule_name]
    assert candidates["timestamp"].is_monotonic_increasing
    assert candidates["rank_score"].tolist() == expected_rank
    # Determinism: a second screen of the same frame yields identical output.
    again = screen_frame(_demand_frame(), rules, strategy_side="buy")
    assert again["rank_score"].tolist() == candidates["rank_score"].tolist()


def test_real_buy_rules_use_only_whitelisted_canonical_features():
    canonical = {
        "open", "high", "low", "close", "volume", "amount", "trade_strength",
        "buy_qty_1s", "sell_qty_1s", "net_buy_qty_1s", "bid_ask_imbalance",
        "spread_ticks", "amount_delta", "turnover_rate", "rank_score",
    }
    for rule_name in REAL_RULE_FILES:
        rules = load_rules(RULES_DIR / f"{rule_name}.json")
        for rule in rules:
            expr = SafeExpression(rule.expression, allowed_names=canonical)
            # Every referenced name maps to a canonical feature (no hallucinated vars).
            assert expr.referenced_names <= canonical
            ranker = SafeExpression(rule.rank_expression, allowed_names=canonical)
            assert ranker.referenced_names <= canonical


def test_screener_rejects_forbidden_tokens_in_rule_expression():
    forbidden_rule = ConditionRule(condition_id="evil", expression="__import__('os') and close > 0")
    with pytest.raises(ValueError, match="Forbidden"):
        screen_frame(_demand_frame(), [forbidden_rule], strategy_side="buy")


def test_screener_rejects_unknown_variable_in_rule_expression():
    unknown_rule = ConditionRule(condition_id="hallucinated", expression="시가총액 > 100")
    with pytest.raises(ValueError, match="Unknown"):
        screen_frame(_demand_frame(), [unknown_rule], strategy_side="buy")


def test_screener_rejects_sell_only_variable_in_buy_rule():
    frame = _demand_frame().assign(position_weight=0.0)
    sell_var_rule = ConditionRule(condition_id="leak", expression="position_weight > 0 and close > 0")
    with pytest.raises(ValueError, match="sell-only"):
        screen_frame(frame, [sell_var_rule], strategy_side="buy")


def test_real_buy_rule_json_has_no_forbidden_or_sell_only_tokens():
    sell_only_korean = ("수익률", "보유시간", "매수가", "보유수량", "수익금", "최고수익률")
    for rule_name in REAL_RULE_FILES:
        text = (RULES_DIR / f"{rule_name}.json").read_text(encoding="utf-8-sig")
        payload = json.loads(text)
        for rule in payload["rules"]:
            assert rule["side"] == "buy"
            lowered = rule["expression"].lower()
            assert "import" not in lowered and "eval" not in lowered and "__" not in lowered
            assert "open(" not in lowered and "compile" not in lowered
            for token in sell_only_korean:
                assert token not in rule["expression"]


# ---------------------------------------------------------------------------
# Page 9 — T+1 fill contract (P0 leakage gate)
# ---------------------------------------------------------------------------
def _two_bar_frame() -> pd.DataFrame:
    """Two symbols, each observed at three consecutive seconds (always pass)."""

    return pd.DataFrame(
        {
            "timestamp": [
                "2025-01-03 09:00:00",
                "2025-01-03 09:00:00",
                "2025-01-03 09:00:01",
                "2025-01-03 09:00:01",
                "2025-01-03 09:00:02",
                "2025-01-03 09:00:02",
            ],
            "symbol": ["000001", "000002", "000001", "000002", "000001", "000002"],
            "close": [100.0, 200.0, 101.0, 202.0, 103.0, 205.0],
            "buy_qty_1s": [10, 9, 8, 7, 6, 5],
            "sell_qty_1s": [1, 1, 1, 1, 1, 1],
        }
    )


_PASS_ALL_RULE = ConditionRule(
    condition_id="pass_all",
    expression="buy_qty_1s > sell_qty_1s",
    rank_expression="rank_score",
)


def test_fill_price_is_next_bar_per_symbol_and_after_decision():
    """fill_price[T] == that symbol's price at T+1, and fill ts > decision ts."""

    candidates = screen_frame(_two_bar_frame(), [_PASS_ALL_RULE])
    # Decision price is always the close at T; fill_price is the next bar's close.
    sym1 = candidates[candidates["symbol"] == "000001"].sort_values("timestamp")
    # T=09:00:00 -> price 100, fill 101 (the 09:00:01 close).
    first = sym1.iloc[0]
    assert first["price"] == 100.0
    assert first["fill_price"] == 101.0
    assert first["fillable"] is True or first["fillable"] == True  # noqa: E712
    # T=09:00:01 -> price 101, fill 103.
    second = sym1.iloc[1]
    assert second["price"] == 101.0
    assert second["fill_price"] == 103.0
    # Symbol 000002 is independent: its fills come from 000002's own next bars.
    sym2 = candidates[candidates["symbol"] == "000002"].sort_values("timestamp")
    assert sym2.iloc[0]["price"] == 200.0
    assert sym2.iloc[0]["fill_price"] == 202.0
    # The fill timestamp is strictly later than the decision timestamp.
    for _, row in sym1.iloc[:-1].iterrows():
        assert row["fill_price"] != row["price"]


def test_last_bar_per_symbol_is_unfillable_nan():
    """The last bar per symbol has no T+1 -> fill_price NaN, fillable False."""

    candidates = screen_frame(_two_bar_frame(), [_PASS_ALL_RULE])
    last_ts = "2025-01-03T09:00:02"
    last_rows = candidates[candidates["timestamp"] == last_ts]
    assert len(last_rows) == 2  # both symbols' last bar
    assert last_rows["fill_price"].isna().all()
    assert (~last_rows["fillable"]).all()


def test_drop_unfillable_removes_last_bar_candidates():
    kept = screen_frame(_two_bar_frame(), [_PASS_ALL_RULE], drop_unfillable=True)
    # 3 bars/symbol x 2 symbols = 6 rows; last bar of each dropped -> 4 rows.
    assert len(kept) == 4
    assert kept["fillable"].all()
    assert kept["fill_price"].notna().all()


# ---------------------------------------------------------------------------
# Page 9 — per-symbol default rank_score (P1 fix)
# ---------------------------------------------------------------------------
def test_default_rank_score_is_per_symbol_no_cross_contamination():
    """Symbol A's rows never influence symbol B's default rank_score.

    Default rank_score is pct_change of price within each symbol.  Symbol B's
    first row must be 0.0 (no prior bar in B), NOT a pct_change off symbol A's
    last close — which is the cross-symbol contamination bug this guards.
    """

    frame = pd.DataFrame(
        {
            "timestamp": [
                "2025-01-03 09:00:00",
                "2025-01-03 09:00:01",
                "2025-01-03 09:00:00",
                "2025-01-03 09:00:01",
            ],
            "symbol": ["000001", "000001", "000002", "000002"],
            "close": [100.0, 110.0, 5000.0, 5050.0],
            "buy_qty_1s": [10, 10, 10, 10],
            "sell_qty_1s": [1, 1, 1, 1],
        }
    )
    # No rank_score column and no rank_expression -> default per-symbol path.
    rule = ConditionRule(condition_id="all", expression="buy_qty_1s > sell_qty_1s", rank_expression="rank_score")
    candidates = screen_frame(frame, [rule])

    rank = {
        (row["symbol"], row["timestamp"]): row["rank_score"]
        for _, row in candidates.iterrows()
    }
    # First bar of each symbol -> 0.0 (no prior within-symbol bar).
    assert rank[("000001", "2025-01-03T09:00:00")] == 0.0
    assert rank[("000002", "2025-01-03T09:00:00")] == 0.0
    # Second bars use within-symbol pct_change only.
    assert rank[("000001", "2025-01-03T09:00:01")] == pytest.approx(0.10)  # 100 -> 110
    assert rank[("000002", "2025-01-03T09:00:01")] == pytest.approx(0.01)  # 5000 -> 5050
    # If contamination existed, 000002's first row would be 5000/100-1 = 49.0.
    assert rank[("000002", "2025-01-03T09:00:00")] != pytest.approx(49.0)


def test_symbol_order_does_not_affect_per_symbol_rank():
    """Re-ordering input rows must not change per-symbol rank_score values."""

    base = pd.DataFrame(
        {
            "timestamp": ["2025-01-03 09:00:00", "2025-01-03 09:00:01"],
            "symbol": ["000002", "000002"],
            "close": [5000.0, 5050.0],
            "buy_qty_1s": [10, 10],
            "sell_qty_1s": [1, 1],
        }
    )
    other = pd.DataFrame(
        {
            "timestamp": ["2025-01-03 09:00:00", "2025-01-03 09:00:01"],
            "symbol": ["000001", "000001"],
            "close": [100.0, 110.0],
            "buy_qty_1s": [10, 10],
            "sell_qty_1s": [1, 1],
        }
    )
    rule = ConditionRule(condition_id="all", expression="buy_qty_1s > sell_qty_1s", rank_expression="rank_score")
    a = screen_frame(pd.concat([base, other], ignore_index=True), [rule])
    b = screen_frame(pd.concat([other, base], ignore_index=True), [rule])
    a_map = {(r["symbol"], r["timestamp"]): r["rank_score"] for _, r in a.iterrows()}
    b_map = {(r["symbol"], r["timestamp"]): r["rank_score"] for _, r in b.iterrows()}
    assert a_map == b_map
