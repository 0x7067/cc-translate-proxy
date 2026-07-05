#!/usr/bin/env bash
# One-command reverse mode: you use English, Claude sees Simplified Chinese.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${CC_I18N_USER_LANG:=en}"
: "${CC_I18N_CLAUDE_LANG:=zh-Hans}"
: "${CC_I18N_REWRITE_TUI:=1}"
: "${CC_I18N_AUTO_TRANSLATE:=1}"
: "${CC_I18N_PROXY_PORT:=8080}"
: "${CC_I18N_RENDER_PORT:=9090}"
: "${ENABLE_TOOL_SEARCH:=auto}"
: "${ANTHROPIC_BASE_URL:=http://localhost:${CC_I18N_PROXY_PORT}}"

export CC_I18N_USER_LANG
export CC_I18N_CLAUDE_LANG
export CC_I18N_REWRITE_TUI
export CC_I18N_AUTO_TRANSLATE
export CC_I18N_PROXY_PORT
export CC_I18N_RENDER_PORT
export ENABLE_TOOL_SEARCH
export ANTHROPIC_BASE_URL

PROXY_HOME="${CC_I18N_PROXY_HOME:-$HOME/.cc-i18n-proxy}"
LOG_DIR="$PROXY_HOME/logs"
mkdir -p "$LOG_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it first: https://github.com/astral-sh/uv"
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "claude is required and was not found on PATH."
  exit 1
fi

port_open() {
  local port="$1"
  (exec 3<>"/dev/tcp/127.0.0.1/${port}") >/dev/null 2>&1
}

for port in "$CC_I18N_PROXY_PORT" "$CC_I18N_RENDER_PORT"; do
  if port_open "$port"; then
    echo "Port $port is already in use. Stop the existing process or set a different port."
    exit 1
  fi
done

PIDS=()

cleanup() {
  for pid in "${PIDS[@]}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  wait "${PIDS[@]}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

start_bg() {
  local name="$1"
  shift
  local log_file="$LOG_DIR/${name}.log"
  "$@" >"$log_file" 2>&1 &
  local pid="$!"
  PIDS+=("$pid")
  sleep 1
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "$name failed to start. Last log lines:"
    tail -40 "$log_file" || true
    exit 1
  fi
  echo "$name log: $log_file"
}

echo "Starting cc-translate-proxy reverse mode..."
uv sync --quiet
start_bg proxy uv run python -m cc_i18n_proxy
start_bg render uv run python scripts/render_server.py

cat <<EOF

Reverse mode is active.
- You type/read English in Claude Code.
- Claude-facing user and assistant history text is Simplified Chinese.
- Translation is enabled automatically; no /intl command is needed.

EOF

set +e
claude "$@"
status="$?"
set -e
exit "$status"
