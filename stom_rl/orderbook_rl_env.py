"""Marketable-only tick + orderbook RL environment for STOM opening trades.

This module is intentionally narrower than a full limit-order-book simulator.
It supports only actions whose fills can be audited from the current 1-second
snapshot:

* ``0`` hold
* ``1`` market_buy (buy crosses ``ask1``)
* ``2`` market_exit (sell hits ``bid1``)

That conservative contract is deliberate.  Without message-level queue
position, limit-order placement/cancel rewards would be mostly fabricated; this
environment instead makes the first reinforcement-learning step honest,
causal, and cost-aware.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .marketable_fill import marketable_entry_price, marketable_exit_price
from .microstructure_features import causal_feature_vector
from .trading_env import BoxSpace, DiscreteSpace


ACTION_HOLD = 0
ACTION_MARKET_BUY = 1
ACTION_MARKET_EXIT = 2
ACTION_NAMES = {
    ACTION_HOLD: "hold",
    ACTION_MARKET_BUY: "market_buy",
    ACTION_MARKET_EXIT: "market_exit",
}

ORDERBOOK_FEATURE_NAMES: Tuple[str, ...] = (
    "ret_open",
    "ret_5",
    "ret_15",
    "ret_30",
    "vol_5",
    "vol_15",
    "vol_30",
    "spread_rel",
    "micro_dev",
    "book_imb_tot",
    "book_imb_l1",
    "ofi_5",
    "ofi_15",
    "ofi_30",
    "sflow_ratio_5",
    "sflow_ratio_15",
    "sflow_ratio_30",
    "ts_level",
    "ts_slope_30",
    "position",
    "unrealized_net_pct",
    "time_frac",
)

KOREAN_TO_CANONICAL = {
    "index": "timestamp_key",
    "현재가": "price",
    "등락율": "cr",
    "체결강도": "ts",
    "초당매수금액": "buy_val",
    "초당매도금액": "sell_val",
    "초당매수수량": "buy_qty",
    "초당매도수량": "sell_qty",
    "매수총잔량": "bid_tot",
    "매도총잔량": "ask_tot",
    "매수호가1": "bid1",
    "매도호가1": "ask1",
    "매수잔량1": "bidq1",
    "매도잔량1": "askq1",
}

CANONICAL_COLUMNS: Tuple[str, ...] = (
    "sec",
    "price",
    "ts",
    "buy_val",
    "sell_val",
    "buy_qty",
    "sell_qty",
    "bid_tot",
    "ask_tot",
    "bid1",
    "ask1",
    "bidq1",
    "askq1",
)

REQUIRED_ORDERBOOK_COLUMNS: Tuple[str, ...] = (
    "price",
    "bid_tot",
    "ask_tot",
    "bid1",
    "ask1",
    "bidq1",
    "askq1",
)

DB_REQUIRED_COLUMNS: Tuple[str, ...] = (
    "index",
    "현재가",
    "체결강도",
    "초당매수금액",
    "초당매도금액",
    "초당매수수량",
    "초당매도수량",
    "매수총잔량",
    "매도총잔량",
    "매수호가1",
    "매도호가1",
    "매수잔량1",
    "매도잔량1",
)

DEFAULT_READINESS_OUTPUT_DIR = Path("webui") / "rl_runs" / "stom_orderbook_rl_readiness"
DEFAULT_OMX_READINESS_DIR = Path(".omx") / "artifacts" / "orderbook_rl_readiness"


@dataclass(frozen=True)
class StomOrderbookRlEnvConfig:
    """Configuration for ``StomOrderbookRlEnv``."""

    csv_path: Optional[str] = None
    lookback_window: int = 30
    cost_bps: float = 23.0
    slippage_bps: float = 0.0
    invalid_action_penalty: float = 0.001
    overtrade_penalty: float = 0.0
    force_close_on_done: bool = True
    max_episode_steps: int = 0
    normalize_observation: bool = False
    seed: int = 100


@dataclass(frozen=True)
class OrderbookRlReadinessConfig:
    """Configuration for DB/data readiness assessment."""

    db_path: str = str(Path("_database") / "stock_tick_back.db")
    output_dir: str = str(DEFAULT_READINESS_OUTPUT_DIR)
    omx_output_dir: str = str(DEFAULT_OMX_READINESS_DIR)
    max_symbols: int = 200
    min_rows_per_episode: int = 35
    lookback_window: int = 30
    min_eligible_episodes: int = 1000
    min_quote_coverage: float = 0.95
    min_valid_spread_coverage: float = 0.90
    write_artifacts: bool = True


def _float_or_zero(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def seconds_since_open(value: Any) -> int:
    """Return seconds since 09:00 from STOM ``index`` or timestamp-like values."""

    if value is None:
        return 0
    try:
        if not isinstance(value, str) and np.isfinite(float(value)):
            text = str(int(float(value)))
        else:
            text = str(value).strip()
    except (TypeError, ValueError):
        text = str(value).strip()

    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 14:
        hhmmss = digits[-6:]
    elif len(digits) >= 6:
        hhmmss = digits[-6:]
    else:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return 0
        hhmmss = f"{parsed.hour:02d}{parsed.minute:02d}{parsed.second:02d}"
    hh = int(hhmmss[:2])
    mm = int(hhmmss[2:4])
    ss = int(hhmmss[4:6])
    return hh * 3600 + mm * 60 + ss - 9 * 3600


def _timestamp_iso(value: Any) -> Optional[str]:
    try:
        if not isinstance(value, str) and np.isfinite(float(value)):
            digits = str(int(float(value)))
        else:
            digits = "".join(ch for ch in str(value) if ch.isdigit())
    except (TypeError, ValueError):
        digits = ""
    if len(digits) >= 14:
        return (
            f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
            f"T{digits[8:10]}:{digits[10:12]}:{digits[12:14]}"
        )
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.isoformat()


def normalize_orderbook_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize Korean STOM or canonical orderbook columns to dense floats."""

    if frame.empty:
        raise ValueError("orderbook frame is empty")

    normalized = frame.copy()
    rename_map = {src: dst for src, dst in KOREAN_TO_CANONICAL.items() if src in normalized.columns}
    normalized = normalized.rename(columns=rename_map)

    if "sec" not in normalized.columns:
        if "timestamp_key" in normalized.columns:
            normalized["sec"] = normalized["timestamp_key"].map(seconds_since_open)
        elif "timestamp" in normalized.columns:
            normalized["sec"] = normalized["timestamp"].map(seconds_since_open)
        else:
            normalized["sec"] = np.arange(len(normalized), dtype=float)

    if "timestamp" not in normalized.columns and "timestamp_key" in normalized.columns:
        normalized["timestamp"] = normalized["timestamp_key"].map(_timestamp_iso)

    missing = [col for col in REQUIRED_ORDERBOOK_COLUMNS if col not in normalized.columns]
    if missing:
        raise ValueError(f"orderbook frame missing required columns: {missing}")

    for column in CANONICAL_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = 0.0
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    canonical_columns = list(CANONICAL_COLUMNS)
    normalized[canonical_columns] = normalized[canonical_columns].ffill().bfill().fillna(0.0)
    normalized = normalized[normalized["price"] > 0].copy()
    normalized = normalized.sort_values("sec").reset_index(drop=True)
    if normalized.empty:
        raise ValueError("orderbook frame has no positive price rows")
    return normalized


