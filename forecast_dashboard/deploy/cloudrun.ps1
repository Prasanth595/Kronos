# ============================================================================
# deploy/cloudrun.ps1 - build the container with Cloud Build and deploy it to
# Cloud Run (managed, scale-to-zero, stable HTTPS URL). Windows PowerShell.
#
#   powershell -ExecutionPolicy Bypass -File deploy\cloudrun.ps1
#
# This is an ALTERNATIVE to the VM deploy (up.ps1). It gives a public HTTPS URL
# with no tunnel/firewall, but Cloud Run general compute is CPU-only so a fresh
# forecast still takes minutes (cached reads are instant). Re-runnable.
# ============================================================================
[CmdletBinding()]
param(
    [string]$Project = $env:KRONOS_GCP_PROJECT,
    [string]$Region  = "asia-south1",
    [string]$Service = "kronos-dashboard",
    [switch]$NoAuth = $true,   # deploy publicly by default; pass -NoAuth:$false to require auth
    # --- demo tuning -------------------------------------------------------
    # The forecast cache is IN-MEMORY (and the SQLite DB lives in ephemeral
    # /tmp), so it is per-instance. To make repeat visits instant the day cache
    # must live on a single, always-warm instance:
    #   MinInstances=1  keep one container warm so the cache survives between hits
    #   MaxInstances=1  never scale out, or requests round-robin to a fresh empty
    #                   instance and miss the cache (some hits, some 3-min recomputes)
    # One instance with concurrency=4 still serves several simultaneous viewers,
    # and capping at 1 also hard-caps the bill (no surprise scale-up). Idle cost
    # at 2 vCPU/2Gi is ~$26/mo (~$13 each for CPU+memory); ~$50/mo at 4 vCPU/4Gi.
    # Pass -MinInstances 0 for $0 idle, but then every visit after an idle period
    # cold-starts AND recomputes (~5 min on 2 vCPU).
    [int]$MinInstances = 1,
    [int]$MaxInstances = 1,
    [int]$Cpu = 2,
    [string]$Memory = "2Gi",
    # After deploy, hit each instrument once so the day's forecasts are cached
    # in the warm instance (compute runs under the request, where CPU is fully
    # allocated). Skip with -Warm:$false.
    [switch]$Warm = $true
)
$ErrorActionPreference = 'Continue'
Set-StrictMode -Version Latest

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here

function Resolve-Gcloud {
    $cmd = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command gcloud -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        "$env:USERPROFILE\google-cloud-sdk\bin\gcloud.cmd",
        "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    )) { if (Test-Path $p) { return $p } }
    throw "gcloud CLI not found."
}
$Gcloud = Resolve-Gcloud
if (-not $env:CLOUDSDK_PYTHON) {
    foreach ($py in @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    )) { if (Test-Path $py) { $env:CLOUDSDK_PYTHON = $py; break } }
}

if (-not $Project -or $Project -eq 'CHANGE_ME') {
    $Project = (& $Gcloud config get-value project 2>$null | Select-Object -First 1)
}
if (-not $Project -or $Project -eq '(unset)') { throw "No GCP project set." }

Write-Host "Project : $Project"
Write-Host "Service : $Service ($Region)"
Write-Host ""

$P = "--project=$Project"

Write-Host "==> [1/2] enabling APIs (idempotent)"
& $Gcloud $P services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com 2>&1 | Out-Host

# Pre-create the Artifact Registry repo that `run deploy --source` needs, so the
# build doesn't stop on an interactive "create repo? (Y/n)" prompt.
$repo = "cloud-run-source-deploy"
& $Gcloud $P artifacts repositories describe $repo --location $Region 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    creating Artifact Registry repo '$repo' in $Region"
    & $Gcloud $P artifacts repositories create $repo --repository-format=docker `
        --location $Region --description "Cloud Run source deploys" --quiet 2>&1 | Out-Host
}

Write-Host "==> [2/2] build + deploy from source (Cloud Build -> Cloud Run)"
$authFlag = if ($NoAuth) { "--allow-unauthenticated" } else { "--no-allow-unauthenticated" }

# CPU-only forecasts are slow: give generous CPU/RAM + a long request timeout,
# and keep concurrency low so heavy computes don't pile up on one instance.
# MinInstances=1 keeps the warm instance's in-memory day cache alive between hits.
& $Gcloud $P run deploy $Service `
    --source "$Root" `
    --region $Region `
    --platform managed `
    --cpu $Cpu `
    --memory $Memory `
    --timeout 900 `
    --concurrency 4 `
    --min-instances $MinInstances `
    --max-instances $MaxInstances `
    --port 8080 `
    --set-env-vars "KRONOS_DEVICE=cpu,KRONOS_PREWARM=0,FORECAST_DB=/tmp/forecasts.db,HF_HOME=/opt/hf_cache" `
    $authFlag --quiet
if ($LASTEXITCODE -ne 0) { throw "Cloud Run deploy failed ($LASTEXITCODE)" }

$url = (& $Gcloud $P run services describe $Service --region $Region --format "value(status.url)" | Select-Object -First 1)

# --- warm the day cache ----------------------------------------------------
# With min-instances>=1 the warm instance holds its per-day forecast cache in
# memory, so warming each instrument once now makes every later visit instant.
# Each fresh CPU forecast is ~2-4 min; we fire them sequentially with a long
# timeout. (No-op for min-instances 0 since the instance would scale away.)
if ($Warm -and $MinInstances -ge 1 -and $url) {
    Write-Host ""
    Write-Host "==> warming day cache at $url (each instrument ~2-4 min on CPU)"
    $instruments = @("silver", "gold", "wti", "gbpjpy")
    foreach ($inst in $instruments) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            $r = Invoke-WebRequest "$url/api/forecast/$inst" -TimeoutSec 870 -UseBasicParsing
            $sw.Stop()
            Write-Host ("    {0,-7} HTTP {1}  {2,5:N0}s" -f $inst, $r.StatusCode, $sw.Elapsed.TotalSeconds)
        } catch {
            $sw.Stop()
            Write-Host ("    {0,-7} ERR after {1,5:N0}s: {2}" -f $inst, $sw.Elapsed.TotalSeconds, $_.Exception.Message)
        }
    }
}

Write-Host ""
Write-Host "==> done. Service URL:"
Write-Host $url
