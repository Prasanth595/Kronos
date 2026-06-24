# deploy/status.ps1 - show VM power state, app/watchdog health, and recent logs.
. "$PSScriptRoot\_common.ps1"
$P = "--project=$Project"

Write-Host "== VM =="
& $GcloudExe $P compute instances describe $INSTANCE "--zone=$ZONE" `
    "--format=value(status, machineType.scope(machineTypes), lastStartTimestamp)" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "VM '$INSTANCE' not found."; exit 0 }

$state = (& $GcloudExe $P compute instances describe $INSTANCE "--zone=$ZONE" `
    "--format=value(status)" 2>$null | Select-Object -First 1)
if ($state -ne 'RUNNING') {
    Write-Host "(VM is $state - start it with: powershell -File deploy\start.ps1)"
    exit 0
}

Write-Host ""
Write-Host "== services =="
$remote = "systemctl is-active kronos.service kronos-watchdog.service; " +
    "echo '--- last 12 app log lines ---'; " +
    "journalctl -u kronos.service -n 12 --no-pager"
& $GcloudExe $P compute ssh $INSTANCE "--zone=$ZONE" --tunnel-through-iap --command="$remote"
if ($LASTEXITCODE -ne 0) { Write-Host "(could not reach VM over IAP yet)" }
