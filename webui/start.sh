#!/bin/bash

# Kronos Web UI startup script

echo "🚀 Starting Kronos Web UI..."
echo "================================"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first:"
    echo "   https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Check if in correct directory
if [ ! -f "app.py" ]; then
    echo "❌ Please run this script in the webui directory"
    exit 1
fi

# Check dependencies
echo "📦 Checking dependencies..."

# Create local virtual environment if it does not exist
if [ ! -d ".venv" ]; then
    echo "🛠️  Creating virtual environment with uv..."
    uv venv
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment"
        exit 1
    fi
fi

echo "⚠️  Syncing dependencies with uv..."
uv pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ Dependencies installation failed"
    exit 1
fi
echo "✅ Dependencies installation completed"

# Start application
echo "🌐 Starting Web server..."
echo "Access URL: http://localhost:7070"
echo "Press Ctrl+C to stop server"
echo ""

uv run app.py