class StomOrderbookRlEnv:
    """Dependency-light single-symbol marketable-only orderbook RL environment."""

    metadata: ClassVar[Dict[str, Any]] = {"render_modes": []}

    def __init__(
        self,
        config: Optional[StomOrderbookRlEnvConfig] = None,
        *,
        frame: Optional[pd.DataFrame] = None,
        **overrides: Any,
    ) -> None:
        if config is not None and overrides:
            raise ValueError("Pass either config or keyword overrides, not both.")
        self.config = config or StomOrderbookRlEnvConfig(**overrides)
        if self.config.lookback_window <= 0:
            raise ValueError("lookback_window must be positive")
        if self.config.cost_bps < 0 or self.config.slippage_bps < 0:
            raise ValueError("cost_bps and slippage_bps must be non-negative")
        if frame is None:
            if not self.config.csv_path:
                raise ValueError("Pass frame=... or config.csv_path")
            frame = pd.read_csv(self.config.csv_path)
        self.frame = normalize_orderbook_frame(frame)
        if len(self.frame) < self.config.lookback_window + 1:
            raise ValueError(
                f"orderbook episode has {len(self.frame)} rows, "
                f"but at least {self.config.lookback_window + 1} are required"
            )

        self.feature_columns = list(ORDERBOOK_FEATURE_NAMES)
        self.action_space = DiscreteSpace(3)
        self.observation_space = BoxSpace((len(self.feature_columns),), dtype=np.float32)
        self._rng = np.random.default_rng(self.config.seed)

        self.current_idx = 0
        self.max_idx = len(self.frame) - 1
        self.start_idx = self.config.lookback_window - 1
        if self.config.max_episode_steps > 0:
            self.max_idx = min(self.max_idx, self.start_idx + int(self.config.max_episode_steps))
        self.position = 0
        self.entry_fill = 0.0
        self.entry_idx: Optional[int] = None
        self.realized_net_return = 0.0
        self.trade_count = 0
        self.invalid_action_count = 0
        self.cumulative_reward = 0.0
        self.last_info: Dict[str, Any] = {}

    @property
    def cost_fraction(self) -> float:
        return float(self.config.cost_bps) / 10_000.0

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        del options
        self.current_idx = self.start_idx
        self.position = 0
        self.entry_fill = 0.0
        self.entry_idx = None
        self.realized_net_return = 0.0
        self.trade_count = 0
        self.invalid_action_count = 0
        self.cumulative_reward = 0.0
        info = self._info(event="reset")
        self.last_info = info
        return self._observation(), info

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        if not self.action_space.contains(action):
            raise ValueError(f"Invalid action {action!r}; expected 0, 1, or 2.")
        if self.current_idx >= self.max_idx:
            raise RuntimeError("Episode is already terminated; call reset().")

        action = int(action)
        nav_before = self._equity_at(self.current_idx)
        position_before = self.position
        invalid_action = False
        fill_price: Optional[float] = None
        realized_trade_return = 0.0

        if action == ACTION_MARKET_BUY:
            if self.position:
                invalid_action = True
            else:
                row = self._row(self.current_idx)
                fill_price = marketable_entry_price(
                    row.get("bid1"),
                    row.get("ask1"),
                    row["price"],
                    slippage_bps=float(self.config.slippage_bps),
                )
                self.position = 1
                self.entry_fill = fill_price
                self.entry_idx = self.current_idx
                self.trade_count += 1
        elif action == ACTION_MARKET_EXIT:
            if not self.position:
                invalid_action = True
            else:
                fill_price, realized_trade_return = self._exit_position(self.current_idx)

        if invalid_action:
            self.invalid_action_count += 1

        self.current_idx += 1
        terminated = self.current_idx >= self.max_idx
        truncated = False
        force_closed = False
        if terminated and self.position and self.config.force_close_on_done:
            fill_price, realized_trade_return = self._exit_position(self.current_idx)
            force_closed = True

        nav_after = self._equity_at(self.current_idx)
        reward = nav_after - nav_before
        if invalid_action:
            reward -= float(self.config.invalid_action_penalty)
        if not invalid_action and action in {ACTION_MARKET_BUY, ACTION_MARKET_EXIT}:
            reward -= float(self.config.overtrade_penalty)

        self.cumulative_reward += float(reward)
        info = self._info(event="step")
        info.update(
            {
                "action": action,
                "action_name": ACTION_NAMES[action],
                "position_before": position_before,
                "position_after": self.position,
                "invalid_action": invalid_action,
                "invalid_action_count": self.invalid_action_count,
                "fill_price": fill_price,
                "realized_trade_return": realized_trade_return,
                "realized_net_return": self.realized_net_return,
                "reward": float(reward),
                "cumulative_reward": self.cumulative_reward,
                "trade_count": self.trade_count,
                "force_closed": force_closed,
                "terminated": terminated,
                "truncated": truncated,
            }
        )
        self.last_info = info
        return self._observation(), float(reward), terminated, truncated, info

    def _exit_position(self, idx: int) -> Tuple[float, float]:
        row = self._row(idx)
        fill_price = marketable_exit_price(
            row.get("bid1"),
            row.get("ask1"),
            row["price"],
            slippage_bps=float(self.config.slippage_bps),
        )
        realized = (fill_price / self.entry_fill - 1.0) - self.cost_fraction
        self.realized_net_return += float(realized)
        self.position = 0
        self.entry_fill = 0.0
        self.entry_idx = None
        self.trade_count += 1
        return fill_price, float(realized)

    def _row(self, idx: int) -> Dict[str, Any]:
        return dict(self.frame.iloc[int(idx)])

    def _window_rows(self) -> List[Dict[str, Any]]:
        start = max(0, self.current_idx - self.config.lookback_window + 1)
        rows = []
        for row in self.frame.iloc[start : self.current_idx + 1].to_dict("records"):
            rows.append({key: row.get(key) for key in CANONICAL_COLUMNS})
        return rows

    def _equity_at(self, idx: int) -> float:
        return 1.0 + self.realized_net_return + self._unrealized_net_return(idx)

    def _unrealized_net_return(self, idx: Optional[int] = None) -> float:
        if not self.position or not self.entry_fill:
            return 0.0
        row = self._row(self.current_idx if idx is None else idx)
        exit_fill = marketable_exit_price(
            row.get("bid1"),
            row.get("ask1"),
            row["price"],
            slippage_bps=float(self.config.slippage_bps),
        )
        return float((exit_fill / self.entry_fill - 1.0) - self.cost_fraction)

    def _observation(self) -> np.ndarray:
        features = causal_feature_vector(self._window_rows())
        features["position"] = float(self.position)
        features["unrealized_net_pct"] = self._unrealized_net_return() * 100.0
        features["time_frac"] = float(features.get("t_frac", 0.0))
        values = np.array([float(features.get(name, 0.0)) for name in self.feature_columns], dtype=np.float32)
        if self.config.normalize_observation:
            values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
        return values

    def _timestamp(self) -> Optional[str]:
        row = self._row(self.current_idx)
        value = row.get("timestamp")
        return str(value) if value else None

    def _info(self, *, event: str) -> Dict[str, Any]:
        return {
            "event": event,
            "current_idx": self.current_idx,
            "timestamp": self._timestamp(),
            "sec": int(_float_or_zero(self._row(self.current_idx).get("sec"))),
            "equity": self._equity_at(self.current_idx),
            "position": self.position,
            "feature_columns": list(self.feature_columns),
            "action_space": dict(ACTION_NAMES),
            "no_future_observation": True,
            "config": asdict(self.config),
        }


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SQLite DB not found: {path}")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _list_stock_tables(conn: sqlite3.Connection, *, max_symbols: int) -> List[str]:
    names = [
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        if str(row[0]).isdigit()
    ]
    if max_symbols and max_symbols > 0:
        return names[: int(max_symbols)]
    return names


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()]


