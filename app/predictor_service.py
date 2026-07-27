"""Local Kronos candle prediction service."""

from __future__ import annotations

import os
import sys
from typing import Any

import pandas as pd
import torch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from model import Kronos, KronosPredictor, KronosTokenizer

MODEL_CONFIGS = {
    "kronos-mini": {
        "model_id": "NeoQuasar/Kronos-mini",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-2k",
        "max_context": 2048,
    },
    "kronos-small": {
        "model_id": "NeoQuasar/Kronos-small",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 512,
    },
    "kronos-base": {
        "model_id": "NeoQuasar/Kronos-base",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "max_context": 512,
    },
}


class CandlePredictor:
    """Loads Kronos once and predicts future OHLCV candles from a history series."""

    def __init__(self, model_key: str = "kronos-small", device: str | None = None):
        if model_key not in MODEL_CONFIGS:
            raise ValueError(f"Unknown model '{model_key}'. Choose from: {list(MODEL_CONFIGS)}")

        self.model_key = model_key
        self.config = MODEL_CONFIGS[model_key]
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")

        print(f"Loading {model_key} on {self.device}...")
        self.tokenizer = KronosTokenizer.from_pretrained(self.config["tokenizer_id"])
        self.model = Kronos.from_pretrained(self.config["model_id"])
        self.predictor = KronosPredictor(
            self.model,
            self.tokenizer,
            device=self.device,
            max_context=self.config["max_context"],
        )
        print(f"Model ready on {self.device}.")

    def _to_dataframe(self, candles: list[dict[str, Any]]) -> pd.DataFrame:
        df = pd.DataFrame(candles)
        required = {"open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing required candle fields: {sorted(missing)}")

        if "timestamps" in df.columns:
            df["timestamps"] = pd.to_datetime(df["timestamps"])
        elif "timestamp" in df.columns:
            df["timestamps"] = pd.to_datetime(df["timestamp"])
        elif "date" in df.columns:
            df["timestamps"] = pd.to_datetime(df["date"])
        else:
            df["timestamps"] = pd.date_range(start="2024-01-01", periods=len(df), freq="5min")

        for col in ["open", "high", "low", "close", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "volume" not in df.columns:
            df["volume"] = 0.0
        if "amount" not in df.columns:
            df["amount"] = 0.0

        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        if len(df) < 2:
            raise ValueError("Need at least 2 valid candles to predict.")

        return df

    def _future_timestamps(self, last_ts: pd.Timestamp, n: int, freq: Any = None) -> pd.Series:
        use_freq = freq if freq is not None else "5min"
        return pd.date_range(start=last_ts, periods=n + 1, freq=use_freq)[1:].to_series(index=range(n))

    def predict(
        self,
        candles: list[dict[str, Any]],
        pred_len: int = 1,
        temperature: float = 1.0,
        top_p: float = 0.9,
        sample_count: int = 1,
        freq: str | None = None,
    ) -> pd.DataFrame:
        if pred_len < 1:
            raise ValueError("pred_len must be >= 1")

        df = self._to_dataframe(candles)
        max_ctx = self.config["max_context"]
        if len(df) > max_ctx:
            df = df.iloc[-max_ctx:].reset_index(drop=True)

        x_df = df[["open", "high", "low", "close", "volume", "amount"]]
        x_timestamp = df["timestamps"]

        # Infer frequency from input when not provided.
        inferred_freq: Any = freq
        if inferred_freq is None and len(df) >= 2:
            delta = df["timestamps"].iloc[-1] - df["timestamps"].iloc[-2]
            if pd.notna(delta) and delta > pd.Timedelta(0):
                try:
                    inferred_freq = pd.tseries.frequencies.to_offset(delta)
                except (ValueError, TypeError):
                    inferred_freq = "5min"

        y_timestamp = self._future_timestamps(df["timestamps"].iloc[-1], pred_len, inferred_freq)

        pred_df = self.predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=temperature,
            top_p=top_p,
            sample_count=sample_count,
            verbose=False,
        )
        pred_df = pred_df.reset_index()
        if "index" in pred_df.columns:
            pred_df = pred_df.rename(columns={"index": "timestamps"})
        elif pred_df.columns[0] != "timestamps":
            pred_df = pred_df.rename(columns={pred_df.columns[0]: "timestamps"})
        return pred_df
