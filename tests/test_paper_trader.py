from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
sys.path.insert(0, str(EXAMPLES))

import paper_trade_kronos_trend_4h as paper


def market_bars(count: int = 402) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=count, freq="4h", tz="UTC")
    close = np.linspace(70_000, 80_000, count)
    return pd.DataFrame(
        {
            "timestamps": timestamps,
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(count, 100.0),
            "amount": close * 100,
        }
    )


class PaperTraderTests(unittest.TestCase):
    def test_market_data_validation_rejects_gap_and_impossible_ohlc(self):
        bars = market_bars()
        paper.validate_market_bars(bars)
        gap = bars.copy()
        gap.loc[200, "timestamps"] += pd.Timedelta(hours=4)
        with self.assertRaisesRegex(ValueError, "desordenados o duplicados|huecos"):
            paper.validate_market_bars(gap)
        impossible = bars.copy()
        impossible.loc[10, "high"] = impossible.loc[10, "close"] - 1
        with self.assertRaisesRegex(ValueError, "OHLC imposible"):
            paper.validate_market_bars(impossible)

    def test_catches_up_pending_bars_exactly_once(self):
        bars = market_bars()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "paper"
            output.mkdir(parents=True)
            with (
                patch.object(paper, "OUTPUT", output),
                patch.object(paper, "STATE_FILE", output / "state.json"),
                patch.object(paper, "JOURNAL_FILE", output / "journal.csv"),
                patch.object(paper, "download_closed_bars", return_value=bars),
                patch.object(paper, "predict_ensemble", return_value=([-0.02, 0.0, 0.02], 0.0, 0.02)),
            ):
                state = {
                    "schema_version": 1,
                    "initial_equity": 10_000.0,
                    "equity": 10_000.0,
                    "peak_equity": 10_000.0,
                    "previous_close": float(bars.iloc[399]["close"]),
                    "last_processed_bar": bars.iloc[399]["timestamps"].isoformat(),
                    "components": {f"ema_{fast}_{slow}": False for fast, slow in paper.COMPONENTS},
                    "prediction_std_history": [0.01] * 1080,
                    "day": None,
                    "day_start_equity": 10_000.0,
                    "halted": False,
                    "halt_reason": None,
                }
                paper.save_state(state)
                result = paper.run_once("http://unused")
                self.assertEqual(result.count("Vela "), 2)
                saved = paper.load_state()
                self.assertEqual(saved["last_processed_bar"], bars.iloc[401]["timestamps"].isoformat())
                journal = pd.read_csv(paper.JOURNAL_FILE)
                self.assertEqual(len(journal), 2)
                self.assertTrue(journal["bar_time"].is_unique)
                self.assertTrue((journal["new_exposure"] == 0).all())
                self.assertTrue((journal["control_new_exposure"] == 0.5).all())
                self.assertTrue((~journal["kronos_risk_ok"]).all())

                duplicate = paper.run_once("http://unused")
                self.assertTrue(duplicate.startswith("Sin vela nueva"))
                self.assertEqual(len(pd.read_csv(paper.JOURNAL_FILE)), 2)

    def test_daily_loss_limit_closes_candidate_and_control(self):
        bars = market_bars(401)
        output = None
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "paper"
            output.mkdir(parents=True)
            with (
                patch.object(paper, "OUTPUT", output),
                patch.object(paper, "STATE_FILE", output / "state.json"),
                patch.object(paper, "JOURNAL_FILE", output / "journal.csv"),
                patch.object(paper, "predict_ensemble", return_value=([0.001, 0.002, 0.003], 0.002, 0.001)),
            ):
                active = {f"ema_{fast}_{slow}": True for fast, slow in paper.COMPONENTS}
                close_day = (bars.iloc[-1]["timestamps"] + pd.Timedelta(hours=4)).strftime("%Y-%m-%d")
                state = {
                    "schema_version": 2,
                    "initial_equity": 10_000.0,
                    "equity": 10_000.0,
                    "peak_equity": 10_000.0,
                    "previous_close": 100_000.0,
                    "last_processed_bar": bars.iloc[-2]["timestamps"].isoformat(),
                    "components": active.copy(),
                    "control_equity": 10_000.0,
                    "control_peak_equity": 10_000.0,
                    "control_components": active.copy(),
                    "prediction_std_history": [0.01] * 1080,
                    "day": close_day,
                    "day_start_equity": 10_000.0,
                    "control_day": close_day,
                    "control_day_start_equity": 10_000.0,
                    "halted": False,
                    "halt_reason": None,
                    "control_halted": False,
                    "control_halt_reason": None,
                }
                paper.save_state(state)
                paper.process_latest_bar(bars, "http://unused")
                saved = paper.load_state()
                self.assertFalse(any(saved["components"].values()))
                self.assertFalse(any(saved["control_components"].values()))
                self.assertFalse(saved["halted"])
                row = pd.read_csv(paper.JOURNAL_FILE).iloc[-1]
                self.assertLess(row["daily_return"], -paper.DAILY_LOSS_LIMIT)
                self.assertEqual(row["new_exposure"], 0)
                self.assertEqual(row["control_new_exposure"], 0)


if __name__ == "__main__":
    unittest.main()
