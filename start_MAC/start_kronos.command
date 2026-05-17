#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

chmod +x "$SCRIPT_DIR/start_kronos.sh"
"$SCRIPT_DIR/start_kronos.sh"

echo ""
echo "Press any key to close this window..."
read -r -n 1
