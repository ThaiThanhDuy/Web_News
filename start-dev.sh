#!/usr/bin/env bash
# Runs the whole stack natively (no Docker): FastAPI, the job-pool worker (python -m app.worker,
# which also runs the scheduler), and the Next.js dev server.
#
# Before starting anything, this kills any leftover instance of these same processes (from a
# previous run of this script, a manually-started server, or a crashed shell). Running two copies
# of `next dev` against the same frontend/.next directory — or two uvicorn/celery processes fighting
# over the same port — is exactly what has caused this project's "site is broken" incidents before,
# so every run now starts from a guaranteed-clean slate.
#
# Prerequisites (see README.md for full setup):
#   - Postgres (with the pgvector extension) and Redis already running
#   - backend/venv created and `pip install -r requirements.txt` already run
#   - backend/.env configured (migrations are applied automatically below)
#   - frontend/.env.local configured and `npm install` already run in frontend/
#   - AI provider (LLM_PROVIDER in backend/.env):
#       groq   — GROQ_API_KEY set in backend/.env (default)
#       ollama — run ./start-ollama.sh in a separate terminal FIRST and leave
#                it running there — this script only checks it's up
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

stop_previous_instances() {
  echo "Stopping any previous instances of this project's services..."

  pkill -f "uvicorn app\.main:app" 2>/dev/null || true
  pkill -f "celery -A app\.worker\.celery_app" 2>/dev/null || true  # pre-job-pool versions
  pkill -INT -f "python -m app\.worker" 2>/dev/null || true
  pkill -f "next-server" 2>/dev/null || true
  pkill -f "next dev" 2>/dev/null || true

  # Give them a moment to shut down gracefully, then force-kill any stragglers
  # (celery's worker pool in particular can be slow to exit).
  sleep 2
  pkill -9 -f "uvicorn app\.main:app" 2>/dev/null || true
  pkill -9 -f "celery -A app\.worker\.celery_app" 2>/dev/null || true
  pkill -9 -f "python -m app\.worker" 2>/dev/null || true
  pkill -9 -f "next-server" 2>/dev/null || true
  pkill -9 -f "next dev" 2>/dev/null || true

  # Belt-and-suspenders: whatever is still squatting on our ports, regardless
  # of how it was started.
  fuser -k 8000/tcp 2>/dev/null || true
  fuser -k 3000/tcp 2>/dev/null || true

  sleep 1
  echo "Clean slate."
}

stop_previous_instances

env_value() {
  grep -E "^$1=" "$BACKEND_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs
}
LLM_PROVIDER="$(env_value LLM_PROVIDER)"
LLM_PROVIDER="${LLM_PROVIDER:-groq}"

if [ "$LLM_PROVIDER" = "ollama" ]; then
  # start-ollama.sh owns Ollama's whole lifecycle (start, live monitor, stop
  # on Ctrl+C) in its own terminal; this only checks it's actually up.
  if ! curl -s -o /dev/null http://localhost:11434/api/version; then
    echo "Ollama chưa chạy. Mở một terminal khác, chạy ./start-ollama.sh, rồi chạy lại script này." >&2
    exit 1
  fi
  echo "AI: Ollama (local) đã sẵn sàng."
else
  if [ -z "$(env_value GROQ_API_KEY)" ]; then
    echo "LLM_PROVIDER=groq nhưng chưa có GROQ_API_KEY trong backend/.env (lấy key tại https://console.groq.com/keys)." >&2
    exit 1
  fi
  echo "AI: Groq API (phân loại: $(env_value CLASSIFY_MODEL), tóm tắt: $(env_value SUMMARIZE_MODEL))."
fi

PIDS=()
cleanup() {
  echo ""
  echo "Stopping all services..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

cd "$BACKEND_DIR"
source venv/bin/activate

echo "Applying database migrations..."
python scripts/init_db.py

echo "Starting FastAPI on http://localhost:8000 ..."
uvicorn app.main:app --reload --port 8000 &
PIDS+=($!)

echo "Starting job-pool worker + scheduler (queues: ${WORKER_QUEUES:-from backend/.env or defaults})..."
python -m app.worker &
PIDS+=($!)

cd "$FRONTEND_DIR"
echo "Starting Next.js dev server on http://localhost:3000 ..."
npm run dev &
PIDS+=($!)

echo ""
echo "All services started. Press Ctrl+C to stop everything."
wait
