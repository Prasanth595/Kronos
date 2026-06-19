import argparse
import json
import os
import random
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


FEATURE_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]
TIME_FEATURE_COLUMNS = ["minute", "hour", "weekday", "day", "month"]
DEFAULT_GROUP_COLUMNS = ["symbol", "session"]


def _normalize_session_bound(value: Optional[str], label: str) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).replace("-", "").strip()
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"{label} must be YYYYMMDD or YYYY-MM-DD, got: {value}")
    return text


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def connect_readonly(db_path: os.PathLike | str) -> sqlite3.Connection:
    """Open a SQLite database in read-only/query-only mode."""

    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {path}")

    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def list_stock_tables(conn: sqlite3.Connection, max_tables: Optional[int] = None) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    tables = [row[0] for row in rows]
    if max_tables and max_tables > 0:
        tables = tables[:max_tables]
    return tables


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({_quote_ident(table_name)})")]


def _first_existing(columns: Sequence[str], candidates: Sequence[str]) -> Optional[str]:
    column_set = set(columns)
    for candidate in candidates:
        if candidate in column_set:
            return candidate
    return None


def infer_stom_column_mapping(columns: Sequence[str], price_mode: str = "db_ohlc") -> Dict[str, Any]:
    """Infer how a STOM tick table maps to Kronos OHLCV columns.

    price_mode:
      - db_ohlc: use DB open/high/low columns when present, close from 종가/현재가.
      - close_only: map open/high/low/close all from the close/current price column.
    """

    if price_mode not in {"db_ohlc", "close_only"}:
        raise ValueError("price_mode must be one of: db_ohlc, close_only")

    timestamp_col = _first_existing(columns, ["index", "timestamps", "timestamp", "datetime", "일시"])
    close_col = _first_existing(columns, ["종가", "현재가", "close", "Close"])
    if timestamp_col is None or close_col is None:
        missing = []
        if timestamp_col is None:
            missing.append("timestamp/index")
        if close_col is None:
            missing.append("close/current price")
        raise ValueError(f"Missing required STOM columns: {', '.join(missing)}")

    if price_mode == "close_only":
        open_col = high_col = low_col = close_col
    else:
        open_col = _first_existing(columns, ["시가", "open", "Open"]) or close_col
        high_col = _first_existing(columns, ["고가", "high", "High"]) or close_col
        low_col = _first_existing(columns, ["저가", "low", "Low"]) or close_col

    volume_col = _first_existing(columns, ["volume", "Volume", "거래량", "초당거래량"])
    buy_qty_col = _first_existing(columns, ["초당매수수량", "매수수량"])
    sell_qty_col = _first_existing(columns, ["초당매도수량", "매도수량"])

    amount_col = _first_existing(columns, ["amount", "Amount", "거래대금", "초당거래대금"])

    warnings: List[str] = []
    if "종가" not in columns and close_col == "현재가":
        warnings.append("종가 column not found; using 현재가 as close.")
    if price_mode == "db_ohlc" and {"시가", "고가", "저가"}.issubset(set(columns)):
        warnings.append(
            "Using DB 시가/고가/저가 as OHLC. If these are cumulative session fields, "
            "use --price-mode close_only for tick-last-price training."
        )
    if volume_col is None and not (buy_qty_col and sell_qty_col):
        warnings.append("No direct volume column; volume will fall back to 0 if buy/sell quantities are absent.")
    if amount_col is None:
        warnings.append("No amount column; amount will be derived from close * volume.")

    return {
        "timestamp": timestamp_col,
        "open": open_col,
        "high": high_col,
        "low": low_col,
        "close": close_col,
        "volume": volume_col,
        "buy_qty": buy_qty_col,
        "sell_qty": sell_qty_col,
        "amount": amount_col,
        "warnings": warnings,
        "price_mode": price_mode,
    }


def _timestamp_series(raw: pd.Series) -> pd.Series:
    if np.issubdtype(raw.dtype, np.number):
        return pd.to_datetime(raw.astype("Int64").astype(str), format="%Y%m%d%H%M%S", errors="coerce")
    parsed = pd.to_datetime(raw, errors="coerce")
    if parsed.isna().all():
        parsed = pd.to_datetime(raw.astype(str), format="%Y%m%d%H%M%S", errors="coerce")
    return parsed


