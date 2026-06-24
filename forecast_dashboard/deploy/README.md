# Deploying the Kronos dashboard to GCP (on-demand, auto-stop)

The model only ever runs **here, on a GCP VM** — never on your laptop. This kit
gives you an on-demand box that you start when you want to use it and that
**auto-stops itself** when idle so it can't quietly burn your budget.

## What you get

- A single **e2-standard-4** VM (4 vCPU / 16 GB) in **asia-south1 (Mumbai)**,
  no public IP, reached over an **IAP SSH tunnel** (`localhost:8000`).
- The app as a **systemd service** (auto-starts on boot) + a **watchdog** that
  stops the VM after **30 min idle** or a **3 h hard cap**.
- **Layer-2 sentiment uses Vertex Gemini with the VM's service account — no API
  key**. If Vertex is unavailable it falls back to Anthropic (if you add a key)
  then to the deterministic keyword baseline.
- A **$30/mo budget alert** (notify-only; the real cost guard is auto-stop).

### Rough cost
e2-standard-4 is ~$0.13/hr in asia-south1. With auto-stop, **a few hours a day,
Mon-Fri** lands around **$8-20/mo**. A stopped VM costs only its boot disk
(~$1.20/mo). Vertex Gemini Flash on a handful of headlines per refresh is pennies.

> **Two flavors of the scripts ship side by side:** `*.sh` for macOS/Linux/Git-Bash
> and `*.ps1` for **native Windows PowerShell** (no WSL/Git-Bash needed — they
> use the `tar.exe` + OpenSSH that ship with Windows 10/11). The `vm_setup.sh`
> always runs *on the Debian VM*, so it stays bash. Pick the column that matches
> your shell below.

## One-time setup

1. **Install the gcloud CLI** and log in:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
2. **Pick/confirm a project with billing enabled.** The scripts use your
   **active gcloud project** automatically (`gcloud config get-value project`).
   To override, set `PROJECT="your-project-id"` in `deploy/config.env`, export
   `KRONOS_GCP_PROJECT=...`, or (PowerShell) pass `-Project your-id` to `up.ps1`.
3. **Deploy** (creates the VM, installs everything, starts the service):
   ```bash
   ./deploy/up.sh                                   # bash
   ```
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\up.ps1   # Windows
   ```
   First boot downloads Kronos weights (~1-2 min). Re-running is idempotent
   (just re-pushes code + re-runs setup).
4. **(Optional) budget alert:** `./deploy/budget.sh`  /  `deploy\budget.ps1`

## Daily use

| action            | bash                  | Windows PowerShell             |
|-------------------|-----------------------|--------------------------------|
| power on          | `./deploy/start.sh`   | `deploy\start.ps1`             |
| tunnel -> :8000   | `./deploy/tunnel.sh`  | `deploy\tunnel.ps1`            |
| power off now     | `./deploy/stop.sh`    | `deploy\stop.ps1`              |
| health + logs     | `./deploy/status.sh`  | `deploy\status.ps1`            |
| delete the VM     | `./deploy/down.sh`    | `deploy\down.ps1`              |

```powershell
# Windows one-liner to power on, then open the tunnel (keep window open):
powershell -ExecutionPolicy Bypass -File deploy\start.ps1
powershell -ExecutionPolicy Bypass -File deploy\tunnel.ps1   # -> http://localhost:8000
```

Then browse **http://localhost:8000** and run forecasts on real Mon-Fri data.
Walk away and the watchdog auto-stops the VM (or stop it now with `stop`).

### Windows notes
- gcloud's bundled Python can be shadowed by the Windows "App Execution Alias".
  The `.ps1` scripts set `CLOUDSDK_PYTHON` to a real Python automatically if one
  is found under `%LOCALAPPDATA%\Programs\Python\Python31x`. To force a specific
  gcloud, set `KRONOS_GCLOUD=C:\path\to\gcloud.cmd`.
- Run from an **un-elevated** PowerShell in the repo root. If scripts are blocked
  by execution policy, invoke with `-ExecutionPolicy Bypass` as shown.

## How auto-stop works (the cost guard)

`server.py` touches `ACTIVITY_FILE` on every non-health API request. The
watchdog (`kronos-watchdog.service`) checks once a minute and runs
`shutdown -h now` when either:

- there's been **no request for `IDLE_MINUTES`** (default 30), or
- the VM has been up for **`HARD_CAP_HOURS`** (default 3),

A guest shutdown moves the instance to **TERMINATED**, so Compute billing stops.
Tune the thresholds in `deploy/config.env` (`KRONOS_IDLE_MIN`,
`KRONOS_HARD_CAP_HRS`) and re-run `up.sh`.

## Security notes

- The VM has **no external IP**; the only ingress is SSH on the IAP range
  (`35.235.240.0/20`). The dashboard is reachable **only through your tunnel**.
- No API keys live in the repo. The VM's `.env` (written by `vm_setup.sh`) holds
  only non-secret config; Gemini auth is the VM's own service account via ADC.
- To also use Anthropic as a sentiment fallback, SSH in and add
  `ANTHROPIC_API_KEY=...` to `/opt/kronos_dashboard/.env`, then
  `sudo systemctl restart kronos`.

## Files

Every `*.sh` below has a matching **`*.ps1`** (same behavior, native Windows);
`_common.ps1` is a shared helper the PowerShell scripts dot-source. `vm_setup.sh`
has no `.ps1` because it only ever runs on the Debian VM.

| file            | what it does                                              |
|-----------------|-----------------------------------------------------------|
| `config.env`    | all knobs (project, zone, VM shape, idle thresholds…)     |
| `up.sh` / `up.ps1`         | create VM + push code + run setup (idempotent)  |
| `vm_setup.sh`   | runs **on the VM**: deps, Kronos clone, systemd, watchdog |
| `start.*`/`stop.*` | power the VM on/off                                    |
| `tunnel.*`      | IAP tunnel to `localhost:8000`                            |
| `status.*`      | health + logs                                             |
| `budget.*`      | $30/mo billing alert                                      |
| `down.*`        | delete the VM                                             |
| `_common.ps1`   | shared PowerShell helper (config parse + gcloud resolve)  |
