"""Causal market-participant proxy features for opening-window research."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd  # noqa: PANDAS_OK - STOM tick/orderbook frames are pandas-based

from .participant_pressure_contract import (
    COL_ASK_TOTAL,
    COL_BID_TOTAL,
    COL_BUY_AMOUNT,
    COL_FOREIGN_NET_BUY,
    COL_INSTITUTION_NET_BUY,
    COL_PROGRAM_NET_BUY,
    COL_SELL_AMOUNT,
    COL_TRADE_STRENGTH,
    COL_TRANSACTION_VALUE,
    FEATURE_SPECS,
    Availability,
    ParticipantComputedFeatures,
    ParticipantFeatureSpecPayload,
    ParticipantPressureError,
    ParticipantProxyFeature,
    ParticipantReadinessPayload,
)

def _causal_rows(frame: pd.DataFrame, decision_second: int) -> pd.DataFrame:
    if frame.empty:
        raise ParticipantPressureError("participant proxy frame must not be empty")
    if decision_second < 0 or decision_second >= len(frame):
        raise ParticipantPressureError("decision_second out of range for participant proxy frame")
    return frame.iloc[: decision_second + 1]


def _require_columns(frame: pd.DataFrame, specs: tuple[ParticipantProxyFeature, ...]) -> None:
    required = [spec for spec in specs if spec.available_at_decision_second == "required"]
    missing = [
        column
        for spec in required
        for column in spec.required_columns
        if column not in frame.columns
    ]
    if missing:
        unique_missing = ", ".join(dict.fromkeys(missing))
        raise ParticipantPressureError(f"missing required participant proxy columns: {unique_missing}")


def _last_float(rows: pd.DataFrame, column: str) -> float:
    return float(rows[column].iloc[-1])


def _sum_float(rows: pd.DataFrame, column: str) -> float:
    return float(rows[column].astype(float).sum())


def _optional_last_float(rows: pd.DataFrame, column: str) -> float | None:
    if column not in rows.columns:
        return None
    value = rows[column].iloc[-1]
    return None if pd.isna(value) else float(value)


def _signed_amount_ratio(rows: pd.DataFrame) -> float:
    buy_sum = _sum_float(rows, COL_BUY_AMOUNT)
    sell_sum = _sum_float(rows, COL_SELL_AMOUNT)
    denominator = buy_sum + sell_sum
    return (buy_sum - sell_sum) / denominator if denominator > 0.0 else 0.0


def _bid_depth_imbalance(rows: pd.DataFrame) -> float:
    latest = rows.iloc[-1]
    bid_total = float(latest[COL_BID_TOTAL])
    ask_total = float(latest[COL_ASK_TOTAL])
    denominator = bid_total + ask_total
    return bid_total / denominator if denominator > 0.0 else 0.0


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _participant_proxy_pressure(trade_strength: float, signed_amount_ratio: float, bid_depth_imbalance: float) -> float:
    trade_component = _clip01(trade_strength / 150.0)
    signed_component = _clip01((signed_amount_ratio + 1.0) / 2.0)
    bid_component = _clip01(bid_depth_imbalance)
    return (trade_component + signed_component + bid_component) / 3.0


def _feature_schema() -> list[ParticipantFeatureSpecPayload]:
    return [spec.to_payload() for spec in FEATURE_SPECS]


def _proxy_availability(frame: pd.DataFrame) -> dict[str, Availability]:
    return {
        spec.name: (
            "available"
            if all(column in frame.columns for column in spec.required_columns)
            else "missing"
        )
        for spec in FEATURE_SPECS
    }


def _missing_proxy_columns(frame: pd.DataFrame) -> list[str]:
    return [
        spec.source_column
        for spec in FEATURE_SPECS
        if spec.available_at_decision_second == "optional"
        and any(column not in frame.columns for column in spec.required_columns)
    ]


def compute_participant_pressure_features(
    frame: pd.DataFrame,
    *,
    decision_second: int,
) -> ParticipantComputedFeatures:
    """Compute participant proxy features using rows up to the decision second only."""

    _require_columns(frame, FEATURE_SPECS)
    rows = _causal_rows(frame, decision_second)
    transaction_value_sum = _sum_float(rows, COL_TRANSACTION_VALUE)
    signed_amount_ratio = _signed_amount_ratio(rows)
    trade_strength = _last_float(rows, COL_TRADE_STRENGTH)
    bid_depth_imbalance = _bid_depth_imbalance(rows)
    return {
        "rows_used": int(len(rows)),
        "transaction_value_sum": transaction_value_sum,
        "transaction_value_surge": transaction_value_sum,
        "signed_amount_ratio": signed_amount_ratio,
        "signed_amount_persistence": signed_amount_ratio,
        "trade_strength": trade_strength,
        "bid_depth_imbalance": bid_depth_imbalance,
        "participant_proxy_pressure": _participant_proxy_pressure(trade_strength, signed_amount_ratio, bid_depth_imbalance),
        "foreign_net_buy": _optional_last_float(rows, COL_FOREIGN_NET_BUY),
        "institution_net_buy": _optional_last_float(rows, COL_INSTITUTION_NET_BUY),
        "program_net_buy": _optional_last_float(rows, COL_PROGRAM_NET_BUY),
    }


def build_participant_pressure_readiness(
    frame: pd.DataFrame,
    *,
    output_dir: Path,
    decision_second: int,
) -> ParticipantReadinessPayload:
    """Write participant proxy readiness metadata for the opening RL workflow."""

    computed = compute_participant_pressure_features(frame, decision_second=decision_second)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "participant_pressure_readiness_summary.json"
    payload: ParticipantReadinessPayload = {
        "artifact_type": "participant_pressure_readiness",
        "mode": "opening_30m_rl_participant_proxy_audit",
        "participant_context_version": "market_participant_proxy_v1",
        "decision_second": int(decision_second),
        "feature_schema": _feature_schema(),
        "proxy_availability": _proxy_availability(frame),
        "missing_proxy_columns": _missing_proxy_columns(frame),
        "computed_features": computed,
        "strategy_context": {
            "line": "participant_proxy_evidence",
            "label": "MARKET PARTICIPANT PROXY",
            "is_reinforcement_learning": False,
            "is_live_ready": False,
            "is_profit_model": False,
            "guardrail": "Proxy evidence only; does not identify real investor actors.",
        },
        "artifacts": {"summary_json": str(summary_path)},
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    summary_path.write_text(content, encoding="utf-8")
    return payload
