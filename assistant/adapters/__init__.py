"""定位引擎适配器。

平台差异只在这一层；助手核心只依赖 ``base.LocationEngine`` 协议。
"""

from __future__ import annotations

from .base import (
    AdapterError,
    AdapterUnavailable,
    CompatReport,
    Device,
    DeviceNotReady,
    EngineStatus,
    Inventory,
    LocationEngine,
    RegionPreset,
    SessionSnapshot,
)
from .registry import create_adapter, detect_platform, platform_label

__all__ = [
    "AdapterError",
    "AdapterUnavailable",
    "CompatReport",
    "Device",
    "DeviceNotReady",
    "EngineStatus",
    "Inventory",
    "LocationEngine",
    "RegionPreset",
    "SessionSnapshot",
    "create_adapter",
    "detect_platform",
    "platform_label",
]
