"""Unit tests for causal microstructure features (Page R-P1).

RULE strategy, NOT reinforcement learning.  Known-value checks for the pure
helpers and the causal feature vector, plus a structural causality check (the
vector at the decision row never depends on future rows).  No DB / no I/O.
"""

from __future__ import annotations

import math

import pytest

from stom_rl.microstructure_features import (
    FEATURE_NAMES,
    causal_feature_vector,
    depth_ofi,
    imbalance,
    linfit_slope,
    microprice,
    pct_return,
    signed_flow,
)


def _approx(value, expected, tol=1e-9):
    return abs(value - expected) <= tol


def test_pct_return():
    assert _approx(pct_return(100.0, 105.0), 5.0)
    assert _approx(pct_return(100.0, 100.0), 0.0)
    assert pct_return(0.0, 5.0) is None
    assert pct_return(None, 5.0) is None


def test_imbalance():
    assert _approx(imbalance(60.0, 40.0), 0.6)
    assert imbalance(0.0, 0.0) is None
    assert imbalance(None, 40.0) is None


def test_signed_flow():
    assert _approx(signed_flow(100.0, 30.0), 70.0)
    assert _approx(signed_flow(None, 30.0), -30.0)
    assert _approx(signed_flow(50.0, None), 50.0)


def test_linfit_slope():
    assert _approx(linfit_slope([1.0, 2.0, 3.0, 4.0]), 1.0)  # perfect slope 1
    assert _approx(linfit_slope([5.0, 5.0, 5.0]), 0.0)       # flat
    assert _approx(linfit_slope([3.0]), 0.0)                 # < 2 points
    assert _approx(linfit_slope([]), 0.0)


def test_microprice_pulled_toward_thin_side():
    # bid=100 ask=102, ask has MORE resting size (30 vs 10) -> price likely to
    # fall -> microprice below mid (101).
    mp = microprice(100.0, 102.0, 10.0, 30.0)
    assert _approx(mp, (100.0 * 30.0 + 102.0 * 10.0) / 40.0)  # = 100.5
    assert mp < 101.0
    assert microprice(None, 102.0, 10.0, 30.0) is None
    assert microprice(100.0, 102.0, 0.0, 0.0) is None


def test_depth_ofi():
    # Δbid_total +20, Δask_total -10 -> OFI = 20 - (-10) = 30 (buy pressure).
    assert _approx(depth_ofi(100.0, 100.0, 120.0, 90.0), 30.0)
    assert _approx(depth_ofi(None, None, 50.0, 50.0), 0.0)


def _win():
    return [
        {"sec": 0, "price": 100.0, "buy_val": 0, "sell_val": 0, "ts": 100,
         "bid_tot": 1000, "ask_tot": 1000, "bid1": 99, "ask1": 101, "bidq1": 50, "askq1": 50},
        {"sec": 1, "price": 101.0, "buy_val": 200, "sell_val": 100, "ts": 110,
         "bid_tot": 1100, "ask_tot": 1000, "bid1": 100, "ask1": 102, "bidq1": 60, "askq1": 40},
        {"sec": 2, "price": 102.0, "buy_val": 300, "sell_val": 50, "ts": 130,
         "bid_tot": 1200, "ask_tot": 900, "bid1": 101, "ask1": 103, "bidq1": 70, "askq1": 30},
    ]


def test_causal_feature_vector_known_values():
    f = causal_feature_vector(_win())
    assert _approx(f["t_sec"], 2.0)
    assert _approx(f["ret_open"], 2.0)                       # 100 -> 102
    assert _approx(f["ts_level"], 130.0)
    assert _approx(f["book_imb_l1"], 0.7)                    # 70/(70+30)
    assert _approx(f["book_imb_tot"], 1200.0 / 2100.0)
    assert _approx(f["sflow_val_5"], 350.0)                  # 0 + 100 + 250
    # microprice dev: mp=(101*30+103*70)/100=102.4, mid=102 -> +0.392%
    assert _approx(f["micro_dev"], (102.4 - 102.0) / 102.0 * 100.0, tol=1e-6)


def test_causal_feature_vector_uses_only_past_rows():
    w = _win()
    # The decision-at-index-1 vector must be independent of any future row 2..N.
    base = causal_feature_vector(w[:2])
    future_added = causal_feature_vector((w + [{"sec": 3, "price": 999.0}])[:2])
    assert base == future_added


def test_causal_feature_vector_empty_raises():
    with pytest.raises(ValueError):
        causal_feature_vector([])


def test_feature_names_stable_and_dense():
    f = causal_feature_vector(_win())
    assert set(f.keys()) == set(FEATURE_NAMES)
    assert len(FEATURE_NAMES) >= 20
    assert all(isinstance(v, float) and math.isfinite(v) for v in f.values())
