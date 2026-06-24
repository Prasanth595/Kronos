#!/usr/bin/env bash
# deploy/status.sh — show VM power state, app/watchdog health, and recent logs.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/config.env"
G="gcloud --project=$PROJECT"

echo "== VM =="
$G compute instances describe "$INSTANCE" --zone="$ZONE" \
    --format="value(status, machineType.scope(machineTypes), lastStartTimestamp)" 2>/dev/null \
    || { echo "VM '$INSTANCE' not found."; exit 0; }

STATE=$($G compute instances describe "$INSTANCE" --zone="$ZONE" --format="value(status)" 2>/dev/null || echo "")
if [ "$STATE" != "RUNNING" ]; then
    echo "(VM is $STATE — start it with ./deploy/start.sh)"; exit 0
fi

echo; echo "== services =="
$G compute ssh "$INSTANCE" --zone="$ZONE" --tunnel-through-iap --command="\
    systemctl is-active kronos.service kronos-watchdog.service; \
    echo '--- last 12 app log lines ---'; \
    journalctl -u kronos.service -n 12 --no-pager" 2>/dev/null || \
    echo "(could not reach VM over IAP yet)"
