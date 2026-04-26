#!/usr/bin/env bash
set -e

echo "=== RadChecker — Oncology MU Evaluator ==="

# Copy .env if not present
if [ ! -f backend/.env ] && [ -f .env ]; then
  cp .env backend/.env
fi

# Install Python dependencies
echo "[1/2] Installing dependencies..."
pip install -r requirements.txt -q

# Start FastAPI backend (serves both API and frontend static files)
echo "[2/2] Starting server..."
echo ""
echo "  App:  http://localhost:8000"
echo "  API:  http://localhost:8000/docs"
echo "  Tip:  Click 'Load Sample Data' on the Dashboard to get started."
echo ""

cd backend
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
