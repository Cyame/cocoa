#!/usr/bin/env bash
# Eyot local dev launcher.
# Starts the FastAPI backend (:4510) and the Vite portal (:5173) in the
# background, prefixed logs in logs/backend.log and logs/portal.log,
# and tears both down on Ctrl+C.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/cocoa-backend"
PORTAL_DIR="$SCRIPT_DIR/cocoa-portal"
LOG_DIR="$SCRIPT_DIR/logs"

BACKEND_PORT=4510
PORTAL_PORT=5173

BLUE=$'\033[0;34m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
RED=$'\033[0;31m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
DIM=$'\033[2m'
RESET=$'\033[0m'

PIDS=()
FRESH=false

usage() {
  cat <<EOF
用法: ./dev.sh [--fresh] [--help]

选项:
  --fresh    强制清理 .venv 与 node_modules 后重装依赖
  --help     显示本帮助

服务端口:
  backend  http://localhost:${BACKEND_PORT}
  portal   http://localhost:${PORTAL_PORT}

日志:
  logs/backend.log
  logs/portal.log
EOF
  exit 0
}

log()  { echo "${CYAN}[dev]${RESET} $*"; }
err()  { echo "${RED}[dev] ERROR:${RESET} $*" >&2; }
warn() { echo "${YELLOW}[dev] WARN:${RESET} $*"; }

# ── 参数解析 ──────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --fresh) FRESH=true ;;
    --help|-h) usage ;;
    *) err "未知参数: $arg"; usage ;;
  esac
done

# ── 清理子进程 ────────────────────────────────────────────
_kill_pid() {
  local pid="$1" signal="${2:-TERM}"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill -"$signal" "$pid" 2>/dev/null || true
  fi
}

_any_alive() {
  if [ "${#PIDS[@]}" -eq 0 ]; then
    return 1
  fi
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  done
  return 1
}

cleanup() {
  echo ""
  log "正在停止所有服务..."

  # 先 SIGTERM，给子进程 5s 优雅退出
  for pid in "${PIDS[@]:-}"; do
    _kill_pid "$pid" "TERM"
  done

  local waited=0
  while [ "$waited" -lt 5 ] && _any_alive; do
    sleep 1
    waited=$((waited + 1))
  done

  # 还活着的就 SIGKILL
  for pid in "${PIDS[@]:-}"; do
    _kill_pid "$pid" "KILL"
  done

  # 收尸，避免 zombie
  for pid in "${PIDS[@]:-}"; do
    if [ -n "$pid" ]; then
      wait "$pid" 2>/dev/null || true
    fi
  done

  log "已停止。"
}

trap cleanup SIGINT SIGTERM

# ── 前置检查 ──────────────────────────────────────────────
log "前置检查..."

if ! command -v uv &>/dev/null; then
  err "未找到 uv，请先安装: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

if ! command -v bun &>/dev/null; then
  err "未找到 bun，请先安装 Bun >= 1.2: https://bun.sh/docs/installation"
  exit 1
fi

if [ ! -d "$BACKEND_DIR" ]; then
  err "未找到后端目录: $BACKEND_DIR"
  exit 1
fi

if [ ! -d "$PORTAL_DIR" ]; then
  err "未找到前端目录: $PORTAL_DIR"
  exit 1
fi

log "前置检查通过 (uv=$(uv --version 2>/dev/null || echo '?'), bun=$(bun --version))"

# ── 依赖安装 ──────────────────────────────────────────────
if [ "$FRESH" = true ]; then
  log "--fresh: 清理并重新安装依赖..."
  rm -rf "$BACKEND_DIR/.venv"
  rm -rf "$PORTAL_DIR/node_modules" "$PORTAL_DIR/bun.lock"
fi

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  log "安装后端依赖 (uv sync)..."
  (cd "$BACKEND_DIR" && uv sync)
else
  log "后端依赖已就绪，跳过安装"
fi

if [ ! -d "$PORTAL_DIR/node_modules" ]; then
  log "安装 Portal 前端依赖 (bun install)..."
  (cd "$PORTAL_DIR" && bun install)
else
  log "Portal 依赖已就绪，跳过安装"
fi

# ── 准备日志目录 ──────────────────────────────────────────
mkdir -p "$LOG_DIR"
: > "$LOG_DIR/backend.log"
: > "$LOG_DIR/portal.log"

# ── 启动服务 ──────────────────────────────────────────────
log "启动服务..."

(
  cd "$BACKEND_DIR"
  exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" \
    --timeout-graceful-shutdown 3 \
    > "$LOG_DIR/backend.log" 2>&1
) &
BACKEND_PID=$!
PIDS+=("$BACKEND_PID")

(
  cd "$PORTAL_DIR"
  exec bun run dev \
    > "$LOG_DIR/portal.log" 2>&1
) &
PORTAL_PID=$!
PIDS+=("$PORTAL_PID")

# 等启动信息落地
sleep 2

# ── 打印摘要 ──────────────────────────────────────────────
echo ""
echo "${BOLD}========================================${RESET}"
echo "${BOLD} Eyot 本地开发环境${RESET}"
echo "${BOLD}========================================${RESET}"
echo "  ${BLUE}BACKEND${RESET}  http://localhost:${BACKEND_PORT}  (pid=${BACKEND_PID}, log=logs/backend.log)"
echo "  ${GREEN}PORTAL${RESET}   http://localhost:${PORTAL_PORT}  (pid=${PORTAL_PID}, log=logs/portal.log)"
echo "${BOLD}========================================${RESET}"
echo "  ${DIM}tail -f logs/backend.log logs/portal.log${RESET}"
echo "  Ctrl+C 停止所有服务"
echo ""

# ── 等待子进程退出 ────────────────────────────────────────
wait_for_children() {
  while _any_alive; do
    sleep 1
  done
  log "所有服务已退出。"
}

wait_for_children
