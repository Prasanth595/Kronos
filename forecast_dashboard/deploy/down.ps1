# deploy/down.ps1 - DELETE the VM (and its boot disk) to stop ALL billing.
# Irreversible for the VM (app code lives in this repo; re-deploy with up.ps1).
# Asks for confirmation.
. "$PSScriptRoot\_common.ps1"
$ans = Read-Host "Delete VM '$INSTANCE' in $ZONE (project $Project)? [y/N]"
if ($ans -eq 'y' -or $ans -eq 'Y') {
    & $GcloudExe "--project=$Project" compute instances delete $INSTANCE `
        "--zone=$ZONE" --quiet
    Write-Host "Deleted. Re-deploy any time with: powershell -File deploy\up.ps1"
} else {
    Write-Host "Aborted."
}
