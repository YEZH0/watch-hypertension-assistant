"""兼容性检查测试。

这里承担整个项目最重要的回归保护：
**任何输入组合都不能产出"功能已开通/已生效"的结论。**
"""

from __future__ import annotations

import json

import pytest
from assistant import compat
from assistant.adapters.base import CompatVerdict
from assistant.compat import UserInputs

FULL_PASS = UserInputs(
    watch_family="series10",
    watch_os="26.1",
    ios_version="26.1",
    age=30,
    diagnosed_hypertension=False,
    pregnant=False,
    wrist_detection=True,
)


def test_only_three_verdicts_exist():
    """结论必须是三值，不允许新增"enabled/supported"这类取值。"""
    assert set(CompatVerdict.__args__) == {  # type: ignore[attr-defined]
        "model_unsupported",
        "eligibility_blocked",
        "needs_manual_verification",
    }


def test_full_pass_still_not_claimed_as_enabled():
    """条件全满足，结论也只能是"需人工核验"。"""
    report = compat.check(FULL_PASS)
    assert report.verdict == "needs_manual_verification"
    assert not report.blockers
    assert not report.unknowns
    assert "已开通" not in report.headline
    assert "已生效" not in report.headline


def test_no_enabled_field_in_serialised_report():
    """序列化结果里不允许出现任何"已启用"语义的键。"""
    payload = json.dumps(compat.check(FULL_PASS).to_dict(), ensure_ascii=False)
    lowered = payload.lower()
    for word in ("enabled", "activated", "已开通", "已生效", "已启用"):
        assert word not in lowered


@pytest.mark.parametrize("family", ["se2", "se3", "series8", "ultra1"])
def test_unsupported_hardware_is_blocked(family):
    report = compat.check(UserInputs(watch_family=family, watch_os="26.1", ios_version="26.1"))
    assert report.verdict == "model_unsupported"
    assert report.blockers


def test_old_watch_os_is_blocked():
    report = compat.check(UserInputs(watch_family="series10", watch_os="25.9", ios_version="26.1"))
    assert report.verdict == "model_unsupported"


def test_old_ios_is_blocked():
    report = compat.check(UserInputs(watch_family="series10", watch_os="26.1", ios_version="18.5"))
    assert report.verdict == "model_unsupported"


@pytest.mark.parametrize(
    "override",
    [
        {"age": 18},
        {"diagnosed_hypertension": True},
        {"pregnant": True},
        {"wrist_detection": False},
    ],
)
def test_medical_eligibility_cannot_be_bypassed(override):
    """医疗适用条件不满足时必须阻断，且向用户明确说明不会提供变通。"""
    inputs = UserInputs(**{**FULL_PASS.__dict__, **override})
    report = compat.check(inputs)
    assert report.verdict == "eligibility_blocked"
    assert report.blockers
    text = json.dumps(report.to_dict(), ensure_ascii=False)
    assert "不会" in text and "绕过" in text


def test_diagnosed_hypertension_mentions_medical_rationale():
    inputs = UserInputs(**{**FULL_PASS.__dict__, "diagnosed_hypertension": True})
    report = compat.check(inputs)
    assert any("医生" in item or "随访" in item for item in report.blockers)


def test_missing_inputs_become_unknowns_not_guesses():
    """没填的项目必须是"未知"，不能被默认值填成"通过"。"""
    report = compat.check(UserInputs())
    assert report.verdict == "needs_manual_verification"
    assert len(report.unknowns) >= 6
    statuses = {item["status"] for item in report.checks}
    assert "pass" not in statuses


def test_unknown_family_is_treated_as_unknown():
    report = compat.check(UserInputs(watch_family="unknown"))
    assert any("不确定" in item or "核对" in item for item in report.unknowns)


def test_series12_and_ultra4_supported_with_hardware_note():
    """新硬件支持，但必须带出"部分地区待审批"的备注，不能只报"支持"。"""
    for family in ("series12", "ultra4"):
        report = compat.check(UserInputs(watch_family=family))
        notes = [c for c in report.checks if c["item"] == "机型备注"]
        assert notes, f"{family} 缺少机型备注"
        assert "监管" in notes[0]["detail"]


def test_report_carries_provenance():
    """兼容性结论必须带核验日期与来源，让用户知道这是快照而非权威。"""
    report = compat.check(FULL_PASS)
    assert report.data_verified_on
    assert len(report.sources) >= 2
    assert any("apple.com" in url for url in report.sources)


def test_version_comparison_handles_patch_and_suffix():
    assert compat._version_tuple("26.1.2") == (26, 1, 2)
    assert compat._version_tuple("26") == (26,)
    assert compat._version_tuple(None) is None
    assert compat._version_at_least("26.0", "26.0") is True
    assert compat._version_at_least("26", "26.0") is True


def test_never_returns_diagnostic_claim():
    """本功能是筛查提醒而非诊断，报告里不应出现诊断性表述。"""
    report = compat.check(FULL_PASS)
    text = json.dumps(report.to_dict(), ensure_ascii=False)
    assert "确诊你" not in text
    assert "诊断为高血压" not in text or "未被诊断" in text
