#!/usr/bin/env bash
# deploy/stop.sh — stop the VM NOW (moves to TERMINATED, VM billing stops; the
# boot disk still costs ~\$1.20/mo). The app state is on disk, so start.sh resumes.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/config.env"
gcloud --project="$PROJECT" compute instances stop "$INSTANCE" --zone="$ZONE"
echo "Stopped. No compute billing while TERMINATED. Resume: ./deploy/start.sh"
