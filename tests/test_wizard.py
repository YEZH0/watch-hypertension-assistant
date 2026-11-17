"""阶段化向导的测试。

覆盖的重点不是「功能跑得通」，而是**误导性输出不会出现**：

- 引擎 active 不等于手机采用了坐标，也不等于功能已开通；
- 用户拒绝 / 中途取消 / 超时 / 服务刷新失败 / 恢复失败，都必须有明确出路；
- 任何异常路径都要留下「会话已停止 + 如何恢复」的指引，不能崩在原地；
- 进度文件里不能出现年龄、诊断、妊娠、经纬度、设备标识符。

每个 case 都尽量走真实的 HTTP 假引擎（见 conftest.py），这样请求序列化、
状态码、JSON 解析这几条容易出错的路径也在覆盖范围内。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from assistant import regions, wizard
from assistant.cli import main
from assistant.workflow import Assistant

# 这些短语一旦出现，就说明输出在做没有依据的断言。
FORBIDDEN_CLAIMS = (
    "模拟定位在手机上生效",
    "功能已开通",
    "开通成功",
    "一键成功",
    "高血压通知已生效",
)


def _collect_keys(node, acc: set[str] | None = None) -> set[str]:
    """递归收集 JSON 里出现的所有 key，用于隐私检查。"""
    acc = acc if acc is not None else set()
    if isinstance(node, dict):
        for key, value in node.items():
            acc.add(str(key))
            _collect_keys(value, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_keys(item, acc)
    return acc


def _wizard(fake_engine, tmp_path: Path, **kwargs) -> wizard.Wizard:
    _, url = fake_engine
    return wizard.Wizard(
        assistant=Assistant(engine_url=url),
        state_path=tmp_path / "wizard-state.json",
        **kwargs,
    )


def _to_region(wiz: wizard.Wizard) -> None:
    """推进到第 4 步（地区预设）之前的所有确认。"""
    assert wiz.submit("accept")["outcome"] == "advanced"
    assert wiz.submit("ready")["outcome"] == "advanced"
    assert wiz.submit("connected")["outcome"] == "advanced"
    assert wiz.submit("confirmed")["outcome"] == "advanced"
    assert wiz.state["stage"] == "region"


def _to_restore(wiz: wizard.Wizard, map_answer: str = "moved", health: str = "setup_done") -> None:
    _to_region(wiz)
    assert wiz.submit("hk")["outcome"] == "advanced"
    assert wiz.submit(map_answer)["outcome"] == "advanced"
    assert wiz.submit(health)["outcome"] == "advanced"
    assert wiz.state["stage"] == "restore"


# ---------------------------------------------------------------- 流程契约


def test_plan_exposes_all_stages_and_real_region_presets():
    """--plan 必须是可执行的契约，不是概念文案。"""
    plan = wizard.Wizard(
        assistant=Assistant(engine_url="http://127.0.0.1:1"),
        state_path=Path("unused.json"),
    ).plan()

    assert [stage["id"] for stage in plan["stages"]] == list(wizard.STAGE_ORDER)
    assert len(plan["stages"]) == 9

    region_stage = next(stage for stage in plan["stages"] if stage["id"] == "region")
    assert [item["value"] for item in region_stage["answers"]] == [
        preset.id for preset in regions.presets()
    ]
    # 只允许四个固定预设，不能出现自由坐标入口。
    assert len(region_stage["answers"]) == 4

    assert "不保存年龄" in plan["privacy_note"]
    assert plan["feature_status"] == "unknown_pending_user_verification"
    assert len(plan["state_separation"]) == 3


def test_plan_is_readonly(fake_engine, tmp_path):
    """只读描述不能碰引擎、不能写进度文件。"""
    state, _ = fake_engine
    wiz = _wizard(fake_engine, tmp_path)
    wiz.plan()
    wiz.describe()
    assert state.calls == []
    assert not wiz.state_path.exists()


def test_initial_stage_waits_for_explicit_confirmation(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    payload = wiz.describe()
    assert payload["stage"] == "safety"
    assert payload["awaiting_user"] is True
    assert [item["value"] for item in payload["answers"]] == ["accept", "decline"]


def test_decline_changes_nothing(fake_engine, tmp_path):
    """用户拒绝时必须一步都不做：不探测引擎、不下发坐标。"""
    state, _ = fake_engine
    wiz = _wizard(fake_engine, tmp_path)
    result = wiz.submit("decline")
    assert result["outcome"] == "declined"
    assert result["exit_code"] == wizard.EXIT_DECLINED
    assert state.calls == []
    assert state.last_payload is None
    assert wiz.state["aborted"] == "user_declined_at_notice"


# ---------------------------------------------------------------- 资格与前置条件


def test_eligibility_blocked_stops_before_any_location_stage(fake_engine, tmp_path):
    """不满足医疗适用条件时，不允许进入定位阶段，也不给绕行路径。"""
    from assistant import compat

    state, _ = fake_engine
    wiz = _wizard(fake_engine, tmp_path, inputs=compat.UserInputs(age=17))
    result = wiz.submit("accept")
    assert result["outcome"] == "blocked"
    assert result["exit_code"] == wizard.EXIT_BLOCKED
    assert wiz.state["stage"] == "safety"
    assert state.last_payload is None
    assert any("22 岁" in item["detail"] for item in result["items"])
    assert any("不会进入定位测试阶段" in result["message"] for _ in [0])

    # 即使手工把阶段改到 region，也拒绝下发（双重保险）。
    wiz.state["stage"] = "region"
    blocked = wiz.submit("hk")
    assert blocked["outcome"] == "blocked"
    assert state.last_payload is None


def test_unsupported_model_warns_but_allows_location_link_test(fake_engine, tmp_path):
    """机型不在支持范围内时，允许继续验证定位链路，但必须明说功能不会出现。"""
    from assistant import compat

    wiz = _wizard(fake_engine, tmp_path, inputs=compat.UserInputs(watch_family="series8"))
    result = wiz.submit("accept")
    assert result["outcome"] == "advanced"
    assert any("不会出现该功能" in text for text in result["warnings"])


def test_missing_engine_blocks_at_environment(tmp_path):
    wiz = wizard.Wizard(
        assistant=Assistant(engine_url="http://127.0.0.1:1"),
        state_path=tmp_path / "s.json",
    )
    assert wiz.submit("accept")["outcome"] == "advanced"
    result = wiz.submit("ready")
    assert result["outcome"] == "blocked"
    assert result["exit_code"] == wizard.EXIT_BLOCKED
    assert wiz.state["stage"] == "environment"
    assert "引擎" in result["message"]


def test_missing_usb_blocks_and_sends_no_coordinates(fake_engine, tmp_path):
    state, _ = fake_engine
    state.devices = []
    wiz = _wizard(fake_engine, tmp_path)
    wiz.submit("accept")
    wiz.submit("ready")
    result = wiz.submit("connected")
    assert result["outcome"] == "blocked"
    assert result["items"][0]["blocking"] is True
    assert wiz.state["stage"] == "usb"
    assert state.last_payload is None, "设备不可见时绝不能下发坐标"


def test_multiple_devices_are_rejected_not_guessed(fake_engine, tmp_path):
    state, _ = fake_engine
    state.devices.append(
        {"udid": "00008110-SECOND", "name": "Second iPhone", "ios_version": "26.1", "model": "iPhone17,3"}
    )
    wiz = _wizard(fake_engine, tmp_path)
    wiz.submit("accept")
    wiz.submit("ready")
    result = wiz.submit("connected")
    assert result["outcome"] == "blocked"
    assert "2 台设备" in result["message"]
    assert state.last_payload is None


def test_baseline_not_confirmed_never_sends_coordinates(fake_engine, tmp_path):
    state, _ = fake_engine
    wiz = _wizard(fake_engine, tmp_path)
    wiz.submit("accept")
    wiz.submit("ready")
    wiz.submit("connected")
    result = wiz.submit("not_yet")
    assert result["outcome"] == "awaiting_user"
    assert wiz.state["stage"] == "baseline"
    assert state.last_payload is None


# ---------------------------------------------------------------- 三态分离


def test_region_answer_records_engine_active_but_not_map_or_health(fake_engine, tmp_path):
    """active 只能记成引擎状态，地图与健康必须是「未知」。"""
    _, url = fake_engine
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    result = wiz.submit("hk")
    assert result["outcome"] == "advanced"
    assert wiz.state["engine_active"] is True
    assert wiz.state["map_verification"] is None
    assert wiz.state["health_result"] is None

    report = wiz.report()
    assert report["simulation"]["engine_active"] is True
    assert "引擎已接受" in report["simulation"]["label"]
    assert report["map"]["verified_by"] is None
    assert "未知" in report["map"]["label"]
    assert report["health"]["verified_by"] is None
    assert report["feature_status"] == "unknown_pending_user_verification"


def test_map_not_moved_is_recorded_as_failure_not_success(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    wiz.submit("jp")
    result = wiz.submit("not_moved")
    assert result["outcome"] == "advanced"
    assert wiz.state["map_verification"] == "not_moved"
    assert any("不等于手机采用了坐标" in text for text in result["warnings"])
    # 条件排查必须给出，且「关定位服务」要标成可能让模拟失效。
    assert any("数据线" in text for text in result["notes"])
    assert any("可能让当前的模拟会话失效" in text for text in result["notes"])
    assert wiz.report()["map"]["label"] == "用户确认蓝点没有移动"


def test_map_unsure_is_recorded_as_unverified(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    wiz.submit("fr")
    result = wiz.submit("unsure")
    assert result["outcome"] == "advanced"
    assert wiz.state["map_verification"] == "unsure"
    assert "未核验" in wiz.report()["map"]["label"]


# ---------------------------------------------------------------- 健康 App


def test_health_stage_shows_remaining_time(fake_engine, tmp_path):
    """进入健康 App 前必须显示剩余时间，避免用户以为时间还很充裕。"""
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    wiz.submit("hk")
    wiz.submit("moved")
    payload = wiz.describe()
    assert payload["stage"] == "health"
    assert any("剩余约 120 秒" in text for text in payload["notes"])


def test_card_absent_gives_multiple_causes_not_a_single_conclusion(fake_engine, tmp_path):
    """卡片不存在不能推断成唯一原因（机型/地区/刷新/菜单差异都可能）。"""
    wiz = _wizard(fake_engine, tmp_path)
    _to_restore(wiz, health="card_absent")
    joined = json.dumps(wiz.report(), ensure_ascii=False)
    assert "找不到" in joined

    # 重放一遍拿当时的 notes：
    wiz2 = _wizard(fake_engine, tmp_path / "x")
    result = None
    _to_region(wiz2)
    wiz2.submit("hk")
    wiz2.submit("moved")
    result = wiz2.submit("card_absent")
    joined_notes = "\n".join(result["notes"])
    assert "区域设置" in joined_notes or "地区" in joined_notes
    assert "无法远程判定" in joined_notes
    assert "这就是结论" not in joined_notes


def test_health_answer_stops_the_session(fake_engine, tmp_path):
    """进入恢复阶段前必须已经停止会话，不能只靠用户自己去 stop。"""
    state, _ = fake_engine
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    wiz.submit("hk")
    assert state.session_state == "active"
    wiz.submit("moved")
    wiz.submit("setup_done")
    assert state.session_state == "idle"
    assert wiz.state["stop_ok"] is True


def test_session_expired_during_health_is_not_a_failure(fake_engine, tmp_path):
    """时长到期是正常结果，不能标记成测试失败。"""
    state, _ = fake_engine
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    wiz.submit("hk")
    wiz.submit("moved")
    state.session_state = "idle"  # 模拟 180 秒到期
    health = wiz.submit("setup_done")
    assert health["outcome"] == "advanced"
    assert wiz.state["session_expired"] is True
    assert any("正常" in text for text in health["notes"])


# ---------------------------------------------------------------- 恢复


def test_restore_not_confirmed_keeps_user_in_the_loop(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    _to_restore(wiz)
    result = wiz.submit("not_restored")
    assert result["outcome"] == "awaiting_user"
    assert wiz.state["stage"] == "restore"
    assert wiz.state["restore_result"] == "not_confirmed"
    assert any("10 秒" in text for text in result["notes"])
    assert any("不是所有人都必须" in text for text in result["warnings"])


def test_restore_unresolved_finishes_with_unconfirmed_state(fake_engine, tmp_path):
    """用户恢复不了时不能把他困在这一步，也不能假装恢复成功。"""
    wiz = _wizard(fake_engine, tmp_path)
    _to_restore(wiz)
    result = wiz.submit("unresolved")
    assert result["outcome"] == "advanced"
    assert wiz.state["stage"] == "report"
    report = wiz.report()
    assert report["restore"]["result"] == "not_confirmed"
    assert "未确认恢复" in report["restore"]["label"]


def test_happy_path_report_separates_every_state(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    _to_restore(wiz)
    result = wiz.submit("restored")
    assert result["outcome"] == "advanced"

    report = wiz.report()
    assert len(report["lines"]) == 5
    assert report["map"]["result"] == "moved"
    assert report["health"]["result"] == "setup_done"
    assert report["restore"]["result"] == "confirmed"
    assert report["feature_status"] == "unknown_pending_user_verification"
    assert "不构成" in report["disclaimer"]


def test_no_claim_of_success_anywhere_in_the_journey(fake_engine, tmp_path):
    """全流程输出里不允许出现「成功 / 已开通」这类没有依据的断言。"""
    wiz = _wizard(fake_engine, tmp_path)
    collected: list[str] = []

    _to_region(wiz)
    collected.append(json.dumps(wiz.describe(), ensure_ascii=False))
    collected.append(json.dumps(wiz.submit("hk"), ensure_ascii=False))
    collected.append(json.dumps(wiz.describe(), ensure_ascii=False))
    collected.append(json.dumps(wiz.submit("moved"), ensure_ascii=False))
    collected.append(json.dumps(wiz.describe(), ensure_ascii=False))
    collected.append(json.dumps(wiz.submit("setup_done"), ensure_ascii=False))
    collected.append(json.dumps(wiz.describe(), ensure_ascii=False))
    collected.append(json.dumps(wiz.submit("restored"), ensure_ascii=False))

    text = "\n".join(collected)
    for forbidden in FORBIDDEN_CLAIMS:
        assert forbidden not in text, f"输出里出现了没有依据的断言：{forbidden}"


# ---------------------------------------------------------------- 中断与异常


def test_emergency_cleanup_stops_active_session(fake_engine, tmp_path):
    state, _ = fake_engine
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    wiz.submit("hk")
    assert state.session_state == "active"

    cleanup = wiz.emergency_cleanup()
    assert cleanup["stopped_attempted"] is True
    assert cleanup["ok"] is True
    assert state.session_state == "idle"
    assert wiz.state["restore_result"] == "not_confirmed"


def test_emergency_cleanup_does_not_touch_engine_before_any_change(fake_engine, tmp_path):
    state, _ = fake_engine
    wiz = _wizard(fake_engine, tmp_path)
    wiz.submit("accept")
    before = len(state.calls)
    cleanup = wiz.emergency_cleanup()
    assert cleanup["stopped_attempted"] is False
    assert len(state.calls) == before


def test_emergency_cleanup_survives_dead_engine(fake_engine, tmp_path):
    """清理路径不能因为引擎没了就抛异常——那会让用户连提示都看不到。"""
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    wiz.submit("hk")
    wiz.assistant._engine = Assistant(engine_url="http://127.0.0.1:1").engine  # noqa: SLF001
    cleanup = wiz.emergency_cleanup()
    assert cleanup["stopped_attempted"] is True
    assert cleanup["ok"] is False
    assert cleanup["restore"] is not None


def test_interactive_ctrl_c_stops_and_returns_130(fake_engine, tmp_path, monkeypatch, capsys):
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    wiz.submit("hk")
    state = fake_engine[0]
    assert state.session_state == "active"

    def _boom(_prompt: str = "") -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _boom)
    code = wizard.run_interactive(wiz)
    assert code == wizard.EXIT_INTERRUPTED
    assert state.session_state == "idle"
    out = capsys.readouterr().out
    assert "已中止" in out
    assert "定位服务" in out
    assert "python -m assistant stop" in out or "已尝试停止" in out


def test_interactive_quit_returns_declined(fake_engine, tmp_path, monkeypatch):
    wiz = _wizard(fake_engine, tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "q")
    code = wizard.run_interactive(wiz)
    assert code == wizard.EXIT_DECLINED
    assert wiz.state_path.exists()


def test_interactive_rejects_garbage_then_accepts(fake_engine, tmp_path, monkeypatch):
    """空输入、乱输入都不能默认成「同意」，只能重新问。"""
    wiz = _wizard(fake_engine, tmp_path)
    answers = iter(["乱码", "", "1", "1", "1", "2", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    code = wizard.run_interactive(wiz)
    assert code == wizard.EXIT_DECLINED
    # 走到 baseline 后回答「还没确认」→ 停在 baseline，不会被当成确认
    assert wiz.state["stage"] == "baseline"
    assert fake_engine[0].last_payload is None


# ---------------------------------------------------------------- 状态文件


def test_state_is_persisted_and_resumable(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)

    _, url = fake_engine
    resumed = wizard.Wizard(
        assistant=Assistant(engine_url=url), state_path=tmp_path / "wizard-state.json"
    )
    assert resumed.state["stage"] == "region"
    assert resumed.state["completed"] == ["safety", "environment", "usb", "baseline"]


def test_state_file_contains_no_personal_data(fake_engine, tmp_path):
    """进度文件不得包含年龄、诊断、妊娠、经纬度、设备标识符。"""
    from assistant import compat

    wiz = _wizard(
        fake_engine,
        tmp_path,
        inputs=compat.UserInputs(age=30, diagnosed_hypertension=False, pregnant=False),
    )
    _to_region(wiz)
    wiz.submit("hk")
    raw = (tmp_path / "wizard-state.json").read_text(encoding="utf-8")
    payload = json.loads(raw)

    forbidden_keys = {
        "age",
        "pregnant",
        "pregnancy",
        "diagnosed_hypertension",
        "hypertension",
        "latitude",
        "longitude",
        "udid",
        "serial",
        "watch_family",
    }
    found = _collect_keys(payload) & forbidden_keys
    assert not found, f"进度文件里不应该出现这些字段：{sorted(found)}"
    # 坐标字面值也不能出现。
    for value in ("22.2819", "114.1588"):
        assert value not in raw


def test_corrupt_state_file_restarts_instead_of_crashing(fake_engine, tmp_path):
    path = tmp_path / "wizard-state.json"
    path.write_text("{ not json", encoding="utf-8")
    wiz = _wizard(fake_engine, tmp_path)
    assert wiz.state["stage"] == "safety"


def test_reset_clears_progress(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    assert wiz.state_path.exists()
    wiz.reset()
    assert not wiz.state_path.exists()
    assert wiz.state["stage"] == "safety"


# ---------------------------------------------------------------- 用法错误


def test_wrong_stage_answer_is_rejected_with_current_stage(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    with pytest.raises(wizard.WizardError) as exc:
        wiz.submit("hk", stage_id="region")
    assert "当前阶段是 safety" in str(exc.value)
    assert "usb / baseline / region" not in str(exc.value)


def test_unknown_answer_lists_options(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    with pytest.raises(wizard.WizardError) as exc:
        wiz.submit("maybe")
    assert "accept" in str(exc.value)
    assert "decline" in str(exc.value)


def test_free_form_coordinates_are_not_a_valid_answer(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    _to_region(wiz)
    with pytest.raises(wizard.WizardError):
        wiz.submit("22.5431,114.0579")
    assert fake_engine[0].last_payload is None


def test_answer_after_finish_raises(fake_engine, tmp_path):
    wiz = _wizard(fake_engine, tmp_path)
    _to_restore(wiz)
    wiz.submit("restored")
    with pytest.raises(wizard.WizardError) as exc:
        wiz.submit("restored")
    assert "流程已结束" in str(exc.value)


# ---------------------------------------------------------------- CLI 集成


def _cli(fake_engine, tmp_path, *extra: str) -> tuple[int, dict]:
    _, url = fake_engine
    state_file = str(tmp_path / "cli-state.json")
    code = main(["--engine-url", url, "wizard", "--state-file", state_file, "--json", *extra])
    return code, state_file


def _read_json(capsys) -> dict:
    captured = capsys.readouterr()
    return json.loads(captured.out)


def test_cli_wizard_defaults_to_awaiting_user_without_stdin(fake_engine, tmp_path, capsys):
    """非交互调用（Agent 管道）只报告阶段，绝不擅自推进。"""
    state, _ = fake_engine
    code, _ = _cli(fake_engine, tmp_path)
    payload = _read_json(capsys)
    assert code == 0
    assert payload["stage"] == "safety"
    assert payload["awaiting_user"] is True
    assert payload["answers"][0]["answer_command"].startswith("python -m assistant wizard --answer")
    assert state.calls == []


def test_cli_wizard_answer_flow(fake_engine, tmp_path, capsys):
    for answer, expected_stage in (
        ("accept", "environment"),
        ("ready", "usb"),
        ("connected", "baseline"),
        ("confirmed", "region"),
    ):
        code, _ = _cli(fake_engine, tmp_path, "--answer", answer)
        payload = _read_json(capsys)
        assert code == 0
        assert payload["stage"] == expected_stage


def test_cli_wizard_blocked_answer_returns_exit_1(fake_engine, tmp_path, capsys):
    state, _ = fake_engine
    state.devices = []
    code, _ = _cli(fake_engine, tmp_path, "--answer", "accept")
    assert code == 0
    _read_json(capsys)
    code, _ = _cli(fake_engine, tmp_path, "--answer", "ready")
    assert code == 0
    _read_json(capsys)
    code, _ = _cli(fake_engine, tmp_path, "--answer", "connected")
    assert code == 1
    payload = _read_json(capsys)
    assert payload["outcome"] == "blocked"
    assert state.last_payload is None


def test_cli_wizard_status_reports_progress(fake_engine, tmp_path, capsys):
    _cli(fake_engine, tmp_path, "--answer", "accept")
    capsys.readouterr()
    code, _ = _cli(fake_engine, tmp_path, "--status")
    payload = _read_json(capsys)
    assert code == 0
    assert payload["state"]["stage"] == "environment"
    assert payload["state"]["completed"] == ["safety"]
    assert payload["finished"] is False


def test_cli_wizard_reset(fake_engine, tmp_path, capsys):
    _cli(fake_engine, tmp_path, "--answer", "accept")
    capsys.readouterr()
    code, _ = _cli(fake_engine, tmp_path, "--reset")
    assert code == 0
    _read_json(capsys)
    code, _ = _cli(fake_engine, tmp_path, "--status")
    assert _read_json(capsys)["state"]["stage"] == "safety"


def test_cli_wizard_usage_error_returns_2(fake_engine, tmp_path, capsys):
    code, _ = _cli(fake_engine, tmp_path, "--answer", "nope")
    assert code == wizard.EXIT_USAGE
    assert "错误" in capsys.readouterr().err


def test_cli_wizard_unknown_stage_returns_2(fake_engine, tmp_path, capsys):
    _, url = fake_engine
    code = main(
        [
            "--engine-url",
            url,
            "wizard",
            "--state-file",
            str(tmp_path / "s.json"),
            "--stage",
            "nope",
            "--json",
        ]
    )
    assert code == wizard.EXIT_USAGE
    assert "未知阶段" in capsys.readouterr().err


def test_cli_wizard_human_output_on_blocked_stage(fake_engine, tmp_path, capsys):
    """人类可读输出里必须能看到「要在 iPhone 上做什么」和「如何确认」。"""
    state, _ = fake_engine
    state.devices = []
    _, url = fake_engine
    state_file = str(tmp_path / "human.json")
    main(["--engine-url", url, "wizard", "--state-file", state_file, "--answer", "accept"])
    capsys.readouterr()
    code = main(["--engine-url", url, "wizard", "--state-file", state_file, "--answer", "ready"])
    capsys.readouterr()
    code = main(["--engine-url", url, "wizard", "--state-file", state_file, "--answer", "connected"])
    out = capsys.readouterr().out
    assert code == 1
    assert "没有检测到 iPhone" in out
    assert "信任" in out
    assert "python -m assistant wizard --answer" in out


def test_cli_start_no_longer_claims_phone_took_the_coordinate(fake_engine, capsys):
    """回归：start 曾经打印「模拟定位在手机上生效」，属于误报。"""
    _, url = fake_engine
    code = main(["--engine-url", url, "start", "--region", "hk"])
    out = capsys.readouterr().out
    assert code == 0
    assert "模拟定位在手机上生效" not in out
    assert "手机有没有采用这个坐标，助手无法判定" in out
    assert "地图" in out


def test_cli_stop_prints_conditional_restore_steps(fake_engine, capsys):
    _, url = fake_engine
    main(["--engine-url", url, "start", "--region", "jp", "--hold", "60"])
    capsys.readouterr()
    code = main(["--engine-url", url, "stop"])
    out = capsys.readouterr().out
    assert code == 0
    assert "按顺序确认" in out
    assert "定位服务" in out
    assert "不是所有人都必须做的前置条件" in out
    assert "必须执行" not in out


def test_cli_guide_mentions_card_absent_has_multiple_causes(capsys):
    assert main(["guide"]) == 0
    out = capsys.readouterr().out
    assert "找不到「高血压通知」卡片" in out
    assert "无法远程判定" in out
    assert "support.apple.com" in out
    # 旧的单一因果断言必须消失
    assert "这就是结论" not in out
