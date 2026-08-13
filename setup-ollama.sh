#!/usr/bin/env bash
# One-time setup for the local AI pipeline: installs Ollama (portable,
# user-space, no root needed) and pulls the model used by
# backend/app/services/llm.py. Every step is a no-op if already done, so
# it's safe to re-run any time (e.g. after changing OLLAMA_MODEL).
#
# Run this once when setting up the project, alongside `pip install -r
# requirements.txt` / `npm install` (see README.md). Day-to-day, use
# start-ollama.sh instead — it starts the server and shows a live monitor.
#
# Usage: ./setup-ollama.sh
set -euo pipefail

OLLAMA_HOME="$HOME/.local/ollama"
OLLAMA_BIN="$OLLAMA_HOME/bin/ollama"
export OLLAMA_MODELS="$OLLAMA_HOME/models"
MODEL="${OLLAMA_MODEL:-qwen2.5:14b-instruct}"

if [ ! -x "$OLLAMA_BIN" ]; then
  echo "Ollama chưa được cài — tải bản portable (không cần quyền root)..."
  mkdir -p "$OLLAMA_HOME"
  TMP_ARCHIVE="$(mktemp)"
  curl -fsSL -o "$TMP_ARCHIVE" "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst"
  tar --zstd -xf "$TMP_ARCHIVE" -C "$OLLAMA_HOME"
  rm -f "$TMP_ARCHIVE"
  echo "Đã cài Ollama vào $OLLAMA_HOME"
else
  echo "Ollama đã được cài tại $OLLAMA_HOME"
fi

if "$OLLAMA_BIN" list | tail -n +2 | awk '{print $1}' | grep -qx "$MODEL" 2>/dev/null; then
  echo "Model $MODEL đã có sẵn."
  exit 0
fi

# Pulling a model needs a running server. If nothing's up yet, start one
# just for this and stop it again afterward — leaving a server running
# long-term is start-ollama.sh's job, not this script's.
STARTED_TEMP_SERVER=0
if ! curl -s -o /dev/null http://localhost:11434/api/version; then
  echo "Khởi động tạm Ollama server để tải model..."
  nohup "$OLLAMA_BIN" serve > "$OLLAMA_HOME/setup.log" 2>&1 &
  TEMP_SERVER_PID=$!
  disown
  STARTED_TEMP_SERVER=1

  for _ in $(seq 1 30); do
    if curl -s -o /dev/null http://localhost:11434/api/version; then
      break
    fi
    sleep 1
  done
  if ! curl -s -o /dev/null http://localhost:11434/api/version; then
    echo "Ollama không khởi động được sau 30s — xem log tại $OLLAMA_HOME/setup.log"
    exit 1
  fi
fi

echo "Đang tải model $MODEL (lần đầu có thể mất vài phút, ~4-5GB)..."
"$OLLAMA_BIN" pull "$MODEL"

if [ "$STARTED_TEMP_SERVER" = "1" ]; then
  kill "$TEMP_SERVER_PID" 2>/dev/null || true
fi

echo ""
echo "Setup xong. Chạy ./start-ollama.sh để khởi động và theo dõi Ollama."
