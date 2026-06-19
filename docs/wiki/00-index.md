# Kronos Wiki Index

This wiki is the current operator-facing documentation for Kronos. It is served
inside **Kronos 대시보드** from the Docs tab and loaded from `docs/wiki/` through
read-only `/api/docs/*` endpoints.

## Categories

### Basics
- [00-index](00-index.md) - this index
- [01-overview](01-overview) - project overview and route map
- [02-architecture](02-architecture) - system architecture

### STOM data
- [03-stom-1tick](03-stom-1tick) - 1-tick data usage
- [04-stom-1min](04-stom-1min) - 1-minute data usage
- [05-stom-1day](05-stom-1day) - daily data usage

### Operations
- [06-know-how](06-know-how) - operating notes
- [07-trial-and-error](07-trial-and-error) - trial/error log
- [08-setup](08-setup) - setup and run guide

### Interface
- [09-api-reference](09-api-reference) - read-only API catalog
- [10-dashboard-guide](10-dashboard-guide) - official dashboard usage guide

## Quick start

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos
$env:KRONOS_WEBUI_PORT = "5070"
$env:KRONOS_WEBUI_HOST = "127.0.0.1"
$env:KRONOS_WEBUI_OPEN_BROWSER = "0"
C:\Python\64\Python3119\python.exe webui\run.py
```

Open `http://127.0.0.1:5070/` for the official dashboard and
`http://127.0.0.1:5070/rl` for the RL evidence dashboard.

Legacy `/v2*` and `/rl-lab` URLs are compatibility redirects only.

## Editing guide

- Use `NN-slug.md` filenames.
- Keep the first line as `# Title`.
- Prefer Korean operator-facing copy, with English terms where they are already
  dashboard labels.
- Do not claim live-trading readiness or profitability from dashboard evidence.
