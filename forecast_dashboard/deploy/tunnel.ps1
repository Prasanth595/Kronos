# deploy/tunnel.ps1 - open an IAP SSH tunnel localhost:LOCAL_PORT -> VM APP_PORT.
# Keep this window open; browse http://localhost:LOCAL_PORT. The app is NEVER
# exposed to the public internet (the VM has no external IP).
. "$PSScriptRoot\_common.ps1"
Write-Host "Tunnel: http://localhost:$LOCAL_PORT  (Ctrl-C to close)"
& $GcloudExe "--project=$Project" compute start-iap-tunnel `
    $INSTANCE $APP_PORT `
    "--local-host-port=localhost:$LOCAL_PORT" "--zone=$ZONE"
