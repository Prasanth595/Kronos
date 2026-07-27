"""
# Kronos Local Candle Predictor

Run the Kronos foundation model on this machine to forecast the next candle(s)
from a historical OHLCV series.

## Requirements

- Python 3.12 (installed)
- NVIDIA GPU recommended (this machine: RTX 4060)
- Virtualenv at `.venv` with CUDA PyTorch

## Quick start

```powershell
# Activate environment
.\.venv\Scripts\Activate.ps1

# 1) CLI — predict next 1 candle from a CSV
python app\predict_cli.py data\sample_candles.csv --pred-len 1

# Predict next 24 candles
python app\predict_cli.py data\sample_candles.csv --pred-len 24 --json

# 2) API — local REST service (downloads model on first run)
cd app
uvicorn main:app --host 127.0.0.1 --port 8000

# 3) Official Web UI (charts + CSV from data/)
cd webui
python run.py
# open http://localhost:7070
```

## API example

```http
POST http://127.0.0.1:8000/predict
Content-Type: application/json

{
  "candles": [
    {"timestamps": "2024-06-18 11:15:00", "open": 11.27, "high": 11.28, "low": 11.26, "close": 11.27, "volume": 379},
    {"timestamps": "2024-06-18 11:20:00", "open": 11.27, "high": 11.28, "low": 11.27, "close": 11.27, "volume": 277}
  ],
  "pred_len": 1,
  "temperature": 1.0,
  "top_p": 0.9
}
```

Response includes `next_candle` (OHLCV) and full `predictions` list.

## Models

| Key | Params | Context | Notes |
|-----|--------|---------|-------|
| `kronos-mini` | 4.1M | 2048 | Fastest |
| `kronos-small` | 24.7M | 512 | Default — good for RTX 4060 |
| `kronos-base` | 102.3M | 512 | Higher quality |

First run downloads weights from Hugging Face (`NeoQuasar/...`).

## Input columns

Required: `open`, `high`, `low`, `close`  
Optional: `volume`, `amount`, `timestamps` / `timestamp` / `date`
