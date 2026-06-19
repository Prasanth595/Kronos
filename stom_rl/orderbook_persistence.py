"""Causal orderbook persistence and overheat scoring for opening trades."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd  # noqa: PANDAS_OK - STOM orderbook research frames are pandas-based

from .participant_pressure_features import (
    COL_ASK_TOTAL,
    COL_BID_TOTAL,
    COL_BUY_AMOUNT,
    COL_SELL_AMOUNT,
    COL_TRADE_STRENGTH,
)


COL_PRICE: Final[str] = "현재가"
COL_BID1: Final[str] = "매수호가1"
COL_ASK1: Final[str] = "매도호가1"
COL_BID_QTY1: Final[str] = "매수잔량1"
COL_ASK_QTY1: Final[str] = "매도잔량1"
SUMMARY_JSON: Final[str] = "orderbook_persistence_score_summary.json"
REQUIRED_SCORE_COMPONENTS: Final[tuple[str, ...]] = (
    "bid_ask_depth_imbalance",
    "bid_depth_persistence",
    "trade_strength_persistence",
    "signed_flow_persistence",
    "ofi_pressure",
    "microprice_pressure",
    "spread_penalty",
    "pullback_reacceleration",
    "overheat_penalty",
    "upper_wick_ratio",
)
FEATURE_GROUPS: Final[dict[str, list[str]]] = {
    "orderbook_imbalance": ["bid_ask_depth_imbalance", "microprice_pressure", "spread_penalty"],
    "orderbook_persistence": ["bid_depth_persistence", "ofi_pressure", "signed_flow_persistence", "trade_strength_persistence"],
    "overheat_upper_wick": ["overheat_penalty", "upper_wick_ratio", "pullback_reacceleration"],
}


@dataclass(frozen=True, slots=True)
class OrderbookPersistenceError(ValueError):
    """Raised when score input rows violate the causal orderbook contract."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _causal_rows(frame: pd.DataFrame, decision_second: int) -> pd.DataFrame:
    if frame.empty:
        raise OrderbookPersistenceError("orderbook persistence score requires non-empty frame")
    if decision_second < 0 or decision_second >= len(frame):
        raise OrderbookPersistenceError("decision_second out of range")
    return frame.iloc[: decision_second + 1]


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _required_columns(frame: pd.DataFrame) -> None:
    required = (
        COL_PRICE,
        COL_TRADE_STRENGTH,
        COL_BUY_AMOUNT,
        COL_SELL_AMOUNT,
        COL_BID_TOTAL,
        COL_ASK_TOTAL,
        COL_BID1,
        COL_ASK1,
        COL_BID_QTY1,
        COL_ASK_QTY1,
    )
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise OrderbookPersistenceError(f"missing orderbook persistence columns: {missing}")


def _bid_depth(rows: pd.DataFrame) -> float:
    bid = rows[COL_BID_TOTAL].astype(float)
    ask = rows[COL_ASK_TOTAL].astype(float)
    ratio = bid / (bid + ask).replace(0.0, pd.NA)
    return _clip01(float(ratio.fillna(0.0).mean()))


def _bid_ask_depth_imbalance(rows: pd.DataFrame) -> float:
    latest = rows.iloc[-1]
    bid_total = float(latest[COL_BID_TOTAL])
    ask_total = float(latest[COL_ASK_TOTAL])
    denominator = bid_total + ask_total
    return _clip01(bid_total / denominator) if denominator > 0.0 else 0.0


def _trade_strength(rows: pd.DataFrame) -> float:
    return _clip01(float(rows[COL_TRADE_STRENGTH].astype(float).mean()) / 150.0)


def _signed_flow(rows: pd.DataFrame) -> float:
    buy_sum = float(rows[COL_BUY_AMOUNT].astype(float).sum())
    sell_sum = float(rows[COL_SELL_AMOUNT].astype(float).sum())
    denominator = buy_sum + sell_sum
    signed = (buy_sum - sell_sum) / denominator if denominator > 0.0 else 0.0
    return _clip01((signed + 1.0) / 2.0)


def _ofi_pressure(rows: pd.DataFrame) -> float:
    bid_change = float(rows[COL_BID_TOTAL].iloc[-1]) - float(rows[COL_BID_TOTAL].iloc[0])
    ask_change = float(rows[COL_ASK_TOTAL].iloc[-1]) - float(rows[COL_ASK_TOTAL].iloc[0])
    raw = bid_change - ask_change
    denominator = abs(bid_change) + abs(ask_change)
    normalized = raw / denominator if denominator > 0.0 else 0.0
    return _clip01((normalized + 1.0) / 2.0)


