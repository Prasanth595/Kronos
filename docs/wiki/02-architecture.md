# System Architecture

## Runtime flow

```text
Browser
  -> Flask :5070
      -> /                 official dashboard dist or explicit SSR fallback
      -> /rl               same shell, RL tab selected
      -> /v1/*             legacy archive templates
      -> /api/*            read-only JSON APIs
          -> finetune outputs, STOM DB, logs, RL artifacts
```

## Backend

`webui/app.py` owns the Flask app and read-only API registration. The dashboard
shell routes are isolated in `webui/v2/__init__.py` for compatibility with the
existing internal path names.

Route behavior:

| Route | Behavior |
|---|---|
| `/` | Serve official dashboard shell |
| `/rl` | Serve official dashboard shell with RL route selected |
| `/training`, `/dashboard` | Serve official dashboard shell with training route selected |
| `/v2`, `/v2/` | 301 redirect to `/` |
| `/v2/rl-trading`, `/v2/rl-lab`, `/rl-lab` | 301 redirect to `/rl` |
| `/api/*` | Existing read-only APIs; no broker/live-order side effects |

## Frontend

`webui/v2_src/` contains the Svelte/Vite source. The name is internal; the
public product name is `Kronos 대시보드` / `Kronos Dashboard`.

```text
index.html
  -> src/main.ts
      -> App.svelte
          -> Sidebar/Header/HeroStrip
          -> tabs/*
          -> lib/polling.ts and lib/api.ts
```

## Shell marker contract

Official shell responses contain:

```html
<meta name="kronos-dashboard-shell" content="hero,live-training,stom,forecast,artifacts,history,system-health" />
```

They must not expose `kronos-v2-version`, `p1-ssr`, or `p1-5-spa` as public
markers.

## Environment knobs

| Variable | Effect |
|---|---|
| `KRONOS_WEBUI_PORT` | Flask port; use `5070` for local dashboard work. |
| `KRONOS_WEBUI_OPEN_BROWSER` | Set `0` for agent/test runs. |
| `KRONOS_DASHBOARD_MODE=ssr` | Force SSR fallback for fallback testing only. |
| `KRONOS_DASHBOARD_SSR_FALLBACK=1` | Same fallback intent as above. |

Normal startup does not need a dist mode flag. If the built dist exists, Flask
serves it by default.

## Related docs

- [08-setup](08-setup) - run guide
- [09-api-reference](09-api-reference) - API catalog
