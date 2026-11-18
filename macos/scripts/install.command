#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo '仅支持 macOS'; exit 1; }
if ! command -v uv >/dev/null; then
  if command -v python3 >/dev/null && python3 -m uv --version >/dev/null 2>&1; then
    uv() { python3 -m uv "$@"; }
  else
    echo '请先安装 uv：https://docs.astral.sh/uv/getting-started/installation/'
    exit 1
  fi
fi
uv python install 3.13
uv sync --locked
uv pip install --python .venv/bin/python --no-deps -e ..
.venv/bin/python -m location_studio_mac.doctor
echo '依赖检查完成。接下来按 agent/macos-install-prompt.md 继续手机操作，不要停在安装。'
echo '共享流程可用后运行：.venv/bin/python -m location_studio_mac.assistant wizard'
xcrun --find devicectl >/dev/null 2>&1 || echo '首次 DVT 准备需要完整 Xcode 的 devicectl；安装并完成 Xcode 初始化。'
[[ -x /usr/bin/sandbox-exec ]] || { echo '缺少 sandbox-exec，不能启动定位 worker'; exit 1; }
