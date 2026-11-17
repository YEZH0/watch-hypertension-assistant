"""健康 App 的人工核验指引。

本模块存在的意义就是防止一个特定的误解：

    「定位测试成功」≠「高血压通知已开通」

定位模拟只能证明「引擎能改动手机报告的位置」。它和健康功能是否可用没有任何
因果关系。真正的判断依据只有一处：用户在 iPhone 健康 App 里看到的实际状态。

所以这里不给任何「已开通 / 已生效」的判断，只给可执行的人工核验步骤。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideStep:
    order: int
    action: str
    expect: str

    def to_dict(self) -> dict[str, str | int]:
        return {"order": self.order, "action": self.action, "expect": self.expect}


CORE_WARNING = (
    "定位测试成功只说明引擎改动了手机报告的位置坐标，不代表高血压通知已开通、"
    "已生效或已验证。这两件事没有因果关系，请勿把前者当成后者。"
)

SETUP_STEPS: tuple[GuideStep, ...] = (
    GuideStep(1, "在 iPhone 打开「健康」App，点右上角头像。", "进入个人中心页面。"),
    GuideStep(2, "进入「健康核对清单」（Health Checklist）。", "能看到体检/健康功能相关的待办卡片。"),
    GuideStep(
        3,
        "找到「高血压通知」卡片并点击。",
        "若卡片不存在，说明当前机型、系统或地区不满足条件——这就是结论，不要想办法绕过。",
    ),
    GuideStep(
        4,
        "按提示确认年龄、是否曾被诊断高血压、是否妊娠。",
        "如实填写。已确诊高血压或处于妊娠期时功能不适用，这是 Apple 的医学设计边界。",
    ),
    GuideStep(5, "完成引导并点「完成」。", "卡片状态变为已设置，开始累积数据。"),
    GuideStep(
        6,
        "确认「腕部检测」已开启（Watch App → 密码 → 腕部检测）。",
        "腕部检测关闭时无法可靠采集数据。",
    ),
)

VERIFICATION_STEPS: tuple[GuideStep, ...] = (
    GuideStep(
        1,
        "每天正常佩戴手表，包含睡眠时段。",
        "首次提醒需要 30 天数据窗口，其中至少 14 天有效数据；短期内不会有任何提醒是正常的。",
    ),
    GuideStep(
        2,
        "在健康 App 中查看该功能卡片的状态与数据积累情况。",
        "这是唯一可信的判断依据。助手无法读取、也不会替你判断这个状态。",
    ),
    GuideStep(
        3,
        "收到提醒时的正确处理：用独立血压计连续测量 7 天并咨询医生。",
        "该功能是筛查提醒，不是诊断；没有收到提醒也不代表血压正常。",
    ),
)


def render(*, location_test_passed: bool | None = None) -> dict[str, object]:
    """生成核验指引。

    ``location_test_passed`` 只用于调整措辞，**绝不**参与任何「功能已开通」的推断。
    """
    opening = CORE_WARNING
    if location_test_passed is True:
        opening = (
            "定位测试已成功，模拟位置在手机上生效了。"
            "现在请立刻注意：" + CORE_WARNING
        )
    elif location_test_passed is False:
        opening = "定位测试没有成功，请先解决前置检查里的阻断项。以下是功能本身的核验步骤。"

    return {
        "opening": opening,
        "setup_steps": [step.to_dict() for step in SETUP_STEPS],
        "verification_steps": [step.to_dict() for step in VERIFICATION_STEPS],
        "never_claim": [
            "不要把定位测试结果当作功能开通证据。",
            "不要在健康 App 之外声称功能状态。",
            "不要在用户不满足医疗适用条件时提供任何变通方案。",
        ],
    }


RESTORE_PROMPT = (
    "定位已停止。请断开 USB 数据线，然后在 iPhone 的「地图」App 中点击定位按钮，"
    "确认蓝点已回到你的真实位置。确认无误后再结束本次测试。"
)

RESTORE_CHECKLIST: tuple[str, ...] = (
    "USB 数据线已断开，或引擎会话已完全退出。",
    "iPhone「地图」App 中的蓝点已回到真实位置。",
    "健康 App 中的功能状态没有任何变化（定位测试不应影响它）。",
)
