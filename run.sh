#!/bin/bash
# ==============================================================================
# Open Nepali Image Platform — Startup Script
# ==============================================================================

set -e

PROJECT_DIR="/Users/paramanada/Desktop/open_nepali_image"
cd "$PROJECT_DIR"

echo "🇳🇵 Initializing Open Nepali Image Platform..."

# 1. Check & start PostgreSQL 16
if ! /opt/homebrew/opt/postgresql@16/bin/pg_isready -q 2>/dev/null; then
    echo "⚙️ Starting PostgreSQL 16 (low-memory tuned)..."
    /opt/homebrew/opt/postgresql@16/bin/pg_ctl -D /opt/homebrew/var/postgresql@16 -l /opt/homebrew/var/postgresql@16/server.log start
fi

# Ensure database exists
/opt/homebrew/opt/postgresql@16/bin/createdb open_nepali_image 2>/dev/null || true

# 2. Check virtualenv
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Error: Virtual environment not found at $VENV_PYTHON"
    exit 1
fi

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "127.0.0.1")
echo "🚀 Starting FastAPI server on 0.0.0.0:8000..."
echo "💻 Computer URL: http://localhost:8000"
echo "📱 Phone / Router URL: http://$LAN_IP:8000"
echo "🤖 MCP Server command for OpenCode: $VENV_PYTHON -m app.mcp.server"
echo "Press Ctrl+C to stop."

exec "$VENV_PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
