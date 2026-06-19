# Kronos Project Overview

Kronos is an experimental research and operations workspace for market-data
modeling, STOM rule/RL experiments, and dashboard-based evidence review. Treat it
as a backtest/research platform, not as a live-trading product.

## Core stack

| Area | Stack |
|---|---|
| Backend | Python 3.11 + Flask + read-only dashboard APIs |
| Model | PyTorch + Kronos model/tokenizer code |
| Data | STOM SQLite data and generated research artifacts |
| Frontend | Svelte 5 + Vite + TypeScript official dashboard |
| Charts | ECharts; Plotly only where existing dynamic imports require it |
| Monitoring | `nvidia-smi` and local status files, read-only |

## Route map

| URL | Purpose |
|---|---|
| `/` | Official Kronos dashboard |
| `/rl` | Official RL trading/evidence dashboard |
| `/training`, `/dashboard` | Dashboard bookmarks for training view |
| `/v1/`, `/v1/training`, `/v1/stom` | Legacy archive pages |
| `/v2`, `/v2/` | Legacy compatibility redirect to `/` |
| `/v2/rl-trading`, `/v2/rl-lab`, `/rl-lab` | Legacy compatibility redirect to `/rl` |
| `/api/*` | Read-only APIs |

## Current constraints

- The built dashboard dist is served by default when present.
- SSR/Jinja fallback is for explicit fallback testing only.
- Internal paths can still contain `v2`; public UI and docs should not present
  the dashboard as a versioned product.
- RL/orderbook screens must show cost, split, baseline, `NO-GO`, and
  not-live-ready guardrails.

## Repository map

```text
Kronos/
+-- webui/              # Flask backend and official dashboard adapters
|   +-- app.py          # API and blueprint registration
|   +-- v2/             # official shell routing, legacy redirects
|   +-- v2_src/         # Svelte/Vite source (internal path name)
|   +-- static/v2/dist/ # generated dashboard dist
|   +-- templates/      # fallback/legacy templates
+-- stom_rl/            # rule/RL experiments and backtests
+-- finetune/           # training code and outputs
+-- model/              # Kronos model core
+-- _database/          # local STOM data
+-- docs/wiki/          # current operator docs
```

## Related docs

- [02-architecture](02-architecture) - detailed system architecture
- [08-setup](08-setup) - setup and run commands
- [10-dashboard-guide](10-dashboard-guide) - dashboard usage
