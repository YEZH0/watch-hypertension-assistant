"""CLI 测试：确保命令可运行、退出码正确、JSON 可被机器读取。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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


def test_redirected_output_survives_non_utf8_locale():
    """回归测试：stdout 被重定向且编码不是 UTF-8 时，中文输出必须不崩。

    这条对应用户最常见的两种场景：
    - GitHub Actions 的 Windows runner（默认 cp1252 管道）
    - 用户自己 `python -m assistant check > log.txt`

    曾经的表现是 UnicodeEncodeError 直接终止进程，用户拿不到任何检查结果。
    """
    repo_root = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "PYTHONIOENCODING": "cp1252",  # 强制模拟非 UTF-8 的管道
        "PYTHONPATH": str(repo_root),
    }
    proc = subprocess.run(
        [sys.executable, "-m", "assistant", "regions"],
        cwd=repo_root,
        capture_output=True,  # stdout/stderr 都是管道，不是终端
        env=env,
        timeout=120,
    )
    stderr = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, f"命令应正常退出，实际 stderr：{stderr}"
    assert "UnicodeEncodeError" not in stderr
    # 切换后输出应当是合法 UTF-8，否则日志在 CI 里就是乱码
    text = proc.stdout.decode("utf-8")
    assert "中国香港" in text


def test_status_shows_restore_hint_when_idle(fake_engine, capsys):
    """idle 状态下必须提示关闭定位服务 10 秒再打开。

    会话自然到期时用户不会执行 stop，如果不在这里补提示，
    用户会带着一个假的模拟位置离开，还以为那就是自己的真实位置。
    """
    _, url = fake_engine
    code = main(["--engine-url", url, "status"])
    assert code == 0
    out = capsys.readouterr().out
    assert "定位服务" in out
    assert "10 秒" in out


def test_status_hides_stale_coordinates_when_idle(fake_engine, capsys):
    """idle 时不打印裸坐标：引擎会把坐标重置成硬编码默认值，
    显示出来会让用户误以为自己还停在那个地点。"""
    _, url = fake_engine
    main(["--engine-url", url, "status"])
    out = capsys.readouterr().out
    assert "状态：idle" in out
    assert "坐标：" not in out


def test_status_shows_coordinates_when_active(fake_engine, capsys):
    """会话活跃时坐标是有意义的，必须显示。"""
    _, url = fake_engine
    main(["--engine-url", url, "start", "--region", "hk", "--hold", "60"])
    capsys.readouterr()
    main(["--engine-url", url, "status"])
    out = capsys.readouterr().out
    assert "状态：active" in out
    assert "22.2819" in out
