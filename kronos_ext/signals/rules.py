"""Minimal placeholder rules for BUY, SELL, and WAIT signal decisions."""

from __future__ import annotations

import pandas as pd

from kronos_ext.core.schemas import Signal


def decide_signal(
    history: pd.DataFrame,
    forecast: pd.DataFrame,
    threshold: float = 0.001,
) -> Signal:
    """Return BUY, SELL, or WAIT from the forecast close-price change.

    The threshold is a fractional move from the latest historical close to the
    final forecast close. This is intentionally simple and not trading advice.
    """

    if "close" not in history.columns or "close" not in forecast.columns:
        raise ValueError("Both history and forecast must include a close column.")
    if history.empty or forecast.empty:
        raise ValueError("History and forecast must not be empty.")

    last_close = float(history["close"].iloc[-1])
    forecast_close = float(forecast["close"].iloc[-1])
    if last_close == 0:
        return Signal(action="WAIT", confidence=0.0, reason="Last close is zero.")

    change = (forecast_close - last_close) / last_close
    confidence = min(abs(change) / max(threshold, 1e-12), 1.0)

    if change > threshold:
        return Signal(action="BUY", confidence=confidence, reason="Forecast close is above threshold.")
    if change < -threshold:
        return Signal(action="SELL", confidence=confidence, reason="Forecast close is below threshold.")
    return Signal(action="WAIT", confidence=confidence, reason="Forecast move is within threshold.")
