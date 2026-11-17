"""前置条件检查：引擎、USB 连接、设备条件。

这一层只做「观察并如实报告」，不尝试修复，也不自动替用户开启开发者模式之类
的安全设置——那属于用户自己的决定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .adapters.base import Device, Inventory, LocationEngine
from .adapters.registry import detect_platform, platform_label

# 高血压通知要求 iOS 26+，但定位测试本身在更低版本也能跑。
# 两者要分开报告，不能因为定位能跑就暗示健康功能可用。
FEATURE_MIN_IOS = (26, 0)


@dataclass
class PreflightItem:
    key: str
    title: str
    passed: bool | None
    detail: str
    blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "passed": self.passed,
            "detail": self.detail,
            "blocking": self.blocking,
        }


@dataclass
class PreflightReport:
    platform: str
    engine_available: bool = False
    engine_detail: str = ""
    inventory: Inventory = field(default_factory=Inventory)
    items: list[PreflightItem] = field(default_factory=list)

    @property
    def can_run_location_test(self) -> bool:
        return self.engine_available and bool(self.inventory.devices) and not any(
            item.blocking and item.passed is False for item in self.items
        )

    @property
    def device(self) -> Device | None:
        return self.inventory.devices[0] if self.inventory.devices else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "platform_label": platform_label(self.platform),
            "engine_available": self.engine_available,
            "engine_detail": self.engine_detail,
            "inventory": self.inventory.to_public_dict(),
            "items": [item.to_dict() for item in self.items],
            "can_run_location_test": self.can_run_location_test,
        }


def _parse_ios(version: str | None) -> tuple[int, int] | None:
    if not version:
        return None
    parts = version.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return None
    return major, minor


def run(engine: LocationEngine, platform_name: str | None = None) -> PreflightReport:
    """执行前置检查。全程只读，不启动任何定位会话。"""
    platform = platform_name or detect_platform()
    report = PreflightReport(platform=platform)

    # ---------------------------------------------------------- 引擎
    status = engine.probe()
    report.engine_available = status.available
    report.engine_detail = status.detail or ("引擎在线" if status.available else "引擎不可用")
    report.items.append(
        PreflightItem(
            key="engine",
            title="定位引擎可用",
            passed=status.available,
            detail=(
                f"{status.engine} {status.version or ''} @ {status.endpoint}".strip()
                if status.available
                else status.detail
            ),
        )
    )

    if not status.available:
        # 引擎都不可用，后续设备检查没有意义，直接返回。
        return report

    # ---------------------------------------------------------- USB 连接
    inventory = engine.list_devices()
    report.inventory = inventory
    report.items.append(
        PreflightItem(
            key="usb",
            title="USB 设备连接",
            passed=bool(inventory.devices),
            detail=(
                f"发现 {len(inventory.devices)} 台设备"
                if inventory.devices
                else (inventory.error or "未检测到设备：请使用数据线连接并解锁 iPhone，在弹窗中选择「信任」")
            ),
        )
    )

    if not inventory.devices:
        return report

    # 多台设备时不做自动选择，避免误改到另一台手机。
    report.items.append(
        PreflightItem(
            key="single_device",
            title="仅一台设备连接",
            passed=len(inventory.devices) == 1,
            detail=(
                "唯一设备，可安全定位测试目标"
                if len(inventory.devices) == 1
                else f"检测到 {len(inventory.devices)} 台设备，请只保留一台再试，避免改错手机"
            ),
        )
    )

    device = inventory.devices[0]

    # ---------------------------------------------------------- 设备条件
    ios = _parse_ios(device.ios_version)
    report.items.append(
        PreflightItem(
            key="ios_known",
            title="可读取 iOS 版本",
            passed=ios is not None,
            detail=(
                f"iOS {device.ios_version}"
                if ios
                else "无法读取 iOS 版本：请解锁手机并「信任此电脑」，并确认开发者模式已开启"
            ),
        )
    )

    if ios:
        report.items.append(
            PreflightItem(
                key="feature_ios",
                title=f"iOS 版本满足高血压通知要求（{FEATURE_MIN_IOS[0]}+）",
                passed=ios >= FEATURE_MIN_IOS,
                detail=(
                    f"iOS {device.ios_version}"
                    if ios >= FEATURE_MIN_IOS
                    else f"iOS {device.ios_version} 低于 26：定位测试仍可进行，但高血压通知功能在此系统上不可用"
                ),
                # 不阻断定位测试，只阻断「功能可用」的期待。
                blocking=False,
            )
        )

    return report
