# KRONOS_EDGE — Full Kronos Skill Extraction

> Maximizes Kronos by using its predicted OHLCV path, ensemble variance, and dynamic re-polling — a real adaptive forecasting framework, not just an entry signal.

## What Makes This Different from POOYER

| Feature | POOYER | KRONOS_EDGE |
|---|---|---|
| SL/TP | ATR formula | Kronos percentile path (85th/15th pct) |
| SL hard cap | None | 2.5 × ATR |
| Confidence | delta/ATR | Ensemble variance-adjusted |
| Signal states | BUY/SELL/FLAT | BUY/SELL/FLAT/NO_TRADE |
| Exit | Fixed TP/SL only | Dynamic Kronos re-poll every bar |
| Forecast expiry | None | Auto-close after N bars |

## Quick Start (1 click)

**Windows:**
```
double-click start_kronos_edge.bat
```

**Linux / Mac:**
```bash
bash start_kronos_edge.sh
```

Both scripts install dependencies and start the bridge automatically.

## MT5 Setup

1. Copy `KRONOS_EDGE.mq5` to your MT5 `Experts/` folder
2. Open MetaEditor and compile (F7)
3. Add `http://127.0.0.1:7800` to **Tools → Options → Expert Advisors → Allowed URLs**
4. Attach KRONOS_EDGE to any chart (M1 or M5 recommended)

## Bridge Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/predict` | POST | Full signal: state, confidence, path_tp, path_sl, variance |
| `/recheck` | POST | Fast re-poll: current direction + confidence (exit decisions) |
| `/health` | GET | Model status |
| `/stats` | GET | Runtime config |
| `/warmup` | POST | Pre-load model before market open |
| `/cache/clear` | POST | Clear bar cache |

## Signal States

| State | Meaning | EA Action |
|---|---|---|
| `BUY` | Upward forecast, variance OK | Open long |
| `SELL` | Downward forecast, variance OK | Open short |
| `FLAT` | Delta < 0.25 × ATR | Skip |
| `NO_TRADE` | Ensemble variance > 0.6 | Skip |

## How the 3 Kronos Skills Work

**Skill A — Percentile Path SL/TP**
Kronos predicts high/low for each of the next 5 bars. TP = 85th percentile of predicted highs. SL = 15th percentile of predicted lows. Hard-capped at 2.5 × ATR to prevent outlier predictions.

**Skill B — Dynamic Exit via /recheck**
Every bar while a trade is open, the EA calls `/recheck`. Exit triggers when:
- **2 consecutive flips** — Kronos direction disagrees on 2 back-to-back bars
- **Confidence collapse** — confidence drops below `entry_confidence × 0.5`
- **Forecast expiry** — position held for `ForecastBars` bars (default 5)

**Skill C — Ensemble Variance Confidence**
5 independent Kronos predictions run per bar. Variance of the final-bar close across samples is normalized by ATR. High variance = uncertain model = `NO_TRADE`. Confidence = `direction_strength × (1 - variance_penalty)`.

## Tuning Guide (after live observation)

| Parameter | Default | Tune when |
|---|---|---|
| `MinConfidence` | 0.40 | Too many losers → raise; too few trades → lower |
| `FlipsToExit` | 2 | Exits too early → raise to 3; too late → lower to 1 |
| `ForecastBars` | 5 | Match to your timeframe's expected move duration |
| `ConfCollapseRatio` | 0.50 | Exits too early → lower; holding losers → raise |
| `VAR_PENALTY_THRESH` (bridge) | 0.6 | Too many NO_TRADE → raise; too many bad entries → lower |

## Files

| File | Description |
|---|---|
| `kronos_edge_bridge.py` | Flask bridge — runs Kronos ensemble, serves /predict and /recheck |
| `KRONOS_EDGE.mq5` | MT5 EA — path SL/TP, flip-resistant exit, forecast expiry |
| `start_kronos_edge.bat` | Windows 1-click launcher |
| `start_kronos_edge.sh` | Linux/Mac 1-click launcher |
| `requirements_edge.txt` | Python dependencies |

## Credits
- **Kronos** — Yu Shi et al., AAAI 2026 ([arXiv:2508.02739](https://arxiv.org/abs/2508.02739))
- **KRONOS_EDGE** — Contributed by [janpauldelacruz](https://github.com/janpauldelacruz)
