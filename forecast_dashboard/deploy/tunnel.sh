#!/usr/bin/env bash
# deploy/tunnel.sh — open an IAP SSH tunnel from localhost:LOCAL_PORT to the
# VM's APP_PORT. Keep this terminal open; browse http://localhost:LOCAL_PORT.
# The app is NEVER exposed to the public internet (VM has no external IP).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/config.env"
echo "Tunnel: http://localhost:$LOCAL_PORT  (Ctrl-C to close)"
exec gcloud --project="$PROJECT" compute start-iap-tunnel \
    "$INSTANCE" "$APP_PORT" \
    --local-host-port="localhost:$LOCAL_PORT" --zone="$ZONE"
