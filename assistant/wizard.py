"""阶段化引导向导（第 0–8 步）。

为什么需要这个模块
------------------

原有的子命令（``env`` / ``devices`` / ``check`` / ``start`` / ``stop``）每一步都能单独跑，
但**没有任何东西保证它们按正确顺序发生**。真实用户把仓库链接丢给 AI Agent 之后，
最常见的失败形态是：装完、跑完 check、直接 start，然后看到「已启动」四个字就以为完事了，
漏掉手机上那三件必须由人做的事——确认真实位置基线、在苹果地图里确认蓝点、在健康 App 里核验。

本模块把这段流程固化成 9 个阶段，每个阶段都：

1. 明确告诉用户**现在要在 iPhone 上做什么**；
2. 停下来等待一个**明确的**回答（不是「继续」这种含糊确认）；
3. 把回答记下来，且**绝不用前一个状态推断后一个状态**。

三个互相独立的状态，任何地方都不许互相推导：

===============  ==================================  ==========================
状态              含义                                谁能确认
===============  ==================================  ==========================
engine_active    引擎建立了会话并下发了模拟请求       助手可以读取
map_location     苹果地图里的蓝点是否真在测试点       只有用户看手机
health_feature   健康 App 里卡片是否存在/是否已设置   只有用户在健康 App 里看
===============  ==================================  ==========================

可继续 / 可中止
--------------

进度保存在工作目录下的 ``.whc-wizard-state.json``。里面**只**有流程位置与
用户自述的核验结论，**不保存**年龄、诊断、妊娠状态、经纬度、设备标识符。

- 中断后重新执行 ``python -m assistant wizard`` 从上次停下的阶段继续；
- ``python -m assistant wizard --reset`` 清空进度；
- 任何时候 Ctrl+C、异常退出，都会尽力调用引擎 ``stop`` 并打印恢复指引。
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import compat, guide, regions, textui
from .adapters.base import AdapterError
from .workflow import DEFAULT_HOLD_SECONDS, FEATURE_STATUS_UNVERIFIED, Assistant

STATE_VERSION = 1
STATE_FILENAME = ".whc-wizard-state.json"

# 退出码：与 cli 其它子命令的语义保持一致，便于脚本/Agent 判断。
EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_USAGE = 2
EXIT_DECLINED = 3
EXIT_INTERRUPTED = 130


class WizardError(RuntimeError):
    """用法错误：阶段顺序不对、回答不属于该阶段的可选项等。"""


class _UserAbort(RuntimeError):
    """用户在交互模式下主动退出（输入 q 或 Ctrl+D）。"""


# ---------------------------------------------------------------- 阶段定义


@dataclass(frozen=True)
class StageSpec:
    id: str
    index: int
    title: str
    goal: str
    answers: tuple[str, ...] = ()
    requires_engine: bool = False
    touches_location: bool = False


STAGES: tuple[StageSpec, ...] = (
    StageSpec(
        "safety",
        0,
        "安全与资格告知",
        "说明影响范围，并按 Apple 官方条件如实核对适用性。",
        ("accept", "decline"),
    ),
    StageSpec(
        "environment",
        1,
        "环境与引擎",
        "确认助手可运行、定位引擎在线。",
        ("ready", "retry"),
        requires_engine=True,
    ),
    StageSpec(
        "usb",
        2,
        "USB 连接",
        "只连接一台 iPhone，并让引擎能看到它。",
        ("connected", "retry"),
        requires_engine=True,
    ),
    StageSpec(
        "baseline",
        3,
        "真实位置基线",
        "在改动任何东西之前，先确认手机现在显示的是你的真实位置。",
        ("confirmed", "not_yet"),
        requires_engine=True,
    ),
    StageSpec(
        "region",
        4,
        "地区测试预设",
        "从四个固定预设里明确选一个，确认之后才下发坐标。",
        ("us", "hk", "fr", "jp"),
        requires_engine=True,
        touches_location=True,
    ),
    StageSpec(
        "simulate",
        5,
        "手机端位置验证",
        "看苹果地图，回答蓝点到底动没动。",
        ("moved", "not_moved", "unsure"),
        requires_engine=True,
    ),
    StageSpec(
        "health",
        6,
        "健康 App 核验",
        "在健康 App 的「健康核对清单」里如实核对功能状态。",
        ("setup_done", "card_absent", "eligibility_blocked", "not_checked"),
        requires_engine=True,
    ),
    StageSpec(
        "restore",
        7,
        "停止与恢复",
        "停止模拟，并确认真实位置已回来。",
        ("restored", "not_restored", "unresolved"),
        requires_engine=True,
        touches_location=True,
    ),
    StageSpec(
        "report",
        8,
        "汇报",
        "把每一层的真实状态分开报告，不合并成一个「成功」。",
    ),
)

STAGE_INDEX: dict[str, StageSpec] = {stage.id: stage for stage in STAGES}
STAGE_ORDER: tuple[str, ...] = tuple(stage.id for stage in STAGES)

# 每个阶段的可选项 -> 中文标签。标签就是给用户看的按钮文字。
ANSWER_LABELS: dict[str, dict[str, str]] = {
    "safety": {
        "accept": "我已阅读上述说明，并已完成资格核对，继续",
        "decline": "我明白了，现在退出（不做任何定位改动）",
    },
    "environment": {
        "ready": "引擎已在线，继续",
        "retry": "我处理过了，重新检查一次",
    },
    "usb": {
        "connected": "手机已用数据线连好、已解锁、已点信任",
        "retry": "我处理过了，重新检查一次",
    },
    "baseline": {
        "confirmed": "我已确认：地图蓝点就是我的真实位置",
        "not_yet": "还没确认 / 蓝点不在我的真实位置",
    },
    "region": {
        "us": "美国 · 纽约（us）",
        "hk": "中国香港 · 中环（hk）",
        "fr": "法国 · 巴黎（fr）",
        "jp": "日本 · 东京（jp）",
    },
    "simulate": {item["value"]: item["label"] for item in guide.MAP_ANSWERS},
    "health": {item["value"]: item["label"] for item in guide.HEALTH_ANSWERS},
    "restore": {
        "restored": "我已确认：地图蓝点回到我的真实位置",
        "not_restored": "蓝点还在测试点，我要继续排查",
        "unresolved": "我试过了但位置仍不对，如实记为「未恢复」并继续汇报",
    },
    "report": {},
}


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _fresh_state() -> dict[str, Any]:
    """新建进度。

    隐私约束写在这里：不存年龄、诊断、妊娠状态、经纬度、设备标识符。
    只存「流程走到哪」和「用户自述的核验结论」。
    """
    return {
        "version": STATE_VERSION,
        "stage": "safety",
        "completed": [],
        "notice_accepted": False,
        "eligibility_verdict": None,
        "engine_available": None,
        "device_seen": None,
        "region": None,
        "engine_active": None,
        "session_remaining": None,
        "started_at": None,
        "map_verification": None,
        "health_result": None,
        "stop_ok": None,
        "session_expired": None,
        "restore_result": None,
        "aborted": None,
        "updated_at": _now(),
    }


# ---------------------------------------------------------------- 向导


@dataclass
class Wizard:
    """阶段化向导。

    ``assistant`` 由调用方注入，测试里可以塞一个指向假引擎的实例。
    """

    assistant: Assistant
    state_path: Path
    inputs: compat.UserInputs = field(default_factory=compat.UserInputs)
    hold_seconds: int = DEFAULT_HOLD_SECONDS
    _state: dict[str, Any] | None = field(default=None, repr=False)

    # ------------------------------------------------------------ 状态文件

    @property
    def state(self) -> dict[str, Any]:
        if self._state is None:
            self._state = self._load()
        return self._state

    def _load(self) -> dict[str, Any]:
        """读取进度。文件损坏时**不猜**，直接从头开始并保留旧文件。"""
        try:
            raw = self.state_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return _fresh_state()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return _fresh_state()
        if not isinstance(payload, dict) or payload.get("version") != STATE_VERSION:
            return _fresh_state()
        if payload.get("stage") not in STAGE_INDEX:
            return _fresh_state()
        merged = _fresh_state()
        merged.update({k: v for k, v in payload.items() if k in merged})
        return merged

    def save(self) -> None:
        self.state["updated_at"] = _now()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def reset(self) -> None:
        self._state = _fresh_state()
        with contextlib.suppress(FileNotFoundError):
            self.state_path.unlink()

    @property
    def current_stage(self) -> StageSpec:
        return STAGE_INDEX[self.state["stage"]]

    # ------------------------------------------------------------ 只读视图

    def _public_state(self) -> dict[str, Any]:
        return {
            "stage": self.state["stage"],
            "stage_index": self.current_stage.index,
            "total_stages": len(STAGES) - 1,
            "completed": list(self.state["completed"]),
            "eligibility_verdict": self.state["eligibility_verdict"],
            "engine_available": self.state["engine_available"],
            "device_seen": self.state["device_seen"],
            "region": self.state["region"],
            "engine_active": self.state["engine_active"],
            "session_remaining": self.state["session_remaining"],
            "map_verification": self.state["map_verification"],
            "health_result": self.state["health_result"],
            "stop_ok": self.state["stop_ok"],
            "session_expired": self.state["session_expired"],
            "restore_result": self.state["restore_result"],
            "aborted": self.state["aborted"],
            "started_at": self.state["started_at"],
            "updated_at": self.state["updated_at"],
            "feature_status": FEATURE_STATUS_UNVERIFIED,
        }

    def plan(self) -> dict[str, Any]:
        """整个 0–8 流程的机器可读描述。只读，不碰引擎。"""
        return {
            "feature_status": FEATURE_STATUS_UNVERIFIED,
            "state_file": str(self.state_path),
            "privacy_note": (
                "进度文件只保存流程位置与用户自述结论；"
                "不保存年龄、诊断、妊娠状态、经纬度或设备标识符。"
            ),
            "state_separation": [dict(item) for item in guide.STATE_SEPARATION],
            "stages": [
                {
                    "id": stage.id,
                    "index": stage.index,
                    "title": stage.title,
                    "goal": stage.goal,
                    "answers": [
                        {"value": value, "label": ANSWER_LABELS.get(stage.id, {}).get(value, value)}
                        for value in stage.answers
                    ],
                    "requires_engine": stage.requires_engine,
                    "touches_location": stage.touches_location,
                }
                for stage in STAGES
            ],
            "usage": {
                "interactive": "python -m assistant wizard",
                "describe": "python -m assistant wizard --json",
                "answer": "python -m assistant wizard --answer <value> [--json]",
                "status": "python -m assistant wizard --status --json",
                "reset": "python -m assistant wizard --reset",
            },
            "core_warning": guide.CORE_WARNING,
            "official_links": [dict(item) for item in guide.OFFICIAL_LINKS],
        }

    def status(self) -> dict[str, Any]:
        """进度快照：走到哪一步、已记录什么、要不要继续。"""
        payload: dict[str, Any] = {
            "state_file": str(self.state_path),
            "state": self._public_state(),
            "finished": self.state["stage"] == "report",
            "awaiting_stage": None if self.state["stage"] == "report" else self.state["stage"],
            "feature_status": FEATURE_STATUS_UNVERIFIED,
        }
        payload["report"] = self.report() if self.state["stage"] == "report" else None
        return payload

    # ------------------------------------------------------------ 当前阶段说明

    def _live_remaining(self, stage: StageSpec) -> float | None:
        """实时的会话剩余秒数；只有 simulate / health 阶段才去问引擎。

        返回值约定：
        - ``None``：读不到（引擎掉线、本阶段没有会话），调用方不得编造秒数；
        - ``> 0``：仍在保持的剩余时间；
        - ``<= 0``：会话已经不在 active，告诉用户"已结束"而不是"还剩 0 秒"。
        """
        if stage.id not in ("simulate", "health"):
            return None
        try:
            snapshot = self.assistant.session()
        except AdapterError:
            return None
        if snapshot.state != "active":
            return 0.0
        return snapshot.remaining if snapshot.remaining is not None else None

    def _instructions(
        self, stage: StageSpec, remaining: float | None = None
    ) -> tuple[list[str], list[str], list[str]]:
        """返回 (要做的事, 注意事项, 助手这边会做什么)。

        说明文字必须真实可执行。写「请检查网络」这种正确但无用的句子，
        等于什么都没说。

        ``remaining`` 必须由调用方实时读取后传入（只有 simulate / health 阶段有意义）。
        不要退回读进度文件里的 ``session_remaining``：那是下发那一刻的快照，用户
        在健康 App 里花上几分钟后它早已过期，照着念会给出错的秒数。
        """

        if stage.id == "safety":
            todo = [
                "本工具会临时改变 iPhone 报告的地理位置；依赖位置的 App（地图、外卖、打卡）会受影响。",
                "只在你本人拥有、或已获得机主授权的设备上使用；不要用于他人设备。",
                "下面按 Apple 官方条件核对：机型、系统版本、腕部检测、年龄、是否已确诊高血压、是否妊娠、地区可用性。",
                "如实填写。已确诊高血压或处于妊娠期时该功能不适用，助手不提供任何绕过方式。",
            ]
            notes = [
                "不想继续随时退出：不启动定位、不改动任何设置。",
                "只读检查可以单独用：python -m assistant check / compat / regions。",
            ]
            helper = ["根据你提供的条件给出兼容性结论；结论只有「机型不支持 / 资格不满足 / 需你自己核验」三种。"]
        elif stage.id == "environment":
            todo = [
                "确认电脑已安装 Python 3.11+（python --version）。",
                "确认定位引擎已安装并在运行；不确定就用下面的「重新检查」让助手探测一次。",
            ]
            notes = [
                "助手不会替你去 GitHub 下载并运行任何未经验证的脚本，也不会自动修改系统设置。",
                "引擎不可用时，可以用 --engine-url 指向你手动启动的引擎。",
            ]
            helper = ["调用引擎的 /api/health 探测可用性；不连接设备、不下发坐标。"]
        elif stage.id == "usb":
            todo = [
                "用数据线连接 iPhone（Wi-Fi 连接不行），不要用只能充电的线。",
                "解锁 iPhone，保持屏幕点亮。",
                "手机上弹出「要信任此电脑吗」时点「信任」并输入锁屏密码。",
                "如果引擎提示需要开发者模式：在 iPhone「设置 → 隐私与安全性 → 开发者模式」里自行开启并重启。",
                "只连接一台手机——连多台时助手会拒绝继续，避免改错设备。",
            ]
            notes = ["助手不采集、不显示、不上传设备序列号。"]
            helper = ["调用引擎的 /api/devices 枚举设备，并检查是否只有一台。"]
        elif stage.id == "baseline":
            todo = [
                "iPhone 打开「设置 → 隐私与安全性 → 定位服务」，确认总开关是打开的。",
                "在「定位服务」列表里找到「地图」，确认允许定位、并且「精确位置」是开的。",
                "打开苹果地图 App，点一下右下角的定位按钮。",
                "确认蓝点就在你现在实际待的地方（家/公司/学校），而不是别处。",
            ]
            notes = [
                "这一步是为了拿到「改动前」的对照。没有这个对照，后面就无法判断蓝点是不是真的动了。",
                "蓝点不在真实位置时不要继续：先解决定位权限或等待地图定位完成。",
            ]
            helper = ["什么都不做。此阶段助手只记录你的确认，不发任何坐标。"]
        elif stage.id == "region":
            todo = [
                "下面四个预设是固定的测试点坐标，任选一个。",
                "选定后助手会立即调用引擎下发坐标；这一步会让手机报告的位置改变。",
                "测试点只是一个地理坐标，不是「解锁某个地区功能」的开关。",
            ]
            notes = [
                "不支持自由经纬度输入，这是刻意的限制。",
                "定位坐标与 Apple ID 地区、iPhone 区域设置是两回事，后者才影响功能可用性。",
            ]
            helper = ["调用引擎 /api/simulate 下发所选坐标，并保持会话。"]
        elif stage.id == "simulate":
            todo = [
                "保持 USB 连接，不要拔线。",
                "回到 iPhone，打开苹果地图 App，点一下右下角定位按钮让它重新取位置。",
                "看蓝点：是在测试点，还是仍在你的真实位置？",
                "按实际情况回答——「不确定」也是有效回答，不要为了走完流程而猜。",
            ]
            notes = [
                guide.MAP_NOT_ADOPTED_NOTE,
                "会话按设定时长自动结束（默认 180 秒），到点不会弹任何提示。",
            ]
            if remaining is not None:
                if remaining > 0:
                    notes.append(f"当前会话剩余约 {int(remaining)} 秒。")
                else:
                    notes.append(
                        "会话已经结束（到达时长自动停止是正常的）。蓝点可能仍停在测试点，"
                        "这是 iOS 定位缓存的表现，不影响你如实回答看到的结果。"
                    )
            helper = ["只记录你看到的结果，不做任何推断。"]
        elif stage.id == "health":
            todo = [
                "iPhone 打开「健康」App → 右上角头像 →「健康核对清单」。",
                "找到「高血压通知」并点进去，按系统提示如实填写年龄、是否确诊高血压、是否妊娠。",
                "确认「腕部检测」已开启（Watch App → 密码 → 腕部检测）。",
                "然后回来回答你实际看到的画面。",
            ]
            notes = [
                "无论定位测试成不成功，这一步都要做：功能状态与定位结果无关。",
                "找不到卡片时不要急着下结论——可能原因有多个（版本、型号、地区、卡片未刷新、"
                "菜单位置差异），回答后助手会把它们全部列出来。",
            ]
            if remaining is not None:
                if remaining > 0:
                    notes.append(
                        f"本次模拟会话剩余约 {int(remaining)} 秒；到时间自动停止是正常的，"
                        "不会影响你在健康 App 里的操作。"
                    )
                else:
                    notes.append(
                        "本次模拟会话已经结束（到达时长自动停止是正常的），"
                        "不影响你在健康 App 里继续核验。"
                    )
            helper = ["在你回答后立即停止模拟会话并进入恢复阶段。"]
        elif stage.id == "restore":
            todo = [
                "打开苹果地图，点一下定位按钮，看蓝点是否回到你的真实位置。",
                "如果还在测试点，按助手给出的顺序排查，不必一上来就改系统设置。",
                "确认后如实回答；没恢复就回答没恢复，助手会记成「未确认」。",
            ]
            notes = [
                guide.RESTORE_CONDITIONAL_NOTE,
                "助手无法读取手机的定位状态，所以这一项只能由你确认。",
            ]
            helper = ["调用引擎 /api/stop 停止会话；这只能保证引擎不再下发坐标。"]
        else:  # report
            todo = ["流程结束。请核对下面的分项报告，任何「未知」都不要自己脑补成「成功」。"]
            notes = [guide.CORE_WARNING]
            helper = []

        return todo, notes, helper

    def describe(self, stage_id: str | None = None) -> dict[str, Any]:
        """当前阶段（或指定阶段）的完整说明。只读，可反复调用。"""
        stage = STAGE_INDEX[stage_id or self.state["stage"]]
        todo, notes, helper = self._instructions(stage, remaining=self._live_remaining(stage))
        answers = [
            {
                "value": value,
                "label": ANSWER_LABELS.get(stage.id, {}).get(value, value),
                "answer_command": f"python -m assistant wizard --answer {value}",
            }
            for value in stage.answers
        ]
        payload: dict[str, Any] = {
            "stage": stage.id,
            "stage_index": stage.index,
            "total_stages": len(STAGES) - 1,
            "title": stage.title,
            "goal": stage.goal,
            "requires_engine": stage.requires_engine,
            "touches_location": stage.touches_location,
            "instructions": todo,
            "notes": notes,
            "assistant_actions": helper,
            "answers": answers,
            "awaiting_user": True,
            "state": self._public_state(),
            "feature_status": FEATURE_STATUS_UNVERIFIED,
        }
        if stage.id == "report":
            payload["awaiting_user"] = False
            payload["report"] = self.report()
        return payload

    # ------------------------------------------------------------ 提交回答

    def submit(self, answer: str, stage_id: str | None = None) -> dict[str, Any]:
        """提交当前阶段的回答并推进。

        阶段顺序是硬约束：只能回答当前阶段。传了 ``stage_id`` 但与当前不一致时
        抛 ``WizardError``，并把当前阶段告诉调用方，而不是悄悄按当前阶段执行。
        """
        current = self.state["stage"]
        if stage_id is not None and stage_id != current:
            raise WizardError(
                f"当前阶段是 {current}（第 {self.current_stage.index} 步），"
                f"不能回答 {stage_id}。先运行 `python -m assistant wizard --json` 看当前阶段。"
            )
        stage = self.current_stage
        if stage.id == "report":
            raise WizardError("流程已结束。要重新开始请运行 `python -m assistant wizard --reset`。")

        normalized = (answer or "").strip().lower()
        if normalized not in stage.answers:
            allowed = " / ".join(
                f"{value}（{ANSWER_LABELS.get(stage.id, {}).get(value, value)}）"
                for value in stage.answers
            )
            raise WizardError(f"阶段 {stage.id} 不接受回答 {answer!r}；可选：{allowed}")

        handler = getattr(self, f"_submit_{stage.id}")
        resolution = handler(normalized)
        self.save()
        return resolution

    # ------------------------------------------------------------ 各阶段处理

    def _submit_safety(self, answer: str) -> dict[str, Any]:
        if answer == "decline":
            self.state["aborted"] = "user_declined_at_notice"
            return self._resolution(
                "declined",
                "你选择了退出。助手没有启动任何定位会话，手机上不会发生任何变化。",
                notes=[
                    "想单独做只读检查：python -m assistant check",
                    "想看健康 App 的核验步骤：python -m assistant guide",
                ],
                exit_code=EXIT_DECLINED,
            )

        report = compat.check(self.inputs)
        self.state["eligibility_verdict"] = report.verdict

        if report.verdict == "eligibility_blocked":
            # 医疗适用条件是 Apple 的边界，不是技术限制。这里不提供任何绕行路径。
            return self._resolution(
                "blocked",
                "按你提供的条件，不满足该功能的医疗适用要求，因此不会进入定位测试阶段。",
                items=[{"title": "阻断项", "detail": text, "blocking": True} for text in report.blockers],
                notes=[
                    "这不是技术问题，改定位、改系统版本都不会改变这个结论。",
                    "只读检查仍然可用：python -m assistant compat / check / guide",
                ],
                exit_code=EXIT_BLOCKED,
            )

        self.state["notice_accepted"] = True
        extra_notes: list[str] = []
        extra_warnings: list[str] = []
        if report.verdict == "model_unsupported":
            # 机型/系统不支持功能，但定位链路测试本身仍然有意义，允许继续。
            extra_warnings.append(
                "机型或系统不在该功能的支持范围内：即使定位测试成功，健康 App 里也不会出现该功能。"
                "继续只是为了验证定位链路。"
            )
        if report.unknowns:
            # 逐条列出而不是拼成一大段：这些是用户要自己去补的信息，一条一行才看得清。
            extra_notes.extend(f"待确认（助手不替你猜）：{text}" for text in report.unknowns)

        return self._advance(
            "environment",
            notes=extra_notes,
            warnings=extra_warnings,
            extra={"compatibility": report.to_dict()},
        )

    def _submit_environment(self, answer: str) -> dict[str, Any]:
        env = self.assistant.environment()
        engine = env["engine"]
        self.state["engine_available"] = bool(engine.get("available"))
        if not engine.get("available"):
            return self._resolution(
                "blocked",
                "定位引擎当前不可用，先不继续。",
                items=[
                    {
                        "title": "引擎",
                        "detail": engine.get("detail") or "无法连接引擎",
                        "blocking": True,
                    }
                ]
                + (
                    [{"title": "建议", "detail": engine["hint"], "blocking": False}]
                    if engine.get("hint")
                    else []
                ),
                notes=[
                    "引擎是独立项目，本仓库不含它，也不会自动替你安装。",
                    "已经手动启动引擎的话，用 --engine-url http://127.0.0.1:8899 指过来。",
                ],
                exit_code=EXIT_BLOCKED,
            )
        return self._advance("usb", extra={"engine": engine})

    def _submit_usb(self, answer: str) -> dict[str, Any]:
        try:
            inventory = self.assistant.engine.list_devices()
        except AdapterError as exc:
            return self._resolution(
                "blocked",
                "无法枚举 USB 设备。",
                items=[{"title": "引擎", "detail": str(exc), "blocking": True}],
                exit_code=EXIT_BLOCKED,
            )

        if not inventory.devices:
            return self._resolution(
                "blocked",
                "没有检测到 iPhone，先停在这一步排查。",
                items=[
                    {
                        "title": "USB 设备",
                        "detail": inventory.error or "未检测到设备",
                        "blocking": True,
                    }
                ],
                notes=[
                    "用数据线，不要用 Wi-Fi。",
                    "手机要解锁；弹「信任此电脑」时点信任。",
                    "换一个 USB 口或换一根线再试。",
                    "设备可见之前不会下发任何坐标。",
                ],
                exit_code=EXIT_BLOCKED,
            )

        if len(inventory.devices) > 1:
            return self._resolution(
                "blocked",
                f"检测到 {len(inventory.devices)} 台设备，助手不会替你挑一台。",
                items=[
                    {
                        "title": "设备数量",
                        "detail": "请只保留目标 iPhone，拔掉其它设备后重试",
                        "blocking": True,
                    }
                ],
                notes=["改错手机的代价比多插拔一次大，所以这里直接拒绝。"],
                exit_code=EXIT_BLOCKED,
            )

        device = inventory.devices[0]
        self.state["device_seen"] = device.to_public_dict()
        return self._advance("baseline", extra={"device": device.to_public_dict()})

    def _submit_baseline(self, answer: str) -> dict[str, Any]:
        if answer != "confirmed":
            return self._resolution(
                "awaiting_user",
                "尚未确认真实位置基线，因此不会下发任何坐标。",
                notes=[
                    "先在苹果地图里点定位按钮，确认蓝点在你实际所在的位置。",
                    "如果蓝点不在真实位置：检查「定位服务」总开关、地图的定位权限，以及是否刚重启过还没定位。",
                ],
            )
        return self._advance("region")

    def _submit_region(self, answer: str) -> dict[str, Any]:
        # 双重保险：即使状态文件被手工改写，也不允许资格不满足的人进入定位阶段。
        if self.state.get("eligibility_verdict") == "eligibility_blocked":
            return self._resolution(
                "blocked",
                "资格核对结论为不满足适用要求，拒绝下发坐标。",
                exit_code=EXIT_BLOCKED,
            )

        preset_ids = [preset.id for preset in regions.presets()]
        if answer not in preset_ids:
            raise WizardError(f"未知地区预设 {answer!r}；可选：{', '.join(preset_ids)}")

        result = self.assistant.start_test(answer, self.hold_seconds)
        if not result["started"]:
            return self._resolution(
                "blocked",
                "引擎没有接受这次定位请求，会话未建立。",
                items=[
                    {
                        "title": item.get("title", "阻断项"),
                        "detail": item.get("detail", ""),
                        "blocking": True,
                    }
                    for item in result.get("blocking_items", [])
                ],
                notes=[result.get("reason") or "引擎未进入 active 状态"],
                exit_code=EXIT_BLOCKED,
            )

        session = result.get("session") or {}
        self.state["region"] = answer
        self.state["engine_active"] = True
        self.state["session_remaining"] = session.get("remaining")
        self.state["started_at"] = _now()

        notes = [preset_note for preset_note in (result.get("hold_note"),) if preset_note]
        notes.append("现在去手机上看地图。引擎说 active 只代表请求下发成功。")
        return self._advance(
            "simulate",
            notes=notes,
            warnings=[guide.MAP_NOT_ADOPTED_NOTE],
            extra={"region": result["region"], "session": session},
        )

    def _submit_simulate(self, answer: str) -> dict[str, Any]:
        self.state["map_verification"] = answer
        notes: list[str] = []
        warnings: list[str] = []

        if answer == "moved":
            notes.append("已记录：你确认蓝点移动到了测试点。这仍然是你的目视结论，不是助手测出来的。")
        elif answer == "not_moved":
            warnings.append(guide.MAP_NOT_ADOPTED_NOTE)
            notes.extend(guide.MAP_NOT_MOVED_CHECKS)
            notes.append(guide.MAP_REFRESH_NOTE)
        else:
            warnings.append("你选择了「不确定」。助手会把这一项记为未核验，不会当作成功。")
            notes.extend(guide.MAP_NOT_MOVED_CHECKS[:3])
            notes.append("可以回地图再点一次定位按钮，看清楚蓝点位置后再回答。")

        notes.append("下一步与定位结果无关：无论蓝点动没动，都要去健康 App 核验功能状态。")
        return self._advance("health", notes=notes, warnings=warnings)

    def _submit_health(self, answer: str) -> dict[str, Any]:
        self.state["health_result"] = answer

        notes: list[str] = []
        warnings: list[str] = []

        if answer == "setup_done":
            notes.append(
                "已记录：你自述已完成设置。设置完成不等于已生效，也不等于已产生提醒——"
                "需要佩戴满 30 天、其中至少 14 天有效数据才可能出首次提醒。"
            )
        elif answer == "card_absent":
            warnings.append(guide.CARD_ABSENT_TITLE + "：助手无法远程判定原因，以下都是可能项。")
            notes.extend(guide.CARD_ABSENT_POSSIBLE_CAUSES)
            notes.append(guide.CARD_ABSENT_CONCLUSION)
        elif answer == "eligibility_blocked":
            warnings.append("系统在设置过程中提示你不符合条件，这是 Apple 的医疗适用边界。")
            notes.append("助手不提供绕过方式；已确诊高血压请按医生建议用血压计记录与随访。")
        else:
            notes.append("你还没核验。这一项会记为未核验，不会被填成「已开通」。")

        notes.append("官方依据：" + "；".join(f"{item['label']} {item['url']}" for item in guide.OFFICIAL_LINKS))

        # 进入恢复阶段前先结束会话：无论定位测试结果如何都要清理。
        expired = None
        cleanup_ok: bool | None = None
        before_state = None
        try:
            before_state = self.assistant.session().state
        except AdapterError as exc:
            warnings.append(f"无法读取会话状态（{exc}），将直接尝试停止。")
        if before_state is not None:
            expired = before_state != "active"
            if expired:
                notes.append(
                    f"会话在你核验期间已结束（当前 {before_state}），这是时长到期的正常结果，"
                    "不影响你已经看到的健康 App 状态。"
                )

        cleanup = self.assistant.safe_stop()
        cleanup_ok = bool(cleanup["ok"])
        if cleanup_ok and not expired:
            # 用户答完这一阶段就被要求去看地图。不告诉他"已经停了"，
            # 他会以为模拟还在跑，或者反过来以为停了就会自动恢复。
            # expired 为真时上面已经说过会话结束了，不必重复。
            notes.append(
                "模拟会话已停止（引擎已无活跃会话）。这只保证引擎不再下发坐标；"
                "手机上蓝点是否回去，仍需你去地图确认。"
            )
        else:
            warnings.append(
                f"停止会话失败（{cleanup.get('error')}）。引擎可能仍在保持模拟，"
                "请手动再运行一次 python -m assistant stop。"
            )

        self.state["session_expired"] = expired
        self.state["stop_ok"] = cleanup_ok

        return self._advance(
            "restore",
            notes=notes,
            warnings=warnings,
            extra={"health_result": answer, "stop": cleanup.get("result")},
        )

    def _submit_restore(self, answer: str) -> dict[str, Any]:
        if answer == "not_restored":
            self.state["restore_result"] = "not_confirmed"
            notes = [step.action if not step.when else f"如果{step.when}：{step.action}" for step in guide.RESTORE_STEPS]
            return self._resolution(
                "awaiting_user",
                "已记为「未确认恢复」。按下面的顺序排查，然后重新回答。",
                notes=notes,
                warnings=[guide.RESTORE_CONDITIONAL_NOTE],
            )

        self.state["restore_result"] = "confirmed" if answer == "restored" else "not_confirmed"
        notes = []
        warnings = []
        if answer == "unresolved":
            warnings.append(
                "已如实记为「真实位置未恢复」。这意味着手机可能仍显示测试点位置。"
            )
            notes.extend(
                [
                    "按顺序再来一遍：地图点定位 → 拔掉数据线 → 关闭定位服务约 10 秒再开 → 重启 iPhone。",
                    "如果全部做完仍不恢复，重新运行 python -m assistant stop 再试一次，并检查是否还有别的调试工具占用设备。",
                ]
            )
        else:
            notes.append("已记录你的确认。这一项只能由你在手机上判断，助手无法验证。")
        return self._advance("report", notes=notes, warnings=warnings)

    # ------------------------------------------------------------ 汇报

    def report(self) -> dict[str, Any]:
        """分项报告。**不存在**「整体成功」这个字段。"""
        state = self.state

        def _cn_engine() -> str:
            if state["engine_available"] is None:
                return "未知（未执行环境检查）"
            return "在线" if state["engine_available"] else "不可用"

        def _cn_simulation() -> str:
            if state["region"] is None:
                return "未下发（流程未到地区测试阶段）"
            base = f"引擎已接受过模拟请求（active），测试点 {state['region']}"
            # 报告大多是在流程末尾生成的，那时会话早该结束了。
            # 只写「引擎已接受（active）」会被读成「现在还 active」，必须带上现状。
            if state["stop_ok"] is True:
                return base + "；会话已停止"
            if state["session_expired"]:
                return base + "；会话已到期结束"
            if state["stop_ok"] is False:
                return base + "；停止失败，可能仍在保持模拟，请手动 stop"
            return base + "；会话是否已停止未确认"

        def _cn_map() -> str:
            mapping = {
                "moved": "用户确认蓝点已移动到测试点",
                "not_moved": "用户确认蓝点没有移动",
                "unsure": "用户不确定（记为未核验）",
            }
            return mapping.get(state["map_verification"], "未知（未核验）")

        def _cn_health() -> str:
            mapping = {
                "setup_done": "用户自述已完成设置（不等于已生效）",
                "card_absent": "用户报告找不到卡片（原因未知）",
                "eligibility_blocked": "系统提示不符合适用条件",
                "not_checked": "未核验",
            }
            return mapping.get(state["health_result"], "未知（未核验）")

        def _cn_restore() -> str:
            if state["restore_result"] == "confirmed":
                return "用户确认已恢复真实位置"
            if state["restore_result"] == "not_confirmed":
                return "未确认恢复（可能仍显示测试点）"
            return "未知（未确认）"

        lines = [
            f"引擎：{_cn_engine()}",
            f"模拟请求：{_cn_simulation()}",
            f"手机地图位置：{_cn_map()}",
            f"健康 App 功能：{_cn_health()}",
            f"真实位置恢复：{_cn_restore()}",
        ]

        return {
            "generated_at": _now(),
            "engine": {
                "available": state["engine_available"],
                "label": _cn_engine(),
            },
            "device": {
                "seen": state["device_seen"],
                "count": 1 if state["device_seen"] else 0,
            },
            "simulation": {
                "region": state["region"],
                "engine_active": state["engine_active"],
                "label": _cn_simulation(),
            },
            "map": {
                "result": state["map_verification"],
                "verified_by": "user" if state["map_verification"] else None,
                "label": _cn_map(),
            },
            "health": {
                "result": state["health_result"],
                "verified_by": "user" if state["health_result"] else None,
                "label": _cn_health(),
            },
            "restore": {
                "stop_ok": state["stop_ok"],
                "session_expired": state["session_expired"],
                "result": state["restore_result"],
                "label": _cn_restore(),
            },
            "lines": lines,
            "completed_stages": list(state["completed"]),
            "aborted": state["aborted"],
            # 唯一允许出现的功能状态。
            "feature_status": FEATURE_STATUS_UNVERIFIED,
            "disclaimer": (
                "第 3–5 项（地图、健康 App、位置恢复）均为用户自述，助手无法独立验证。"
                "本报告不构成「高血压通知已开通 / 已生效」的结论。"
            ),
            "core_warning": guide.CORE_WARNING,
        }

    # ------------------------------------------------------------ 内部工具

    def _advance(
        self,
        next_stage: str,
        *,
        notes: list[str] | None = None,
        warnings: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.state["stage"]
        if current not in self.state["completed"]:
            self.state["completed"].append(current)
        self.state["stage"] = next_stage
        resolution = self._resolution(
            "advanced",
            f"第 {STAGE_INDEX[current].index} 步（{STAGE_INDEX[current].title}）已完成。",
            notes=notes,
            warnings=warnings,
            extra=extra,
        )
        return resolution

    def _resolution(
        self,
        outcome: str,
        message: str,
        *,
        items: list[dict[str, Any]] | None = None,
        notes: list[str] | None = None,
        warnings: list[str] | None = None,
        extra: dict[str, Any] | None = None,
        exit_code: int = EXIT_OK,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "accepted": outcome == "advanced",
            "outcome": outcome,
            "message": message,
            "stage": self.state["stage"],
            "items": items or [],
            "notes": notes or [],
            "warnings": warnings or [],
            "exit_code": exit_code,
            "state": self._public_state(),
            "feature_status": FEATURE_STATUS_UNVERIFIED,
        }
        if extra:
            payload["details"] = extra
        if self.state["stage"] == "report":
            payload["report"] = self.report()
            # 流程终点同样要给出「下一步」，否则 --answer 的最后一次调用只打印
            # 「第 7 步已完成」就退出，用户得再跑一次 --status 才看得到报告——
            # 真机实测时就是这样掉进空白的。describe() 在这里返回的就是报告本身。
            payload["next"] = self.describe()
            payload["exit_code"] = EXIT_OK
        else:
            payload["next"] = self.describe()
        return payload

    # ------------------------------------------------------------ 中断清理

    def emergency_cleanup(self) -> dict[str, Any]:
        """Ctrl+C / 异常 / 用户取消时的收尾。

        两种情况下必须真的去 stop：
        - 已经下发过坐标（``region`` 已记录）；
        - 当前阶段在 simulate / health / restore 之间。

        其它阶段没有会话，不去打扰引擎。
        """
        needs_stop = bool(self.state.get("region")) or self.state["stage"] in (
            "simulate",
            "health",
            "restore",
        )
        if not needs_stop:
            self.state["aborted"] = self.state["aborted"] or "aborted_before_location_change"
            return {"stopped_attempted": False, "ok": True, "restore": None}

        result = self.assistant.safe_stop()
        self.state["stop_ok"] = bool(result["ok"])
        self.state["aborted"] = self.state["aborted"] or "aborted_with_active_session"
        if self.state["restore_result"] is None:
            self.state["restore_result"] = "not_confirmed"
        return {"stopped_attempted": True, "ok": bool(result["ok"]), "restore": result}


# ---------------------------------------------------------------- 终端渲染


def render_description(payload: dict[str, Any], *, interactive: bool) -> None:
    stage = STAGE_INDEX[payload["stage"]]
    textui.section(f"第 {stage.index}/{payload['total_stages']} 步 · {stage.title}")
    print(payload["goal"])
    textui.blank()

    if stage.id == "report":
        render_report(payload["report"])
        return

    if payload["instructions"]:
        print("现在要做的事：")
        for index, item in enumerate(payload["instructions"], 1):
            textui.numbered(index, item)
    if payload.get("assistant_actions"):
        textui.blank()
        print("助手这边：")
        for item in payload["assistant_actions"]:
            textui.bullet(item)
    if payload["notes"]:
        textui.blank()
        print("注意：")
        for item in payload["notes"]:
            textui.bullet(item)

    textui.blank()
    print("可选回答：")
    for index, item in enumerate(payload["answers"], 1):
        textui.numbered(index, f"{item['label']}  ({item['value']})")

    if not interactive:
        textui.blank()
        print("这是需要你确认的节点。确认后运行（把 <value> 换成上面括号里的值）：")
        textui.bullet("python -m assistant wizard --answer <value>")
        textui.blank()
        textui.caption("助手不会跳过这一步自行继续。")


def render_resolution(result: dict[str, Any]) -> None:
    textui.section("结果")
    print(result["message"])

    items = result.get("items") or []
    if items:
        textui.blank()
        for item in items:
            marker = "[阻断]" if item.get("blocking") else "[信息]"
            print(f"  {marker} {item.get('title')}：{item.get('detail')}")

    if result.get("warnings"):
        textui.blank()
        for text in result["warnings"]:
            print(f"! {text}")

    if result.get("notes"):
        textui.blank()
        for text in result["notes"]:
            textui.bullet(text)

    textui.blank()
    textui.caption(result["feature_status"] + " —— 功能状态始终需要用户在健康 App 中核验。")


def render_report(report: dict[str, Any]) -> None:
    textui.section("分项报告")
    for text in report["lines"]:
        print(f"  {text}")
    textui.blank()
    print(report["disclaimer"])
    textui.blank()
    textui.caption(report["core_warning"])


# ---------------------------------------------------------------- 交互模式


def _prompt_choice(payload: dict[str, Any]) -> str:
    """读一个明确的回答。空输入、乱输入都重新问，不猜。"""
    answers = payload["answers"]
    while True:
        try:
            raw = input("请输入编号后回车（q = 退出）：").strip()
        except EOFError as exc:  # 管道被关闭 / Ctrl+Z
            raise _UserAbort from exc
        if raw.lower() in ("q", "quit", "exit"):
            raise _UserAbort
        if raw.isdigit() and 1 <= int(raw) <= len(answers):
            return answers[int(raw) - 1]["value"]
        for item in answers:
            if raw.lower() == item["value"]:
                return item["value"]
        print("没有这个选项。请输入上面列出的编号，或直接输入括号里的英文值。")


def run_interactive(wizard: Wizard) -> int:
    """逐阶段推进的交互循环。

    所有异常都在这里收口：先尽力 stop，再打印恢复指引，最后给出真实退出码。
    绝不出现「崩了但模拟还在跑」的状态。
    """
    try:
        while True:
            payload = wizard.describe()
            render_description(payload, interactive=True)
            if payload["stage"] == "report":
                return EXIT_OK

            answer = _prompt_choice(payload)
            result = wizard.submit(answer)
            render_resolution(result)

            if result["outcome"] == "declined":
                return EXIT_DECLINED
            if result["outcome"] == "blocked":
                print()
                print("这一步没通过，先处理上面的阻断项。处理完按回车重试，或输入 q 退出。")
                try:
                    if input().strip().lower() in ("q", "quit", "exit"):
                        raise _UserAbort
                except EOFError as exc:
                    raise _UserAbort from exc
                continue
            if result["outcome"] == "awaiting_user":
                # 用户回答「还没确认」——不推进，重新问同一个阶段。
                continue
    except _UserAbort:
        # 用户主动输入 q / 关闭输出流：按「取消」处理，退出码 3。
        return _finish_aborted(wizard, EXIT_DECLINED)
    except KeyboardInterrupt:
        return _finish_aborted(wizard, EXIT_INTERRUPTED)
    except Exception as exc:  # noqa: BLE001 - 兜底，保证一定会尝试清理
        print(f"\n出现未预期的错误：{exc}", flush=True)
        return _finish_aborted(wizard, EXIT_BLOCKED)


def _finish_aborted(wizard: Wizard, exit_code: int) -> int:
    textui.section("已中止")
    cleanup = wizard.emergency_cleanup()
    wizard.save()

    if cleanup["stopped_attempted"]:
        if cleanup["ok"]:
            print("已尝试停止定位会话：引擎已进入 idle。")
        else:
            print("停止会话失败，引擎可能仍在保持模拟。请手动运行：python -m assistant stop")

    textui.blank()
    print(guide.RESTORE_PROMPT)
    textui.blank()
    print("按顺序确认（不必每一步都做）：")
    for step in guide.RESTORE_STEPS:
        textui.numbered(step.order, step.to_line())
    textui.blank()
    textui.caption(guide.RESTORE_CONDITIONAL_NOTE)
    textui.blank()
    print("进度已保存，稍后可用 python -m assistant wizard 继续。")
    return exit_code
