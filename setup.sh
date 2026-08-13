#!/usr/bin/env bash
# One-time project setup: backend Python deps (venv + pip), frontend npm
# deps, .env files, and the local Ollama AI model. Run this once after
# cloning, before ever using start-dev.sh. Safe to re-run any time — every
# step is skipped if already done.
#
# Still needed after this, separately (not handled here — see README.md):
#   - Postgres (with the pgvector extension) and Redis running and reachable
#   - backend/.env / frontend/.env.local filled in with real values if the
#     copied defaults below aren't already correct for your machine
#   - `python scripts/init_db.py` (from backend/, venv active) to create
#     the database schema, once Postgres is up
#
# Usage: ./setup.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "======================================================================"
echo " 1/3 — Backend (Python)"
echo "======================================================================"
cd "$BACKEND_DIR"

if [ ! -d venv ]; then
  echo "Tạo venv..."
  python3 -m venv venv
else
  echo "venv đã có sẵn."
fi

source venv/bin/activate
echo "Cài thư viện Python (pip install -r requirements.txt)..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate
echo "Xong thư viện backend."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Đã tạo backend/.env từ .env.example — kiểm tra lại giá trị nếu cần."
else
  echo "backend/.env đã có sẵn."
fi

echo ""
echo "======================================================================"
echo " 2/3 — Frontend (Node)"
echo "======================================================================"
cd "$FRONTEND_DIR"

echo "Cài thư viện Node (npm install)..."
npm install --silent
echo "Xong thư viện frontend."

if [ ! -f .env.local ]; then
  cp .env.local.example .env.local
  echo "Đã tạo frontend/.env.local từ .env.local.example."
else
  echo "frontend/.env.local đã có sẵn."
fi

echo ""
echo "======================================================================"
echo " 3/3 — Ollama (AI local)"
echo "======================================================================"
"$ROOT_DIR/setup-ollama.sh"

echo ""
echo "======================================================================"
echo " Xong setup."
echo "======================================================================"
echo "Còn lại trước khi chạy ./start-dev.sh:"
echo "  - Đảm bảo Postgres (có pgvector) và Redis đang chạy"
echo "  - Kiểm tra backend/.env và frontend/.env.local đúng với máy bạn"
echo "  - Chạy 'python scripts/init_db.py' trong backend/ (venv active) nếu là lần đầu"
echo "  - Chạy ./start-ollama.sh ở terminal riêng, rồi ./start-dev.sh"
