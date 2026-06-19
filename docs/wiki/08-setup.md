# Setup and Run Guide

## Python environment

```powershell
C:\Python\64\Python3119\python.exe --version  # Python 3.11.x
cd D:\Chanil_Park\Project\Programming\Kronos
C:\Python\64\Python3119\python.exe -m pip install -r requirements.txt
```

## Frontend build

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos\webui\v2_src
npm ci --prefer-offline --no-audit --no-fund
npm run build
```

The build writes `webui/static/v2/dist/index.html` and generated assets. The
internal output path is retained for compatibility.

## Daily dashboard run

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos
$env:KRONOS_WEBUI_PORT = "5070"
$env:KRONOS_WEBUI_HOST = "127.0.0.1"
$env:KRONOS_WEBUI_OPEN_BROWSER = "0"
C:\Python\64\Python3119\python.exe webui\run.py
```

Open:

- `http://127.0.0.1:5070/` - official dashboard
- `http://127.0.0.1:5070/rl` - RL trading/evidence dashboard
- `http://127.0.0.1:5070/v1/` - legacy archive

## Environment reference

| Variable | Default | Recommended local value |
|---|---:|---:|
| `KRONOS_WEBUI_PORT` | `7070` | `5070` |
| `KRONOS_WEBUI_HOST` | `0.0.0.0` | `127.0.0.1` |
| `KRONOS_WEBUI_OPEN_BROWSER` | `1` | `0` for agent/test runs |

Fallback-only knobs:

```powershell
$env:KRONOS_DASHBOARD_MODE = "ssr"
# or
$env:KRONOS_DASHBOARD_SSR_FALLBACK = "1"
```

Do not set these for normal dashboard use. The built dist is the default when it
exists.

## Verification

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos
py -3.11 -m pytest tests/test_v2_route.py tests/test_v2_dist_marker.py tests/test_v2_blueprint_isolation.py -q
curl -s http://127.0.0.1:5070/ | findstr kronos-dashboard-shell
```

## Workflow for dashboard source changes

1. Edit `webui/v2_src/src/**`.
2. Run `cd webui/v2_src && npm run check && npm run build`.
3. Run targeted pytest for route/static marker coverage.
4. Commit source and generated dist together if committing.

## Troubleshooting

| Symptom | Check |
|---|---|
| `/` is 404 | Flask is running and dashboard blueprint registered. |
| Shell is stale | Rebuild dist and hard refresh browser (`Ctrl+Shift+R`). |
| Chart data missing | Check `/api/training/*` or `/api/rl/*` returns 200 JSON. |
| Need fallback shell | Use `KRONOS_DASHBOARD_MODE=ssr` for that test only. |
