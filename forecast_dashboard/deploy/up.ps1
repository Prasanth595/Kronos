# ============================================================================
# deploy/up.ps1 - Windows (PowerShell) port of deploy/up.sh.
#
# One-shot: enable APIs, create the VM (if absent), push the app, run
# vm_setup.sh on it, then print the tunnel command. Re-runnable / idempotent.
#
#   powershell -ExecutionPolicy Bypass -File deploy\up.ps1
#
# Requires: gcloud CLI authenticated (gcloud auth login) with billing on the
# target project, plus Windows tar.exe + OpenSSH (both ship with Win10/11).
# Reads deploy/config.env for non-secret knobs; PROJECT is taken from the
# active gcloud config unless -Project is passed or KRONOS_GCP_PROJECT is set.
# ============================================================================
[CmdletBinding()]
param(
    [string]$Project = $env:KRONOS_GCP_PROJECT,
    [string]$Gcloud  = $env:KRONOS_GCLOUD     # full path to gcloud(.cmd); auto-detected if empty
)
# NOTE: we deliberately do NOT use $ErrorActionPreference='Stop' globally.
# gcloud (and especially ssh/scp over IAP) write lots of normal progress to
# stderr; under 'Stop' PowerShell would treat every such line as a terminating
# NativeCommandError and abort. Instead we leave it at 'Continue' and gate every
# call on $LASTEXITCODE via Invoke-Gcloud (throws) / Test-Gcloud (boolean).
$ErrorActionPreference = 'Continue'
Set-StrictMode -Version Latest

# --- locate this script + repo root ----------------------------------------
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here

# --- parse deploy/config.env (KEY="${OVERRIDE:-default}" lines) -------------
function Get-ConfigDefaults($path) {
    $cfg = @{}
    foreach ($line in Get-Content $path) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        if ($t -match '^([A-Za-z_][A-Za-z0-9_]*)="?(.*?)"?$') {
            $key = $Matches[1]; $val = $Matches[2]
            # resolve ${VAR:-default} -> default (we don't honor env overrides here
            # except PROJECT, which is handled explicitly below)
            if ($val -match '^\$\{[^:}]+:-(.*)\}$') { $val = $Matches[1] }
            $val = $val.Trim('"')
            $cfg[$key] = $val
        }
    }
    return $cfg
}
$cfg = Get-ConfigDefaults (Join-Path $Here 'config.env')

# --- resolve gcloud --------------------------------------------------------
function Resolve-Gcloud($explicit) {
    if ($explicit -and (Test-Path $explicit)) { return $explicit }
    $cmd = Get-Command gcloud.cmd -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cmd = Get-Command gcloud -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        "$env:USERPROFILE\google-cloud-sdk\bin\gcloud.cmd",
        "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    )) { if (Test-Path $p) { return $p } }
    throw "gcloud CLI not found. Pass -Gcloud <path> or add it to PATH."
}
$GcloudExe = Resolve-Gcloud $Gcloud
# Make gcloud use a real Python if the bundled one is missing (Windows App
# Execution Alias 'python' can shadow it). Harmless if already correct.
if (-not $env:CLOUDSDK_PYTHON) {
    foreach ($py in @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    )) { if (Test-Path $py) { $env:CLOUDSDK_PYTHON = $py; break } }
}

function Invoke-Gcloud {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
    & $GcloudExe @Args
    if ($LASTEXITCODE -ne 0) { throw "gcloud $($Args -join ' ') -> exit $LASTEXITCODE" }
}
# non-throwing variant for "describe ... || create" idempotency checks.
# gcloud writes to stderr when a resource is absent; under
# $ErrorActionPreference='Stop' PowerShell would turn that into a terminating
# NativeCommandError, so we relax it locally and swallow stderr.
function Test-Gcloud {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $GcloudExe @Args 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $old
    }
}

# --- resolve PROJECT --------------------------------------------------------
if (-not $Project -or $Project -eq 'CHANGE_ME') {
    $Project = (& $GcloudExe config get-value project 2>$null | Select-Object -First 1)
}
if (-not $Project -or $Project -eq 'CHANGE_ME' -or $Project -eq '(unset)') {
    throw "No GCP project. Pass -Project <id>, set KRONOS_GCP_PROJECT, or run 'gcloud config set project <id>'."
}