def _coverage_rows_for_table(conn: sqlite3.Connection, table: str) -> List[Tuple[Any, ...]]:
    qt = _quote_ident(table)
    q = f"""
        SELECT
          substr(CAST("index" AS TEXT), 1, 8) AS session,
          COUNT(*) AS total_rows,
          SUM(CASE WHEN "현재가" > 0 THEN 1 ELSE 0 END) AS price_rows,
          SUM(CASE WHEN "매수호가1" > 0 AND "매도호가1" > 0
                    AND "매수잔량1" >= 0 AND "매도잔량1" >= 0
                   THEN 1 ELSE 0 END) AS quote_rows,
          SUM(CASE WHEN "매수호가1" > 0 AND "매도호가1" > "매수호가1"
                   THEN 1 ELSE 0 END) AS valid_spread_rows
        FROM {qt}
        WHERE substr(CAST("index" AS TEXT), 9, 6) >= '090000'
          AND substr(CAST("index" AS TEXT), 9, 6) <= '092000'
        GROUP BY session
        ORDER BY session
    """
    return conn.execute(q).fetchall()


def _sample_episode_frame(
    conn: sqlite3.Connection,
    table: str,
    session: str,
    *,
    limit: int,
) -> pd.DataFrame:
    qt = _quote_ident(table)
    cols = ", ".join(_quote_ident(col) for col in DB_REQUIRED_COLUMNS)
    q = f"""
        SELECT {cols}
        FROM {qt}
        WHERE substr(CAST("index" AS TEXT), 1, 8) = ?
          AND substr(CAST("index" AS TEXT), 9, 6) >= '090000'
          AND substr(CAST("index" AS TEXT), 9, 6) <= '092000'
        ORDER BY "index"
        LIMIT ?
    """
    return pd.read_sql_query(q, conn, params=(str(session), int(limit)))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def assess_orderbook_rl_readiness(config: Optional[OrderbookRlReadinessConfig] = None) -> Dict[str, Any]:
    """Assess whether local STOM data is ready for marketable-only orderbook RL."""

    config = config or OrderbookRlReadinessConfig()
    db_path = Path(config.db_path)
    scanned_tables: List[str] = []
    missing_column_tables: List[Dict[str, Any]] = []
    coverage_rows: List[Dict[str, Any]] = []
    sample_env_smoke: Dict[str, Any] = {"passed": False, "message": "no eligible sample episode"}

    conn = _connect_readonly(db_path)
    try:
        all_tables = _list_stock_tables(conn, max_symbols=0)
        tables = all_tables[: int(config.max_symbols)] if config.max_symbols and config.max_symbols > 0 else all_tables
        for table in tables:
            columns = set(_table_columns(conn, table))
            missing = [col for col in DB_REQUIRED_COLUMNS if col not in columns]
            if missing:
                missing_column_tables.append({"table": table, "missing": missing})
                continue
            scanned_tables.append(table)
            for session, total_rows, price_rows, quote_rows, spread_rows in _coverage_rows_for_table(conn, table):
                total = int(total_rows or 0)
                row = {
                    "table": table,
                    "session": str(session),
                    "total_rows": total,
                    "price_rows": int(price_rows or 0),
                    "quote_rows": int(quote_rows or 0),
                    "valid_spread_rows": int(spread_rows or 0),
                    "eligible": total >= int(config.min_rows_per_episode),
                }
                coverage_rows.append(row)
                if not sample_env_smoke["passed"] and row["eligible"]:
                    try:
                        sample = _sample_episode_frame(
                            conn,
                            table,
                            str(session),
                            limit=max(int(config.min_rows_per_episode), int(config.lookback_window) + 3),
                        )
                        env = StomOrderbookRlEnv(
                            StomOrderbookRlEnvConfig(
                                lookback_window=int(config.lookback_window),
                                cost_bps=23.0,
                                slippage_bps=0.0,
                                max_episode_steps=3,
                            ),
                            frame=sample,
                        )
                        obs, info = env.reset(seed=100)
                        _, buy_reward, _, _, buy_info = env.step(ACTION_MARKET_BUY)
                        _, hold_reward, _, _, hold_info = env.step(ACTION_HOLD)
                        _, exit_reward, _, _, exit_info = env.step(ACTION_MARKET_EXIT)
                        sample_env_smoke = {
                            "passed": bool(env.observation_space.contains(obs)),
                            "table": table,
                            "session": str(session),
                            "feature_count": len(info["feature_columns"]),
                            "action_space": dict(ACTION_NAMES),
                            "buy_reward": buy_reward,
                            "hold_reward": hold_reward,
                            "exit_reward": exit_reward,
                            "position_after_exit": exit_info["position_after"],
                            "trade_count": exit_info["trade_count"],
                            "no_future_observation": bool(
                                info["no_future_observation"]
                                and buy_info["no_future_observation"]
                                and hold_info["no_future_observation"]
                                and exit_info["no_future_observation"]
                            ),
                        }
                    except Exception as exc:  # pragma: no cover - defensive path
                        sample_env_smoke = {
                            "passed": False,
                            "table": table,
                            "session": str(session),
                            "message": str(exc),
                        }
    finally:
        conn.close()

    total_rows = sum(int(row["total_rows"]) for row in coverage_rows)
    quote_rows = sum(int(row["quote_rows"]) for row in coverage_rows)
    valid_spread_rows = sum(int(row["valid_spread_rows"]) for row in coverage_rows)
    eligible_episodes = sum(1 for row in coverage_rows if row["eligible"])
    quote_coverage = quote_rows / total_rows if total_rows else 0.0
    valid_spread_coverage = valid_spread_rows / total_rows if total_rows else 0.0
    sample_limited = bool(config.max_symbols and config.max_symbols > 0 and len(scanned_tables) < len(all_tables))

    column_ok = bool(scanned_tables) and not missing_column_tables
    coverage_ok = quote_coverage >= float(config.min_quote_coverage)
    spread_ok = valid_spread_coverage >= float(config.min_valid_spread_coverage)
    episode_ok = eligible_episodes >= int(config.min_eligible_episodes)
    smoke_ok = bool(sample_env_smoke.get("passed")) and bool(sample_env_smoke.get("no_future_observation"))

    if not column_ok or not coverage_rows:
        readiness_status = "NO-GO_DATA"
    elif coverage_ok and spread_ok and smoke_ok and episode_ok and not sample_limited:
        readiness_status = "READY_FOR_MARKETABLE_RL"
    elif coverage_ok and spread_ok and smoke_ok:
        readiness_status = "INCONCLUSIVE"
    else:
        readiness_status = "NO-GO_DATA"

    summary = {
        "readiness_status": readiness_status,
        "verdict": readiness_status,
        "is_live_ready": False,
        "is_profit_model": False,
        "environment": "StomOrderbookRlEnv",
        "action_space": dict(ACTION_NAMES),
        "feature_count": len(ORDERBOOK_FEATURE_NAMES),
        "scanned_table_count": len(scanned_tables),
        "total_table_count": len(all_tables),
        "sample_limited": sample_limited,
        "coverage_row_count": total_rows,
        "eligible_episode_count": eligible_episodes,
        "quote_coverage": quote_coverage,
        "valid_spread_coverage": valid_spread_coverage,
        "min_eligible_episodes": int(config.min_eligible_episodes),
        "min_quote_coverage": float(config.min_quote_coverage),
        "min_valid_spread_coverage": float(config.min_valid_spread_coverage),
        "sample_env_smoke_passed": smoke_ok,
        "safety_note": (
            "Marketable-only RL readiness artifact. This is not a live-trading "
            "approval and not a profitability claim."
        ),
    }
    payload: Dict[str, Any] = {
        "mode": "stom_orderbook_rl_readiness",
        "artifact_type": "orderbook_rl_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "config": asdict(config),
        "required_db_columns": list(DB_REQUIRED_COLUMNS),
        "observation_features": list(ORDERBOOK_FEATURE_NAMES),
        "sample_env_smoke": sample_env_smoke,
        "coverage_sample": coverage_rows[:200],
        "missing_column_tables": missing_column_tables[:50],
        "artifacts": {
            "output_dir": str(Path(config.output_dir)),
            "summary_json": str(Path(config.output_dir) / "orderbook_rl_readiness_summary.json"),
            "summary_csv": str(Path(config.output_dir) / "orderbook_rl_readiness.csv"),
            "omx_summary_json": str(Path(config.omx_output_dir) / "summary.json"),
        },
    }

    if config.write_artifacts:
        output_dir = Path(config.output_dir)
        _write_json(output_dir / "orderbook_rl_readiness_summary.json", payload)
        _write_csv(
            output_dir / "orderbook_rl_readiness.csv",
            [summary],
            [
                "readiness_status",
                "verdict",
                "scanned_table_count",
                "total_table_count",
                "sample_limited",
                "coverage_row_count",
                "eligible_episode_count",
                "quote_coverage",
                "valid_spread_coverage",
                "sample_env_smoke_passed",
            ],
        )
        _write_json(Path(config.omx_output_dir) / "summary.json", payload)
    return payload


