"""macOS 适配器：委托给 ``macos/`` 子项目（由 Mac Agent 实现）。

许可证边界在这里是硬约束：

* 本仓库根目录与 ``assistant/`` 是 MIT；
* 已完成的 macOS 成果（``macos/``）因 vendor 了 ``aur3l14no/accessory-location``
  而整体是 **GPL-3.0-only**；
* 若把 GPL 代码复制进 MIT 目录，会让整个项目被迫变成 GPL。

所以这里**不 import 任何 macOS 引擎模块**，只按契约通过本机 HTTP 调用。
两段代码是两个独立进程、两个独立许可证，互不传染。

契约（Mac Agent 需要提供的唯一东西）：
    在 ``macos/`` 下提供一个桥接进程，监听 127.0.0.1:8900，暴露与 Windows 引擎
    完全相同的四个 JSON 接口：

        GET  /api/health    -> {"ok": true, "version": "..."}
        GET  /api/devices   -> {"connected": bool, "devices": [{"udid","name","ios_version","model"}]}
        GET  /api/status    -> {"session": {...}}
        POST /api/simulate  -> {"session": {...}}   请求体 {"latitude","longitude","hold_seconds"}
        POST /api/stop      -> {"session": {...}}

    会话字段与 Windows 引擎一致：state 取 idle/connecting/active/stopping/error。
    详细规格见 ``docs/ADAPTER-CONTRACT.md``。
"""

from __future__ import annotations

import subprocess
import sys
import time

from .base import AdapterUnavailable, EngineStatus
from .http_engine import HttpLocationEngine

DEFAULT_URL = "http://127.0.0.1:8900"
LAUNCH_WAIT_SECONDS = 20.0

# 由 Mac Agent 在 macos/ 下实现的桥接模块。缺失时给出可执行指引，不静默降级。
BRIDGE_MODULE = "location_studio_mac.bridge"


class MacOSLocationEngine(HttpLocationEngine):
    """macOS 平台：调用 ``macos/`` 子项目提供的桥接接口。

    DVT 仍然是默认路线；iAP2 由桥接进程内部决定，默认不启用
    （iAP2 需要用户自备证书，且历史上存在「有 ACK 不采纳位置」的记录，
    所以它对助手来说只能作为实验性选项，不参与自动判定）。
    """

    name = "macos-dvt"

    def __init__(self, base_url: str | None = None) -> None:
        super().__init__(base_url or DEFAULT_URL, platform="macos")

    def probe(self) -> EngineStatus:
        status = super().probe()
        if status.available:
            return status

        # 桥接没起来：尝试启动一次，但不反复重试。
        launch_error = self._launch_bridge()
        if launch_error:
            return EngineStatus(
                available=False,
                platform="macos",
                engine=self.name,
                endpoint=self.base_url,
                detail=launch_error,
            )

        deadline = time.monotonic() + LAUNCH_WAIT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(0.5)
            status = super().probe()
            if status.available:
                return status

        return EngineStatus(
            available=False,
            platform="macos",
            engine=self.name,
            endpoint=self.base_url,
            detail="桥接进程已启动但未在等待时间内就绪。",
        )

    def _launch_bridge(self) -> str | None:
        """尝试启动 Mac Agent 提供的桥接进程。"""
        check = subprocess.run(
            [sys.executable, "-c", f"import {BRIDGE_MODULE}"],
            capture_output=True,
            check=False,
        )
        if check.returncode != 0:
            return (
                "未检测到 macOS 桥接接口。macOS 支持由 Mac Agent 在 macos/ 下实现，"
                f"需要提供可导入的 {BRIDGE_MODULE}（规格见 docs/ADAPTER-CONTRACT.md）。"
            )

        try:
            subprocess.Popen(  # noqa: S603 - 参数固定，无 shell
                [sys.executable, "-m", BRIDGE_MODULE, "--host", "127.0.0.1", "--port", "8900"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            return f"启动 macOS 桥接失败：{exc}"
        return None


def adapter_unavailable_hint() -> AdapterUnavailable:
    return AdapterUnavailable(
        "macOS 定位能力尚未接入。",
        hint=(
            "Mac Agent 从 main 创建 feat/macos 分支，在 macos/ 内实现桥接接口后即可自动启用；"
            "助手核心无需改动。"
        ),
    )
