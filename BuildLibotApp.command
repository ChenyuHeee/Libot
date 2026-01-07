#!/bin/zsh
set -euo pipefail

# One-click builder for a double-clickable macOS .app via PyInstaller.

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

echo "[Libot] 安装 PyInstaller"
"$VPY" -m pip install -U pyinstaller

echo "[Libot] 开始打包（会生成 dist/Libot.app）"
ADD_DATA_ARGS=()
if [[ -f "libot_bundled.json" ]]; then
  echo "[Libot] 打包内置配置：libot_bundled.json"
  ADD_DATA_ARGS+=(--add-data "libot_bundled.json:.")
elif [[ -f "libot_bundled.example.json" ]]; then
  echo "[Libot] 未找到 libot_bundled.json，将使用空模板 libot_bundled.example.json"
  ADD_DATA_ARGS+=(--add-data "libot_bundled.example.json:.")
fi
"$VPY" -m PyInstaller \
  -y --clean \
  --name Libot \
  --windowed \
  "${ADD_DATA_ARGS[@]}" \
  app_gui.py

echo "[Libot] 打包完成：dist/Libot.app"
echo "[Libot] 你可以在 Finder 里打开 dist/Libot.app"
