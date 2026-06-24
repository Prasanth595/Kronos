#!/usr/bin/env bash
# deploy/down.sh — DELETE the VM (and its boot disk) to stop ALL billing.
# Irreversible for the VM (the app code lives in this repo, so re-deploy with
# up.sh any time). Asks for confirmation.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/config.env"
read -r -p "Delete VM '$INSTANCE' in $ZONE (project $PROJECT)? [y/N] " ans
case "$ans" in
    y|Y) gcloud --project="$PROJECT" compute instances delete "$INSTANCE" \
            --zone="$ZONE" --quiet
         echo "Deleted. Re-deploy any time with ./deploy/up.sh" ;;
    *)   echo "Aborted." ;;
esac
