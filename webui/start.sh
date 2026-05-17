#!/bin/bash

# Kronos Flask API startup script.
# Next.js serves the browser UI from ../webui-next on port 3000.

echo "Starting Kronos Flask API..."
echo "============================="

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python3 is not installed. Please install Python3 first."
    exit 1
fi

if [ ! -f "app.py" ]; then
    echo "Please run this script from the webui directory."
    exit 1
fi

echo "Checking backend dependencies..."
if ! python3 -c "import flask, flask_cors, pandas, numpy, plotly" >/dev/null 2>&1; then
    echo "Missing dependencies, installing..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "Dependency installation failed."
        exit 1
    fi
fi

echo "Starting API server on http://localhost:7070"
echo "Use the Next.js UI at http://localhost:3000"
echo "Press Ctrl+C to stop this API server"
echo ""

python3 app.py
