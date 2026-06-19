# Official Dashboard Guide

The official Kronos dashboard is served at `/`. The RL trading/evidence view is
served at `/rl`. Old versioned/lab URLs are kept only as redirects so existing
bookmarks do not break.

## Main areas

### Live Training

- Stage-aware training progress and ETA.
- Loss curve and training-health cards.
- GPU utilization, temperature, and VRAM telemetry.
- APIs: `/api/training/{status,history,gpu,artifacts}`.

### Forecast Workbench

- Model/data selection for local inference experiments.
- Lookback, prediction length, temperature, and top-p controls.
- ECharts comparison of input, forecast, and observed series.
- APIs: `/api/{available-models,data-files,load-model,load-data,predict}`.

### STOM Diagnostics

- STOM data summary and prediction/backtest artifact browsers.
- Diagnostics panels for selected prediction files.
- APIs: `/api/stom/*`.

### RL Trading / Evidence

- Read-only RL/run artifact explorer.
- Must preserve `RULE MAINLINE`, `RL EXPERIMENT`, `NO-GO`, cost, split, seed,
  baseline, and not-live-ready labels.
- Equity/reward curves are evidence views. They are not live-profit claims.
- APIs: `/api/rl/*`.

### Artifacts & Models

- Recent checkpoints, pretrained model weights, and predictor artifacts.
- API: `/api/training/artifacts`.

### History & Runs

- Training run list, status filters, and run cards.
- API: `/api/training/runs`.

### System Health

- GPU/CPU/RAM telemetry and polling status.
- APIs: `/api/training/gpu`, `/api/training/system`.

### Settings

- Theme, sidebar, refresh interval, and browser notification settings.
- Settings are client-local and do not modify model/trading state.

### Docs

- Reads Markdown from `docs/wiki/` through `/api/docs/{list,read}`.
- Editing a wiki file and refreshing the dashboard is enough for local docs.

## Navigation and routes

| Route | Behavior |
|---|---|
| `/` | Official dashboard |
| `/rl` | RL Trading / Evidence tab |
| `/training`, `/dashboard` | Training dashboard bookmarks |
| `/v2`, `/v2/` | Redirect to `/` |
| `/v2/rl-trading`, `/v2/rl-lab`, `/rl-lab` | Redirect to `/rl` |

## Browser shortcuts

| Key | Action |
|---|---|
| `Ctrl+R` | Refresh |
| `Ctrl+Shift+R` | Hard refresh, bypassing cache |
| `F12` | DevTools |

## Guardrails

- Do not hide failed episodes, skipped trades, costs, or baseline overlays.
- Do not label rule baselines as reinforcement learning.
- Do not claim live trading readiness or profitability from dashboard visuals.
