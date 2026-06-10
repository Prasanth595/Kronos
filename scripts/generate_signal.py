"""Placeholder script for future forecast-to-signal generation."""

from __future__ import annotations

import pandas as pd

from kronos_ext.signals.engine import generate_signal


def main() -> int:
    """Run a tiny offline signal example."""

    history = pd.DataFrame([{"close": 100.0}])
    forecast = pd.DataFrame([{"close": 100.0}])
    signal = generate_signal(history=history, forecast=forecast)
    print(signal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
