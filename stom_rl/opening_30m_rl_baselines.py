"""Same-decision baselines for opening 30-minute RL workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd  # noqa: PANDAS_OK - matches existing STOM tick/orderbook DataFrame pipeline

from .marketable_fill import DEFAULT_TIME_EXIT_SEC, EXIT_TIME, marketable_entry_price, marketable_exit_price


POLICY_NO_TRADE = "no_trade"
POLICY_BUY_AND_HOLD = "buy_and_hold"
POLICY_TS_IMB = "ts_imb_same_decision_tp5_sl1_time"


@dataclass(frozen=True, slots=True)
class OpeningBaselineConfig:
    """Configuration for same-decision opening baseline evaluation."""

    decision_index: int = 0
    cost_bps: float = 23.0
    tp_pct: float = 5.0
    sl_pct: float = 1.0
    time_exit_sec: int = DEFAULT_TIME_EXIT_SEC
    trade_strength_threshold: float = 100.0
    imbalance_threshold: float = 0.5


@dataclass(frozen=True, slots=True)
class OpeningBaselineError(ValueError):
    """Raised when baseline input frames violate the contract."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _seconds(frame: pd.DataFrame) -> list[int]:
    return list(range(len(frame)))


def _imbalance(row: pd.Series) -> float:
    bid_total = float(row["매수총잔량"])
    ask_total = float(row["매도총잔량"])
    denom = bid_total + ask_total
    return bid_total / denom if denom > 0.0 else 0.0


def _passes_ts_imb(row: pd.Series, config: OpeningBaselineConfig) -> bool:
    return float(row["체결강도"]) >= config.trade_strength_threshold and _imbalance(row) >= config.imbalance_threshold


def _marketable_hold_return(frame: pd.DataFrame, config: OpeningBaselineConfig) -> tuple[float, float, float]:
    entry = frame.iloc[config.decision_index]
    exit_row = frame.iloc[-1]
    entry_price = marketable_entry_price(
        float(entry["매수호가1"]),
        float(entry["매도호가1"]),
        float(entry["현재가"]),
    )
    exit_price = marketable_exit_price(
        float(exit_row["매수호가1"]),
        float(exit_row["매도호가1"]),
        float(exit_row["현재가"]),
    )
    net_pct = (exit_price / entry_price - 1.0) * 100.0 - config.cost_bps / 100.0
    return entry_price, exit_price, net_pct


def _rule_exit_index(frame: pd.DataFrame, entry_price: float, config: OpeningBaselineConfig) -> tuple[int, str]:
    prices = [float(value) for value in frame["현재가"].tolist()]
    secs = _seconds(frame)
    tp_level = entry_price * (1.0 + config.tp_pct / 100.0)
    sl_level = entry_price * (1.0 - config.sl_pct / 100.0)
    for idx in range(config.decision_index + 1, len(frame)):
        if secs[idx] >= config.time_exit_sec:
            return idx, EXIT_TIME
        price = prices[idx]
        if price <= sl_level:
            return idx, "sl"
        if price >= tp_level:
            return idx, "tp"
    return len(frame) - 1, EXIT_TIME


def _rule_row(frame: pd.DataFrame, config: OpeningBaselineConfig) -> dict[str, Any]:
    entry = frame.iloc[config.decision_index]
    if not _passes_ts_imb(entry, config):
        return _base_row(frame, POLICY_TS_IMB, config) | {
            "entry_price": None,
            "exit_price": None,
            "net_return_pct": 0.0,
            "exit_reason": "skip_filter",
            "trade_count": 0,
        }
    entry_price = marketable_entry_price(
        float(entry["매수호가1"]),
        float(entry["매도호가1"]),
        float(entry["현재가"]),
    )
    exit_idx, reason = _rule_exit_index(frame, entry_price, config)
    exit_row = frame.iloc[exit_idx]
    exit_price = marketable_exit_price(
        float(exit_row["매수호가1"]),
        float(exit_row["매도호가1"]),
        float(exit_row["현재가"]),
    )
    net_pct = (exit_price / entry_price - 1.0) * 100.0 - config.cost_bps / 100.0
    return _base_row(frame, POLICY_TS_IMB, config) | {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "net_return_pct": net_pct,
        "exit_reason": reason,
        "trade_count": 2,
    }


def _base_row(frame: pd.DataFrame, policy: str, config: OpeningBaselineConfig) -> dict[str, Any]:
    return {
        "episode_id": f"{frame['symbol'].iloc[0]}_{frame['session'].iloc[0]}",
        "symbol": str(frame["symbol"].iloc[0]),
        "session": str(frame["session"].iloc[0]),
        "policy": policy,
        "is_reinforcement_learning": False,
        "cost_bps": float(config.cost_bps),
        "decision_index": int(config.decision_index),
    }


def _rows_for_frame(frame: pd.DataFrame, config: OpeningBaselineConfig) -> list[dict[str, Any]]:
    if frame.empty:
        raise OpeningBaselineError("baseline comparator requires non-empty frames")
    if not 0 <= config.decision_index < len(frame):
        raise OpeningBaselineError("decision_index out of range")
    hold_entry, hold_exit, hold_net = _marketable_hold_return(frame, config)
    return [
        _base_row(frame, POLICY_NO_TRADE, config) | {
            "entry_price": None,
            "exit_price": None,
            "net_return_pct": 0.0,
            "exit_reason": "no_trade",
            "trade_count": 0,
        },
        _base_row(frame, POLICY_BUY_AND_HOLD, config) | {
            "entry_price": hold_entry,
            "exit_price": hold_exit,
            "net_return_pct": hold_net,
            "exit_reason": "hold_to_window_end",
            "trade_count": 2,
        },
        _rule_row(frame, config),
    ]


def _baseline_delta_inputs(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, list[float]] = {}
    for row in rows:
        policy = str(row["policy"])
        totals.setdefault(policy, []).append(float(row["net_return_pct"]))
    return {policy: sum(values) / len(values) for policy, values in sorted(totals.items())}


def evaluate_opening_baselines(
    frames: Sequence[pd.DataFrame],
    config: OpeningBaselineConfig,
) -> dict[str, Any]:
    """Evaluate non-RL opening baselines on the same decision boundary."""

    rows = [row for frame in frames for row in _rows_for_frame(frame, config)]
    return {
        "mode": "opening_30m_baseline_comparator",
        "artifact_type": "opening_30m_baseline_comparator",
        "strategy_context": {
            "line": "rule_baseline",
            "label": "RULE BASELINE",
            "primary_baseline": "ts_imb",
            "is_reinforcement_learning": False,
            "is_live_ready": False,
            "is_profit_model": False,
            "guardrail": "RULE strategy baseline; not reinforcement learning.",
        },
        "summary": {
            "policy_count": 3,
            "episode_count": len(frames),
            "cost_bps": float(config.cost_bps),
            "baseline_delta_inputs": _baseline_delta_inputs(rows),
        },
        "rows": rows,
    }
