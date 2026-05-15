#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${BP_RENDER_FIXTURE_PORT:-8765}"
HOST="${BP_RENDER_FIXTURE_HOST:-127.0.0.1}"
PID_FILE="$ROOT_DIR/scripts/.render_fixture_server.pid"
LOG_FILE="$ROOT_DIR/scripts/.render_fixture_server.log"
FIXTURE_URL="http://$HOST:$PORT/BetterParameters/palette.html?mock=1&layoutdebug=1&fixture=render-large"

usage() {
  cat <<EOF
Usage: $(basename "$0") <start|stop|restart|status|url>

Env overrides:
  BP_RENDER_FIXTURE_HOST   default: 127.0.0.1
  BP_RENDER_FIXTURE_PORT   default: 8765
EOF
}

pid_is_running() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null
}

pid_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null || true
}

is_expected_server_pid() {
  local pid="$1"
  local cmd
  cmd="$(pid_command "$pid")"
  [[ -n "$cmd" && "$cmd" == *"python"* && "$cmd" == *"http.server"* && "$cmd" == *"$PORT"* ]]
}

port_listener_pid() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN -nP 2>/dev/null | head -n 1 || true
}

tracked_pid() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if [[ -n "$pid" ]] && pid_is_running "$pid" && is_expected_server_pid "$pid"; then
      printf '%s\n' "$pid"
      return 0
    fi
    rm -f "$PID_FILE"
  fi

  local detected
  detected="$(port_listener_pid)"
  if [[ -n "$detected" ]] && is_expected_server_pid "$detected"; then
    printf '%s\n' "$detected" > "$PID_FILE"
    printf '%s\n' "$detected"
    return 0
  fi

  return 1
}

wait_until_ready() {
  local attempts=30
  local i
  for ((i=0; i<attempts; i+=1)); do
    if curl -fsS "http://$HOST:$PORT/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

start_server() {
  if pid="$(tracked_pid)"; then
    echo "Already running on http://$HOST:$PORT (pid $pid)"
    echo "$FIXTURE_URL"
    return 0
  fi

  local port_pid
  port_pid="$(port_listener_pid)"
  if [[ -n "$port_pid" ]]; then
    echo "Port $PORT already in use by pid $port_pid; refusing to start."
    echo "Command: $(pid_command "$port_pid")"
    exit 1
  fi

  (
    cd "$ROOT_DIR"
    python3 -m http.server "$PORT" --bind "$HOST" >"$LOG_FILE" 2>&1
  ) &
  local pid="$!"
  printf '%s\n' "$pid" > "$PID_FILE"

  if ! wait_until_ready; then
    echo "Server did not become ready. See $LOG_FILE"
    exit 1
  fi

  echo "Started render fixture server on http://$HOST:$PORT (pid $pid)"
  echo "$FIXTURE_URL"
}

stop_server() {
  local pid
  if ! pid="$(tracked_pid)"; then
    echo "Not running."
    return 0
  fi

  kill "$pid"
  local i
  for ((i=0; i<25; i+=1)); do
    if ! pid_is_running "$pid"; then
      rm -f "$PID_FILE"
      echo "Stopped render fixture server (pid $pid)"
      return 0
    fi
    sleep 0.2
  done

  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "Force-stopped render fixture server (pid $pid)"
}

status_server() {
  local pid
  if pid="$(tracked_pid)"; then
    echo "Running on http://$HOST:$PORT (pid $pid)"
    echo "$FIXTURE_URL"
    return 0
  fi
  echo "Not running."
}

case "${1:-}" in
  start)
    start_server
    ;;
  stop)
    stop_server
    ;;
  restart)
    stop_server
    start_server
    ;;
  status)
    status_server
    ;;
  url)
    echo "$FIXTURE_URL"
    ;;
  *)
    usage
    exit 1
    ;;
esac
