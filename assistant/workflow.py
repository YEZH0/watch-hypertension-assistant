"""助手主流程：把平台识别、前置检查、兼容性、地区预设、定位测试串起来。

设计上刻意保持「一步一件事」，且每一步都能单独输出，便于用户在终端里逐步确认。
不追求架构上的优雅：这是最小可运行版本。

三条贯穿全流程的不变量（有测试保护）：
1. 任何输出都不包含「高血压通知已开通/已生效」这类断言；
2. 兼容性结论只有三值，未知就是未知；
3. 定位测试失败时不会给出「再来一次也许就好了」的模糊建议，只报告真实原因。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from . import compat, guide, preflight, regions
from .adapters.base import (
    AdapterUnavailable,
    CompatReport,
    EngineStatus,
    LocationEngine,
    RegionPreset,
    SessionSnapshot,
)
from .adapters.registry import create_adapter, detect_platform, platform_label

# 会话时长限制：够用户切到手机上核验即可，避免长时间挂着一个模拟定位。
#
# 上限必须与定位引擎的硬约束一致。实测 ios-location-studio 的
# POST /api/simulate 只接受 hold_seconds <= 180（181 直接返回 HTTP 422），
# 因此这里不能声明更大的值——否则助手会发出注定被拒的请求，
# 用户拿到的是一段 Pydantic 英文校验错误，而不是可理解的提示。
#
# 引擎升级后若放宽了上限，用环境变量覆盖，不必改代码。
MAX_HOLD_SECONDS = int(os.environ.get("WHC_MAX_HOLD_SECONDS", "180"))
MIN_HOLD_SECONDS = 60
DEFAULT_HOLD_SECONDS = 180

# 唯一允许出现的功能状态表述。刻意不可枚举出「已开通」。
FEATURE_STATUS_UNVERIFIED = "unknown_pending_user_verification"


@dataclass
class Assistant:
    engine_url: str | None = None
    platform_name: str | None = None
    _engine: LocationEngine | None = field(default=None, repr=False)

    @property
    def platform(self) -> str:
        return self.platform_name or detect_platform()

    @property
    def engine(self) -> LocationEngine:
        if self._engine is None:
            self._engine = create_adapter(self.platform, self.engine_url)
        return self._engine

    # ------------------------------------------------------------ 阶段一

    def environment(self) -> dict[str, Any]:
        """平台识别 + 引擎探测。"""
        platform = self.platform
        try:
            status: EngineStatus = self.engine.probe()
            engine_payload = status.to_dict()
        except AdapterUnavailable as exc:
            engine_payload = {
                "available": False,
                "platform": platform,
                "engine": "n/a",
                "detail": str(exc),
                "hint": exc.hint,
            }
        return {
            "platform": platform,
            "platform_label": platform_label(platform),
            "engine": engine_payload,
        }

    # ------------------------------------------------------------ 阶段二

    def preflight(self) -> preflight.PreflightReport:
        return preflight.run(self.engine, self.platform)

    def compatibility(self, inputs: compat.UserInputs | None = None) -> CompatReport:
        return compat.check(inputs or compat.UserInputs())

    # ------------------------------------------------------------ 阶段三

    def start_test(
        self, region_id: str, hold_seconds: int = DEFAULT_HOLD_SECONDS
    ) -> dict[str, Any]:
        """启动一次地区预设定位测试。

        前置条件不满足时**不会**尝试强行启动，而是把阻断项原样返回。
        """
        preset = self._preset_or_error(region_id)
        hold = self._clamp_hold(hold_seconds)
        hold_note = self._hold_adjustment_note(hold_seconds, hold)

        report = self.preflight()
        if not report.can_run_location_test:
            # 即使没启动成功，也要把"定位≠功能状态"和"定位≠区域可用性"两条警告带上：
            # 用户在失败场景下更容易产生"再试一次就能开通"的误解。
            return {
                "started": False,
                "region": preset.to_dict(),
                "reason": "前置检查未通过，未启动定位测试。",
                "blocking_items": [
                    item.to_dict() for item in report.items if item.passed is False and item.blocking
                ],
                "location_test_does_not_imply": guide.CORE_WARNING,
                "engine_active_note": guide.ENGINE_ACTIVE_NOTE,
                "map_verification_required": False,
                "feature_status": FEATURE_STATUS_UNVERIFIED,
                "region_warning": regions.critical_warning(),
                "verification_guide": guide.render(engine_active=False),
            }

        session = self.engine.start_location(preset.latitude, preset.longitude, hold)
        started = session.state == "active"
        return {
            "started": started,
            "region": preset.to_dict(),
            "session": session.to_dict(),
            "hold_seconds": hold,
            # 被夹到安全区间时必须说清楚，否则用户以为自己设的是请求值。
            "hold_note": hold_note,
            "reason": "" if started else (session.error or session.message or "引擎未进入 active 状态"),
            # 无论成功与否都附带这句，避免成功被误读。
            "location_test_does_not_imply": guide.CORE_WARNING,
            # active 只是引擎的自述。手机有没有采纳坐标，必须由用户看地图回答。
            "engine_active_note": guide.ENGINE_ACTIVE_NOTE,
            "map_verification_required": True,
            "map_verification_answers": [dict(item) for item in guide.MAP_ANSWERS],
            "feature_status": FEATURE_STATUS_UNVERIFIED,
            "region_warning": regions.critical_warning(),
            "verification_guide": guide.render(engine_active=started),
        }

    def stop_test(self) -> dict[str, Any]:
        session = self.engine.stop_location()
        return {
            "stopped": session.state in ("idle",),
            "session": session.to_dict(),
            "restore_prompt": guide.RESTORE_PROMPT,
            # 新结构：带触发条件，便于区分「总是要做」与「按情况排查」。
            "restore_steps": [step.to_dict() for step in guide.RESTORE_STEPS],
            # 兼容字段：名称沿用旧版，内容已条件化（见 guide.RestoreStep.to_line）。
            "restore_force_steps": list(guide.RESTORE_FORCE_STEPS),
            "restore_note": guide.RESTORE_CONDITIONAL_NOTE,
            "restore_checklist": list(guide.RESTORE_CHECKLIST),
            # 助手无法验证手机是否真的回到真实位置，这里如实标为未确认。
            "user_confirmed_restored": None,
            "feature_status": FEATURE_STATUS_UNVERIFIED,
        }

    def session(self) -> SessionSnapshot:
        return self.engine.session()

    def safe_stop(self) -> dict[str, Any]:
        """尽力停止会话，**绝不抛异常**。

        用于 Ctrl+C、异常退出、用户取消这类「必须收拾干净但不能因为收拾失败
        再崩一次」的场景。返回值里的 ``ok`` 为 False 时，调用方要把
        「请手动确认恢复」这件事告诉用户，而不是假装已经停好了。
        """
        try:
            result = self.stop_test()
            return {"ok": True, "result": result, "error": None}
        except Exception as exc:  # noqa: BLE001 - 清理路径必须吞掉所有异常
            return {
                "ok": False,
                "result": None,
                "error": str(exc),
                "restore_prompt": guide.RESTORE_PROMPT,
                "restore_steps": [step.to_dict() for step in guide.RESTORE_STEPS],
            }

    # ------------------------------------------------------------ 报告

    def full_report(self, inputs: compat.UserInputs | None = None) -> dict[str, Any]:
        """一次性输出完整检查报告（不启动定位）。"""
        env = self.environment()
        pre = self.preflight()
        compat_report = self.compatibility(inputs)
        return {
            "platform": env,
            "preflight": pre.to_dict(),
            "compatibility": compat_report.to_dict(),
            "regions": [preset.to_dict() for preset in regions.presets()],
            "region_warning": regions.critical_warning(),
            "state_separation": [dict(item) for item in guide.STATE_SEPARATION],
            "official_links": [dict(item) for item in guide.OFFICIAL_LINKS],
            "feature_status": FEATURE_STATUS_UNVERIFIED,
            "core_warning": guide.CORE_WARNING,
        }

    # ------------------------------------------------------------ 辅助

    def _preset_or_error(self, region_id: str) -> RegionPreset:
        try:
            return regions.get(region_id)
        except KeyError as exc:
            # 未知地区是**用户输入错误**，不是「引擎不可用」。包装成
            # AdapterUnavailable 会让 CLI 用错误的退出码（1 而非 2）并给出
            # 「确认引擎已启动」这类完全无关的建议。
            available = ", ".join(p.id for p in regions.presets())
            raise KeyError(f"未知地区预设 {region_id!r}；可选：{available}") from exc

    @staticmethod
    def _clamp_hold(hold_seconds: int) -> int:
        """把时长夹到安全区间。不允许 0 或无限长——挂着模拟定位有实际风险。"""
        try:
            value = int(hold_seconds)
        except (TypeError, ValueError):
            return DEFAULT_HOLD_SECONDS
        return max(MIN_HOLD_SECONDS, min(MAX_HOLD_SECONDS, value))

    @staticmethod
    def _hold_adjustment_note(requested: Any, effective: int) -> str:
        """请求值与实际生效值不一致时，给一句人能看懂的说明。

        静默夹取会让用户误以为“我设的就是这个时长”，排查问题时很误导。
        """
        try:
            requested_int = int(requested)
        except (TypeError, ValueError):
            return ""
        if requested_int == effective:
            return ""
        if requested_int < MIN_HOLD_SECONDS:
            return (
                f"请求的 {requested_int} 秒低于允许的最小值 {MIN_HOLD_SECONDS} 秒，"
                f"已按 {effective} 秒执行（时长太短会来不及在手机上观察效果）。"
            )
        return (
            f"请求的 {requested_int} 秒超过允许的最大值 {MAX_HOLD_SECONDS} 秒，"
            f"已按 {effective} 秒执行（长时间挂着模拟定位有风险）。"
        )
