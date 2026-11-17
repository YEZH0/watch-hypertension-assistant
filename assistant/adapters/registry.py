"""适配器注册与平台自动识别。"""

from __future__ import annotations

import platform as _platform
import sys

from .base import AdapterUnavailable, LocationEngine
from .http_engine import HttpLocationEngine

SUPPORTED_PLATFORMS = ("windows", "macos")


def detect_platform() -> str:
    """返回 ``windows`` / ``macos`` / ``linux`` / ``unknown``。

    只用 ``sys.platform``，不去探测硬件或设备——平台识别必须零副作用。
    """
    value = sys.platform
    if value.startswith("win"):
        return "windows"
    if value == "darwin":
        return "macos"
    if value.startswith("linux"):
        return "linux"
    return "unknown"


def platform_label(name: str) -> str:
    return {
        "windows": "Windows",
        "macos": "macOS",
        "linux": "Linux（不受支持）",
    }.get(name, f"未知平台（{_platform.system() or name}）")


def create_adapter(platform_name: str | None = None, engine_url: str | None = None) -> LocationEngine:
    """按平台创建适配器。

    延迟导入：在 Windows 上就不会加载 macOS 适配器，反之亦然。
    """
    name = platform_name or detect_platform()

    if engine_url:
        # 显式指定地址时，不做任何自动启动，纯客户端模式。
        return HttpLocationEngine(engine_url, platform=name)

    if name == "windows":
        from .windows import WindowsLocationEngine

        return WindowsLocationEngine()

    if name == "macos":
        from .macos import MacOSLocationEngine

        return MacOSLocationEngine()

    raise AdapterUnavailable(
        f"不支持的平台：{platform_label(name)}。",
        hint="本助手只支持 Windows 与 macOS；定位引擎本身不支持 Linux。",
    )
