"""Timeframe normalization helpers for cTrader-style inputs.

TODO: Expand this mapping once the real cTrader bridge shape is confirmed.
"""

from __future__ import annotations


_TIMEFRAME_ALIASES = {
    "m1": "1min",
    "minute1": "1min",
    "m5": "5min",
    "minute5": "5min",
    "m15": "15min",
    "minute15": "15min",
    "m30": "30min",
    "minute30": "30min",
    "h1": "1h",
    "hour1": "1h",
    "h4": "4h",
    "hour4": "4h",
    "d1": "1d",
    "day1": "1d",
}


def normalize_timeframe(value: str) -> str:
    """Return a canonical timeframe string for known cTrader-style aliases."""

    key = value.strip().lower()
    return _TIMEFRAME_ALIASES.get(key, key)
