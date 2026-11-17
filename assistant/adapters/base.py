"""统一适配器接口与数据模型。

设计约束（对应项目第二阶段的硬性要求）：

1. 本模块**不包含任何定位协议实现**。定位能力一律由外部已完成的引擎提供。
2. 适配器只负责「调用」，不负责「理解 DVT / iAP2 报文」。
3. 同一套接口同时服务 Windows 与 macOS，平台差异收敛在适配器内部。

因此，本文件是 Windows Agent 与 Mac Agent 之间唯一需要共同遵守的契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# 校验结果只允许三种取值。
# 关键：没有 "SUPPORTED" 这种"功能已可用"的结论——机型可能支持，但功能是否开通
# 只有用户在 iPhone 健康 App 里亲眼看到才算数。
CompatVerdict = Literal[
    "model_unsupported",  # 机型/系统确定不支持
    "eligibility_blocked",  # 机型支持，但用户不满足医疗使用条件
    "needs_manual_verification",  # 机型支持且资格未排除，仍需用户自行核验
]

SessionState = Literal["idle", "connecting", "active", "stopping", "error"]


class AdapterError(RuntimeError):
    """适配器调用失败的基类。"""


class AdapterUnavailable(AdapterError):
    """引擎不存在、未安装或无法启动。

    ``hint`` 必须给出用户可执行的下一步，而不是只说"失败"。
    """

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


class DeviceNotReady(AdapterError):
    """检测到设备，但未满足可定位测试的条件。"""

    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


@dataclass(frozen=True)
class EngineStatus:
    """引擎可达性快照。"""

    available: bool
    platform: str
    engine: str
    version: str | None = None
    endpoint: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "platform": self.platform,
            "engine": self.engine,
            "version": self.version,
            "endpoint": self.endpoint,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Device:
    """一台已连接设备的最小描述。

    刻意**不采集**序列号以外的识别信息；序列号只在内存中转发给引擎，
    不写入日志、不落盘、不进入任何报告。
    """

    handle: str
    name: str | None = None
    ios_version: str | None = None
    model: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        """对外输出用：去掉设备标识句柄。"""
        return {"name": self.name, "ios_version": self.ios_version, "model": self.model}


@dataclass(frozen=True)
class Inventory:
    connected: bool = False
    devices: tuple[Device, ...] = ()
    error: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "count": len(self.devices),
            "devices": [d.to_public_dict() for d in self.devices],
            "error": self.error,
        }


@dataclass(frozen=True)
class SessionSnapshot:
    """一次定位测试会话的状态。

    注意 ``location_active`` 只表示「引擎已下发模拟定位」，
    绝不表示「手机上的健康功能已生效」。
    """

    state: SessionState = "idle"
    latitude: float | None = None
    longitude: float | None = None
    remaining: float | None = None
    message: str = ""
    error: str | None = None
    location_active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "remaining": self.remaining,
            "message": self.message,
            "error": self.error,
            "location_active": self.location_active,
        }


@dataclass(frozen=True)
class RegionPreset:
    """固定地区测试预设。第一版只有四个，不接受自由经纬度。"""

    id: str
    region_code: str
    label: str
    city: str
    latitude: float
    longitude: float
    availability: str
    availability_note: str = ""
    hardware_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "region_code": self.region_code,
            "label": self.label,
            "city": self.city,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "availability": self.availability,
            "availability_note": self.availability_note,
            "hardware_note": self.hardware_note,
        }


@dataclass(frozen=True)
class CompatReport:
    """兼容性检查结论。

    ``verdict`` 三值语义见 ``CompatVerdict``。任何情况下本类都**不**存在
    "功能已开通" 这个字段，从类型层面杜绝误导。
    """

    verdict: CompatVerdict
    headline: str
    checks: tuple[dict[str, Any], ...] = ()
    blockers: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    data_verified_on: str = ""
    sources: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "headline": self.headline,
            "checks": list(self.checks),
            "blockers": list(self.blockers),
            "unknowns": list(self.unknowns),
            "next_steps": list(self.next_steps),
            "data_verified_on": self.data_verified_on,
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class StepRecord:
    """助手流程中的一步，用于阶段化输出。"""

    index: int
    title: str
    status: Literal["done", "skipped", "blocked", "pending"]
    detail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LocationEngine(Protocol):
    """定位引擎适配器契约。

    Windows 与 macOS 各自实现，助手核心只依赖此协议。
    实现方**不得**在此层实现任何协议握手、报文构造或证书逻辑。
    """

    name: str

    def probe(self) -> EngineStatus:
        """检查引擎是否可用（不需要连接设备）。"""
        ...

    def list_devices(self) -> Inventory:
        """枚举已连接的 USB 设备。"""
        ...

    def start_location(self, latitude: float, longitude: float, hold_seconds: int | None) -> SessionSnapshot:
        """下发模拟定位并保持会话。返回时若未 active 视为失败。"""
        ...

    def stop_location(self) -> SessionSnapshot:
        """停止并恢复真实定位。"""
        ...

    def session(self) -> SessionSnapshot:
        """查询当前会话状态。"""
        ...
