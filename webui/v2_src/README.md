# Kronos Dashboard Source (`webui/v2_src`)

This directory contains the Svelte/Vite source for the official Kronos dashboard.
The path name still contains `v2_src` for implementation compatibility, but the
public product name is **Kronos 대시보드** / **Kronos Dashboard**.

## Quick start

```powershell
# 1. Install frontend dependencies once
cd D:\Chanil_Park\Project\Programming\Kronos\webui\v2_src
npm ci --prefer-offline --no-audit --no-fund

# 2. Build the official dashboard dist
npm run build
# output: ..\static\v2\dist\index.html and assets\*.{css,js,map}

# 3. Run Flask. No dist feature flag is required for normal startup.
cd D:\Chanil_Park\Project\Programming\Kronos
$env:KRONOS_WEBUI_PORT = "5070"
$env:KRONOS_WEBUI_HOST = "127.0.0.1"
$env:KRONOS_WEBUI_OPEN_BROWSER = "0"
C:\Python\64\Python3119\python.exe webui\run.py
```

Open:

- `http://127.0.0.1:5070/` - official dashboard
- `http://127.0.0.1:5070/rl` - official RL trading/evidence dashboard
- `http://127.0.0.1:5070/v1/` - legacy archive page

Legacy bookmarks are compatibility redirects only:

- `/v2`, `/v2/` -> `/`
- `/v2/rl-trading`, `/v2/rl-lab`, `/rl-lab` -> `/rl`

## Runtime environment

| Variable | Default behavior | Use |
|---|---|---|
| `KRONOS_WEBUI_PORT` | `7070` | Use `5070` for local dashboard work. |
| `KRONOS_WEBUI_HOST` | `0.0.0.0` | Use `127.0.0.1` for local-only access. |
| `KRONOS_WEBUI_OPEN_BROWSER` | `1` | Set `0` for agent/test runs. |
| `KRONOS_DASHBOARD_MODE=ssr` | unset | Force Jinja fallback shell for fallback testing only. |
| `KRONOS_DASHBOARD_SSR_FALLBACK=1` | unset | Same fallback intent as above. |

`KRONOS_V2_DIST` is legacy compatibility state. Normal startup serves the built
dist by default when `webui/static/v2/dist/index.html` exists.

## Directory map

```text
webui/v2_src/
+-- index.html              # Vite entry with official dashboard marker
+-- package.json
+-- vite.config.ts          # base: '/static/v2/dist/'
+-- src/
    +-- App.svelte          # route-to-tab mapping
    +-- layout/             # Sidebar, Header, HeroStrip
    +-- lib/                # API, stores, polling, formatting, icons
    +-- tabs/               # dashboard tabs including RLTradingTab
    +-- charts/             # chart renderer wrappers
    +-- widgets/            # live-training widgets
```

## Marker contract

Both the Vite dist shell and the SSR fallback shell use:

```html
<meta name="kronos-dashboard-shell" content="hero,live-training,stom,forecast,artifacts,history,system-health" />
```

Public shells must not expose `kronos-v2-version`, `p1-ssr`, or `p1-5-spa`.

## Verification

```powershell
cd D:\Chanil_Park\Project\Programming\Kronos
py -3.11 -m pytest tests/test_v2_route.py tests/test_v2_dist_marker.py tests/test_v2_blueprint_isolation.py tests/test_stom_rl_dashboard_tab.py -q

cd webui\v2_src
npm run check
npm run build
```

## Notes

- Keep internal path names as-is unless a separate migration plan is approved.
- Do not add broker/live-order side effects to dashboard code.
- RL dashboard visuals are evidence/falsification tools, not proof of live
  profitability.
