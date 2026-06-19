"""Market-participant proxy studies for opening-window research."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from statistics import fmean, stdev
from typing import Any, Final, Mapping, Sequence

import pandas as pd  # noqa: PANDAS_OK - STOM research fixtures and DB adapters are pandas-based

from .participant_pressure_features import (
    COL_FOREIGN_NET_BUY,
    COL_INSTITUTION_NET_BUY,
    COL_PROGRAM_NET_BUY,
    COL_TRANSACTION_VALUE,
)


COL_PRICE: Final[str] = "현재가"
ABSOLUTE_AMOUNT_THRESHOLD_KRW: Final[float] = 100_000_000_000.0
AMOUNT_MULTIPLES: Final[tuple[float, ...]] = (2.0, 3.0, 5.0, 10.0)
FORWARD_HORIZONS: Final[tuple[int, ...]] = (1, 3, 5, 20)
AMOUNT_UNIT_KRW: Final[float] = 1_000_000.0
SUMMARY_JSON: Final[str] = "market_participant_study_summary.json"
EPISODES_CSV: Final[str] = "market_participant_study_episodes.csv"
GROUPS_CSV: Final[str] = "market_participant_study_groups.csv"


@dataclass(frozen=True, slots=True)
class MarketParticipantStudyError(ValueError):
    """Raised when market-participant study inputs violate the contract."""

    reason: str

    def __str__(self) -> str:
        return self.reason


def _causal_rows(frame: pd.DataFrame, decision_second: int) -> pd.DataFrame:
    if frame.empty:
        raise MarketParticipantStudyError("market participant study requires non-empty frames")
    if decision_second < 0 or decision_second >= len(frame):
        raise MarketParticipantStudyError("decision_second out of range")
    return frame.iloc[: decision_second + 1]


def _close_price(frame: pd.DataFrame, decision_second: int) -> float:
    return float(_causal_rows(frame, decision_second)[COL_PRICE].iloc[-1])


def _episode_amount_krw(frame: pd.DataFrame, decision_second: int, amount_unit_krw: float) -> float:
    rows = _causal_rows(frame, decision_second)
    return float(rows[COL_TRANSACTION_VALUE].astype(float).sum()) * float(amount_unit_krw)


def _upper_wick(frame: pd.DataFrame, decision_second: int) -> dict[str, Any]:
    rows = _causal_rows(frame, decision_second)
    opening = float(rows[COL_PRICE].iloc[0])
    close = float(rows[COL_PRICE].iloc[-1])
    high = float(rows[COL_PRICE].astype(float).max())
    body = abs(close - opening)
    upper = max(0.0, high - max(opening, close))
    threshold = max(body * 2.0, 1e-9)
    return {
        "open": opening,
        "close": close,
        "high": high,
        "body": body,
        "upper_wick": upper,
        "upper_wick_ratio": upper / body if body > 0.0 else None,
        "upper_wick_exhaustion": upper > threshold,
    }


def _base_rows(
    frames: Sequence[pd.DataFrame],
    *,
    decision_second: int,
    amount_unit_krw: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for frame in frames:
        if frame.empty:
            continue
        symbol = str(frame["symbol"].iloc[0])
        session = str(frame["session"].iloc[0])
        close = _close_price(frame, decision_second)
        wick = _upper_wick(frame, decision_second)
        rows.append(
            {
                "episode_id": f"{symbol}_{session}",
                "symbol": symbol,
                "session": session,
                "decision_second": int(decision_second),
                "close_price": close,
                "opening_amount_krw": _episode_amount_krw(frame, decision_second, amount_unit_krw),
                "absolute_surge": False,
                "rolling_amount_baseline_krw": None,
                "amount_multiple": None,
                "upper_wick_exhaustion": wick["upper_wick_exhaustion"],
                "upper_wick_ratio": wick["upper_wick_ratio"],
            }
        )
    if not rows:
        raise MarketParticipantStudyError("market participant study requires at least one episode")
    return sorted(rows, key=lambda item: (str(item["symbol"]), str(item["session"])))


def _attach_forward_returns(rows: list[dict[str, Any]]) -> None:
    by_symbol: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_symbol.setdefault(str(row["symbol"]), []).append(index)
        for horizon in FORWARD_HORIZONS:
            row[f"forward_{horizon}_session_return_pct"] = None
    for indexes in by_symbol.values():
        indexes.sort(key=lambda idx: str(rows[idx]["session"]))
        for pos, row_index in enumerate(indexes):
            close = float(rows[row_index]["close_price"])
            for horizon in FORWARD_HORIZONS:
                target_pos = pos + horizon
                if target_pos >= len(indexes):
                    continue
                future_close = float(rows[indexes[target_pos]]["close_price"])
                rows[row_index][f"forward_{horizon}_session_return_pct"] = (future_close / close - 1.0) * 100.0


def _attach_amount_multiples(rows: list[dict[str, Any]]) -> None:
    by_symbol: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_symbol.setdefault(str(row["symbol"]), []).append(index)
        row["absolute_surge"] = float(row["opening_amount_krw"]) >= ABSOLUTE_AMOUNT_THRESHOLD_KRW
    for indexes in by_symbol.values():
        indexes.sort(key=lambda idx: str(rows[idx]["session"]))
        previous: list[float] = []
        for row_index in indexes:
            amount = float(rows[row_index]["opening_amount_krw"])
            if previous:
                baseline = fmean(previous[-20:])
                rows[row_index]["rolling_amount_baseline_krw"] = baseline
                rows[row_index]["amount_multiple"] = amount / baseline if baseline > 0.0 else None
            previous.append(amount)


def _mean(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def _ci95(values: Sequence[float]) -> list[float | None]:
    if len(values) < 2:
        return [None, None]
    mean = fmean(values)
    half = 1.96 * stdev(values) / sqrt(len(values))
    return [mean - half, mean + half]


def _group_summary(label: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "label": label,
        "episode_count": len(rows),
        "baseline_policy": "ts_imb RULE baseline",
    }
    for horizon in FORWARD_HORIZONS:
        column = f"forward_{horizon}_session_return_pct"
        values = [float(row[column]) for row in rows if row[column] is not None]
        summary[f"{column}_mean"] = _mean(values)
        summary[f"{column}_ci95"] = _ci95(values)
    return summary


def _surge_groups(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    groups = {
        "absolute_ge_100b_krw": _group_summary(
            "absolute_ge_100b_krw",
            [row for row in rows if bool(row["absolute_surge"])],
        )
    }
    for multiple in AMOUNT_MULTIPLES:
        key = f"amount_multiple_ge_{int(multiple)}x"
        groups[key] = _group_summary(
            key,
            [
                row
                for row in rows
                if row["amount_multiple"] is not None and float(row["amount_multiple"]) >= multiple
            ],
        )
    return groups


def _upper_wick_study(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [row for row in rows if bool(row["upper_wick_exhaustion"])]
    return {
        "upper_wick_rule": "upper_wick > body * 2",
        "episode_count": len(rows),
        "upper_wick_count": len(selected),
        "groups": {
            "upper_wick_exhaustion": _group_summary("upper_wick_exhaustion", selected),
            "not_upper_wick_exhaustion": _group_summary(
                "not_upper_wick_exhaustion",
                [row for row in rows if not bool(row["upper_wick_exhaustion"])],
            ),
        },
    }


def _proxy_strata(frames: Sequence[pd.DataFrame], episode_count: int) -> list[dict[str, Any]]:
    optional = (
        ("foreign_net_buy", COL_FOREIGN_NET_BUY),
        ("institution_net_buy", COL_INSTITUTION_NET_BUY),
        ("program_net_buy", COL_PROGRAM_NET_BUY),
    )
    rows: list[dict[str, Any]] = []
    for name, column in optional:
        if not any(column in frame.columns for frame in frames):
            rows.append({"proxy": name, "status": "proxy_unavailable", "episode_count": episode_count, "net_buy_sum": None})
            continue
        total = sum(float(frame[column].fillna(0.0).iloc[-1]) for frame in frames if column in frame.columns)
        rows.append({"proxy": name, "status": "available", "episode_count": episode_count, "net_buy_sum": total})
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = sorted({key for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})


def build_market_participant_studies(
    frames: Sequence[pd.DataFrame],
    *,
    output_dir: Path,
    decision_second: int = 5,
    amount_unit_krw: float = AMOUNT_UNIT_KRW,
) -> dict[str, Any]:
    """Build preregistered non-RL market-participant proxy studies."""

    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _base_rows(frames, decision_second=decision_second, amount_unit_krw=amount_unit_krw)
    _attach_forward_returns(rows)
    _attach_amount_multiples(rows)
    surge_groups = _surge_groups(rows)
    proxy_strata = _proxy_strata(frames, len(rows))
    artifacts = {
        "summary_json": str(output_dir / SUMMARY_JSON),
        "episodes_csv": str(output_dir / EPISODES_CSV),
        "groups_csv": str(output_dir / GROUPS_CSV),
    }
    payload: dict[str, Any] = {
        "artifact_type": "market_participant_study",
        "mode": "market_participant_proxy_research",
        "verdict": "NO-GO_SAMPLE" if len(rows) < 5 else "RESEARCH_ONLY",
        "config": {
            "absolute_amount_threshold_krw": ABSOLUTE_AMOUNT_THRESHOLD_KRW,
            "amount_multiples": list(AMOUNT_MULTIPLES),
            "amount_unit_krw": float(amount_unit_krw),
            "decision_second": int(decision_second),
        },
        "summary": {
            "episode_count": len(rows),
            "forward_return_columns": [f"forward_{h}_session_return_pct" for h in FORWARD_HORIZONS],
        },
        "strategy_context": {
            "line": "participant_proxy_research",
            "label": "MARKET PARTICIPANT STUDY",
            "is_reinforcement_learning": False,
            "is_live_ready": False,
            "is_profit_model": False,
        },
        "surge_groups": surge_groups,
        "upper_wick_study": _upper_wick_study(rows),
        "proxy_strata": proxy_strata,
        "episodes": rows,
        "artifacts": artifacts,
    }
    Path(artifacts["summary_json"]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(Path(artifacts["episodes_csv"]), rows)
    _write_csv(Path(artifacts["groups_csv"]), list(surge_groups.values()))
    return payload
