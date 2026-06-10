#!/usr/bin/env bash
# Start / stop / status helper for the Foundry Sec web UI.
#
# Usage:
#   scripts/foundry-ui.sh start    # launch UI in background
#   scripts/foundry-ui.sh stop     # stop UI (and any in-flight run subprocess)
#   scripts/foundry-ui.sh restart
#   scripts/foundry-ui.sh status
#   scripts/foundry-ui.sh logs     # tail -f the UI log

set -euo pipefail

PORT="${FOUNDRY_UI_PORT:-8088}"
CONFIG="${FOUNDRY_CONFIG:-configs/demo.yaml}"
LOG="${FOUNDRY_UI_LOG:-/tmp/foundry-ui.log}"
DSN="${FOUNDRY_DSN:-postgresql://foundry:foundry@localhost:5432/foundry}"

# Always run from impl/ (parent of scripts/)
cd "$(dirname "$0")/.."

ui_pids() { lsof -ti tcp:"$PORT" 2>/dev/null || true; }
run_pids() { pgrep -f "foundry\.cli run" 2>/dev/null || true; }

start() {
  local pids
  pids="$(ui_pids)"
  if [ -n "$pids" ]; then
    echo "UI already running on :$PORT (pids: $pids)"
    return 0
  fi

  if [ ! -d .venv ]; then
    echo "error: .venv missing — run 'python3 -m venv .venv && pip install -e .[dev]' first" >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate

  export FOUNDRY_DSN="$DSN"
  # MISTRAL_API_KEY (and any SSL_CERT_FILE) inherited from caller's env

  echo "starting UI on :$PORT  (config=$CONFIG)"
  echo "  log:  $LOG"
  echo "  dsn:  $DSN"
  if [ -n "${MISTRAL_API_KEY:-}" ]; then
    echo "  mistral key: set (${#MISTRAL_API_KEY} chars)"
  else
    echo "  mistral key: UNSET (LLM calls will use mock)"
  fi

  nohup foundry ui --config "$CONFIG" --port "$PORT" > "$LOG" 2>&1 &
  disown
  sleep 1
  pids="$(ui_pids)"
  if [ -n "$pids" ]; then
    echo "✓ UI up — http://localhost:$PORT  (pids: $pids)"
  else
    echo "✗ UI failed to bind :$PORT — tail $LOG for details" >&2
    tail -20 "$LOG" >&2 || true
    exit 1
  fi
}

stop() {
  local rpids upids
  rpids="$(run_pids)"
  if [ -n "$rpids" ]; then
    echo "killing in-flight run subprocess(es): $rpids"
    kill -9 $rpids 2>/dev/null || true
  fi
  upids="$(ui_pids)"
  if [ -n "$upids" ]; then
    echo "stopping UI on :$PORT (pids: $upids)"
    kill -9 $upids 2>/dev/null || true
  else
    echo "UI not running on :$PORT"
  fi
  sleep 1
  if [ -n "$(ui_pids)" ]; then
    echo "✗ port :$PORT still bound" >&2
    exit 1
  fi
  echo "✓ stopped"
}

status() {
  local upids rpids
  upids="$(ui_pids)"
  rpids="$(run_pids)"
  if [ -n "$upids" ]; then
    echo "UI:  RUNNING on :$PORT  (pids: $upids)"
    curl -s "http://localhost:$PORT/api/run/status" 2>/dev/null | python3 -m json.tool 2>/dev/null || true
  else
    echo "UI:  stopped"
  fi
  if [ -n "$rpids" ]; then
    echo "run: ACTIVE (pids: $rpids)"
  else
    echo "run: idle"
  fi
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop || true; start ;;
  status)  status ;;
  logs)    tail -f "$LOG" ;;
  *)
    echo "usage: $0 {start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
