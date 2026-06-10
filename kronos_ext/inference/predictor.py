"""Thin inference wrapper boundary around upstream KronosPredictor.

This module does not load real models. It exists to keep extension workflows
decoupled from the upstream ``model`` package until model objects are provided.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from kronos_ext.core.validation import validate_ohlcv_columns


@dataclass
class KronosPredictorAdapter:
    """Adapter for an already constructed upstream KronosPredictor instance."""

    predictor: Any | None = None

    def predict(
        self,
        candles: pd.DataFrame,
        x_timestamp: pd.Series,
        y_timestamp: pd.Series,
        pred_len: int,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Validate inputs and delegate to a provided KronosPredictor.

        Raises:
            RuntimeError: If no upstream predictor has been injected.
        """

        validate_ohlcv_columns(candles)

        if self.predictor is None:
            raise RuntimeError(
                "No KronosPredictor instance has been provided. "
                "Inject a pre-loaded upstream predictor before inference."
            )

        return self.predictor.predict(
            df=candles,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            **kwargs,
        )
