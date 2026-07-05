#!/usr/bin/env bash
# Manage cc-translate-proxy as macOS user LaunchAgents.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND="${1:-status}"

LABEL_PREFIX="${CC_I18N_LAUNCHD_LABEL_PREFIX:-local.cc-translate-proxy}"
PROXY_LABEL="${LABEL_PREFIX}.proxy"
RENDER_LABEL="${LABEL_PREFIX}.render"
DOMAIN="gui/$(id -u)"

LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PROXY_PLIST="${LAUNCH_AGENTS_DIR}/${PROXY_LABEL}.plist"
RENDER_PLIST="${LAUNCH_AGENTS_DIR}/${RENDER_LABEL}.plist"

PROXY_HOME="${CC_I18N_PROXY_HOME:-${HOME}/.cc-i18n-proxy}"
LOG_DIR="${CC_I18N_LOG_DIR:-${PROXY_HOME}/logs}"

CC_I18N_USER_LANG="${CC_I18N_USER_LANG:-en}"
CC_I18N_CLAUDE_LANG="${CC_I18N_CLAUDE_LANG:-zh-Hans}"
CC_I18N_REWRITE_TUI="${CC_I18N_REWRITE_TUI:-1}"
CC_I18N_AUTO_TRANSLATE="${CC_I18N_AUTO_TRANSLATE:-1}"
CC_I18N_PROXY_PORT="${CC_I18N_PROXY_PORT:-8080}"
CC_I18N_RENDER_PORT="${CC_I18N_RENDER_PORT:-9090}"
CC_I18N_PROXY_HOME="${CC_I18N_PROXY_HOME:-${PROXY_HOME}}"

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  start        Install or refresh the proxy launchd job
  start-render Install or refresh the optional render launchd job
  start-all    Install or refresh both proxy and render launchd jobs
  stop         Stop proxy and render launchd jobs without deleting plist files
  stop-render  Stop only the optional render launchd job
  restart      Stop, refresh, and start the proxy launchd job
  status      Show launchd and port status
  logs        Tail proxy and render logs
  print-env   Print the Claude Code shell export
  uninstall   Stop jobs and delete their plist files

Environment overrides:
  CC_I18N_USER_LANG=$CC_I18N_USER_LANG
  CC_I18N_CLAUDE_LANG=$CC_I18N_CLAUDE_LANG
  CC_I18N_REWRITE_TUI=$CC_I18N_REWRITE_TUI
  CC_I18N_AUTO_TRANSLATE=$CC_I18N_AUTO_TRANSLATE
  CC_I18N_PROXY_PORT=$CC_I18N_PROXY_PORT
  CC_I18N_RENDER_PORT=$CC_I18N_RENDER_PORT
  CC_I18N_PROXY_HOME=$CC_I18N_PROXY_HOME
EOF
}

require_macos_launchd() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "launchd background mode is only supported on macOS." >&2
    exit 1
  fi
  if ! command -v launchctl >/dev/null 2>&1; then
    echo "launchctl is required but was not found." >&2
    exit 1
  fi
}

require_uv() {
  if ! UV_BIN="$(command -v uv)"; then
    echo "uv is required. Install it first: https://github.com/astral-sh/uv" >&2
    exit 1
  fi
  export UV_BIN
}

port_open() {
  local port="$1"
  (exec 3<>"/dev/tcp/127.0.0.1/${port}") >/dev/null 2>&1
}

wait_for_port() {
  local port="$1"
  local name="$2"
  for _ in {1..20}; do
    if port_open "$port"; then
      return 0
    fi
    sleep 0.5
  done
  echo "$name did not open port $port. Last log lines:" >&2
  tail -40 "$LOG_DIR/${name}.log" >&2 || true
  return 1
}

service_loaded() {
  local label="$1"
  launchctl print "${DOMAIN}/${label}" >/dev/null 2>&1
}

stop_label() {
  local label="$1"
  launchctl bootout "$DOMAIN" "${LAUNCH_AGENTS_DIR}/${label}.plist" >/dev/null 2>&1 || true
}

write_plist() {
  local label="$1"
  local python_args="$2"
  local log_file="$3"
  local plist_path="$4"

  SERVICE_LABEL="$label" \
  SERVICE_PYTHON_ARGS="$python_args" \
  SERVICE_LOG_FILE="$log_file" \
  SERVICE_PLIST_PATH="$plist_path" \
  "$UV_BIN" run python - <<'PY'
import os
import plistlib

env = {
    "CC_I18N_ROOT": os.environ["ROOT"],
    "UV_BIN": os.environ["UV_BIN"],
    "PATH": os.environ["PATH"],
    "CC_I18N_PROXY_HOME": os.environ["CC_I18N_PROXY_HOME"],
    "CC_I18N_USER_LANG": os.environ["CC_I18N_USER_LANG"],
    "CC_I18N_CLAUDE_LANG": os.environ["CC_I18N_CLAUDE_LANG"],
    "CC_I18N_REWRITE_TUI": os.environ["CC_I18N_REWRITE_TUI"],
    "CC_I18N_AUTO_TRANSLATE": os.environ["CC_I18N_AUTO_TRANSLATE"],
    "CC_I18N_PROXY_PORT": os.environ["CC_I18N_PROXY_PORT"],
    "CC_I18N_RENDER_PORT": os.environ["CC_I18N_RENDER_PORT"],
}

python_args = os.environ["SERVICE_PYTHON_ARGS"]
command = 'cd "$CC_I18N_ROOT" && exec "$UV_BIN" run python ' + python_args

plist = {
    "Label": os.environ["SERVICE_LABEL"],
    "WorkingDirectory": os.environ["ROOT"],
    "ProgramArguments": ["/bin/bash", "-lc", command],
    "EnvironmentVariables": env,
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": os.environ["SERVICE_LOG_FILE"],
    "StandardErrorPath": os.environ["SERVICE_LOG_FILE"],
}

with open(os.environ["SERVICE_PLIST_PATH"], "wb") as f:
    plistlib.dump(plist, f, sort_keys=False)
PY
}

