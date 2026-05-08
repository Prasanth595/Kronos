# MetaTrader 5 Bridge for Kronos

> **The first production-grade MetaTrader 5 ↔ Kronos bridge.**
> Serves real-time OHLCV forecasts from the Kronos foundation model directly to MT5 Expert Advisors via HTTP.

## Architecture

```
MT5 EA (POOYER.mq5)
    │
    │  POST /predict  {"symbol":"XAUUSD", "bars":[{ohlcv}×400]}
    ▼
pooyer_bridge.py  (Flask · port 7799)
    │
    ▼
Kronos Foundation Model  (Kronos-mini / small / base)
    │
    ▼
Signal Engine  →  {"direction":"BUY", "confidence":0.72, "sl_pips":0.003, ...}
    │
    ▼
MT5 EA executes trade with ATR-based SL/TP + Asymmetric Breakeven
```

## Files

| File | Description |
|---|---|
| `pooyer_bridge.py` | Flask server — loads Kronos, serves predictions via HTTP |
| `POOYER.mq5` | MT5 Expert Advisor — sends OHLCV bars, receives and executes signals |
| `requirements_bridge.txt` | Python dependencies for the bridge |

## Quick Start

### 1. Install dependencies
```bash
pip install -r examples/mt5_bridge/requirements_bridge.txt
```

### 2. Start the bridge
```bash
cd examples/mt5_bridge
python pooyer_bridge.py
```
Bridge starts on `http://127.0.0.1:7799`

### 3. Configure MetaTrader 5
1. Copy `POOYER.mq5` to your MT5 `Experts/` folder
2. Compile in MetaEditor (F7)
3. Add `http://127.0.0.1:7799` to **Tools → Options → Expert Advisors → Allowed URLs**
4. Attach POOYER to any chart

### 4. Monitor
Open `pooyer_dashboard.html` in any browser for live signal monitoring.

## API Reference

### POST /predict
```json
// Request — "freq" is optional pandas offset alias (default "1min"); match your chart timeframe
{"symbol": "XAUUSD", "freq": "1min", "bars": [{"open":2340.5,"high":2341.2,"low":2339.8,"close":2340.9,"volume":1200}, ...]}

// Response
{
  "symbol":        "XAUUSD",
  "direction":     "BUY",
  "confidence":    0.7234,
  "pred_close":    [2341.2, 2341.8, 2342.5, 2343.1, 2343.8],
  "pred_high":     [2341.9, 2342.5, 2343.2, 2343.8, 2344.5],
  "pred_low":      [2340.5, 2341.1, 2341.8, 2342.4, 2343.1],
  "current_close": 2340.9,
  "forecast_end":  2343.8,
  "atr":           0.00320,
  "sl_pips":       0.00480,
  "tp_pips":       0.00960,
  "delta_pips":    0.00290,
  "inference_ms":  847,
  "model":         "NeoQuasar/Kronos-mini"
}
```

### GET /health — Bridge and model status
### GET /stats — Runtime configuration
### POST /warmup — Pre-load model before market open
### POST /cache/clear — Clear prediction cache
### POST /multi_predict — Batch predictions for multiple symbols

## Signal Engine Logic

| Parameter | Formula |
|---|---|
| Direction | BUY if `forecast_end > current + 0.25×ATR`, SELL if opposite, else FLAT |
| Confidence | `abs(delta) / (2×ATR)` — saturates at 1.0 |
| SL distance | `ATR × 1.5` |
| TP distance | `ATR × 3.0` (2:1 RR minimum) |

## EA Risk Features

- **% risk sizing** — ATR-scaled lot calculation per trade
- **Confidence filter** — skip signals below threshold
- **Spread guard** — skip on excessive spread
- **Kill hours** — no new trades at configurable UTC hours
- **Daily loss limit** — auto-halt if drawdown exceeded
- **Asymmetric breakeven** — trigger at +N pips, lock above entry
- **Max positions cap** — limit simultaneous open trades
- **Health watchdog** — pings `/health` before every bar

## Model Selection

| Model | Params | Context | Best For |
|---|---|---|---|
| `Kronos-mini` | 4.1M | 2048 bars | CPU / VPS (default) |
| `Kronos-small` | 24.7M | 512 bars | Balance of speed/accuracy |
| `Kronos-base` | 102M | 512 bars | GPU, maximum accuracy |

Change `MODEL_NAME` in `pooyer_bridge.py`.

## Performance

- Kronos-mini on CPU: ~800–2000ms per inference
- Built-in bar-hash cache: same candle = <1ms response
- Call `/warmup` at startup to pre-load model

## Tested Symbols
XAUUSD, EURUSD, GBPUSD, BTCUSD, US30

## Disclaimer
This is a research and educational integration example. Always backtest thoroughly and apply proper risk management before live trading.

## Credits
- **Kronos** — Yu Shi et al., AAAI 2026 ([arXiv:2508.02739](https://arxiv.org/abs/2508.02739))
- **MT5 Bridge** — Contributed by [janpauldelacruz](https://github.com/janpauldelacruz)
