"""Lightweight data contracts used across the extension layer.

These dataclasses intentionally avoid runtime validation beyond basic typing.
Use ``kronos_ext.core.validation`` for DataFrame checks before inference.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


SignalAction = Literal["BUY", "SELL", "WAIT"]


@dataclass(frozen=True)
class Candle:
    """Normalized OHLCV candle used before conversion to a pandas DataFrame."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class ForecastRequest:
    """Request metadata for a local Kronos forecast workflow."""

    symbol: str
    timeframe: str
    lookback: int
    pred_len: int
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ForecastResult:
    """Container for forecast output and associated request metadata."""

    request: ForecastRequest
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class Signal:
    """Simple trading signal representation without execution details."""

    action: SignalAction
    confidence: float
    reason: str
