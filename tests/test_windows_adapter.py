"""Windows 适配器的引擎发现测试。

重点不是「能启动引擎」，而是**启动失败时说的话是否指向正确方向**。

实测踩过的坑：`pip install -e .` 在某些环境下生成的路径钩子不生效，
`ios-location-studio.exe` 存在但一执行就 `ModuleNotFoundError`。
旧实现只看 `shutil.which`，于是 Popen 一个注定失败的进程，白等 25 秒，
最后报「已启动引擎但在等待时间内未就绪」——用户会去查 USB、查端口、查防火墙。
"""

from __future__ import annotations

import subprocess
import sys

from assistant.adapters import windows as win


def test_verify_entrypoint_accepts_working_command():
    """正常能跑的命令必须判定为可用。"""
    assert win.WindowsLocationEngine._verify_entrypoint([sys.executable]) is None


def test_verify_entrypoint_reports_import_failure_with_actionable_hint():
    """导入失败要说清「不等于没装」，并给出可直接照抄的启动命令。"""
    missing = "definitely_missing_module_xyz"
    issue = win.WindowsLocationEngine._verify_entrypoint(
        [sys.executable, "-c", f"import {missing}"]
    )

    assert issue is not None
    assert "导入失败" in issue
    assert missing in issue
    # 这三条是给用户下一步动作的，缺一条就还是不知道怎么自救。
    assert "不等于引擎没装" in issue
    assert "PYTHONPATH=src" in issue
    assert "--engine-url" in issue


def test_verify_entrypoint_keeps_working_when_version_flag_unsupported():
    """老版本引擎不认 --version 时不能误判为不可用。"""
    # 模拟 argparse 对未知参数的退出码与提示。
    code = (
        "import sys; sys.stderr.write('error: unrecognized arguments: --version'); "
        "sys.exit(2)"
    )
    assert win.WindowsLocationEngine._verify_entrypoint([sys.executable, "-c", code]) is None


def test_existing_entrypoint_falls_back_to_module_when_script_is_broken(monkeypatch):
    """入口脚本坏了要继续尝试模块方式，而不是直接放弃。"""
    engine = win.WindowsLocationEngine()
    calls: list[list[str]] = []

    monkeypatch.setattr(win.shutil, "which", lambda name: "/fake/ios-location-studio.exe")

    def fake_verify(command: list[str]) -> str | None:
        calls.append(command)
        if "ios-location-studio" in command[0]:
            return "脚本存在但导入失败"
        return None  # 模块方式可用

    monkeypatch.setattr(win.WindowsLocationEngine, "_verify_entrypoint", staticmethod(fake_verify))

    assert engine._existing_entrypoint() == [sys.executable, "-m", "ios_location_studio"]
    assert len(calls) == 2, "脚本失败后应当继续尝试模块方式"


def test_launch_failure_explains_why_not_just_not_found(monkeypatch):
    """全部候选都失败时，错误信息必须带上具体原因。

    只说「未找到」会让人去重装一个其实已经装好的引擎。
    """
    engine = win.WindowsLocationEngine()
    monkeypatch.setattr(win.shutil, "which", lambda name: None)

    def fake_verify(command: list[str]) -> str:
        return "python -m ios_location_studio 存在但导入失败：No module named 'ios_location_studio'"

    monkeypatch.setattr(win.WindowsLocationEngine, "_verify_entrypoint", staticmethod(fake_verify))

    message = engine._launch()

    assert message is not None
    assert "找不到能启动的" in message
    assert "导入失败" in message
    assert "No module named" in message


def test_probe_reports_half_installed_engine_without_waiting_for_timeout(monkeypatch):
    """整条 probe 走完，必须把原因透传到 EngineStatus.detail。"""
    engine = win.WindowsLocationEngine()
    monkeypatch.setattr(win.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        win.WindowsLocationEngine,
        "_verify_entrypoint",
        staticmethod(lambda command: "存在但导入失败：No module named 'ios_location_studio'"),
    )

    status = engine.probe()

    assert status.available is False
    assert "导入失败" in status.detail
    # 不该再出现那句把人引向 USB / 端口的措辞。
    assert "等待时间内未就绪" not in status.detail


def test_verify_entrypoint_bounded_by_timeout():
    """验证动作本身必须有上限，不能把 CLI 卡死。"""
    # 只做结构性断言：确认调用时带了 timeout，避免以后被改成无超时。
    source = subprocess.run  # 保持 flake8/ruff 对 import 的使用
    assert source is not None
    import inspect

    body = inspect.getsource(win.WindowsLocationEngine._verify_entrypoint)
    assert "timeout=" in body
