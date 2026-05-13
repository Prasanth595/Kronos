# KRONOS PURE — MetaTrader 5 Expert Advisor

**30-path Monte Carlo ensemble | M15/H1 native | Directional confluence gate**

> KRONOS PURE is a production EA built exclusively around the Kronos model's Binary Spherical Quantization (BSQ) structural tokenization. It uses 30 independent Monte Carlo paths to measure directional agreement, then gates trades on confluence — not raw model output.

---

## Why M15/H1 Only

Kronos BSQ tokenizes price action into structural tokens that filter micro-noise. On M1/M5, ATR-normalized variance exceeds the model's prediction spread, collapsing confidence to zero. M15+ is where Kronos operates cleanly.

---

## Architecture

```
MT5 EA (KRONOS_PURE.mq5)
    │  POST /predict  (300 bars of M15 OHLCV)
    ▼
Python Bridge (port 7900)
    ├── 30× Kronos.predict() calls (sample_count=1 each — preserves variance signal)
    ├── Direction vote: buy_votes / sell_votes / flat_votes
    ├── dir_agreement = votes / 30
    ├── variance_penalty = std(final_closes) / ATR
    ├── confidence = dir_agreement × (1 − variance_penalty)
    ├── SL = 30th percentile of predicted lows  (floor: 2.0×ATR)
    └── TP = 70th percentile of predicted highs (cap:  2.5×ATR)
    │
    │  JSON response
    ▼
EA applies filters:
    ├── dir_agreement ≥ 70%  (24/30 paths)  → primary gate
    ├── confidence ≥ 0.35                   → variance sanity
    ├── RR ≥ 0.90                           → EV floor
    └── SL within 30–2000 pts              → broker sanity
```

**Why sample_count=1 per path?** `sample_count>1` averages internally and destroys the variance signal. 30 independent calls with `sample_count=1` is the Alpha Trader ensemble method — each path is a distinct stochastic draw.

---

## Directional Agreement vs Actual Win Rate

| Agreement | Win Rate | EV @ 1:1 RR |
|-----------|----------|-------------|
| 70%+      | ~54%     | +0.08R      |
| 80%+      | ~58%     | +0.16R      |
| 90–100%   | ~60%     | +0.20R      |

Default threshold: **70%** — trades more frequently while remaining +EV. Raise to 80% after 500+ live trades confirm win rate.

---

## Model Failover

- **Primary:** `NeoQuasar/Kronos-mini` (4.1M params, ctx=2048)
- **Backup:** `NeoQuasar/Kronos-base` (102.3M params, ctx=512)

Bridge tries mini first. If download or load fails, automatically falls back to base. `/health` endpoint reports which model is active.

---

## Quick Start

### 1. Run the installer (Windows)

```bat
INSTALL_AND_RUN.bat
```

Choose option **[1] Install + Start Bridge**. This will:
- Check Python
- Install all dependencies
- Copy `KRONOS_PURE.mq5` to all detected MT5 terminals
- Start the bridge on `http://127.0.0.1:7900`

First launch downloads `Kronos-mini` (~30–90 seconds).

### 2. Compile the EA

1. Open MetaEditor in MT5 (F4)
2. Open `KRONOS_PURE.mq5`
3. Press **F7** to compile

### 3. Attach to chart

- Symbol: **XAUUSD** (optimized for gold; other symbols work)
- Timeframe: **M15**
- Enable live trading (Ctrl+E)
- Add `http://127.0.0.1:7900` to MT5 allowed URLs

---

## EA Inputs

| Group | Input | Default | Notes |
|-------|-------|---------|-------|
| Bridge | `BridgeURL` | `http://127.0.0.1:7900` | |
| Bridge | `BarsToSend` | 300 | M15 bars sent per request |
| Signal Filter | `MinDirAgree` | 0.70 | Primary gate — 70% of 30 paths must agree |
| Signal Filter | `MinConfidence` | 0.35 | Variance-dampened secondary check |
| Signal Filter | `MinRR` | 0.90 | Risk:Reward floor |
| SL Bounds | `MinSLPoints` | 30 | XAUUSD M15 minimum |
| SL Bounds | `MaxSLPoints` | 2000 | XAUUSD M15 maximum |
| Breakeven | `BEAtR` | 1.0 | Move SL to breakeven at 1R profit |
| Trailing | `TrailStartR` | 1.3 | Begin trailing at 1.3R |
| Trailing | `TrailDistR` | 0.8 | Trail distance in R multiples |
| Risk | `RiskPercent` | 0.5 | % equity per trade |
| Risk | `DailyLossLimit` | 2.0 | Daily halt threshold |
| Session | `SessionStart` | 7 | London open (UTC) |
| Session | `SessionEnd` | 20 | NY close (UTC) |

---

## Bridge API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predict` | POST | 30-path ensemble signal |
| `/recheck` | POST | Re-evaluate open position direction |
| `/health` | GET | Model status + active model name |
| `/stats` | GET | Current config values |
| `/cache/clear` | POST | Flush bar-hash cache |
| `/warmup` | POST | Pre-load model |

### `/predict` Request

```json
{
  "symbol": "XAUUSD",
  "freq": "15min",
  "bars": [
    {"time": 1700000000, "open": 1980.5, "high": 1982.1, "low": 1979.3, "close": 1981.7, "tick_volume": 1200},
    ...
  ]
}
```

### `/predict` Response

```json
{
  "ok": true,
  "direction": "BUY",
  "confidence": 0.52,
  "dir_agreement": 0.73,
  "buy_votes": 22,
  "sell_votes": 4,
  "flat_votes": 4,
  "entry_ref": 1981.7,
  "path_tp": 1987.4,
  "path_sl": 1978.2,
  "atr": 3.82,
  "variance_penalty": 0.29,
  "model": "NeoQuasar/Kronos-mini",
  "inference_ms": 1840.0
}
```

---

## Trade Logger

Every closed trade is written to `MQL5/Files/KRONOS_PURE_trades.csv`:

```
time, symbol, direction, dir_agreement, confidence, rr, entry, sl, tp,
spread_pts, slippage_pts, latency_ms, session, atr,
result_R, mfe_R, mae_R, hold_minutes, exit_reason
```

**500+ trades is the data threshold** for statistically significant tuning of `MinDirAgree`, `MinRR`, and session windows.

---

## Stop / Close All

```bat
INSTALL_AND_RUN.bat  →  [2] Stop Bridge
INSTALL_AND_RUN.bat  →  [3] Close All KRONOS_PURE Positions
INSTALL_AND_RUN.bat  →  [4] Stop Bridge + Close All
```

`close_all.py` closes all positions with MagicNumber `202602` via the MT5 Python API.

---

## Credits

Built by **AURELIA EMPIRE | ZEROEMOTIONS** on top of [Kronos](https://github.com/shiyu-coder/Kronos) by shiyu-coder.

MagicNumber: `202602`