prepare_launchd() {
  require_macos_launchd
  require_uv
  export ROOT
  export CC_I18N_PROXY_HOME CC_I18N_USER_LANG CC_I18N_CLAUDE_LANG
  export CC_I18N_REWRITE_TUI CC_I18N_AUTO_TRANSLATE
  export CC_I18N_PROXY_PORT CC_I18N_RENDER_PORT

  mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"

  cd "$ROOT"
  "$UV_BIN" sync --quiet
}

start_proxy() {
  prepare_launchd
  write_plist "$PROXY_LABEL" "-m cc_i18n_proxy" "$LOG_DIR/proxy.log" "$PROXY_PLIST"

  stop_label "$PROXY_LABEL"
  # Keep the default workflow proxy-only, even if an older install started render.
  stop_label "$RENDER_LABEL"
  sleep 1

  if port_open "$CC_I18N_PROXY_PORT"; then
    echo "Port $CC_I18N_PROXY_PORT is already in use by another process." >&2
    exit 1
  fi

  launchctl bootstrap "$DOMAIN" "$PROXY_PLIST"
  launchctl kickstart -k "${DOMAIN}/${PROXY_LABEL}"
  wait_for_port "$CC_I18N_PROXY_PORT" proxy

  echo "Started ${PROXY_LABEL} on http://localhost:${CC_I18N_PROXY_PORT}"
  echo "Logs: ${LOG_DIR}/proxy.log"
  echo
  print_env
}

start_render() {
  prepare_launchd
  write_plist "$RENDER_LABEL" "scripts/render_server.py" "$LOG_DIR/render.log" "$RENDER_PLIST"

  stop_label "$RENDER_LABEL"
  sleep 1

  if port_open "$CC_I18N_RENDER_PORT"; then
    echo "Port $CC_I18N_RENDER_PORT is already in use by another process." >&2
    exit 1
  fi

  launchctl bootstrap "$DOMAIN" "$RENDER_PLIST"
  launchctl kickstart -k "${DOMAIN}/${RENDER_LABEL}"
  wait_for_port "$CC_I18N_RENDER_PORT" render

  echo "Started ${RENDER_LABEL} on http://localhost:${CC_I18N_RENDER_PORT}"
  echo "Logs: ${LOG_DIR}/render.log"
}

start_all() {
  start_proxy
  start_render
}

stop_services() {
  require_macos_launchd
  stop_label "$PROXY_LABEL"
  stop_label "$RENDER_LABEL"
  echo "Stopped ${PROXY_LABEL} and ${RENDER_LABEL}."
}

stop_render() {
  require_macos_launchd
  stop_label "$RENDER_LABEL"
  echo "Stopped ${RENDER_LABEL}."
}

status_services() {
  require_macos_launchd
  for label in "$PROXY_LABEL" "$RENDER_LABEL"; do
    if service_loaded "$label"; then
      echo "$label: loaded"
    else
      echo "$label: not loaded"
    fi
  done

  if port_open "$CC_I18N_PROXY_PORT"; then
    echo "proxy port ${CC_I18N_PROXY_PORT}: open"
  else
    echo "proxy port ${CC_I18N_PROXY_PORT}: closed"
  fi

  if port_open "$CC_I18N_RENDER_PORT"; then
    echo "render port ${CC_I18N_RENDER_PORT}: open"
  else
    echo "render port ${CC_I18N_RENDER_PORT}: closed"
  fi
}

tail_logs() {
  mkdir -p "$LOG_DIR"
  touch "$LOG_DIR/proxy.log" "$LOG_DIR/render.log"
  tail -f "$LOG_DIR/proxy.log" "$LOG_DIR/render.log"
}

print_env() {
  cat <<EOF
In new Claude Code shells, run:
export ANTHROPIC_BASE_URL=http://localhost:${CC_I18N_PROXY_PORT}
EOF
}

uninstall_services() {
  stop_services
  rm -f "$PROXY_PLIST" "$RENDER_PLIST"
  echo "Deleted $PROXY_PLIST"
  echo "Deleted $RENDER_PLIST"
}

case "$COMMAND" in
  start)
    start_proxy
    ;;
  start-render)
    start_render
    ;;
  start-all)
    start_all
    ;;
  stop)
    stop_services
    ;;
  stop-render)
    stop_render
    ;;
  restart)
    stop_services
    start_proxy
    ;;
  status)
    status_services
    ;;
  logs)
    tail_logs
    ;;
  print-env)
    print_env
    ;;
  uninstall)
    uninstall_services
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
