"""固定地区测试预设。

第一版**刻意不支持自由经纬度输入**：只有四个固定预设。
这样既符合需求，也避免了「随手把坐标发到任意位置」这类被滥用的空间。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .adapters.base import RegionPreset

DATA_DIR = Path(__file__).parent / "data"
REGIONS_FILE = DATA_DIR / "regions.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    with REGIONS_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def presets() -> tuple[RegionPreset, ...]:
    return tuple(
        RegionPreset(
            id=item["id"],
            region_code=item["region_code"],
            label=item["label"],
            city=item["city"],
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            availability=item["availability"],
            availability_note=item.get("availability_note", ""),
            hardware_note=item.get("hardware_note", ""),
        )
        for item in _load()["presets"]
    )


def get(preset_id: str) -> RegionPreset:
    """按 id 取预设；不存在就报错，绝不回退到某个默认坐标。"""
    normalized = preset_id.strip().lower()
    for preset in presets():
        if preset.id == normalized:
            return preset
    available = ", ".join(p.id for p in presets())
    raise KeyError(f"未知地区预设 {preset_id!r}；可选：{available}")


def critical_warning() -> str:
    """关于「定位 ≠ 区域可用性」的强制提示。"""
    return str(_load()["critical_warning_zh"])


def verified_on() -> str:
    return str(_load()["verified_on"])
