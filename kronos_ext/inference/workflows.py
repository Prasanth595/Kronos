"""High-level local inference workflow placeholders."""

from __future__ import annotations

import pandas as pd

from kronos_ext.core.schemas import ForecastRequest
from kronos_ext.inference.predictor import KronosPredictorAdapter


def run_forecast(
    request: ForecastRequest,
    candles: pd.DataFrame,
    x_timestamp: pd.Series,
    y_timestamp: pd.Series,
    predictor: KronosPredictorAdapter,
) -> pd.DataFrame:
    """Run a local forecast through an injected predictor adapter."""

    return predictor.predict(
        candles=candles,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=request.pred_len,
        **request.parameters,
    )
