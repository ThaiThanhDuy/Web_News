#!/usr/bin/env bash
# Starts the local Ollama server used by the AI pipeline (see
# backend/app/services/llm.py) and shows a live monitor of it.
#
# This script owns Ollama's whole lifecycle: start it, watch it live, and
# stop it. Run it in its own terminal BEFORE start-dev.sh — start-dev.sh no
# longer starts Ollama itself, it just checks this is already running.
# Installing Ollama and pulling the model is setup-ollama.sh's job (run once,
# see README.md) — this script just calls it first so it still works
# standalone even if you skipped that.
#
# Usage:
#   ./start-ollama.sh
#       Starts Ollama, then shows a live monitor of it: every server-log
#       line tagged [LOG]/[WARN]/[ERROR]/[TASK], plus a periodic [SYS] line
#       with CPU/RAM/GPU usage of just the Ollama process (not the whole
#       machine). Press Ctrl+C to stop the monitor AND shut Ollama down.
set -euo pipefail

OLLAMA_HOME="$HOME/.local/ollama"
OLLAMA_BIN="$OLLAMA_HOME/bin/ollama"
export OLLAMA_MODELS="$OLLAMA_HOME/models"
MODEL="${OLLAMA_MODEL:-qwen2.5:14b-instruct}"
LOG_FILE="$OLLAMA_HOME/serve.log"
SYS_INTERVAL="${OLLAMA_SYS_INTERVAL:-5}"

# Match backend's CELERY_CONCURRENCY (start-dev.sh) so requests actually run
# in parallel instead of queueing up inside Ollama itself. 4 was tried and
# measured worse on this 8-core CPU-only machine — 4 concurrent requests
# fighting over the same cores made each one take ~4-5min instead of
# ~1-3min, some breaching the 300s timeout entirely. 2 is what's proven
# stable here.
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-2}"

"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup-ollama.sh"

if curl -s -o /dev/null http://localhost:11434/api/version; then
  echo "Ollama server đã chạy sẵn ở http://localhost:11434"
else
  echo "Đang khởi động Ollama server..."
  nohup "$OLLAMA_BIN" serve > "$LOG_FILE" 2>&1 &
  disown

  for _ in $(seq 1 30); do
    if curl -s -o /dev/null http://localhost:11434/api/version; then
      break
    fi
    sleep 1
  done

  if ! curl -s -o /dev/null http://localhost:11434/api/version; then
    echo "Ollama không khởi động được sau 30s — xem log tại $LOG_FILE"
    exit 1
  fi
  echo "Ollama server đã sẵn sàng."
fi

echo ""
echo "Sẵn sàng — Ollama đang chạy tại http://localhost:11434 với model $MODEL"

# ---------------------------------------------------------------------------
# Live monitor. Ctrl+C stops the monitor AND shuts Ollama down.
# ---------------------------------------------------------------------------

COLOR_LOG="\033[2m"
COLOR_WARN="\033[33m"
COLOR_ERROR="\033[31m"
COLOR_TASK="\033[32m"
COLOR_SYS="\033[36m"
COLOR_RESET="\033[0m"
if [ ! -t 1 ]; then
  COLOR_LOG=""; COLOR_WARN=""; COLOR_ERROR=""; COLOR_TASK=""; COLOR_SYS=""; COLOR_RESET=""
fi

HAS_NVIDIA=0
if command -v nvidia-smi >/dev/null 2>&1; then
  HAS_NVIDIA=1
fi

print_sys_line() {
  local ts pids cpu mem rss_kb rss_mb gpu_str
  ts="$(date '+%H:%M:%S')"
  pids="$(pgrep -f "$OLLAMA_HOME" 2>/dev/null | paste -sd, - || true)"
  if [ -z "$pids" ]; then
    echo -e "${COLOR_SYS}[$ts] [SYS]   Không tìm thấy tiến trình Ollama nào đang chạy.${COLOR_RESET}"
    return
  fi
  read -r cpu mem rss_kb < <(ps -o %cpu=,%mem=,rss= -p "$pids" 2>/dev/null | awk '{c+=$1; m+=$2; r+=$3} END {printf "%.1f %.1f %d\n", c, m, r}')
  rss_mb=$(( rss_kb / 1024 ))
  gpu_str="GPU: CPU-only (không phát hiện GPU NVIDIA)"
  if [ "$HAS_NVIDIA" = "1" ]; then
    gpu_str="GPU: $(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null | head -1)"
  fi
  echo -e "${COLOR_SYS}[$ts] [SYS]   CPU ${cpu}% | RAM ${rss_mb} MB (${mem}% hệ thống) | ${gpu_str}${COLOR_RESET}"
}

echo ""
echo "======================================================================"
echo " Giám sát Ollama trực tiếp — Ctrl+C để dừng giám sát VÀ dừng Ollama"
echo " [LOG] log nội bộ  [TASK] yêu cầu API  [WARN] cảnh báo  [ERROR] lỗi"
echo " [SYS] CPU/RAM/GPU của riêng tiến trình Ollama, mỗi ${SYS_INTERVAL}s"
echo "======================================================================"

# Both the [SYS] ticker and the log-tail classifier run in the background;
# the main script just blocks on `wait`. This matters because `tail -F`
# never exits on its own, and bash defers running a trap until whatever's
# in the foreground finishes — so if that pipeline were in the foreground,
# Ctrl+C would never actually reach the trap. `wait` (the builtin, no args)
# is interrupted immediately by a trapped signal, unlike waiting on a
# foreground external command. Same pattern start-dev.sh already uses.
( while true; do sleep "$SYS_INTERVAL"; print_sys_line; done ) &
TICKER_PID=$!

tail -n 0 -F "$LOG_FILE" 2>/dev/null | while IFS= read -r line; do
  ts="$(date '+%H:%M:%S')"
  if [[ "$line" == *level=ERROR* ]]; then
    echo -e "${COLOR_ERROR}[$ts] [ERROR] $line${COLOR_RESET}"
  elif [[ "$line" == *"[GIN]"* ]] && ! [[ "$line" =~ \|[[:space:]]*2[0-9][0-9][[:space:]]*\| ]]; then
    echo -e "${COLOR_ERROR}[$ts] [ERROR] $line${COLOR_RESET}"
  elif [[ "$line" == *level=WARN* ]]; then
    echo -e "${COLOR_WARN}[$ts] [WARN]  $line${COLOR_RESET}"
  elif [[ "$line" == *"[GIN]"* ]]; then
    echo -e "${COLOR_TASK}[$ts] [TASK]  $line${COLOR_RESET}"
  else
    echo -e "${COLOR_LOG}[$ts] [LOG]   $line${COLOR_RESET}"
  fi
done &
TAIL_JOB_PID=$!

cleanup_monitor() {
  echo ""
  echo "Đang dừng giám sát và Ollama server..."
  kill "$TICKER_PID" "$TAIL_JOB_PID" 2>/dev/null || true
  pkill -f "tail -n 0 -F $LOG_FILE" 2>/dev/null || true
  # Matches both `ollama serve` and any model-runner subprocess it spawned
  # from the same binary path.
  pkill -f "$OLLAMA_BIN" 2>/dev/null || true
  sleep 1
  pkill -9 -f "$OLLAMA_BIN" 2>/dev/null || true
  echo "Đã dừng Ollama."
  exit 0
}
trap cleanup_monitor INT TERM

wait
