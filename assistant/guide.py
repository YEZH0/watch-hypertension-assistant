"""健康 App 的人工核验指引，以及「恢复真实位置」的条件化排查步骤。

本模块存在的意义就是防止三类特定的误解：

1. 「引擎进入 active」≠「手机采用了该坐标」≠「高血压通知已开通」
   这三个状态互相独立。引擎只知道自己的请求发成功了；手机有没有采纳，
   只有用户在看地图才能回答；功能状态只有健康 App 能回答。

2. 「定位测试成功」≠「高血压通知已开通」
   定位模拟只改变手机报告的位置。它和健康功能是否可用没有因果关系。

3. 「停止后必须关定位服务 10 秒」不是普遍规律
   关定位服务确实能清缓存，但它是排查链路里的一环，不是所有人都必须执行的
   前置条件。把它写成「不这样做就一定恢复不了」属于没有依据的绝对化表述，
   会让用户在本来已经恢复的情况下做多余的破坏性操作（关闭定位会中断正在
   导航、正在记录的 App）。

所以这里的措辞原则是：**给出可执行的排查顺序，标明每一步的适用条件，
并且明确「助手看不见你手机里的状态」。**
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


@dataclass(frozen=True)
class RestoreStep:
    """恢复真实位置的一步。

    ``when`` 为空字符串表示「总是要做」；否则它是这一步的触发条件。
    分级的目的是让已经恢复的用户不必再去做关闭定位服务这类打断性操作。
    """

    order: int
    action: str
    expect: str
    when: str = ""
    may_break_simulation: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "order": self.order,
            "action": self.action,
            "expect": self.expect,
            "when": self.when,
            "conditional": bool(self.when),
            "may_break_simulation": self.may_break_simulation,
        }

    def to_line(self) -> str:
        """兼容旧字段 ``restore_force_steps`` 的纯文本形式。

        旧字段名带 "force"（强制），历史版本用它表达「不做就无法恢复」。
        现在语义变了：条件步骤会带上「如果…」前缀，读 JSON 的下游程序
        不会再把它们当成无条件必须执行的步骤。
        """
        if self.when:
            return f"如果{self.when}：{self.action}"
        return self.action


CORE_WARNING = (
    "引擎进入 active 只说明它认为模拟请求下发成功，既不等于手机采用了该坐标，"
    "也不代表高血压通知已开通、已生效或已验证。这三件事互相独立，"
    "请勿把前一件当成后一件。"
)

ENGINE_ACTIVE_NOTE = (
    "引擎已接受请求并进入 active。接下来必须在苹果地图里由你确认蓝点是否真的移动——"
    "助手看不到手机屏幕，无法替你判断。"
)

MAP_NOT_ADOPTED_NOTE = (
    "引擎返回 active 不等于手机采用了坐标。地图没变化时，这是手机端的问题，"
    "不是「再点一次 start 就好」的问题。"
)

# ---------------------------------------------------------------- 三态定义

#: 三个互相独立的状态。任何地方都不允许用前一个推断后一个。
STATE_SEPARATION = (
    {
        "key": "engine_active",
        "label": "引擎状态",
        "meaning": "引擎是否建立了会话并下发了模拟请求。",
        "who_can_verify": "助手可以读取。",
    },
    {
        "key": "map_location",
        "label": "手机地图位置",
        "meaning": "iPhone 苹果地图里的蓝点是否真的位于测试点。",
        "who_can_verify": "只有用户看手机才能确认。",
    },
    {
        "key": "health_feature",
        "label": "健康功能状态",
        "meaning": "健康 App 中「高血压通知」卡片是否存在、是否已完成设置。",
        "who_can_verify": "只有用户在健康 App 中才能确认。",
    },
)


# ---------------------------------------------------------------- 健康 App 设置

SETUP_STEPS: tuple[GuideStep, ...] = (
    GuideStep(1, "在 iPhone 打开「健康」App，点右上角头像。", "进入个人中心页面。"),
    GuideStep(2, "进入「健康核对清单」（Health Checklist）。", "能看到体检/健康功能相关的待办卡片。"),
    GuideStep(
        3,
        "找到「高血压通知」（Hypertension Notifications）卡片并点击。",
        "能进入就说明这一项对你的机型/系统/账号是可用的；进不去见下面的「卡片不存在」说明。",
    ),
    GuideStep(
        4,
        "按提示确认年龄、是否曾被诊断高血压、是否妊娠。",
        "如实填写。已确诊高血压或处于妊娠期时该功能不适用，这是 Apple 的医学设计边界。",
    ),
    GuideStep(5, "完成引导并点「完成」。", "卡片状态变为已设置，开始累积数据。"),
    GuideStep(
        6,
        "确认「腕部检测」已开启（Watch App → 密码 → 腕部检测）。",
        "腕部检测关闭时手表无法可靠采集用于分析的数据。",
    ),
)

# 卡片不存在**不是**单一原因的证据。历史版本在这里写「卡片不存在就说明机型、
# 系统或地区不满足」，这对用户是有害的：可能是系统还没刷出卡片、可能是 Apple ID
# 地区、也可能只是这一版系统把入口放在了别的位置。给人一个确定的错误结论，
# 会让他去买新表或者去改账号地区。
CARD_ABSENT_TITLE = "如果找不到「高血压通知」卡片"
CARD_ABSENT_POSSIBLE_CAUSES: tuple[str, ...] = (
    "iPhone 的 iOS 版本或 Apple Watch 的 watchOS 版本低于该功能要求。",
    "手表型号不在 Apple 官方支持范围内（大致为 Series 9 及后续、Ultra 2 及后续，以官方页面为准）。",
    "配对 iPhone 的区域设置或 Apple ID 所属地区尚未开放该功能。",
    "系统刚更新完，卡片可能还没刷新出来；先重启 iPhone 与手表再看一次。",
    "健康核对清单在不同 iOS 版本/语言下位置和名称略有差异，可以在健康 App 里搜一下「高血压」。",
)
CARD_ABSENT_CONCLUSION = (
    "以上原因助手都无法远程判定。请按官方页面逐项核对，不要因为「卡片不存在」"
    "就断定是某一个具体原因，也不要通过改地区、改账号等方式尝试绕过。"
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

OFFICIAL_LINKS: tuple[dict[str, str], ...] = (
    {
        "label": "Apple 支持：使用 Apple Watch 的高血压通知",
        "url": "https://support.apple.com/en-us/117296",
    },
    {
        "label": "Apple：watchOS 功能可用性（按地区）",
        "url": "https://www.apple.com/watchos/feature-availability/",
    },
)

# 用户在健康 App 里可能给出的结果。未知就记未知，不做推断。
HEALTH_ANSWERS: tuple[dict[str, str], ...] = (
    {"value": "setup_done", "label": "卡片存在且我已完成设置"},
    {"value": "card_absent", "label": "找不到「高血压通知」卡片"},
    {"value": "eligibility_blocked", "label": "进入了设置，但系统提示我不符合条件"},
    {"value": "not_checked", "label": "我还没去看 / 现在不方便"},
)


def render(*, engine_active: bool | None = None, location_test_passed: bool | None = None) -> dict[str, object]:
    """生成核验指引。

    ``engine_active`` 只用于调整开场措辞，**绝不**参与任何「功能已开通」的推断。
    ``location_test_passed`` 是历史参数的兼容别名（旧代码/旧脚本仍在传它），
    语义等同 ``engine_active``。
    """
    if engine_active is None:
        engine_active = location_test_passed

    opening = CORE_WARNING
    if engine_active is True:
        opening = ENGINE_ACTIVE_NOTE + CORE_WARNING
    elif engine_active is False:
        opening = (
            "定位请求没有成功下发，请先解决前置检查里的阻断项。"
            "以下是功能本身的核验步骤，与定位结果无关。"
        )

    return {
        "opening": opening,
        "state_separation": [dict(item) for item in STATE_SEPARATION],
        "setup_steps": [step.to_dict() for step in SETUP_STEPS],
        "card_absent": {
            "title": CARD_ABSENT_TITLE,
            "possible_causes": list(CARD_ABSENT_POSSIBLE_CAUSES),
            "conclusion": CARD_ABSENT_CONCLUSION,
        },
        "verification_steps": [step.to_dict() for step in VERIFICATION_STEPS],
        "official_links": [dict(item) for item in OFFICIAL_LINKS],
        "never_claim": [
            "不要把 active 或定位测试结果当作功能开通证据。",
            "不要在健康 App 之外声称功能状态。",
            "不要在用户不满足医疗适用条件时提供任何变通方案。",
        ],
    }


# ---------------------------------------------------------------- 恢复真实位置

RESTORE_PROMPT = (
    "模拟已停止，引擎不再下发坐标。但手机上的真实位置有没有回来，助手看不到——"
    "需要你在苹果地图里确认。多数情况下点一次定位按钮就会恢复；"
    "没恢复再按下面顺序排查，不必一上来就改系统设置。"
)

#: 分级排查步骤。「关闭定位服务约 10 秒」只是其中一环，且带条件。
#:
#: 为什么不再写成「必须执行」：
#: - iOS 的 locationd 确实会缓存最近的定位结果，但缓存失效的实际时机与系统版本、
#:   App 后台状态有关，并非固定需要重启定位服务；
#: - 关闭定位服务会打断正在导航、正在记录轨迹的 App，属于有副作用的操作；
#: - 把它写成通用前置条件，等于让已经恢复的用户去做无谓的破坏性操作。
RESTORE_STEPS: tuple[RestoreStep, ...] = (
    RestoreStep(
        order=1,
        action="打开 iPhone「地图」App，点一下右下角的定位按钮。",
        expect="蓝点回到你实际所在的位置。",
    ),
    RestoreStep(
        order=2,
        action="拔掉 USB 数据线，并确认会话已停止（`python -m assistant status` 显示 idle）。",
        expect="断开调试隧道后，大多数设备会重新按真实 GPS 定位。",
        when="蓝点仍停在测试点",
    ),
    RestoreStep(
        order=3,
        action="关闭「定位服务」总开关，等约 10 秒再打开，然后重开地图点一次定位。",
        expect="强制清空定位缓存并重启定位服务；生效时间因设备和系统版本而异。",
        when="拔线后仍然没有恢复",
        may_break_simulation=True,
    ),
    RestoreStep(
        order=4,
        action="重启 iPhone，再打开地图确认一次。",
        expect="清掉残留的定位会话状态。",
        when="关闭定位服务后仍然没有恢复",
    ),
    RestoreStep(
        order=5,
        action="回到健康 App，确认功能状态与测试前一致。",
        expect="定位测试不应改变健康功能状态。",
    ),
)

RESTORE_CONDITIONAL_NOTE = (
    "「关闭定位服务约 10 秒」是排查链路中的一步，不是所有人都必须做的前置条件。"
    "它可能让当前模拟会话彻底失效，也可能打断正在使用定位的 App——"
    "只在前面几步无效时再用。"
)

RESTORE_CHECKLIST: tuple[str, ...] = (
    "会话已停止（`status` 显示 idle，或终端已退出）。",
    "苹果地图里的蓝点已回到你的真实位置（这一项只能由你自己确认）。",
    "如果蓝点仍停在测试点：先拔线；仍然不对，再考虑关闭定位服务约 10 秒后重开。",
    "健康 App 中的功能状态与测试前一致。",
)

#: 兼容字段：旧版 JSON 里叫 ``restore_force_steps``。
#: 名称保留（下游脚本可能读它），但内容已改为条件化表述。
RESTORE_FORCE_STEPS: tuple[str, ...] = tuple(step.to_line() for step in RESTORE_STEPS)

# 会话自然到期时用户不会执行 stop，也就看不到完整的恢复步骤。
# status 在 idle 状态下补一句，避免「测试跑完了但位置还停在模拟地点」。
IDLE_RESTORE_HINT = (
    "若刚才跑过定位测试，蓝点可能仍停在模拟位置："
    "先在苹果地图里点一次定位；还是不对，再考虑关闭定位服务约 10 秒后重开"
    "（这一步只在点定位无效时才需要）。"
)

# ---------------------------------------------------------------- 地图验证

MAP_ANSWERS: tuple[dict[str, str], ...] = (
    {"value": "moved", "label": "蓝点已经移动到测试点"},
    {"value": "not_moved", "label": "蓝点没有移动"},
    {"value": "unsure", "label": "不确定 / 没看清"},
)

# 地图没动时的条件排查。顺序刻意从「不影响其他 App」到「有副作用」。
MAP_NOT_MOVED_CHECKS: tuple[str, ...] = (
    "确认用的是数据线，不是 Wi-Fi 同步；换一个 USB 口或换一根线再试。",
    "确认 iPhone 已解锁，并且屏幕上没有「是否信任此电脑」的待确认弹窗。",
    "确认 iPhone「设置 → 隐私与安全性 → 定位服务」总开关是打开的，且「地图」允许定位、允许精确位置。",
    "用 `python -m assistant status` 确认会话仍是 active（不是 idle/error）。",
    "在苹果地图里点一下右下角定位按钮，让它重新取一次位置，而不是看旧画面。",
    "地图 App 在后台被系统挂起时可能不刷新：把它从后台完全划掉再打开。",
)

# 把「关定位服务」单列为**可能让模拟失效**的排查项，避免用户以为这是万能药。
MAP_REFRESH_NOTE = (
    "以上都不行时，可以尝试关闭「定位服务」总开关约 10 秒再打开，然后重新点定位。"
    "注意：这一步可能让当前的模拟会话失效（引擎仍显示 active，但手机已不再采用模拟坐标），"
    "属于条件性排查手段，不是所有设备都必须执行的步骤。"
)

# ---------------------------------------------------------------- 引擎消息改写

# 引擎在 idle 时会把 message 写成「已停止，真实定位已恢复」。
# 但这句话助手无法验证——iOS 可能仍在使用缓存的模拟坐标。
# 按本项目的原则，不替用户下没有依据的结论，这里换成可执行的表述。
ENGINE_MESSAGE_REWRITES = {
    "已停止，真实定位已恢复": "模拟已停止；位置是否真的恢复，需按下方提示在手机上确认。",
    "模拟定位已生效": "引擎已下发模拟坐标；手机是否采用，需要在苹果地图里确认。",
}


def rewrite_engine_message(message: str) -> str:
    """把引擎里无法验证的断言换成可核实的表述。"""
    if not message:
        return message
    return ENGINE_MESSAGE_REWRITES.get(message.strip(), message)
