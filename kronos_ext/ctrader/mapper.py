"""Mapping helpers from cTrader-like candle payloads to Kronos inputs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from kronos_ext.core.validation import validate_ohlcv_columns


def candles_to_dataframe(candles: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Convert generic cTrader-like candle dictionaries to an OHLCV DataFrame.

    Accepted timestamp keys are preserved as a ``timestamp`` column when present.
    Accepted volume aliases are ``volume`` and ``tickVolume``.

    TODO: Adjust field aliases when the real cTrader payload is selected.
    """

    rows: list[dict[str, Any]] = []
    for candle in candles:
        rows.append(
            {
                "timestamp": candle.get("timestamp", candle.get("time")),
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle.get("volume", candle.get("tickVolume", 0.0)),
            }
        )

    df = pd.DataFrame(rows)
    validate_ohlcv_columns(df)
    return df
