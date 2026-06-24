#!/usr/bin/env bash
# ============================================================================
# deploy/up.sh — one-shot: enable APIs, create the VM (if absent), push the
# app, run vm_setup.sh on it, then print the tunnel command. Re-runnable: if
# the VM exists it just re-pushes code and re-runs setup (idempotent).
#
#   ./deploy/up.sh
#
# Requires: gcloud CLI authenticated (`gcloud auth login`) with billing on the
# target project. Reads deploy/config.env (edit PROJECT first!).
# ============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
# shellcheck disable=SC1091
source "$HERE/config.env"

if [ "$PROJECT" = "CHANGE_ME" ]; then
    echo "ERROR: set PROJECT in deploy/config.env (or export KRONOS_GCP_PROJECT)." >&2
    exit 1
fi
command -v gcloud >/dev/null || { echo "ERROR: gcloud CLI not found." >&2; exit 1; }

G="gcloud --project=$PROJECT"

echo "==> [1/7] enabling required APIs (idempotent)"
$G services enable compute.googleapis.com aiplatform.googleapis.com \
    cloudbilling.googleapis.com billingbudgets.googleapis.com iap.googleapis.com -q

echo "==> [2/7] ensure firewall allows SSH + app port (IAP range) — tunnel needs it"
$G compute firewall-rules describe kronos-allow-ssh >/dev/null 2>&1 || \
$G compute firewall-rules create kronos-allow-ssh \
    --direction=INGRESS --action=ALLOW --rules=tcp:22 \
    --source-ranges=35.235.240.0/20 --quiet >/dev/null || true
# IAP TCP-forwards the app port (tunnel.sh connects straight to APP_PORT over
# IAP, not via SSH), so the IAP range needs tcp:$APP_PORT too. Without this the
# tunnel fails with '4003: failed to connect to backend'.
$G compute firewall-rules describe kronos-allow-iap-app >/dev/null 2>&1 || \
$G compute firewall-rules create kronos-allow-iap-app \
    --direction=INGRESS --action=ALLOW --rules="tcp:$APP_PORT" \
    --source-ranges=35.235.240.0/20 --quiet >/dev/null || true

echo "==> [3/7] ensure Cloud NAT for outbound internet (private VM has no public IP)"
# The VM is created with --no-address (not reachable from the internet). It
# still needs *outbound* access for apt/git/pip/HuggingFace. Cloud NAT via a
# Cloud Router provides egress-only internet while keeping the VM unexposed.
$G compute routers describe kronos-router --region="$REGION" >/dev/null 2>&1 || \
$G compute routers create kronos-router \
    --network=default --region="$REGION" --quiet >/dev/null || true
$G compute routers nats describe kronos-nat --router=kronos-router --region="$REGION" >/dev/null 2>&1 || \
$G compute routers nats create kronos-nat \
    --router=kronos-router --region="$REGION" \
    --auto-allocate-nat-external-ips \
    --nat-all-subnet-ip-ranges --quiet >/dev/null || true

echo "==> [4/7] create VM if absent: $INSTANCE ($MACHINE_TYPE, $ZONE)"
if ! $G compute instances describe "$INSTANCE" --zone="$ZONE" >/dev/null 2>&1; then
    $G compute instances create "$INSTANCE" \
        --zone="$ZONE" \
        --machine-type="$MACHINE_TYPE" \
        --image-family="$IMAGE_FAMILY" --image-project="$IMAGE_PROJECT" \
        --boot-disk-size="${BOOT_DISK_GB}GB" --boot-disk-type=pd-balanced \
        --scopes=cloud-platform \
        --no-address \
        --labels=app=kronos-demo
    echo "    waiting 25s for sshd..."; sleep 25
else
    echo "    VM exists; ensuring it's running"
    $G compute instances start "$INSTANCE" --zone="$ZONE" -q || true
    sleep 8
fi

# --no-address + IAP tunneling = no public IP (cheaper + safer). All ssh/scp
# below go through IAP.
SSH="$G compute ssh $INSTANCE --zone=$ZONE --tunnel-through-iap"
SCP="$G compute scp --zone=$ZONE --tunnel-through-iap --recurse"

echo "==> [5/7] push app code (tarball of the working tree, sans junk)"
TARBALL="$(mktemp -u).tar.gz"
tar --exclude='./Kronos' --exclude='./.git' --exclude='./.venv' \
    --exclude='*.db' --exclude='__pycache__' --exclude='.env' \
    -czf "$TARBALL" -C "$ROOT" .
$SSH --command="sudo mkdir -p $REMOTE_DIR && sudo chown -R \$(whoami) $REMOTE_DIR"
$SCP "$TARBALL" "$INSTANCE:/tmp/kronos_app.tar.gz"
$SSH --command="tar -xzf /tmp/kronos_app.tar.gz -C $REMOTE_DIR && rm /tmp/kronos_app.tar.gz"
rm -f "$TARBALL"

echo "==> [6/7] run vm_setup.sh on the VM (installs deps, services, watchdog)"
$SSH --command="chmod +x $REMOTE_DIR/deploy/vm_setup.sh && \
    $REMOTE_DIR/deploy/vm_setup.sh '$REMOTE_DIR' '$APP_PORT' '$IDLE_MINUTES' \
        '$HARD_CAP_HOURS' '$GEMINI_MODEL' '$VERTEX_LOCATION' \$(whoami)"

echo "==> [7/7] done."
cat <<EOF

  VM is up and the app is starting (first model load downloads Kronos weights
  ~1-2 min). It auto-stops after ${IDLE_MINUTES}m idle / ${HARD_CAP_HOURS}h hard cap.

  Open the dashboard:   ./deploy/tunnel.sh     then  http://localhost:$LOCAL_PORT
  Stop now (save money): ./deploy/stop.sh
  Start again later:     ./deploy/start.sh
  Set the budget alert:  ./deploy/budget.sh
EOF
