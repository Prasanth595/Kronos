# Kronos Operating Notes

These are current operating notes for training, dashboard inspection, and local
artifact review. Historical design notes live elsewhere; use this page for daily
operations.

## Dashboard operations

### Theme and refresh

- Use the sun/moon toggle or Settings tab for light/dark mode.
- Use 5 seconds as the normal refresh interval during active monitoring.
- Use 30-60 seconds when the dashboard is background-only.

### Live Training quick diagnosis

1. Read the status badge and readiness card first.
2. Check loss trend and stage-aware progress.
3. Check GPU utilization, temperature, and VRAM.
4. If progress is stale, verify `/api/training/status` and the training process
   before changing dashboard code.

### RL evidence quick diagnosis

- Check whether an item is a RULE baseline or an RL experiment.
- Check cost, split, seed, trade count, drawdown, and baseline delta.
- Treat `NO-GO` as a result to surface, not a problem to hide.
- Do not infer live profitability from a dashboard curve.

## Build and deployment notes

```powershell
cd webui\v2_src
npm run build
# updates webui/static/v2/dist/
```

The built dist is served by default when present. Flask does not need a dist
feature flag for normal operation.

If a browser appears stale, use `Ctrl+Shift+R` after rebuilding because generated
asset hashes can remain cached.

## Explicit fallback testing

Only use the fallback shell for route/fallback tests:

```powershell
$env:KRONOS_DASHBOARD_MODE = "ssr"
# or
$env:KRONOS_DASHBOARD_SSR_FALLBACK = "1"
```

Clear those variables for normal dashboard use.

## Debugging snippets

```powershell
curl -s http://127.0.0.1:5070/api/training/status | py -3.11 -c "import sys,json; print(json.load(sys.stdin))"
curl -s http://127.0.0.1:5070/ | findstr kronos-dashboard-shell
```

For chart issues, inspect DevTools Console and Network responses for the
corresponding `/api/*` endpoint before changing frontend logic.

## Browser shortcuts

- `Ctrl+R` - refresh
- `Ctrl+Shift+R` - hard refresh, bypass cache
- `F12` - DevTools