def _microprice_pressure(rows: pd.DataFrame) -> float:
    latest = rows.iloc[-1]
    bid = float(latest[COL_BID1])
    ask = float(latest[COL_ASK1])
    bid_qty = float(latest[COL_BID_QTY1])
    ask_qty = float(latest[COL_ASK_QTY1])
    denominator = bid_qty + ask_qty
    if denominator <= 0.0 or bid <= 0.0 or ask <= 0.0:
        return 0.5
    microprice = (ask * bid_qty + bid * ask_qty) / denominator
    mid = (bid + ask) / 2.0
    return _clip01(0.5 + ((microprice - mid) / mid) * 50.0) if mid > 0.0 else 0.5


def _spread_penalty(rows: pd.DataFrame) -> float:
    bid = rows[COL_BID1].astype(float)
    ask = rows[COL_ASK1].astype(float)
    price = rows[COL_PRICE].astype(float)
    spread = ((ask - bid).clip(lower=0.0) / price.replace(0.0, pd.NA)).fillna(0.0)
    return _clip01(float(spread.mean()) * 100.0)


def _pullback_reacceleration(rows: pd.DataFrame) -> float:
    prices = rows[COL_PRICE].astype(float)
    if len(prices) < 3:
        return 0.0
    high = float(prices.max())
    low_after_high = float(prices.iloc[prices.argmax() :].min())
    latest = float(prices.iloc[-1])
    pullback = high - low_after_high
    recovery = latest - low_after_high
    return _clip01(recovery / pullback) if pullback > 0.0 else 0.0


def _overheat_penalty(rows: pd.DataFrame) -> float:
    ratio = _upper_wick_ratio(rows)
    if ratio <= 2.0:
        return 0.0
    return _clip01(ratio / 5.0)


def _upper_wick_ratio(rows: pd.DataFrame) -> float:
    prices = rows[COL_PRICE].astype(float)
    opening = float(prices.iloc[0])
    close = float(prices.iloc[-1])
    high = float(prices.max())
    body = abs(close - opening)
    upper = max(0.0, high - max(opening, close))
    return upper / max(body, 1e-9)


def _components(rows: pd.DataFrame) -> dict[str, float]:
    return {
        "bid_ask_depth_imbalance": _bid_ask_depth_imbalance(rows),
        "bid_depth_persistence": _bid_depth(rows),
        "trade_strength_persistence": _trade_strength(rows),
        "signed_flow_persistence": _signed_flow(rows),
        "ofi_pressure": _ofi_pressure(rows),
        "microprice_pressure": _microprice_pressure(rows),
        "spread_penalty": _spread_penalty(rows),
        "pullback_reacceleration": _pullback_reacceleration(rows),
        "overheat_penalty": _overheat_penalty(rows),
        "upper_wick_ratio": _upper_wick_ratio(rows),
    }


def _score(components: dict[str, float]) -> float:
    positive = (
        components["bid_depth_persistence"]
        + components["trade_strength_persistence"]
        + components["signed_flow_persistence"]
        + components["bid_ask_depth_imbalance"]
        + components["ofi_pressure"]
        + components["microprice_pressure"]
        + components["pullback_reacceleration"]
    ) / 7.0
    penalty = (components["spread_penalty"] + components["overheat_penalty"]) / 2.0
    return _clip01(positive - penalty * 0.5)


def build_orderbook_persistence_score(
    frame: pd.DataFrame,
    *,
    decision_second: int,
) -> dict[str, Any]:
    """Compute a causal componentized orderbook persistence score."""

    _required_columns(frame)
    rows = _causal_rows(frame, decision_second)
    components = _components(rows)
    return {
        "artifact_type": "orderbook_persistence_score",
        "mode": "opening_orderbook_persistence",
        "decision_second": int(decision_second),
        "rows_used": int(len(rows)),
        "score": _score(components),
        "components": components,
        "feature_groups": FEATURE_GROUPS,
        "artifact_fields": ["component_values", "feature_groups", "score", "decision_second", "rows_used"],
        "strategy_context": {
            "line": "orderbook_proxy_evidence",
            "label": "ORDERBOOK PERSISTENCE",
            "is_reinforcement_learning": False,
            "is_live_ready": False,
            "is_profit_model": False,
        },
    }


def write_orderbook_persistence_artifact(
    frame: pd.DataFrame,
    *,
    output_dir: Path,
    decision_second: int,
) -> dict[str, Any]:
    """Write a componentized orderbook persistence score artifact."""

    payload = build_orderbook_persistence_score(frame, decision_second=decision_second)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_JSON
    payload["artifacts"] = {"summary_json": str(summary_path)}
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
