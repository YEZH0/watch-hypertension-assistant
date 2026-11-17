"""CLI 测试：确保命令可运行、退出码正确、JSON 可被机器读取。"""

from __future__ import annotations

import json

import pytest
from assistant.cli import main


def test_regions_command(capsys):
    assert main(["regions"]) == 0
    out = capsys.readouterr().out
    assert "中国香港" in out
    assert "不支持自由经纬度" in out


def test_regions_json_is_parseable(capsys):
    assert main(["regions", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["presets"]) == 4


def test_guide_command(capsys):
    assert main(["guide"]) == 0
    out = capsys.readouterr().out
    assert "健康" in out
    assert "30 天" in out


def test_families_command(capsys):
    assert main(["families"]) == 0
    out = capsys.readouterr().out
    assert "Series 10" in out
    assert "不支持" in out


def test_compat_command_with_full_input(capsys):
    code = main(
        [
            "compat",
            "--watch",
            "series10",
            "--watchos",
            "26.1",
            "--ios",
            "26.1",
            "--age",
            "30",
            "--no-hypertension",
            "--no-pregnant",
            "--wrist-detection",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "不代表" not in out or "已开通" not in out
    assert "健康" in out


def test_compat_blocks_underage(capsys):
    code = main(["compat", "--watch", "series10", "--age", "17"])
    assert code == 0
    out = capsys.readouterr().out
    assert "阻断" in out


def test_env_command_json_on_dead_engine(capsys):
    code = main(["--engine-url", "http://127.0.0.1:1", "env", "--json"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["engine"]["available"] is False


def test_default_command_is_check(capsys):
    """不带子命令时执行完整检查，且不会因为引擎缺失而崩溃。"""
    code = main(["--engine-url", "http://127.0.0.1:1"])
    assert code == 0
    out = capsys.readouterr().out
    assert "前置检查" in out
    assert "兼容性" in out


def test_start_with_dead_engine_reports_blocked(capsys):
    code = main(["--engine-url", "http://127.0.0.1:1", "start", "--region", "hk"])
    assert code == 1
    out = capsys.readouterr().out
    assert "未启动" in out


def test_stop_with_dead_engine_exits_nonzero(capsys):
    code = main(["--engine-url", "http://127.0.0.1:1", "stop"])
    assert code == 2


def test_invalid_region_exits_two(capsys):
    code = main(["--engine-url", "http://127.0.0.1:1", "start", "--region", "nowhere"])
    assert code == 2
    assert "us, hk, fr, jp" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["env", "devices", "status"])
def test_readonly_commands_are_safe_on_dead_engine(command, capsys):
    """只读命令在引擎缺失时必须优雅失败，不能抛未捕获异常。"""
    code = main(["--engine-url", "http://127.0.0.1:1", command])
    assert code in (1, 2)
