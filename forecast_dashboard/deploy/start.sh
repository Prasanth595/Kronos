#!/usr/bin/env bash
# deploy/start.sh — start the (existing) VM. App + watchdog auto-start via systemd.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/config.env"
gcloud --project="$PROJECT" compute instances start "$INSTANCE" --zone="$ZONE"
echo "Started. Give it ~20s, then: ./deploy/tunnel.sh -> http://localhost:$LOCAL_PORT"
