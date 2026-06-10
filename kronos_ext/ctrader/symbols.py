"""Symbol normalization helpers for cTrader-facing workflows."""

from __future__ import annotations


def normalize_symbol(symbol: str) -> str:
    """Normalize a symbol string without applying broker-specific mapping."""

    return symbol.strip().upper()
