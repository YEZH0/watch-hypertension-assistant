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
# 公共向导（MIT，仓库根目录的 assistant/）装进了同一个 venv。Mac 侧的
# `location_studio_mac.assistant` 只是转发它，缺了就在后面某一步莫名其妙地失败。
# 在安装阶段就把这件事暴露出来，别让用户走到手机上才发现。
.venv/bin/python -c 'import assistant.wizard' || {
  echo '公共助手（assistant）未装好，向导无法运行。请确认在仓库根目录执行本脚本。'
  exit 1
}
.venv/bin/python -m location_studio_mac.doctor
echo '依赖检查完成。接下来按 agent/macos-install-prompt.md 继续手机操作，不要停在安装。'
echo '共享流程可用后运行：.venv/bin/python -m location_studio_mac.assistant wizard'
xcrun --find devicectl >/dev/null 2>&1 || echo '首次 DVT 准备需要完整 Xcode 的 devicectl；安装并完成 Xcode 初始化。'
[[ -x /usr/bin/sandbox-exec ]] || { echo '缺少 sandbox-exec，不能启动定位 worker'; exit 1; }
