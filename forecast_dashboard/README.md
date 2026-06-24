# Kronos Forecasting Dashboard

A small, honest toolkit for **forecasting** and **measuring forecast quality** on a
demo (paper) trading account. It wraps the [Kronos](https://github.com/shiyu-coder/Kronos)
pretrained price model and forecasts four instruments: **Silver, Gold, WTI crude, GBP/JPY**.

> **The single most important thing:** this tool is honest about uncertainty.
> - The forecast is a **distribution** of sample paths (a p10–p90 band), never a lone "prediction".
> - The model sees **past daily price candles only**. It cannot see Fed/BoE/BoJ
>   decisions, CPI prints, OPEC headlines, or risk events. News is shown as
>   *"things the model did NOT see"*, never as a confidence input.
> - There is **no fabricated confidence score** anywhere.
> - Every forecast is **logged** and later **reconciled** against actuals so you can
>   see, as a number, whether the band is calibrated (the point of the demo account).

---

## What's in here

```
Kronos/forecast_dashboard/
├── forecast_engine.py    # CORE — all model + data logic (single source of truth)
├── server.py             # PRIMARY UI — FastAPI JSON API + bespoke web frontend
├── web/                  # hand-built dashboard (HTML/CSS/JS, ECharts vendored offline)
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── vendor/echarts.min.js
├── app.py                # legacy Streamlit dashboard (thin client, fallback)
├── mcp_server.py         # MCP server exposing the engine as tools (thin client)
├── notebook_sync.ipynb   # experimentation notebook (thin client, zero dup logic)
├── instruments.py        # the four instruments + their caveats
├── storage.py            # forecast logging + accuracy tracking (SQLite)
├── ui_theme.py           # minimalist black & white themes (Streamlit legacy)
├── news_context.py       # "model did NOT see" headlines + text analysis bot
├── deploy/               # optional GCP VM + Cloud Run deploy kit (see deploy/README.md)
├── Dockerfile            # Cloud Run container image
├── requirements.txt
├── .env.example
└── README.md
```

`forecast_engine.py` holds **100%** of the model/data logic. `server.py`, `app.py`,
`mcp_server.py`, and the notebook all import it. Change forecasting behaviour in one place.

---

## Setup

This dashboard ships **inside the Kronos repo** (at `Kronos/forecast_dashboard/`),
so the model package (`from model import ...`) is already importable from the
parent directory. No separate clone is needed.

```bash
git clone https://github.com/shiyu-coder/Kronos.git
cd Kronos/forecast_dashboard
```

> The engine auto-discovers the model code: it uses `$KRONOS_DIR` if set,
> otherwise the parent Kronos repo root, otherwise a sibling `./Kronos` clone
> (so this folder also works if copied out and used standalone).

### Install dependencies

```bash
pip install -r requirements.txt
```

This installs the dashboard's stack (streamlit, yfinance, pandas, numpy, plotly,
matplotlib, mcp, python-dotenv) **and** Kronos's own deps (torch, einops,
huggingface_hub, safetensors, tqdm).

> CPU-only torch is fine for the small/base models. For CPU wheels:
> `pip install torch --index-url https://download.pytorch.org/whl/cpu`

### Configure

```bash
cp .env.example .env   # then edit
```

Key settings: `KRONOS_DIR`, `KRONOS_DEVICE` (`cpu` | `cuda:0` | `mps`), forecast
defaults, `FORECAST_DB`. The `ANTHROPIC_API_KEY` / `TAVILY_API_KEY` are **optional**
and only used for the *"context the model did not see"* news panel and an optional
LLM-phrased narrative — they never feed the forecast and never produce a score.

### 4. First run downloads model weights

The first forecast pulls the model + tokenizer from HuggingFace (~100 MB) into your
local HF cache (`~/.cache/huggingface`). Subsequent runs reuse the cache.

---

## Run each piece

### Smoke tests (do these first)

