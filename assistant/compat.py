"""Apple Watch 高血压通知兼容性检查。

这个模块的核心职责是**如实表达"不知道"**。

工程设计上的两条红线：

1. 不伪造设备兼容性结果。
   助手无法查询用户手表型号、watchOS 版本、是否已被诊断高血压。这些只能由用户
   自报。用户没填，结论就是「未知」，不允许猜。

2. 不把「机型支持」当成「功能已开通」。
   ``CompatVerdict`` 里根本没有 "enabled" 这个取值。即使全部条件都满足，结论也只
   是 ``needs_manual_verification``——必须由用户在 iPhone 健康 App 里亲眼确认。

医疗使用条件（22 岁以上、未确诊高血压、未怀孕、腕部检测开启）是 Apple 设定的
适用边界。本模块只做「如实报告不满足」，不提供任何绕过路径。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .adapters.base import CompatReport

DATA_FILE = Path(__file__).parent / "data" / "watch_compat.json"


@lru_cache(maxsize=1)
def _facts() -> dict:
    with DATA_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


@dataclass(frozen=True)
class UserInputs:
    """全部由用户自报。缺省即未知，不用默认值填补。"""

    watch_family: str | None = None
    watch_os: str | None = None
    ios_version: str | None = None
    age: int | None = None
    diagnosed_hypertension: bool | None = None
    pregnant: bool | None = None
    wrist_detection: bool | None = None


def _version_tuple(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    parts: list[int] = []
    for chunk in str(value).strip().split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or None


def _version_at_least(value: str | None, minimum: str) -> bool | None:
    """三值比较：None 表示无法判断。

    需要把短版本补零，否则 ``(26,) >= (26, 0)`` 在 Python 里是 False，
    会把 "26" 误判成低于 "26.0"。
    """
    actual = _version_tuple(value)
    floor = _version_tuple(minimum)
    if actual is None or floor is None:
        return None
    width = max(len(actual), len(floor))
    padded_actual = actual + (0,) * (width - len(actual))
    padded_floor = floor + (0,) * (width - len(floor))
    return padded_actual >= padded_floor


def _family(family_id: str | None) -> dict | None:
    if not family_id:
        return None
    for item in _facts()["families"]:
        if item["id"] == family_id:
            return item
    return None


def families() -> tuple[dict, ...]:
    return tuple(_facts()["families"])


def check(inputs: UserInputs) -> CompatReport:
    """产出兼容性结论。任何异常输入都只会让结论更保守。"""
    facts = _facts()
    feature = facts["feature"]
    eligibility = facts["eligibility"]
    provenance = facts["provenance"]

    checks: list[dict] = []
    blockers: list[str] = []
    unknowns: list[str] = []

    # ---------------------------------------------------------- 机型
    family = _family(inputs.watch_family)
    if family is None:
        unknowns.append("未提供 Apple Watch 机型，无法判断是否在支持范围内。")
        checks.append({"item": "机型", "status": "unknown", "detail": "未填写"})
    elif family["supported"] is True:
        checks.append({"item": "机型", "status": "pass", "detail": family["label"]})
        if family.get("note"):
            checks.append({"item": "机型备注", "status": "info", "detail": family["note"]})
    elif family["supported"] is False:
        blockers.append(
            f"{family['label']} 不在 Apple 官方支持范围内"
            f"（{family.get('note') or '官方仅支持 Series 9 及后续、Ultra 2 及后续'}）。"
        )
        checks.append({"item": "机型", "status": "fail", "detail": family["label"]})
    else:
        unknowns.append("机型选择为「不确定」，请先在 iPhone 的 Watch App 中核对型号。")
        checks.append({"item": "机型", "status": "unknown", "detail": "待用户核对"})

    # ---------------------------------------------------------- 系统版本
    for label, value, minimum, key in (
        ("watchOS 版本", inputs.watch_os, feature["min_watch_os"], "watchOS"),
        ("iOS 版本", inputs.ios_version, feature["min_ios"], "iOS"),
    ):
        result = _version_at_least(value, minimum)
        if result is None:
            unknowns.append(f"未提供 {label}，无法判断是否满足 {minimum}+ 要求。")
            checks.append({"item": key, "status": "unknown", "detail": "未填写"})
        elif result:
            checks.append({"item": key, "status": "pass", "detail": f"{value} ≥ {minimum}"})
        else:
            blockers.append(f"{label} 为 {value}，低于要求的 {minimum}。")
            checks.append({"item": key, "status": "fail", "detail": f"{value} < {minimum}"})

    # ---------------------------------------------------------- 医疗资格条件
    if inputs.age is None:
        unknowns.append("未提供年龄，无法判断是否满足 22 岁以上要求。")
        checks.append({"item": "年龄", "status": "unknown", "detail": "未填写"})
    elif inputs.age < eligibility["min_age"]:
        blockers.append(
            f"该功能面向 {eligibility['min_age']} 岁及以上用户，当前填写年龄为 {inputs.age} 岁。"
        )
        checks.append({"item": "年龄", "status": "fail", "detail": f"{inputs.age} < 22"})
    else:
        checks.append({"item": "年龄", "status": "pass", "detail": f"{inputs.age} ≥ 22"})

    if inputs.diagnosed_hypertension is None:
        unknowns.append("未说明是否已被诊断高血压，无法判断是否在适用人群内。")
        checks.append({"item": "高血压诊断史", "status": "unknown", "detail": "未填写"})
    elif inputs.diagnosed_hypertension:
        blockers.append(
            "已被诊断高血压的用户不在该功能的目标人群内。Apple 的设计是："
            "已确诊者应使用血压记录与医生随访，而不是这套筛查提醒。助手不会绕过这一条件。"
        )
        checks.append({"item": "高血压诊断史", "status": "fail", "detail": "已确诊"})
    else:
        checks.append({"item": "高血压诊断史", "status": "pass", "detail": "未确诊"})

    if inputs.pregnant is None:
        unknowns.append("未说明是否处于妊娠期，无法判断是否在适用人群内。")
        checks.append({"item": "妊娠状态", "status": "unknown", "detail": "未填写"})
    elif inputs.pregnant:
        blockers.append("妊娠期用户不在该功能的目标人群内，助手不会绕过这一条件。")
        checks.append({"item": "妊娠状态", "status": "fail", "detail": "妊娠期"})
    else:
        checks.append({"item": "妊娠状态", "status": "pass", "detail": "非妊娠期"})

    if inputs.wrist_detection is None:
        unknowns.append("未确认腕部检测是否开启；未开启时该功能不会正常采集数据。")
        checks.append({"item": "腕部检测", "status": "unknown", "detail": "未确认"})
    elif inputs.wrist_detection:
        checks.append({"item": "腕部检测", "status": "pass", "detail": "已开启"})
    else:
        blockers.append("腕部检测未开启，手表无法可靠采集用于分析的心率数据。")
        checks.append({"item": "腕部检测", "status": "fail", "detail": "未开启"})

    # ---------------------------------------------------------- 结论
    verdict, headline, next_steps = _verdict(blockers, unknowns)

    return CompatReport(
        verdict=verdict,
        headline=headline,
        checks=tuple(checks),
        blockers=tuple(blockers),
        unknowns=tuple(unknowns),
        next_steps=next_steps,
        data_verified_on=str(provenance["verified_on"]),
        sources=tuple(provenance["sources"]),
    )


def _verdict(blockers: list[str], unknowns: list[str]) -> tuple[str, str, tuple[str, ...]]:
    if blockers:
        return (
            "model_unsupported" if _only_hardware(blockers) else "eligibility_blocked",
            "当前条件下不满足该功能的适用要求。",
            (
                "先解决上面列出的阻断项；助手不会、也无法绕过这些条件。",
                "如果阻断项与硬件有关，更换设备后再重新运行本检查。",
            ),
        )
    if unknowns:
        return (
            "needs_manual_verification",
            "已填写的信息未见冲突，但仍有项目无法确认，功能状态未知。",
            (
                "补齐上面标注「未填写」的项目后重新运行检查。",
                "最终是否可用，只能在 iPhone 健康 App 的「健康核对清单」里实际确认。",
            ),
        )
    return (
        "needs_manual_verification",
        "机型与资格条件均满足，但功能的实际状态仍然未知。",
        (
            "在 iPhone 打开「健康」App → 头像 →「健康核对清单」→ 高血压通知，完成设置。",
            "设置完成后需要佩戴满 30 天、其中至少 14 天有效数据，才可能产生首次提醒。",
            "功能是否真的在运行，以健康 App 中该卡片的状态为准，而不是以本检查结论为准。",
        ),
    )


_HARDWARE_MARKERS = ("watchOS", "iOS", "不在 Apple 官方支持范围")


def _only_hardware(blockers: list[str]) -> bool:
    """区分「硬件/系统不支持」与「医疗资格不满足」，便于给不同建议。"""
    return all(any(marker in item for marker in _HARDWARE_MARKERS) for item in blockers)
