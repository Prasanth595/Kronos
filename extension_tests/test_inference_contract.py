"""Tests for the inert inference adapter contract."""

import pandas as pd
import pytest

from kronos_ext.inference.predictor import KronosPredictorAdapter


def test_predictor_adapter_requires_injected_predictor():
    adapter = KronosPredictorAdapter()
    candles = pd.DataFrame(
        [{"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0}]
    )
    timestamps = pd.Series(pd.to_datetime(["2026-01-01T00:00:00Z"]))

    with pytest.raises(RuntimeError):
        adapter.predict(candles, timestamps, timestamps, pred_len=1)
