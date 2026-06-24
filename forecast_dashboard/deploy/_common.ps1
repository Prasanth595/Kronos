# ============================================================================
# deploy/_common.ps1 - shared helpers for the Windows deploy scripts.
# Dot-source this: . "$PSScriptRoot\_common.ps1"
# Exposes: $GcloudExe, $Project, and the parsed $cfg hashtable (ZONE, INSTANCE,
# APP_PORT, LOCAL_PORT, ...). Resolves gcloud + a working Python for it.
# ============================================================================
$ErrorActionPreference = 'Stop'

function Get-ConfigDefaults($path) {
    $cfg = @{}
    foreach ($line in Get-Content $path) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        if ($t -match '^([A-Za-z_][A-Za-z0-9_]*)="?(.*?)"?$') {
            $key = $Matches[1]; $val = $Matches[2]
            if ($val -match '^\$\{[^:}]+:-(.*)\}$') { $val = $Matches[1] }
            $cfg[$key] = $val.Trim('"')
        }
    }
    return $cfg
}

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
    throw "gcloud CLI not found. Set KRONOS_GCLOUD or add it to PATH."
}

$Here = $PSScriptRoot
$cfg  = Get-ConfigDefaults (Join-Path $Here 'config.env')
$GcloudExe = Resolve-Gcloud $env:KRONOS_GCLOUD

if (-not $env:CLOUDSDK_PYTHON) {
    foreach ($py in @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    )) { if (Test-Path $py) { $env:CLOUDSDK_PYTHON = $py; break } }
}

$Project = $env:KRONOS_GCP_PROJECT
if (-not $Project -or $Project -eq 'CHANGE_ME') {
    $Project = (& $GcloudExe config get-value project 2>$null | Select-Object -First 1)
}
if (-not $Project -or $Project -eq 'CHANGE_ME' -or $Project -eq '(unset)') {
    throw "No GCP project. Set KRONOS_GCP_PROJECT or run 'gcloud config set project <id>'."
}

# config values with fallbacks
$ZONE       = if ($cfg['ZONE'])       { $cfg['ZONE'] }       else { 'asia-south1-c' }
$INSTANCE   = if ($cfg['INSTANCE'])   { $cfg['INSTANCE'] }   else { 'kronos-demo' }
$APP_PORT   = if ($cfg['APP_PORT'])   { $cfg['APP_PORT'] }   else { '8000' }
$LOCAL_PORT = if ($cfg['LOCAL_PORT']) { $cfg['LOCAL_PORT'] } else { '8000' }
