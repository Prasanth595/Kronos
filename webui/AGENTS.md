# webui Knowledge

## Overview

`webui/` is the Flask backend plus dashboard adapter layer. It serves the
**official Kronos dashboard** at `/`, exposes the regular RL evidence route at
`/rl`, and keeps old versioned/lab URLs only as compatibility redirects.

Internal implementation paths still use `v2` names (`webui/v2`,
`webui/v2_src`, `/static/v2/dist/`). Do not rename those paths in ordinary
feature work; remove only public/user-facing version labels.

## Key Files

| File | Role |
|---|---|
| `app.py` | Flask app, API routes, official dashboard blueprint registration. |
| `run.py` | Local dashboard launcher. |
| `training_monitor.py` | Training/log/GPU status adapter. |
| `stom_dashboard.py` | STOM prediction/backtest dashboard adapter. |
| `rl_dashboard.py` | RL run discovery, summaries, events, table readers. |
| `v2/__init__.py` | Official shell routing plus legacy compatibility redirects. |
| `v2_src/` | Svelte/Vite dashboard source. |

## Route Rules

- `/` is the official dashboard route.
- `/rl` is the official RL trading/evidence route.
- `/training` and `/dashboard` are supported dashboard bookmarks.
- `/v2`, `/v2/`, `/v2/rl-trading`, `/v2/rl-lab`, and `/rl-lab` are legacy
  compatibility redirects only.
- Built `webui/static/v2/dist/index.html` is served by default when present.
- Use `KRONOS_DASHBOARD_MODE=ssr` or `KRONOS_DASHBOARD_SSR_FALLBACK=1` only
  when explicitly testing the Jinja fallback shell.

## API Rules

- Keep dashboard APIs read-only. Do not add broker/live-order side effects here.
- Prevent path traversal when exposing artifacts or table aliases.
- Prefer server-computed comparison fields for baselines/cost gates so the UI
  does not invent trading interpretations.
- Any readiness card must distinguish "data/env ready" from "model usable".

## Dashboard Direction

- The RL dashboard should falsify models clearly: show `NO-GO`, baseline delta,
  split/seed/cost metadata, drawdown, and trade count.
- Live/replay visuals are observation tools, not evidence of profitability.
- If an equity curve comes from a rule baseline, label it as rule/baseline.

## Verification

```powershell
py -3.11 -m pytest tests/test_stom_rl_dashboard_api.py tests/test_v2_route.py tests/test_v2_dist_marker.py -q
cd webui/v2_src
npm run build
```

## Gotchas

- `webui/rl_runs/`, `prediction_results/`, `qlib_backtests/`, and similar
  folders are generated outputs.
- Dist assets under `webui/static/v2/dist/` must match the latest frontend build.
