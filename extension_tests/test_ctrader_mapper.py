"""Tests for cTrader payload mapping."""

from kronos_ext.ctrader.mapper import candles_to_dataframe


def test_candles_to_dataframe_maps_ohlcv_columns():
    candles = [
        {
            "time": "2026-01-01T00:00:00Z",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "tickVolume": 10,
        }
    ]

    df = candles_to_dataframe(candles)

    assert list(df[["open", "high", "low", "close", "volume"]].columns) == [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    assert df.loc[0, "volume"] == 10
