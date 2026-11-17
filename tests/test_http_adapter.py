"""HTTP 适配器测试：用真实 HTTP 打桩引擎，覆盖请求/解析/错误映射。"""

from __future__ import annotations

import pytest
from assistant.adapters.base import AdapterError, AdapterUnavailable
from assistant.adapters.http_engine import HttpLocationEngine, assert_loopback
from assistant.adapters.registry import create_adapter, detect_platform


def test_probe_reports_online(fake_engine):
    _, url = fake_engine
    status = HttpLocationEngine(url).probe()
    assert status.available is True
    assert status.version == "0.1.0"
    assert status.endpoint == url


def test_probe_reports_offline_without_raising():
    """引擎没起来时必须返回不可用，而不是抛异常把整个检查打断。"""
    status = HttpLocationEngine("http://127.0.0.1:1").probe()
    assert status.available is False
    assert status.detail


def test_devices_are_parsed(fake_engine):
    _, url = fake_engine
    inventory = HttpLocationEngine(url).list_devices()
    assert inventory.connected is True
    assert len(inventory.devices) == 1
    device = inventory.devices[0]
    assert device.ios_version == "26.1"
    assert device.handle  # 内部句柄保留，供引擎回调


def test_public_device_dict_hides_identifier(fake_engine):
    """对外输出必须剥离设备标识符（交付要求：不上传设备识别信息）。"""
    _, url = fake_engine
    public = HttpLocationEngine(url).list_devices().to_public_dict()
    assert "udid" not in public["devices"][0]
    assert "00008110-TEST-UDID" not in str(public)


def test_start_location_sends_preset_payload(fake_engine):
    state, url = fake_engine
    session = HttpLocationEngine(url).start_location(22.2819, 114.1588, 180)
    assert session.state == "active"
    assert session.location_active is True
    assert state.last_payload == {
        "latitude": 22.2819,
        "longitude": 114.1588,
        "hold_seconds": 180,
    }


def test_stop_returns_idle(fake_engine):
    _, url = fake_engine
    engine = HttpLocationEngine(url)
    engine.start_location(22.2819, 114.1588, 60)
    session = engine.stop_location()
    assert session.state == "idle"
    assert session.location_active is False


def test_session_reflects_engine_state(fake_engine):
    state, url = fake_engine
    engine = HttpLocationEngine(url)
    assert engine.session().state == "idle"
    state.session_state = "active"
    assert engine.session().location_active is True


def test_http_error_surfaces_detail(fake_engine):
    """引擎返回 5xx 时要把原因带出来，不能吞掉。"""
    state, url = fake_engine
    state.fail_simulate_with = 502
    with pytest.raises(AdapterError) as excinfo:
        HttpLocationEngine(url).start_location(1.0, 2.0, 60)
    assert "502" in str(excinfo.value)


def test_no_device_returns_conflict(fake_engine):
    state, url = fake_engine
    state.devices = []
    with pytest.raises(AdapterError) as excinfo:
        HttpLocationEngine(url).start_location(1.0, 2.0, 60)
    assert "409" in str(excinfo.value)


@pytest.mark.parametrize("url", ["http://192.168.1.10:8899", "http://example.com", "https://8.8.8.8"])
def test_non_loopback_urls_are_rejected(url):
    """只允许本机回环，避免把设备控制面或坐标发到远端。"""
    with pytest.raises(AdapterUnavailable):
        assert_loopback(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8899", "http://localhost:8899", "http://[::1]:8899"])
def test_loopback_urls_are_accepted(url):
    assert_loopback(url)


def test_registry_creates_platform_specific_adapter():
    adapter = create_adapter("windows")
    assert adapter.name == "windows-dvt"
    adapter_mac = create_adapter("macos")
    assert adapter_mac.name == "macos-dvt"


def test_registry_rejects_linux():
    with pytest.raises(AdapterUnavailable) as excinfo:
        create_adapter("linux")
    assert "Linux" in str(excinfo.value)


def test_registry_explicit_url_is_pure_client(fake_engine):
    """显式给地址时不自动拉起引擎，纯客户端模式。"""
    _, url = fake_engine
    adapter = create_adapter("windows", engine_url=f"{url}/")
    status = adapter.probe()
    assert status.available is True
    assert status.endpoint == url


def test_detect_platform_returns_known_value():
    assert detect_platform() in {"windows", "macos", "linux", "unknown"}
