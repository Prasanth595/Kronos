# webui/v2_src Knowledge

## Overview

This is the Svelte/Vite source for the official Kronos dashboard. It consumes
Flask APIs from `webui/app.py` and builds into `webui/static/v2/dist/`.

`v2_src` and `/static/v2/dist/` are internal implementation path names. Public
UI, browser titles, docs, and user-facing instructions should call the product
`Kronos 대시보드` / `Kronos Dashboard`, not a versioned dashboard.

## Key Files

| File | Role |
|---|---|
| `src/App.svelte` | Route-to-tab mapping. |
| `src/layout/Sidebar.svelte` | Navigation. |
| `src/layout/Header.svelte` | Breadcrumb/status header. |
| `src/lib/api.ts` | API contracts and fetch helpers. |
| `src/tabs/RLTradingTab.svelte` | Main RL/trading dashboard page. |
| `vite.config.ts` | Build base/output configuration. |

## Rules

- Use `src/lib/api.ts` types/helpers for new backend calls.
- Keep run/evaluation labels explicit: smoke vs full, train/test split, cost,
  seed, baseline, `GO/NO-GO`.
- Do not make a chart look better by hiding failed episodes, skipped trades, or
  baseline overlays.
- `RLTradingTab.svelte` is already large; prefer small helper functions or
  focused components when adding substantial UI.
- Build output is generated; source changes belong in `src/`.

## Commands

```powershell
npm run check
npm run build
```

Node must satisfy the engines in `package.json`: Node 20 or 22, npm 9+.

## Testing Hooks

Frontend behavior is partly checked from Python tests via source/dist markers:

```powershell
py -3.11 -m pytest tests/test_stom_rl_dashboard_tab.py tests/test_v2_dist_marker.py -q
```