```bash
python forecast_engine.py   # loads model, forecasts all 4 instruments, prints bands
python storage.py           # logs a fake forecast, reconciles, checks band hit-rate
```

`forecast_engine.py` should print sane bands for all four instruments, and GBP/JPY
should report it used the **no-volume path** (it has no reliable volume).

### Dashboard (bespoke web UI — primary)

```bash
python server.py
# open http://localhost:8000
```

A hand-built, minimalist dashboard (FastAPI backend + vanilla HTML/CSS/JS with
Apache ECharts vendored locally, so it works fully offline on a GCP box). Pick an
instrument from the top tabs, tune horizon / lookback / sample count, click
**Run forecast**. **All four** shows a glance grid of every instrument. The theme
button (top-right) cycles Paper / Ink / Slate / E-ink live. **Refresh actuals**
reconciles past forecasts against realized closes.

The fan chart makes the **p10–p90 band the most prominent element**, draws the
median **dashed** (so it never reads as "the answer"), and overlays faint
individual sample paths. The server **prewarms** all four forecasts in the
background on startup, so the first visitor doesn't wait on CPU inference
(disable with `KRONOS_PREWARM=0`).

### Dashboard (legacy Streamlit — fallback)

```bash
streamlit run app.py
# open http://localhost:8501
```

### MCP server (ask Claude to forecast)

```bash
python mcp_server.py    # stdio transport
```

Register it with your Claude client. Example `claude_desktop_config.json` snippet
(adjust paths; on Windows use double backslashes):

```json
{
  "mcpServers": {
    "kronos-forecast": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "/path/to/Kronos/forecast_dashboard"
    }
  }
}
```

Tools exposed: `list_instruments`, `get_forecast`, `get_accuracy`, `refresh_actuals`.
Every response carries the caveats (band-not-point, model-did-not-see-news, the
per-instrument confidence note).

### Notebook

Open `notebook_sync.ipynb`. It imports `forecast_engine` and calls the same
functions the dashboard does — no duplicated model logic.

---

## The four instruments

| Display | Ticker (primary) | Fallback | Volume | Note |
|---|---|---|---|---|
| Silver (XAG/USD) | `SI=F` | `XAGUSD=X` | real (futures) | |
| Gold (XAU/USD) | `GC=F` | `XAUUSD=X` | real (futures) | |
| WTI Crude Oil | `CL=F` | — | real (futures) | **EVENT-SENSITIVE** (OPEC/inventory) |
| GBP/JPY | `GBPJPY=X` | — | **unreliable** | **LOW CONFIDENCE**, routes to no-volume path |

The UI flags GBP/JPY as low-confidence and WTI as event-sensitive. This is by design.

---

## Accuracy tracking (the point of the demo account)

- Every forecast is logged to SQLite (`forecasts.db`) at generation time.
- `update_actuals()` fetches realized closes for past target dates and stores them
  next to the predictions.
- `accuracy_summary(instrument)` reports the **headline metric — band hit-rate**
  (a calibrated p10–p90 band should contain the actual ~80% of the time), plus
  median absolute error and directional accuracy.

After enough days, the dashboard's "Accuracy so far" panel tells you, as a number,
whether the model is calibrated on each instrument — not a vibe.

---

## Running on GCP (the user's environment)

Run the bespoke web dashboard bound to all interfaces:

```bash
python server.py            # honours HOST/PORT env vars
# or explicitly:
HOST=0.0.0.0 PORT=8000 python server.py
# or via uvicorn:
uvicorn server:app --host 0.0.0.0 --port 8000
```

ECharts is vendored under `web/vendor/`, so the dashboard renders with **no
external CDN** — it works on a locked-down GCP box. On startup the server
prewarms all four forecasts in the background (CPU inference is slow on the first
hit; this hides that latency).

**Reaching it (recommended: SSH port-forward — no firewall changes):**

```bash
gcloud compute ssh YOUR_VM --zone YOUR_ZONE -- -L 8000:localhost:8000
# then open http://localhost:8000 on your laptop
```

