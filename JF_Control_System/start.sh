#!/bin/bash
# Start JF_Control_System with conda environment slsdet9
# Usage: bash start.sh

set -e

# Clear inherited venv (Agent is launched via `uv run`, which sets VIRTUAL_ENV)
unset VIRTUAL_ENV

# Locate and source conda
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
    source "/opt/conda/etc/profile.d/conda.sh"
else
    echo "ERROR: Cannot find conda.sh" >&2
    exit 1
fi

conda activate slsdet9

ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "=== JF_Control_System Starting ==="

# Backend (use explicit conda Python to avoid inherited venv)
"$CONDA_PREFIX/bin/python" "$ROOT/run.py" &
BACKEND_PID=$!
echo "[backend:$BACKEND_PID] Started uvicorn on :8000"

# Frontend
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!
echo "[frontend:$FRONTEND_PID] Started Vite on :5173"

echo "=== Ready ==="
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"

cleanup() {
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    wait
    echo "Stopped."
}
trap cleanup EXIT INT TERM

wait
