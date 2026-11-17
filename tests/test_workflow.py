"""助手主流程测试：前置检查阻断、启动/停止、不变量。"""

from __future__ import annotations

import json

import pytest
from assistant import compat, guide, preflight
from assistant.adapters.http_engine import HttpLocationEngine
from assistant.workflow import (
    DEFAULT_HOLD_SECONDS,
    MAX_HOLD_SECONDS,
    MIN_HOLD_SECONDS,
    Assistant,
)


def _assistant(url: str) -> Assistant:
    return Assistant(engine_url=url)


# ---------------------------------------------------------------- 前置检查


def test_preflight_passes_with_device(fake_engine):
    _, url = fake_engine
    report = preflight.run(HttpLocationEngine(url), "windows")
    assert report.engine_available is True
    assert report.can_run_location_test is True
    assert report.device is not None


def test_preflight_blocks_without_device(fake_engine):
    state, url = fake_engine
    state.devices = []
    report = preflight.run(HttpLocationEngine(url), "windows")
    assert report.can_run_location_test is False
    usb = next(item for item in report.items if item.key == "usb")
    assert usb.passed is False
    assert "信任" in usb.detail


def test_preflight_blocks_when_engine_down():
    report = preflight.run(HttpLocationEngine("http://127.0.0.1:1"), "windows")
    assert report.engine_available is False
    assert report.can_run_location_test is False


def test_preflight_does_not_block_on_old_ios(fake_engine):
    """定位测试在 iOS 26 以下仍可跑，但必须标注健康功能不可用。"""
    state, url = fake_engine
    state.devices[0]["ios_version"] = "18.5"
    report = preflight.run(HttpLocationEngine(url), "windows")
    assert report.can_run_location_test is True
    item = next(i for i in report.items if i.key == "feature_ios")
    assert item.passed is False
    assert item.blocking is False
    assert "26" in item.detail


def test_preflight_refuses_multi_device_ambiguity(fake_engine):
    state, url = fake_engine
    state.devices.append(
        {"udid": "SECOND-UDID", "name": "Second", "ios_version": "26.1", "model": "iPhone17,1"}
    )
    report = preflight.run(HttpLocationEngine(url), "windows")
    assert report.can_run_location_test is False
    item = next(i for i in report.items if i.key == "single_device")
    assert item.passed is False


def test_preflight_output_hides_udid(fake_engine):
    _, url = fake_engine
    payload = json.dumps(preflight.run(HttpLocationEngine(url), "windows").to_dict())
    assert "00008110-TEST-UDID" not in payload


# ---------------------------------------------------------------- 启动测试


def test_start_uses_fixed_preset_coordinates(fake_engine):
    state, url = fake_engine
    result = _assistant(url).start_test("hk", 120)
    assert result["started"] is True
    assert state.last_payload["latitude"] == pytest.approx(22.2819)
    assert state.last_payload["longitude"] == pytest.approx(114.1588)


def test_start_payload_never_claims_feature_enabled(fake_engine):
    """最关键的不变量：启动成功也必须明确否定因果关系。"""
    _, url = fake_engine
    result = _assistant(url).start_test("us", 60)
    assert result["started"] is True
    assert result["feature_status"] == "unknown_pending_user_verification"
    assert "不代表" in result["location_test_does_not_imply"]
    text = json.dumps(result, ensure_ascii=False)
    assert "已开通" not in text.replace("不代表高血压通知已开通", "")


def test_start_blocked_without_device(fake_engine):
    state, url = fake_engine
    state.devices = []
    result = _assistant(url).start_test("fr", 60)
    assert result["started"] is False
    assert result["blocking_items"]
    assert state.last_payload is None  # 没有向引擎下发任何坐标


def test_start_rejects_unknown_region(fake_engine):
    _, url = fake_engine
    from assistant.adapters.base import AdapterUnavailable

    with pytest.raises(AdapterUnavailable) as excinfo:
        _assistant(url).start_test("tokyo", 60)
    assert "us, hk, fr, jp" in excinfo.value.hint


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(-999, MIN_HOLD_SECONDS), (0, MIN_HOLD_SECONDS), (1, MIN_HOLD_SECONDS), (999999, MAX_HOLD_SECONDS)],
)
def test_hold_seconds_are_clamped(fake_engine, requested, expected):
    """不允许 0 或超长会话——挂着模拟定位有实际风险。"""
    state, url = fake_engine
    _assistant(url).start_test("jp", requested)
    assert state.last_payload["hold_seconds"] == expected


def test_stop_returns_restore_guidance(fake_engine):
    _, url = fake_engine
    assistant = _assistant(url)
    assistant.start_test("jp", 60)
    result = assistant.stop_test()
    assert result["stopped"] is True
    assert "真实位置" in result["restore_prompt"]
    assert len(result["restore_checklist"]) >= 3


def test_full_report_contains_every_required_section(fake_engine):
    _, url = fake_engine
    report = _assistant(url).full_report(compat.UserInputs(watch_family="series10"))
    for key in ("platform", "preflight", "compatibility", "regions", "region_warning", "core_warning"):
        assert key in report
    assert len(report["regions"]) == 4
    assert report["feature_status"] == "unknown_pending_user_verification"


def test_full_report_does_not_start_session(fake_engine):
    state, url = fake_engine
    _assistant(url).full_report()
    assert state.last_payload is None


# ---------------------------------------------------------------- 指引


def test_guide_never_promotes_test_result_to_feature_status():
    payload = guide.render(location_test_passed=True)
    assert "不代表" in payload["opening"]
    text = json.dumps(payload["setup_steps"], ensure_ascii=False)
    assert "健康" in text


def test_guide_states_30_day_window():
    text = json.dumps(guide.render()["verification_steps"], ensure_ascii=False)
    assert "30 天" in text


def test_guide_forbids_bypassing_conditions():
    payload = guide.render()
    joined = " ".join(payload["never_claim"])
    assert "变通方案" in joined


@pytest.mark.parametrize("requested", [-999, 0, 1, 999999])
def test_hold_clamping_is_explained_not_silent(fake_engine, requested):
    """时长被夹到安全区间时必须给出说明。

    静默改写用户请求的时长会让人误以为"设的就是这个值"，
    排查效果时非常误导。
    """
    _, url = fake_engine
    result = _assistant(url).start_test("jp", requested)
    assert result["hold_note"], "被夹取时必须说明原因，不能静默"
    assert str(requested) in result["hold_note"]


def test_hold_within_range_has_no_note(fake_engine):
    """请求值本来就在区间内，不需要画蛇添足的提示。"""
    _, url = fake_engine
    result = _assistant(url).start_test("jp", DEFAULT_HOLD_SECONDS)
    assert result["hold_note"] == ""


def test_max_hold_matches_engine_hard_limit():
    """助手的时长上限不能超过引擎的实际接受范围。

    实测 ios-location-studio 的 POST /api/simulate：
    180 秒返回 200，181 秒返回 HTTP 422（Input should be <= 180）。
    曾把上限写成 1800，导致助手发出注定被拒的请求，用户只看到一段
    Pydantic 英文校验错误。这条测试把契约钉住。
    """
    assert MAX_HOLD_SECONDS <= 180, (
        f"MAX_HOLD_SECONDS={MAX_HOLD_SECONDS} 超过引擎实测上限 180，"
        "会导致 /api/simulate 返回 422"
    )
    assert MIN_HOLD_SECONDS < MAX_HOLD_SECONDS
    assert DEFAULT_HOLD_SECONDS <= MAX_HOLD_SECONDS
