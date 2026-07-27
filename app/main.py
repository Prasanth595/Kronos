"""FastAPI app: POST candle series, get next-candle forecast from local Kronos."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from predictor_service import MODEL_CONFIGS, CandlePredictor

predictor: CandlePredictor | None = None


class Candle(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    amount: float | None = None
    timestamps: str | None = None
    timestamp: str | None = None
    date: str | None = None


class PredictRequest(BaseModel):
    candles: list[Candle] = Field(..., min_length=2, description="Historical OHLCV candles")
    pred_len: int = Field(1, ge=1, le=512, description="Number of future candles to predict")
    temperature: float = Field(1.0, ge=0.1, le=2.0)
    top_p: float = Field(0.9, ge=0.1, le=1.0)
    sample_count: int = Field(1, ge=1, le=5)
    freq: str | None = Field(None, description="Optional pandas offset alias, e.g. '5min', '1h', '1D'")


class LoadModelRequest(BaseModel):
    model: Literal["kronos-mini", "kronos-small", "kronos-base"] = "kronos-small"
    device: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global predictor
    # Default: small model on CUDA if available (fits RTX 4060 well).
    predictor = CandlePredictor(model_key="kronos-small")
    yield


app = FastAPI(
    title="Kronos Candle Predictor",
    description="Local financial candle forecasting with the Kronos foundation model.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    import torch

    return {
        "status": "ok",
        "model_loaded": predictor is not None,
        "model": predictor.model_key if predictor else None,
        "device": predictor.device if predictor else None,
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


@app.get("/models")
def list_models() -> dict[str, Any]:
    return {"models": MODEL_CONFIGS, "active": predictor.model_key if predictor else None}


@app.post("/load_model")
def load_model(req: LoadModelRequest) -> dict[str, Any]:
    global predictor
    try:
        predictor = CandlePredictor(model_key=req.model, device=req.device)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": "loaded", "model": predictor.model_key, "device": predictor.device}


@app.post("/predict")
def predict(req: PredictRequest) -> dict[str, Any]:
    if predictor is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    candles = [c.model_dump(exclude_none=True) for c in req.candles]
    try:
        pred_df = predictor.predict(
            candles=candles,
            pred_len=req.pred_len,
            temperature=req.temperature,
            top_p=req.top_p,
            sample_count=req.sample_count,
            freq=req.freq,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    records = pred_df.to_dict(orient="records")
    for row in records:
        if "timestamps" in row:
            row["timestamps"] = str(row["timestamps"])

    return {
        "model": predictor.model_key,
        "device": predictor.device,
        "input_candles": len(candles),
        "pred_len": req.pred_len,
        "predictions": records,
        "next_candle": records[0] if records else None,
    }
