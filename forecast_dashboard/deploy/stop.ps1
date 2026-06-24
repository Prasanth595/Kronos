# deploy/stop.ps1 - stop the VM NOW (-> TERMINATED, VM billing stops; the boot
# disk still costs ~$1.20/mo). App state is on disk, so start.ps1 resumes it.
. "$PSScriptRoot\_common.ps1"
& $GcloudExe "--project=$Project" compute instances stop $INSTANCE "--zone=$ZONE"
Write-Host "Stopped. No compute billing while TERMINATED. Resume: powershell -File deploy\start.ps1"
