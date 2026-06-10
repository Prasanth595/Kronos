"""Signal engine facade for forecast outputs."""

from __future__ import annotations

import pandas as pd

from kronos_ext.core.schemas import Signal
from kronos_ext.signals.rules import decide_signal


def generate_signal(history: pd.DataFrame, forecast: pd.DataFrame) -> Signal:
    """Generate a simple signal from historical and forecast close prices."""

    return decide_signal(history=history, forecast=forecast)
