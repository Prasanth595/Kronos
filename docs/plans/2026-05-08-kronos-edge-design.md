# KRONOS_EDGE — Design Document

**Date:** 2026-05-08  
**Author:** janpauldelacruz  
**Status:** Approved — ready for implementation

---

## Goal

Maximize the value extracted from Kronos by using its full predicted OHLCV path, ensemble variance, and dynamic re-polling — going beyond simple directional entry signals into an adaptive forecasting framework.

---

## Three Core Kronos Skills

### Skill A — Percentile-Based Path SL/TP
Use Kronos's predicted `high`/`low` arrays across all forecast bars, but stabilized with percentiles instead of raw max/min:
- **BUY TP:** 85th percentile of `pred_high` values across forecast window
- **BUY SL:** 15th percentile of `pred_low` values across forecast window
- **SELL TP/SL:** mirrored
- **Hard cap:** SL distance clipped to `max(Kronos_SL, 2.5 × ATR)` — prevents outlier predictions from creating dangerously wide stops

### Skill B — Flip-Resistant Dynamic Exit
The EA polls `/recheck` on every new bar while a trade is open. Single direction flip does NOT exit. Exit requires:
1. **2 consecutive flips** — Kronos disagrees on two back-to-back bars, OR
2. **Confidence collapse** — confidence drops below `entry_confidence × 0.5`

Consecutive flip counter resets if Kronos agrees with trade direction again.

### Skill C — Ensemble Variance Confidence + NO_TRADE State
Run `sample_count=5`. Compute `std` of the 5 predicted closes at the final forecast bar.

**Confidence formula:**
```
variance_penalty = std / atr          # normalized uncertainty
direction_strength = abs(delta) / (2 × atr)
confidence = direction_strength × (1 - min(variance_penalty, 1.0))
```

**Signal states (returned by bridge):**
- `BUY` — confidence ≥ threshold, direction clear, variance acceptable
- `SELL` — confidence ≥ threshold, direction clear, variance acceptable
- `FLAT` — delta too small (< 0.25 × ATR)
- `NO_TRADE` — variance too high (variance_penalty > 0.6) or expected move too small relative to spread

### Forecast Expiry
Kronos predicts `pred_len=5` bars ahead. If a trade is still open after `pred_len` bars, it has outlived its forecast horizon → close it regardless of P&L. This prevents zombie trades that were entered on stale Kronos data.

---

## Bridge Design (`kronos_edge_bridge.py`)

**Port:** 7800 (separate from POOYER bridge on 7799)

**Endpoints:**
| Endpoint | Method | Purpose |
|---|---|---|
| `/predict` | POST | Full signal with path SL/TP, ensemble confidence, signal state |
| `/recheck` | POST | Lightweight re-poll: direction + confidence + should_exit bool |
| `/health` | GET | Bridge + model status |
| `/warmup` | POST | Pre-load model |

**`/predict` response:**
```json
{
  "symbol": "XAUUSD",
  "signal_state": "BUY",
  "confidence": 0.71,
  "path_tp": 2345.80,
  "path_sl": 2338.20,
  "sl_capped": false,
  "atr": 1.85,
  "variance_penalty": 0.18,
  "direction_strength": 0.86,
  "forecast_bars": 5,
  "current_close": 2340.10,
  "inference_ms": 920
}
```

**`/recheck` response:**
```json
{
  "symbol": "XAUUSD",
  "direction": "BUY",
  "confidence": 0.65,
  "should_exit": false,
  "exit_reason": null
}
```

---

## EA Design (`KRONOS_EDGE.mq5`)

**Entry logic:**
1. New bar → call `/predict`
2. If `signal_state == NO_TRADE` or `FLAT` → skip
3. If `confidence < MinConfidence` → skip
4. Open trade using `path_tp` / `path_sl` (hard-capped at 2.5 × ATR)

**Management logic (every new bar, per open trade):**
1. Call `/recheck`
2. Increment `flip_count` if direction disagrees, reset if agrees
3. Exit if `flip_count >= 2` OR `confidence < entry_confidence × 0.5`
4. Exit if `bars_held >= forecast_bars` (forecast expiry)

**Risk:**
- % risk sizing (same CalcLots as POOYER)
- Daily loss limit halt
- Spread guard
- Max positions cap

---

## What We're NOT Tuning Yet
- Percentile values (85/15) — adjust after live observation
- `variance_penalty` threshold (0.6) — adjust after seeing NO_TRADE frequency
- Consecutive flip count (2) — may tighten to 1 or loosen to 3 after observation
- `pred_len` / `sample_count` — 5/5 defaults, tune after latency data

---

## Files
```
examples/kronos_edge/
├── kronos_edge_bridge.py
├── KRONOS_EDGE.mq5
├── README.md
└── requirements_edge.txt
```