def _required_sql_columns(mapping: Dict[str, Any]) -> List[str]:
    cols = {
        mapping["timestamp"],
        mapping["open"],
        mapping["high"],
        mapping["low"],
        mapping["close"],
    }
    for optional_key in ("volume", "buy_qty", "sell_qty", "amount"):
        value = mapping.get(optional_key)
        if value:
            cols.add(value)
    return sorted(cols)


def read_stom_table_as_kline(
    conn: sqlite3.Connection,
    table_name: str,
    price_mode: str = "db_ohlc",
    time_start: str = "090000",
    time_end: str = "093000",
    session_start: Optional[str] = None,
    session_end: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Read one STOM symbol table and convert it to Kronos OHLCV rows."""

    session_start = _normalize_session_bound(session_start, "session_start")
    session_end = _normalize_session_bound(session_end, "session_end")
    if session_start and session_end and session_start > session_end:
        raise ValueError("session_start must be <= session_end")

    columns = get_table_columns(conn, table_name)
    mapping = infer_stom_column_mapping(columns, price_mode=price_mode)
    sql_columns = _required_sql_columns(mapping)
    select_clause = ", ".join(_quote_ident(col) for col in sql_columns)
    order_col = _quote_ident(mapping["timestamp"])
    timestamp_session_expr = (
        f"substr(replace(replace(replace(CAST({order_col} AS TEXT), '-', ''), ':', ''), ' ', ''), 1, 8)"
    )
    where_clauses = []
    params: List[str] = []
    if session_start:
        where_clauses.append(f"{timestamp_session_expr} >= ?")
        params.append(session_start)
    if session_end:
        where_clauses.append(f"{timestamp_session_expr} <= ?")
        params.append(session_end)
    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    source = pd.read_sql_query(
        f"SELECT {select_clause} FROM {_quote_ident(table_name)}{where_sql} ORDER BY {order_col}",
        conn,
        params=params,
    )

    timestamps = _timestamp_series(source[mapping["timestamp"]])
    close = pd.to_numeric(source[mapping["close"]], errors="coerce")
    if price_mode == "close_only":
        open_ = high = low = close
    else:
        open_ = pd.to_numeric(source[mapping["open"]], errors="coerce")
        high = pd.to_numeric(source[mapping["high"]], errors="coerce")
        low = pd.to_numeric(source[mapping["low"]], errors="coerce")

    if mapping.get("volume"):
        volume = pd.to_numeric(source[mapping["volume"]], errors="coerce").fillna(0.0)
    elif mapping.get("buy_qty") and mapping.get("sell_qty"):
        buy_qty = pd.to_numeric(source[mapping["buy_qty"]], errors="coerce").fillna(0.0)
        sell_qty = pd.to_numeric(source[mapping["sell_qty"]], errors="coerce").fillna(0.0)
        volume = buy_qty + sell_qty
    else:
        volume = pd.Series(np.zeros(len(source)), index=source.index, dtype="float64")

    if mapping.get("amount"):
        amount = pd.to_numeric(source[mapping["amount"]], errors="coerce").fillna(0.0)
    else:
        amount = close.fillna(0.0) * volume.fillna(0.0)

    frame = pd.DataFrame(
        {
            "symbol": table_name,
            "timestamps": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": amount,
        }
    )
    frame = frame.dropna(subset=["timestamps", "open", "high", "low", "close"])
    frame = frame[(frame[["open", "high", "low", "close"]] > 0).all(axis=1)]

    if time_start or time_end:
        hhmmss = frame["timestamps"].dt.strftime("%H%M%S")
        if time_start:
            frame = frame[hhmmss >= time_start]
        if time_end:
            frame = frame[hhmmss <= time_end]

    frame["session"] = frame["timestamps"].dt.strftime("%Y%m%d")
    if session_start:
        frame = frame[frame["session"] >= session_start]
    if session_end:
        frame = frame[frame["session"] <= session_end]
    frame = frame.sort_values(["session", "timestamps"]).drop_duplicates(
        subset=["symbol", "session", "timestamps"], keep="last"
    )
    return frame[DEFAULT_GROUP_COLUMNS + ["timestamps"] + FEATURE_COLUMNS].reset_index(drop=True), mapping


def inspect_stom_tick_db(
    db_path: os.PathLike | str,
    max_tables: int = 20,
    lookback_window: int = 300,
    predict_window: int = 60,
    price_mode: str = "db_ohlc",
) -> Dict[str, Any]:
    """Inspect a STOM SQLite DB and report whether it can produce training windows."""

    min_rows = lookback_window + predict_window + 1
    db_file = Path(db_path)
    conn = connect_readonly(db_file)
    try:
        all_tables = list_stock_tables(conn, max_tables=None)
        scan_tables = all_tables[:max_tables] if max_tables and max_tables > 0 else all_tables
        compatible_tables = 0
        eligible_groups = 0
        table_summaries = []
        warnings = set()

        for table in scan_tables:
            try:
                columns = get_table_columns(conn, table)
                mapping = infer_stom_column_mapping(columns, price_mode=price_mode)
                warnings.update(mapping.get("warnings", []))
                row_count = conn.execute(f"SELECT COUNT(*) FROM {_quote_ident(table)}").fetchone()[0]
                minmax = conn.execute(
                    f"SELECT MIN({_quote_ident(mapping['timestamp'])}), MAX({_quote_ident(mapping['timestamp'])}) "
                    f"FROM {_quote_ident(table)}"
                ).fetchone()
                group_rows = conn.execute(
                    f"SELECT substr(CAST({_quote_ident(mapping['timestamp'])} AS TEXT), 1, 8) AS session, "
                    f"COUNT(*) AS rows FROM {_quote_ident(table)} "
                    f"GROUP BY session HAVING rows >= ? ORDER BY session",
                    (min_rows,),
                ).fetchall()
                compatible_tables += 1
                eligible_groups += len(group_rows)
                table_summaries.append(
                    {
                        "table": table,
                        "row_count": row_count,
                        "min_timestamp": minmax[0],
                        "max_timestamp": minmax[1],
                        "eligible_sessions": len(group_rows),
                        "columns": columns,
                        "mapping": {k: v for k, v in mapping.items() if k != "warnings"},
                    }
                )
            except Exception as exc:  # pragma: no cover - included in JSON report for real DBs
                table_summaries.append({"table": table, "error": str(exc)})

        return {
            "db_path": str(db_file),
            "db_size_bytes": db_file.stat().st_size if db_file.exists() else None,
            "table_count": len(all_tables),
            "scanned_table_count": len(scan_tables),
            "compatible_table_count": compatible_tables,
            "min_rows_per_group": min_rows,
            "eligible_group_count": eligible_groups,
            "trainable": compatible_tables > 0 and eligible_groups > 0,
            "price_mode": price_mode,
            "warnings": sorted(warnings),
            "tables": table_summaries,
        }
    finally:
        conn.close()


def export_stom_tick_db_to_csv(
    db_path: os.PathLike | str,
    output_path: os.PathLike | str,
    max_tables: int = 0,
    tables: Optional[Sequence[str]] = None,
    lookback_window: int = 300,
    predict_window: int = 60,
    price_mode: str = "db_ohlc",
    time_start: str = "090000",
    time_end: str = "093000",
    session_start: Optional[str] = None,
    session_end: Optional[str] = None,
    max_rows_per_group: int = 0,
) -> Dict[str, Any]:
    """Convert STOM per-symbol SQLite tables to a grouped Kronos training CSV."""

    session_start = _normalize_session_bound(session_start, "session_start")
    session_end = _normalize_session_bound(session_end, "session_end")
    if session_start and session_end and session_start > session_end:
        raise ValueError("session_start must be <= session_end")

    min_rows = lookback_window + predict_window + 1
    if max_rows_per_group and max_rows_per_group > 0 and max_rows_per_group < min_rows:
        raise ValueError(
            f"max_rows_per_group={max_rows_per_group} is smaller than required window rows={min_rows}."
        )
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    conn = connect_readonly(db_path)
    try:
        selected_tables = list(tables) if tables else list_stock_tables(conn, max_tables=None)
        if max_tables and max_tables > 0:
            selected_tables = selected_tables[:max_tables]

        if output_file.exists():
            output_file.unlink()

        written_rows = 0
        written_groups = 0
        skipped_groups = 0
        clipped_groups = 0
        table_reports = []
        wrote_header = False

        for table in selected_tables:
            try:
                frame, mapping = read_stom_table_as_kline(
                    conn,
                    table,
                    price_mode=price_mode,
                    time_start=time_start,
                    time_end=time_end,
                    session_start=session_start,
                    session_end=session_end,
                )
                kept_parts = []
                for (_, _), group in frame.groupby(DEFAULT_GROUP_COLUMNS, sort=True):
                    if len(group) >= min_rows:
                        if max_rows_per_group and max_rows_per_group > 0 and len(group) > max_rows_per_group:
                            group = group.head(max_rows_per_group)
                            clipped_groups += 1
                        kept_parts.append(group)
                    else:
                        skipped_groups += 1

                if not kept_parts:
                    table_reports.append(
                        {
                            "table": table,
                            "written_rows": 0,
                            "written_groups": 0,
                            "skipped_reason": f"no group with at least {min_rows} rows",
                        }
                    )
                    continue

                out = pd.concat(kept_parts, ignore_index=True)
                out.to_csv(
                    output_file,
                    mode="a",
                    header=not wrote_header,
                    index=False,
                    encoding="utf-8-sig",
                )
                wrote_header = True
                written_rows += len(out)
                written_groups += len(kept_parts)
                table_reports.append(
                    {
                        "table": table,
                        "written_rows": len(out),
                        "written_groups": len(kept_parts),
                        "mapping": {k: v for k, v in mapping.items() if k != "warnings"},
                        "warnings": mapping.get("warnings", []),
                    }
                )
            except Exception as exc:  # pragma: no cover - included in JSON report for real DBs
                table_reports.append({"table": table, "error": str(exc)})

        return {
            "db_path": str(db_path),
            "output_path": str(output_file),
            "selected_table_count": len(selected_tables),
            "written_rows": written_rows,
            "written_groups": written_groups,
            "skipped_groups": skipped_groups,
            "clipped_groups": clipped_groups,
            "max_rows_per_group": max_rows_per_group,
            "min_rows_per_group": min_rows,
            "price_mode": price_mode,
            "session_start": session_start,
            "session_end": session_end,
            "trainable_csv_created": written_rows > 0 and written_groups > 0,
            "tables": table_reports,
        }
    finally:
        conn.close()


class GroupedKlineDataset:
    """Kronos OHLCV dataset that never crosses symbol/session boundaries."""

    def __init__(
        self,
        data_path: os.PathLike | str,
        data_type: str = "train",
        lookback_window: int = 90,
        predict_window: int = 10,
        clip: float = 5.0,
        seed: int = 100,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        group_columns: Optional[Sequence[str]] = None,
        sample_stride: int = 1,
        max_samples: Optional[int] = None,
        normalize_using: str = "lookback",
    ):
        self.data_path = str(data_path)
        self.data_type = data_type
        self.lookback_window = lookback_window
        self.predict_window = predict_window
        self.window = lookback_window + predict_window + 1
        self.clip = clip
        self.seed = seed
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.group_columns = list(group_columns or DEFAULT_GROUP_COLUMNS)
        self.sample_stride = max(1, int(sample_stride))
        self.max_samples = max_samples
        self.normalize_using = normalize_using
        self.feature_list = FEATURE_COLUMNS
        self.time_feature_list = TIME_FEATURE_COLUMNS
        self.py_rng = random.Random(seed)

        if normalize_using not in {"lookback", "window"}:
            raise ValueError("normalize_using must be one of: lookback, window")

        self._load_groups()
        self._split_groups()
        self._build_sample_index()
        print(
            f"[{data_type.upper()}][GROUPED] Groups: {len(self.groups)}, "
            f"Available samples: {len(self.sample_index)}"
        )

    def _load_groups(self):
        dtype = {column: str for column in self.group_columns}
        df = pd.read_csv(self.data_path, dtype=dtype)
        required = set(self.group_columns + ["timestamps"] + self.feature_list)
        missing = sorted(required - set(df.columns))
        if missing:
            raise ValueError(f"Grouped CSV missing required columns: {missing}")

        df["timestamps"] = pd.to_datetime(df["timestamps"])
        df = df.sort_values(self.group_columns + ["timestamps"]).reset_index(drop=True)

        for feature in self.feature_list:
            df[feature] = pd.to_numeric(df[feature], errors="coerce")
        df[self.feature_list] = df.groupby(self.group_columns, sort=False)[self.feature_list].ffill()
        df[self.feature_list] = df.groupby(self.group_columns, sort=False)[self.feature_list].bfill()
        df = df.dropna(subset=self.feature_list + ["timestamps"])

        df["minute"] = df["timestamps"].dt.minute
        df["hour"] = df["timestamps"].dt.hour
        df["weekday"] = df["timestamps"].dt.weekday
        df["day"] = df["timestamps"].dt.day
        df["month"] = df["timestamps"].dt.month

        groups = []
        for group_key, group_df in df.groupby(self.group_columns, sort=True):
            if len(group_df) < self.window:
                continue
            if not isinstance(group_key, tuple):
                group_key = (group_key,)
            values = group_df[self.feature_list + self.time_feature_list].values.astype(np.float32)
            timestamps = group_df["timestamps"].reset_index(drop=True)
            groups.append(
                {
                    "key": tuple(str(part) for part in group_key),
                    "first_timestamp": timestamps.iloc[0],
                    "last_timestamp": timestamps.iloc[-1],
                    "values": values,
                    "timestamps": timestamps,
                    "rows": len(group_df),
                }
            )

        if not groups:
            raise ValueError(
                f"No grouped CSV segment has enough rows for window={self.window}. "
                f"Check lookback_window/predict_window or export more data."
            )
        self.all_groups = sorted(groups, key=lambda item: (item["first_timestamp"], item["key"]))

    def _split_groups(self):
        total = len(self.all_groups)
        train_end = int(total * self.train_ratio)
        val_end = int(total * (self.train_ratio + self.val_ratio))

        if self.train_ratio > 0 and train_end == 0 and total > 0:
            train_end = 1
        if self.val_ratio > 0 and val_end <= train_end and total > train_end:
            val_end = train_end + 1

        if self.data_type == "train":
            groups = self.all_groups[:train_end]
        elif self.data_type == "val":
            groups = self.all_groups[train_end:val_end]
        elif self.data_type == "test":
            groups = self.all_groups[val_end:]
        else:
            raise ValueError("data_type must be one of: train, val, test")

        if not groups:
            raise ValueError(
                f"No groups available for split '{self.data_type}'. "
                f"Ratios train={self.train_ratio}, val={self.val_ratio}, test={self.test_ratio}, "
                f"total_groups={total}."
            )
        self.groups = groups

    def _build_sample_index(self):
        sample_index = []
        for group_idx, group in enumerate(self.groups):
            max_start = group["rows"] - self.window
            for start_idx in range(0, max_start + 1, self.sample_stride):
                sample_index.append((group_idx, start_idx))

        if self.max_samples is not None and len(sample_index) > self.max_samples:
            rng = random.Random(self.seed)
            sample_index = sorted(rng.sample(sample_index, int(self.max_samples)))

        self.sample_index = sample_index
        if not self.sample_index:
            raise ValueError("No samples available after applying grouped dataset filters.")
        self.n_samples = len(self.sample_index)

    def set_epoch_seed(self, epoch):
        epoch_seed = self.seed + epoch
        self.py_rng.seed(epoch_seed)
        self.current_epoch = epoch

    def __len__(self):
        return len(self.sample_index)

    def _resolve_index(self, idx: int) -> Tuple[int, int]:
        if self.data_type == "train":
            epoch = getattr(self, "current_epoch", 0)
            mapped_idx = (idx * 9973 + (epoch + 1) * 104729) % len(self.sample_index)
            return self.sample_index[mapped_idx]
        return self.sample_index[idx % len(self.sample_index)]

    def sample_metadata(self, idx: int) -> Dict[str, Any]:
        group_idx, start_idx = self._resolve_index(idx)
        group = self.groups[group_idx]
        end_idx = start_idx + self.window
        return {
            "group_key": group["key"],
            "start_idx": start_idx,
            "end_idx": end_idx,
            "start_timestamp": str(group["timestamps"].iloc[start_idx]),
            "end_timestamp": str(group["timestamps"].iloc[end_idx - 1]),
        }

    def get_numpy(self, idx: int) -> Tuple[np.ndarray, np.ndarray]:
        group_idx, start_idx = self._resolve_index(idx)
        group = self.groups[group_idx]
        end_idx = start_idx + self.window
        window_data = group["values"][start_idx:end_idx]

        x = window_data[:, : len(self.feature_list)].astype(np.float32)
        x_stamp = window_data[:, len(self.feature_list) :].astype(np.float32)

        norm_ref = x[: self.lookback_window] if self.normalize_using == "lookback" else x
        x_mean, x_std = np.mean(norm_ref, axis=0), np.std(norm_ref, axis=0)
        x = (x - x_mean) / (x_std + 1e-5)
        x = np.clip(x, -self.clip, self.clip)

        return x, x_stamp

    def __getitem__(self, idx):
        import torch

        x, x_stamp = self.get_numpy(idx)
        return torch.from_numpy(x), torch.from_numpy(x_stamp)


def _write_json_if_requested(payload: Dict[str, Any], json_output: Optional[str]):
    if not json_output:
        return
    output_path = Path(json_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare STOM 1tick SQLite data for Kronos finetuning.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect DB schema and trainability.")
    inspect_parser.add_argument("--db", required=True, help="Path to STOM SQLite DB.")
    inspect_parser.add_argument("--max-tables", type=int, default=20, help="Tables to scan. 0 means all.")
    inspect_parser.add_argument("--lookback-window", type=int, default=300)
    inspect_parser.add_argument("--predict-window", type=int, default=60)
    inspect_parser.add_argument("--price-mode", choices=["db_ohlc", "close_only"], default="db_ohlc")
    inspect_parser.add_argument("--json-output", default=None)

    export_parser = subparsers.add_parser("export", help="Export grouped Kronos OHLCV CSV.")
    export_parser.add_argument("--db", required=True, help="Path to STOM SQLite DB.")
    export_parser.add_argument("--output", required=True, help="Output CSV path.")
    export_parser.add_argument("--max-tables", type=int, default=100, help="Tables to export. 0 means all.")
    export_parser.add_argument("--tables", nargs="*", default=None, help="Optional explicit table/symbol names.")
    export_parser.add_argument("--lookback-window", type=int, default=300)
    export_parser.add_argument("--predict-window", type=int, default=60)
    export_parser.add_argument("--price-mode", choices=["db_ohlc", "close_only"], default="db_ohlc")
    export_parser.add_argument("--time-start", default="090000")
    export_parser.add_argument("--time-end", default="093000")
    export_parser.add_argument("--session-start", default=None, help="Optional inclusive YYYYMMDD session lower bound.")
    export_parser.add_argument("--session-end", default=None, help="Optional inclusive YYYYMMDD session upper bound.")
    export_parser.add_argument(
        "--max-rows-per-group",
        type=int,
        default=0,
        help="Clip each symbol/session group to this many contiguous rows after filtering. 0 means keep all rows.",
    )
    export_parser.add_argument("--json-output", default=None)

    args = parser.parse_args(argv)

    if args.command == "inspect":
        payload = inspect_stom_tick_db(
            db_path=args.db,
            max_tables=args.max_tables,
            lookback_window=args.lookback_window,
            predict_window=args.predict_window,
            price_mode=args.price_mode,
        )
    else:
        payload = export_stom_tick_db_to_csv(
            db_path=args.db,
            output_path=args.output,
            max_tables=args.max_tables,
            tables=args.tables,
            lookback_window=args.lookback_window,
            predict_window=args.predict_window,
            price_mode=args.price_mode,
            time_start=args.time_start,
            time_end=args.time_end,
            session_start=args.session_start,
            session_end=args.session_end,
            max_rows_per_group=args.max_rows_per_group,
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    _write_json_if_requested(payload, getattr(args, "json_output", None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
