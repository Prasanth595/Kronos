import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


class NoStackDataFrame(pd.DataFrame):
    @property
    def _constructor(self):
        return NoStackDataFrame

    def stack(self, *args, **kwargs):
        raise AssertionError("preprocessing must not stack the full Qlib dataset")


def load_preprocess_module(monkeypatch, data):
    finetune_dir = Path(__file__).parents[1] / "finetune"
    monkeypatch.syspath_prepend(str(finetune_dir))

    qlib = types.ModuleType("qlib")
    qlib.init = lambda **kwargs: None

    qlib_config = types.ModuleType("qlib.config")
    qlib_config.REG_CN = "cn"

    qlib_data = types.ModuleType("qlib.data")
    qlib_data.D = SimpleNamespace(
        calendar=lambda: np.array(
            list(pd.date_range("2024-01-01", periods=7)),
            dtype=object,
        )
    )

    class FakeQlibDataLoader:
        def __init__(self, config):
            self.config = config

        def load(self, instruments, start_time, end_time):
            return data

    qlib_loader = types.ModuleType("qlib.data.dataset.loader")
    qlib_loader.QlibDataLoader = FakeQlibDataLoader
    qlib_dataset = types.ModuleType("qlib.data.dataset")

    monkeypatch.setitem(sys.modules, "qlib", qlib)
    monkeypatch.setitem(sys.modules, "qlib.config", qlib_config)
    monkeypatch.setitem(sys.modules, "qlib.data", qlib_data)
    monkeypatch.setitem(sys.modules, "qlib.data.dataset", qlib_dataset)
    monkeypatch.setitem(sys.modules, "qlib.data.dataset.loader", qlib_loader)
    sys.modules.pop("qlib_data_preprocess", None)

    return importlib.import_module("qlib_data_preprocess")


def make_qlib_frame(index_order):
    dates = pd.date_range("2024-01-01", periods=5, name="datetime")
    instruments = pd.Index(["SH600000", "SH600001"], name="instrument")
    index = pd.MultiIndex.from_product([dates, instruments])

    row = np.arange(len(index), dtype=np.float64)
    data = NoStackDataFrame(
        {
            "$open": 10.0 + row,
            "$close": 10.5 + row,
            "$high": 11.0 + row,
            "$low": 9.5 + row,
            "$volume": 100.0 + row,
            "$vwap": 10.25 + row,
        },
        index=index,
    )
    data = data.drop(
        index=[
            (dates[1], "SH600001"),
            (dates[3], "SH600000"),
        ]
    )
    data.loc[(dates[1], "SH600000"), "$close"] = np.nan
    data.loc[(dates[3], "SH600001"), :] = np.nan
    return data.reorder_levels(index_order).sort_index()


@pytest.mark.parametrize(
    "index_order",
    [
        ["datetime", "instrument"],
        ["instrument", "datetime"],
    ],
)
def test_load_qlib_data_processes_each_instrument_without_global_stack(
    monkeypatch,
    index_order,
):
    raw_data = make_qlib_frame(index_order)
    module = load_preprocess_module(monkeypatch, raw_data)
    preprocessor = object.__new__(module.QlibDataPreprocessor)
    preprocessor.config = SimpleNamespace(
        dataset_begin_time="2024-01-02",
        dataset_end_time="2024-01-05",
        lookback_window=1,
        predict_window=1,
        instrument=["SH600000", "SH600001"],
        feature_list=["open", "high", "low", "close", "vol", "amt"],
    )
    preprocessor.data_fields = ["open", "close", "high", "low", "volume", "vwap"]
    preprocessor.data = {}

    preprocessor.load_qlib_data()

    assert list(preprocessor.data) == ["SH600000", "SH600001"]
    for symbol, expected_group in raw_data.groupby(level="instrument", sort=False):
        expected = expected_group.droplevel("instrument").rename(
            columns={f"${field}": field for field in preprocessor.data_fields}
        )
        expected["vol"] = expected["volume"]
        expected["amt"] = (
            expected[["open", "high", "low", "close"]].sum(axis=1)
            / 4
            * expected["vol"]
        )
        expected = expected[preprocessor.config.feature_list]
        expected = expected.dropna()
        expected.columns.name = "field"

        pd.testing.assert_frame_equal(preprocessor.data[symbol], expected)