# --- pull config values (with sane fallbacks) ------------------------------
$ZONE            = $cfg['ZONE'];            if (-not $ZONE)            { $ZONE = 'asia-south1-c' }
$REGION          = $cfg['REGION'];          if (-not $REGION)          { $REGION = 'asia-south1' }
$INSTANCE        = $cfg['INSTANCE'];        if (-not $INSTANCE)        { $INSTANCE = 'kronos-demo' }
$MACHINE_TYPE    = $cfg['MACHINE_TYPE'];    if (-not $MACHINE_TYPE)    { $MACHINE_TYPE = 'e2-standard-4' }
$BOOT_DISK_GB    = $cfg['BOOT_DISK_GB'];    if (-not $BOOT_DISK_GB)    { $BOOT_DISK_GB = '30' }
$IMAGE_FAMILY    = $cfg['IMAGE_FAMILY'];    if (-not $IMAGE_FAMILY)    { $IMAGE_FAMILY = 'debian-12' }
$IMAGE_PROJECT   = $cfg['IMAGE_PROJECT'];   if (-not $IMAGE_PROJECT)   { $IMAGE_PROJECT = 'debian-cloud' }
$APP_PORT        = $cfg['APP_PORT'];        if (-not $APP_PORT)        { $APP_PORT = '8000' }
$LOCAL_PORT      = $cfg['LOCAL_PORT'];      if (-not $LOCAL_PORT)      { $LOCAL_PORT = '8000' }
$REMOTE_DIR      = $cfg['REMOTE_DIR'];      if (-not $REMOTE_DIR)      { $REMOTE_DIR = '/opt/kronos_dashboard' }
$IDLE_MINUTES    = $cfg['IDLE_MINUTES'];    if (-not $IDLE_MINUTES)    { $IDLE_MINUTES = '30' }
$HARD_CAP_HOURS  = $cfg['HARD_CAP_HOURS'];  if (-not $HARD_CAP_HOURS)  { $HARD_CAP_HOURS = '3' }
$GEMINI_MODEL    = $cfg['GEMINI_MODEL'];    if (-not $GEMINI_MODEL)    { $GEMINI_MODEL = 'gemini-2.0-flash-001' }
$VERTEX_LOCATION = $cfg['VERTEX_LOCATION']; if (-not $VERTEX_LOCATION) { $VERTEX_LOCATION = 'asia-south1' }

Write-Host "Project : $Project"
Write-Host "VM      : $INSTANCE ($MACHINE_TYPE, $ZONE)"
Write-Host ""

$P = "--project=$Project"

Write-Host "==> [1/7] enabling required APIs (idempotent)"
Invoke-Gcloud $P services enable compute.googleapis.com aiplatform.googleapis.com `
    cloudbilling.googleapis.com billingbudgets.googleapis.com iap.googleapis.com -q

Write-Host "==> [2/7] ensure firewall allows SSH + app port (IAP range 35.235.240.0/20)"
if (-not (Test-Gcloud $P compute firewall-rules describe kronos-allow-ssh)) {
    Invoke-Gcloud $P compute firewall-rules create kronos-allow-ssh `
        --direction=INGRESS --action=ALLOW --rules=tcp:22 `
        --source-ranges=35.235.240.0/20 --quiet
}
# IAP TCP-forwards the app port (tunnel.ps1 connects straight to APP_PORT over
# IAP, not via SSH), so the IAP range needs tcp:$APP_PORT too. Without this the
# tunnel fails with '4003: failed to connect to backend'.
if (-not (Test-Gcloud $P compute firewall-rules describe kronos-allow-iap-app)) {
    Invoke-Gcloud $P compute firewall-rules create kronos-allow-iap-app `
        --direction=INGRESS --action=ALLOW --rules="tcp:$APP_PORT" `
        --source-ranges=35.235.240.0/20 --quiet
}

Write-Host "==> [3/7] ensure Cloud NAT for outbound internet (private VM has no public IP)"
# The VM is created with --no-address (not reachable from the internet). It
# still needs *outbound* access for apt/git/pip/HuggingFace. Cloud NAT via a
# Cloud Router provides egress-only internet while keeping the VM unexposed.
# NAT itself is free; you pay only for data processed + the ephemeral IP while
# the VM runs (pennies/day, and nothing while auto-stopped).
if (-not (Test-Gcloud $P compute routers describe kronos-router --region=$REGION)) {
    Invoke-Gcloud $P compute routers create kronos-router `
        --network=default --region=$REGION --quiet
}
if (-not (Test-Gcloud $P compute routers nats describe kronos-nat --router=kronos-router --region=$REGION)) {
    Invoke-Gcloud $P compute routers nats create kronos-nat `
        --router=kronos-router --region=$REGION `
        --auto-allocate-nat-external-ips `
        --nat-all-subnet-ip-ranges --quiet
}

Write-Host "==> [4/7] create VM if absent"
if (-not (Test-Gcloud $P compute instances describe $INSTANCE --zone=$ZONE)) {
    Invoke-Gcloud $P compute instances create $INSTANCE `
        --zone=$ZONE `
        --machine-type=$MACHINE_TYPE `
        --image-family=$IMAGE_FAMILY --image-project=$IMAGE_PROJECT `
        "--boot-disk-size=$($BOOT_DISK_GB)GB" --boot-disk-type=pd-balanced `
        --scopes=cloud-platform `
        --no-address `
        --labels=app=kronos-demo
    Write-Host "    waiting 30s for sshd..."; Start-Sleep -Seconds 30
} else {
    Write-Host "    VM exists; ensuring it's running"
    & $GcloudExe $P compute instances start $INSTANCE --zone=$ZONE -q 2>$null | Out-Null
    Start-Sleep -Seconds 8
}

