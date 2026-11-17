"""地区预设测试。

重点不是"功能对不对"，而是**边界对不对**：
只允许四个固定预设、不允许自由经纬度、必须携带"定位≠区域"的强制提示。
"""

from __future__ import annotations

import pytest
from assistant import regions


def test_exactly_four_presets():
    """第一版只允许四个固定地区，多一个都算超出需求。"""
    assert [p.id for p in regions.presets()] == ["us", "hk", "fr", "jp"]


def test_region_codes_match_requirement():
    codes = {p.region_code for p in regions.presets()}
    assert codes == {"US", "HK", "FR", "JP"}


@pytest.mark.parametrize("preset_id", ["us", "hk", "fr", "jp"])
def test_coordinates_within_valid_range(preset_id):
    preset = regions.get(preset_id)
    assert -90.0 <= preset.latitude <= 90.0
    assert -180.0 <= preset.longitude <= 180.0


def test_hong_kong_is_not_mainland_china():
    """中国香港与大陆地区可用性不同，必须区分清楚。"""
    hk = regions.get("hk")
    assert hk.label == "中国香港"
    assert hk.region_code == "HK"
    assert "中国大陆" in hk.availability_note


def test_no_free_coordinate_input_api():
    """地区模块不暴露任何"按经纬度取预设"的接口。"""
    public = {name for name in dir(regions) if not name.startswith("_")}
    forbidden = {"nearest", "from_coordinates", "at", "closest"}
    assert not (public & forbidden)


def test_unknown_preset_raises_instead_of_defaulting():
    """未知预设必须报错，不能悄悄回退到某个默认坐标。"""
    with pytest.raises(KeyError):
        regions.get("mars")


def test_preset_lookup_is_case_insensitive_but_strict():
    assert regions.get("HK").id == "hk"
    with pytest.raises(KeyError):
        regions.get("hkong")


def test_critical_warning_is_present_and_specific():
    """必须明确说明"定位模拟无法改变/验证区域可用性"。"""
    warning = regions.critical_warning()
    assert "区域设置" in warning
    assert "Apple ID" in warning
    assert "不会" in warning


def test_verified_on_is_iso_date():
    value = regions.verified_on()
    assert len(value) == 10 and value[4] == "-" and value[7] == "-"
