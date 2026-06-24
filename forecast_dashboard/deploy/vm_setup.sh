#!/usr/bin/env bash
# ============================================================================
# deploy/vm_setup.sh — runs ON the VM (pushed + executed by deploy/up.sh).
# Idempotent: safe to re-run. Installs system deps, Python venv, clones Kronos,
# installs the systemd service + idle watchdog. Does NOT start a forecast.
# ============================================================================
set -euo pipefail

REMOTE_DIR="${1:-/opt/kronos_dashboard}"
APP_PORT="${2:-8000}"
IDLE_MINUTES="${3:-30}"
HARD_CAP_HOURS="${4:-3}"
GEMINI_MODEL="${5:-gemini-2.0-flash-001}"
VERTEX_LOCATION="${6:-asia-south1}"
RUN_USER="${7:-$(whoami)}"

KRONOS_REPO="https://github.com/shiyu-coder/Kronos.git"
ACTIVITY_FILE="/run/kronos_activity"

echo "==> [1/7] apt deps"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3-venv python3-pip git curl >/dev/null

echo "==> [2/7] clone Kronos (price-only FLM)"
if [ ! -d "$REMOTE_DIR/Kronos/.git" ]; then
    git clone --depth 1 "$KRONOS_REPO" "$REMOTE_DIR/Kronos"
else
    git -C "$REMOTE_DIR/Kronos" pull --ff-only || true
fi

echo "==> [3/7] python venv + deps"
cd "$REMOTE_DIR"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
# CPU-only torch keeps the image small and avoids CUDA wheels we don't need.
pip install -q --index-url https://download.pytorch.org/whl/cpu torch || \
    pip install -q torch
pip install -q -r requirements.txt

echo "==> [4/7] write VM .env (keyless Vertex Gemini)"
PROJECT_ID="$(curl -s -H 'Metadata-Flavor: Google' \
    http://metadata.google.internal/computeMetadata/v1/project/project-id || echo '')"
cat > "$REMOTE_DIR/.env" <<EOF
KRONOS_DIR=$REMOTE_DIR/Kronos
KRONOS_MODEL=NeoQuasar/Kronos-small
KRONOS_TOKENIZER=NeoQuasar/Kronos-Tokenizer-base
KRONOS_DEVICE=cpu
HOST=0.0.0.0
PORT=$APP_PORT
KRONOS_PREWARM=1
ACTIVITY_FILE=$ACTIVITY_FILE
# Layer-2 sentiment: Vertex Gemini via the VM service account (NO api key).
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=$PROJECT_ID
GOOGLE_CLOUD_LOCATION=$VERTEX_LOCATION
GEMINI_MODEL=$GEMINI_MODEL
SENTIMENT_TTL=900
EOF

echo "==> [5/7] systemd service for the app"
sudo tee /etc/systemd/system/kronos.service >/dev/null <<EOF
[Unit]
Description=Kronos Forecasting Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REMOTE_DIR
EnvironmentFile=$REMOTE_DIR/.env
# '+' runs this as root (the main process below stays unprivileged $RUN_USER);
# needed because $ACTIVITY_FILE lives in root-owned /run.
ExecStartPre=+/usr/bin/install -m 666 /dev/null $ACTIVITY_FILE
ExecStart=$REMOTE_DIR/.venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port $APP_PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "==> [6/7] idle-watchdog (auto-stop = cost guard)"
sudo tee /usr/local/bin/kronos_watchdog.sh >/dev/null <<EOF
#!/usr/bin/env bash
# Stops the VM after \$IDLE_MINUTES of no user request OR \$HARD_CAP_HOURS uptime.
set -u
IDLE_SECS=\$(( $IDLE_MINUTES * 60 ))
HARD_CAP_SECS=\$(( $HARD_CAP_HOURS * 3600 ))
ACTIVITY_FILE="$ACTIVITY_FILE"
BOOT_EPOCH=\$(date +%s)
while true; do
    sleep 60
    NOW=\$(date +%s)
    # hard cap
    if [ \$(( NOW - BOOT_EPOCH )) -ge \$HARD_CAP_SECS ]; then
        logger -t kronos-watchdog "hard cap reached -> shutting down"
        sudo shutdown -h now; exit 0
    fi
    # idle since last request (fall back to boot time if file missing)
    if [ -f "\$ACTIVITY_FILE" ]; then
        LAST=\$(cut -d. -f1 < "\$ACTIVITY_FILE" 2>/dev/null || echo "\$BOOT_EPOCH")
    else
        LAST=\$BOOT_EPOCH
    fi
    if [ \$(( NOW - LAST )) -ge \$IDLE_SECS ]; then
        logger -t kronos-watchdog "idle \${IDLE_MINUTES}m -> shutting down"
        sudo shutdown -h now; exit 0
    fi
done
EOF
sudo chmod +x /usr/local/bin/kronos_watchdog.sh
sudo tee /etc/systemd/system/kronos-watchdog.service >/dev/null <<EOF
[Unit]
Description=Kronos idle auto-stop watchdog
After=kronos.service

[Service]
Type=simple
ExecStart=/usr/local/bin/kronos_watchdog.sh
Restart=always

[Install]
WantedBy=multi-user.target
EOF

echo "==> [7/7] enable + (re)start services"
sudo systemctl daemon-reload
sudo systemctl enable --now kronos.service
sudo systemctl enable --now kronos-watchdog.service
sleep 2
sudo systemctl --no-pager --lines=5 status kronos.service || true
echo "==> done. app on 0.0.0.0:$APP_PORT (reach via SSH tunnel)."