Write-Host "==> [5/7] push app code (tarball of the working tree, sans junk)"
$Tarball = Join-Path $env:TEMP ("kronos_app_{0}.tar.gz" -f ([guid]::NewGuid().ToString('N')))
# Windows ships bsdtar as tar.exe; --exclude works the same way.
& tar.exe `
    --exclude='./Kronos' --exclude='./.git' --exclude='./.venv' `
    --exclude='*.db' --exclude='__pycache__' --exclude='./.env' `
    --exclude='*.log' --exclude='./_*' `
    -czf "$Tarball" -C "$Root" .
if ($LASTEXITCODE -ne 0) { throw "tar failed ($LASTEXITCODE)" }

# IAP SSH/SCP. gcloud manages the OpenSSH invocation + key for us. --quiet so
# the first-time "generate an SSH key?" prompt auto-confirms (we run headless).
$SshBase = @($P, 'compute', 'ssh', $INSTANCE, "--zone=$ZONE", '--tunnel-through-iap', '--quiet')
$ScpBase = @($P, 'compute', 'scp', "--zone=$ZONE", '--tunnel-through-iap', '--quiet')

# Host-key warm-up: on Windows gcloud uses PuTTY's plink, which prompts to cache
# an unknown host key. --quiet makes plink run in -batch mode, which *rejects*
# uncached keys outright. So do ONE non-quiet ssh first and pipe "y" to cache the
# key; every --quiet call afterwards then connects headlessly. (No-op once cached.)
Write-Host "    warming up SSH host key (first connect)..."
"y`n" | & $GcloudExe $P compute ssh $INSTANCE "--zone=$ZONE" --tunnel-through-iap --command="true" 2>&1 | Out-Null

Invoke-Gcloud @SshBase --command="sudo mkdir -p $REMOTE_DIR && sudo chown -R `$(whoami) $REMOTE_DIR"
Invoke-Gcloud @ScpBase "$Tarball" "$($INSTANCE):/tmp/kronos_app.tar.gz"
Invoke-Gcloud @SshBase --command="tar -xzf /tmp/kronos_app.tar.gz -C $REMOTE_DIR && rm /tmp/kronos_app.tar.gz"
Remove-Item -Force $Tarball -ErrorAction SilentlyContinue

Write-Host "==> [6/7] run vm_setup.sh on the VM (installs deps, services, watchdog)"
$SetupCmd = "chmod +x $REMOTE_DIR/deploy/vm_setup.sh && " +
    "$REMOTE_DIR/deploy/vm_setup.sh '$REMOTE_DIR' '$APP_PORT' '$IDLE_MINUTES' " +
    "'$HARD_CAP_HOURS' '$GEMINI_MODEL' '$VERTEX_LOCATION' `$(whoami)"
Invoke-Gcloud @SshBase --command="$SetupCmd"

Write-Host "==> [7/7] done."
Write-Host ""
Write-Host "  VM is up and the app is starting (first model load downloads Kronos"
Write-Host "  weights ~1-2 min). It auto-stops after ${IDLE_MINUTES}m idle / ${HARD_CAP_HOURS}h hard cap."
Write-Host ""
Write-Host "  Open the dashboard:    powershell -File deploy\tunnel.ps1   then  http://localhost:$LOCAL_PORT"
Write-Host "  Stop now (save money): powershell -File deploy\stop.ps1"
Write-Host "  Start again later:     powershell -File deploy\start.ps1"
Write-Host "  Check status:          powershell -File deploy\status.ps1"
