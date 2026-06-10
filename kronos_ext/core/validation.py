"""Validation helpers for extension DataFrame inputs."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def validate_ohlcv_columns(
    df: pd.DataFrame,
    required_columns: Iterable[str] = REQUIRED_OHLCV_COLUMNS,
) -> None:
    """Validate that a DataFrame contains the required OHLCV columns.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.
        ValueError: If required columns are missing or contain null values.
    """

    if not isinstance(df, pd.DataFrame):
        raise TypeError("Expected a pandas DataFrame.")

    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    if df[list(required_columns)].isnull().values.any():
        raise ValueError("OHLCV columns must not contain null values.")
