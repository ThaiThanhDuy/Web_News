#!/usr/bin/env bash
# Runs the whole stack natively (no Docker): FastAPI, Celery worker, Celery beat, Next.js dev server.
#
# Before starting anything, this kills any leftover instance of these same 4 processes (from a
# previous run of this script, a manually-started server, or a crashed shell). Running two copies
# of `next dev` against the same frontend/.next directory — or two uvicorn/celery processes fighting
# over the same port — is exactly what has caused this project's "site is broken" incidents before,
# so every run now starts from a guaranteed-clean slate.
#
# Prerequisites (see README.md for full setup):
#   - Postgres (with the pgvector extension) and Redis already running
#   - backend/venv created and `pip install -r requirements.txt` already run
#   - backend/.env configured, and `python scripts/init_db.py` already run once
#   - frontend/.env.local configured and `npm install` already run in frontend/
#   - Ollama: run ./start-ollama.sh in a separate terminal FIRST and leave it
#     running there — this script only checks it's up, it doesn't start it
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

stop_previous_instances() {
  echo "Stopping any previous instances of this project's services..."

  pkill -f "uvicorn app\.main:app" 2>/dev/null || true
  pkill -f "celery -A app\.worker\.celery_app" 2>/dev/null || true
  pkill -f "next-server" 2>/dev/null || true
  pkill -f "next dev" 2>/dev/null || true

  # Give them a moment to shut down gracefully, then force-kill any stragglers
  # (celery's worker pool in particular can be slow to exit).
  sleep 2
  pkill -9 -f "uvicorn app\.main:app" 2>/dev/null || true
  pkill -9 -f "celery -A app\.worker\.celery_app" 2>/dev/null || true
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

# Ollama is no longer managed by this script — start-ollama.sh owns its
# whole lifecycle (start, live [LOG]/[SYS]/... monitor, and stop on
# Ctrl+C), and is meant to be left running in its own terminal. This just
# checks it's actually up rather than starting it, since starting it here
# too would fight over who gets to stop it.
if ! curl -s -o /dev/null http://localhost:11434/api/version; then
  echo "Ollama chưa chạy. Mở một terminal khác, chạy ./start-ollama.sh, rồi chạy lại script này." >&2
  exit 1
fi
echo "Ollama đã sẵn sàng."

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

echo "Starting FastAPI on http://localhost:8000 ..."
uvicorn app.main:app --reload --port 8000 &
PIDS+=($!)

# On CPU-only inference, each in-flight request already wants several
# cores for itself — pushing this to 4 was tried and measured worse: each
# article went from ~1-3min to ~4-5min (some even breaching the 300s
# timeout and retrying) because 4 requests were fighting over the same 8
# cores instead of adding real throughput. 2 is the empirically-good value
# for this machine; matched by OLLAMA_NUM_PARALLEL in start-ollama.sh.
# Raise both together only if you have a strong GPU behind Ollama.
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-2}"

echo "Starting Celery worker (concurrency=$CELERY_CONCURRENCY)..."
celery -A app.worker.celery_app worker --loglevel=info --concurrency="$CELERY_CONCURRENCY" &
PIDS+=($!)

echo "Starting Celery beat (scrape every ${SCRAPE_INTERVAL_SECONDS:-180}s)..."
celery -A app.worker.celery_app beat --loglevel=info &
PIDS+=($!)

cd "$FRONTEND_DIR"
echo "Starting Next.js dev server on http://localhost:3000 ..."
npm run dev &
PIDS+=($!)

echo ""
echo "All services started. Press Ctrl+C to stop everything."
wait
