"""Tests for placeholder signal rules."""

import pandas as pd

from kronos_ext.signals.rules import decide_signal


def test_decide_signal_buy_sell_wait():
    history = pd.DataFrame([{"close": 100.0}])

    assert decide_signal(history, pd.DataFrame([{"close": 101.0}])).action == "BUY"
    assert decide_signal(history, pd.DataFrame([{"close": 99.0}])).action == "SELL"
    assert decide_signal(history, pd.DataFrame([{"close": 100.01}])).action == "WAIT"