def _parse_args(argv: Optional[Sequence[str]] = None) -> OrderbookRlReadinessConfig:
    parser = argparse.ArgumentParser(
        description="Assess STOM tick+orderbook readiness for marketable-only RL."
    )
    parser.add_argument("--db-path", "--db", default=str(Path("_database") / "stock_tick_back.db"))
    parser.add_argument("--output-dir", default=str(DEFAULT_READINESS_OUTPUT_DIR))
    parser.add_argument("--omx-output-dir", default=str(DEFAULT_OMX_READINESS_DIR))
    parser.add_argument("--max-symbols", type=int, default=200)
    parser.add_argument("--min-rows-per-episode", type=int, default=35)
    parser.add_argument("--lookback-window", type=int, default=30)
    parser.add_argument("--min-eligible-episodes", type=int, default=1000)
    parser.add_argument("--min-quote-coverage", type=float, default=0.95)
    parser.add_argument("--min-valid-spread-coverage", type=float, default=0.90)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    return OrderbookRlReadinessConfig(
        db_path=args.db_path,
        output_dir=args.output_dir,
        omx_output_dir=args.omx_output_dir,
        max_symbols=args.max_symbols,
        min_rows_per_episode=args.min_rows_per_episode,
        lookback_window=args.lookback_window,
        min_eligible_episodes=args.min_eligible_episodes,
        min_quote_coverage=args.min_quote_coverage,
        min_valid_spread_coverage=args.min_valid_spread_coverage,
        write_artifacts=not args.no_write,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    payload = assess_orderbook_rl_readiness(_parse_args(argv))
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    if payload.get("artifacts"):
        print(f"wrote -> {payload['artifacts']['summary_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
