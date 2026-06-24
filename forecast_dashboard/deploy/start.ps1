# deploy/start.ps1 - start the (existing) VM. App + watchdog auto-start via systemd.
. "$PSScriptRoot\_common.ps1"
& $GcloudExe "--project=$Project" compute instances start $INSTANCE "--zone=$ZONE"
Write-Host "Started. Give it ~20s, then: powershell -File deploy\tunnel.ps1 -> http://localhost:$LOCAL_PORT"
