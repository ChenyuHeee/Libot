#!/bin/zsh
set -euo pipefail

# Double-clickable launcher for macOS Terminal (.command).
# It bootstraps a local venv, installs Libot (with GUI deps), then starts the GUI.

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo "ERROR: 找不到 python3/python。请先安装 Python 3。"
  exit 1
fi

VENV_DIR=".venv"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "[Libot] 创建虚拟环境：$VENV_DIR"
  "$PY" -m venv "$VENV_DIR"
fi

VPY="$VENV_DIR/bin/python"

echo "[Libot] 升级 pip"
"$VPY" -m pip install -U pip >/dev/null

echo "[Libot] 安装/更新依赖（含 GUI）：.[gui]"
"$VPY" -m pip install -e ".[gui]"

echo "[Libot] 启动 GUI..."
exec "$VPY" -m libot.gui
