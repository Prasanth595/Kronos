#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  KRONOS EDGE Bridge v1.0"
echo "  AURELIA EMPIRE | ZEROEMOTIONS | CLAUDE inside"
echo "============================================================"
echo ""

# Install dependencies
echo "[1/3] Checking dependencies..."
pip install -q -r requirements_edge.txt
echo "      Done."

echo "[2/3] Starting bridge on http://127.0.0.1:7800 ..."
echo "      (First startup loads the Kronos model — takes 30-90s)"
echo ""
echo "[3/3] MT5 Setup reminder:"
echo "      - Copy KRONOS_EDGE.mq5 to your MT5 Experts/ folder"
echo "      - Compile in MetaEditor (F7)"
echo "      - Add http://127.0.0.1:7800 to Allowed URLs"
echo "        (Tools -> Options -> Expert Advisors -> Allowed URLs)"
echo ""
echo "Press Ctrl+C to stop the bridge."
echo "============================================================"
echo ""

python kronos_edge_bridge.py