Alternatively you can open the firewall port `8000`, but that exposes the app to
the internet (there is no auth by default) — prefer the port-forward.

> Legacy Streamlit fallback: `streamlit run app.py --server.port 8501 --server.address 0.0.0.0`

### ⚠️ Cost guardrail (required reading)

- **Stop the VM when you're not using it.** A *stopped* VM bills only for its disk
  (~**$1–2/month**). An `e2-standard-2` left running 24/7 is roughly **~$50/month**.
- **Set a billing budget alert** in GCP (Billing → Budgets & alerts) so you get
  emailed before a surprise bill.

---

## Deploy to Cloud Run (stable public HTTPS, no VM/tunnel)

`deploy/cloudrun.ps1` builds the container with Cloud Build and deploys it to
**Cloud Run** — a managed, autoscaling service with a stable HTTPS URL and no
firewall/tunnel to manage. The `Dockerfile` clones Kronos and bakes the model
weights into the image at build time, so cold starts don't pay the download cost.

```powershell
powershell -ExecutionPolicy Bypass -File deploy\cloudrun.ps1 -Project YOUR_PROJECT
```

It enables the needed APIs, pre-creates the Artifact Registry repo, builds +
deploys, then **warms** each instrument once so the day's forecasts are cached.

**Speed reality (important):** Cloud Run general compute is **CPU-only** (no GPU),
so a *fresh* forecast still takes **~4–5 min**. The mitigation is the in-memory
per-day cache: it's computed once (at warm time) and every later visit that same
day is **instant** — *as long as it lands on the warm instance*. Because the cache
is in-memory (and the SQLite DB lives in ephemeral `/tmp`), it is **per-instance**.
So the script pins the service to a **single always-warm instance** —
`-MinInstances 1 -MaxInstances 1` — otherwise Cloud Run can scale out and requests
round-robin to a fresh empty instance, half hitting the cache and half paying the
full ~4-min recompute. One instance at `--concurrency 4` still serves several
simultaneous viewers, and capping at 1 also hard-caps the bill.

| flag | default | effect |
|------|---------|--------|
| `-MinInstances 1` | warm | keeps the day cache alive → instant repeat visits |
| `-MaxInstances 1` | pinned | never scale out → cache stays consistent + cost is capped |
| `-MinInstances 0` | — | $0 idle cost, but **every** visit after idle cold-starts + recomputes (~5 min) |
| `-Warm:$false` | warm on | skip the post-deploy cache warming |
| `-Cpu` / `-Memory` | `2` / `2Gi` | per-instance resources (Kronos barely uses >2 threads, so 2 vCPU ≈ 4 vCPU speed) |

> Cost note (this billing account is **INR**): the always-warm instance is the
> dominant cost — **~$26/mo (~₹2200)** at 2 vCPU/2Gi, ~$50/mo at 4 vCPU/4Gi.
> Request compute on top is cents. With `-MinInstances 0` Cloud Run scales to
> zero ($0 idle) but every visit after idle is a slow cold recompute. Set a GCP
> budget alert (Billing → Budgets) so an always-on instance can't surprise you.

---

## Design notes

- **Minimalist black & white.** Monochrome by design; color is never used to imply
  confidence. The p10–p90 band is the most visually prominent element on the chart.
- **Live theme switcher**: Paper (white), Ink (black), Slate, E-ink, High-contrast.
- **Text-based analysis ("bot")**: a deterministic plain-English read of the
  distribution (bands, skew, realized vol, calibration). With `ANTHROPIC_API_KEY`
  set, an optional LLM rephrases it — explicitly labelled unvalidated, never adding
  a score or a buy/sell call.

## Non-goals (deliberately not built)

Intraday/session forecasting (we're on daily data), order execution / broker
integration, a single buy/sell signal or confidence-score headline, reimplementing
Kronos internals, and fine-tuning.
