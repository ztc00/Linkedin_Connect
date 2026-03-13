#!/bin/bash
set -e

echo ""
echo "  LinkedIn Prospect Intelligence — Setup"
echo "  ─────────────────────────────────────────"
echo ""

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "  ✗ Node.js not found. Install it from https://nodejs.org (v18+)"
    exit 1
fi
echo "  ✓ Node.js $(node -v)"

# Check Python 3
if command -v python3 &> /dev/null; then
    PY=python3
elif command -v python &> /dev/null; then
    PY=python
else
    echo "  ✗ Python 3 not found. Install it from https://python.org"
    exit 1
fi
echo "  ✓ Python $($PY --version 2>&1 | awk '{print $2}')"

# Install frontend dependencies
echo ""
echo "  Installing frontend dependencies..."
cd app && npm install && cd ..
echo "  ✓ Frontend ready"

# Create Python venv and install backend deps
echo ""
echo "  Setting up Python environment..."
$PY -m venv .venv
source .venv/bin/activate
pip install --quiet fastapi uvicorn anthropic python-dotenv httpx
echo "  ✓ Backend ready"

# Check for Connections.csv
echo ""
if [ -f "Connections.csv" ]; then
    echo "  ✓ Connections.csv found"
    cp Connections.csv app/public/Connections.csv
    echo "  ✓ Copied to app/public/"
elif [ -f "app/public/Connections.csv" ]; then
    echo "  ✓ Connections.csv found in app/public/"
    cp app/public/Connections.csv Connections.csv
    echo "  ✓ Copied to project root"
else
    echo "  ✗ Connections.csv not found!"
    echo "    Drop it in this folder and run setup.sh again."
    echo ""
    echo "    How to get it:"
    echo "    1. linkedin.com → Settings → Data Privacy → Get a copy of your data"
    echo "    2. Request full archive → wait for email → download zip"
    echo "    3. Find Connections.csv inside the zip"
    exit 1
fi

# Check for API key
echo ""
if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo "  ✓ ANTHROPIC_API_KEY is set"
else
    echo "  ✗ ANTHROPIC_API_KEY not set"
    echo "    Run: export ANTHROPIC_API_KEY=\"sk-ant-...\""
    echo "    Get a key at: console.anthropic.com → API Keys"
    exit 1
fi

echo ""
echo "  ─────────────────────────────────────────"
echo "  ✓ All prerequisites met!"
echo ""
echo "  Next steps:"
echo "    1. cd app && npm run generate && cd ..   (score all connections, ~5 min)"
echo "    2. cd app && npm run dev                 (start frontend — Terminal 1)"
echo "    3. source .venv/bin/activate && python backend.py   (start backend — Terminal 2)"
echo "    4. python enrichment_service.py          (optional — Terminal 3, enables live LinkedIn lookups)"
echo ""
echo "  The 'Ranked List' tab shows pre-scored prospects."
echo "  The 'Ask My Network' tab uses Claude AI to search all your connections intelligently."
echo "  With the enrichment service running, it also fetches LinkedIn profiles for better results."
echo ""
