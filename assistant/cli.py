"""命令行入口。

刻意用标准库 argparse 而不是第三方 CLI 框架：整个助手的运行时依赖为零，
用户不需要为了跑一个检查脚本而下载一堆未经验证的包。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__, compat, guide, regions
from .adapters.base import AdapterError, AdapterUnavailable
from .workflow import DEFAULT_HOLD_SECONDS, Assistant

# ---------------------------------------------------------------- 输出工具


def _supports_unicode() -> bool:
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in encoding


def _ensure_utf8_when_redirected() -> None:
    """保证中文输出不会因为编码问题让整个命令崩掉。

    背景：真实的 Windows 控制台里 Python 走 WriteConsoleW（UTF-16），
    中文本来就是好的。但只要输出被重定向——管道、`> log.txt`、
    CI 日志采集、Git Bash 的 `/dev/null`——编码就可能退化成系统
    locale（中文系统 cp936、英文系统 cp1252），此时打印「──」「地区」
    这类字符会抛 UnicodeEncodeError，命令直接死在输出上。

    策略分两种：
    - 非终端（管道/文件/CI）：切到 UTF-8，日志可读且不乱码。
    - 终端：保留终端自己的编码，只加 errors="replace"。
      因为终端编码是用户环境的既定事实，强行改会造成乱码，
      但绝不能因为一个画线字符就让用户拿不到检查结果。
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if encoding == "utf8":
                continue
            if stream.isatty():
                # Windows 的字符设备（包括 MSYS 的 /dev/null）也可能报 isatty=True，
                # 因此这里不能假设“是终端就一定安全”，仍要兜住。
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # 某些被替换过的流对象不支持 reconfigure，忽略即可。
            pass


def _emit_json(payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _supports_unicode():
        # Windows 旧代码页下避免整段输出崩掉。
        text = json.dumps(payload, ensure_ascii=True, indent=2)
    print(text)


def _section(title: str) -> None:
    print()
    print(f"── {title} " + "─" * max(0, 52 - len(title)))


def _ok(flag: bool | None) -> str:
    if flag is True:
        return "[通过]"
    if flag is False:
        return "[阻断]"
    return "[未知]"


def _print_compat(report: compat.CompatReport) -> None:
    _section("高血压通知兼容性")
    print(f"结论：{report.headline}")
    print(f"（数据核验日期：{report.data_verified_on}）")
    for item in report.checks:
        status = item.get("status")
        marker = {"pass": "[通过]", "fail": "[阻断]", "unknown": "[未知]", "info": "[信息]"}
        print(f"  {marker.get(status, '[信息]')} {item.get('item')}：{item.get('detail')}")
    if report.blockers:
        print()
        print("阻断项：")
        for text in report.blockers:
            print(f"  - {text}")
    if report.unknowns:
        print()
        print("待确认：")
        for text in report.unknowns:
            print(f"  - {text}")
    if report.next_steps:
        print()
        print("下一步：")
        for text in report.next_steps:
            print(f"  - {text}")
    print()
    print("※ 本结论不表示高血压通知已开通或已生效；最终状态只能在 iPhone 健康 App 中确认。")


def _print_guide() -> None:
    payload = guide.render()
    _section("健康 App 人工核验")
    print(payload["opening"])
    print()
    print("设置步骤：")
    for step in payload["setup_steps"]:
        print(f"  {step['order']}. {step['action']}")
        print(f"     → {step['expect']}")
    print()
    print("核验步骤：")
    for step in payload["verification_steps"]:
        print(f"  {step['order']}. {step['action']}")
        print(f"     → {step['expect']}")
    print()
    print("禁止事项：")
    for text in payload["never_claim"]:
        print(f"  - {text}")


# ---------------------------------------------------------------- 各子命令


def _cmd_env(assistant: Assistant, as_json: bool) -> int:
    env = assistant.environment()
    if as_json:
        _emit_json(env)
        return 0 if env["engine"].get("available") else 1

    _section("运行环境")
    print(f"平台：{env['platform_label']}（{env['platform']}）")
    engine = env["engine"]
    print(f"引擎：{engine.get('engine')} · {'在线' if engine.get('available') else '不可用'}")
    if engine.get("endpoint"):
        print(f"地址：{engine['endpoint']}")
    if not engine.get("available"):
        print(f"原因：{engine.get('detail')}")
        if engine.get("hint"):
            print(f"建议：{engine['hint']}")
    return 0 if engine.get("available") else 1


def _cmd_devices(assistant: Assistant, as_json: bool) -> int:
    inventory = assistant.engine.list_devices()
    if as_json:
        _emit_json(inventory.to_public_dict())
        return 0 if inventory.devices else 1

    _section("USB 设备")
    if not inventory.devices:
        print("未检测到 iPhone。请用数据线连接、解锁，并在弹窗中选择「信任」。")
        if inventory.error:
            print(f"底层信息：{inventory.error}")
        return 1
    print(f"发现 {len(inventory.devices)} 台设备：")
    for index, device in enumerate(inventory.devices, 1):
        print(
            f"  {index}. {device.name or '未命名'} · "
            f"iOS {device.ios_version or '未知'} · {device.model or '型号未知'}"
        )
    print("※ 未输出设备标识符；助手不采集、不上传序列号。")
    return 0


def _cmd_regions(as_json: bool) -> int:
    payload = [preset.to_dict() for preset in regions.presets()]
    if as_json:
        _emit_json({"presets": payload, "warning": regions.critical_warning()})
        return 0

    _section("地区测试预设")
    for preset in payload:
        print(f"  {preset['id']:<4} {preset['label']} · {preset['city']}")
        print(f"       {preset['latitude']}, {preset['longitude']}")
        if preset["availability_note"]:
            print(f"       可用性：{preset['availability_note']}")
        if preset["hardware_note"]:
            print(f"       硬件注意：{preset['hardware_note']}")
    print()
    print("※ 只提供这四个固定预设，不支持自由经纬度输入。")
    print(f"※ {regions.critical_warning()}")
    return 0


def _cmd_compat(args: argparse.Namespace) -> int:
    inputs = compat.UserInputs(
        watch_family=args.watch,
        watch_os=args.watchos,
        ios_version=args.ios,
        age=args.age,
        diagnosed_hypertension=_tri(args.hypertension),
        pregnant=_tri(args.pregnant),
        wrist_detection=_tri(args.wrist_detection),
    )
    report = compat.check(inputs)
    if args.json:
        _emit_json(report.to_dict())
        return 0
    _print_compat(report)
    return 0


def _cmd_check(assistant: Assistant, args: argparse.Namespace) -> int:
    inputs = compat.UserInputs(
        watch_family=args.watch,
        watch_os=args.watchos,
        ios_version=args.ios,
        age=args.age,
        diagnosed_hypertension=_tri(args.hypertension),
        pregnant=_tri(args.pregnant),
        wrist_detection=_tri(args.wrist_detection),
    )
    report = assistant.full_report(inputs)
    if args.json:
        _emit_json(report)
        return 0

    env = report["platform"]
    _section("运行环境")
    print(f"平台：{env['platform_label']}")
    engine = env["engine"]
    print(f"引擎：{'在线' if engine.get('available') else '不可用'} {engine.get('version') or ''}")
    if not engine.get("available"):
        print(f"原因：{engine.get('detail')}")

    _section("前置检查")
    for item in report["preflight"]["items"]:
        print(f"  {_ok(item['passed'])} {item['title']}：{item['detail']}")

    _print_compat(compat.CompatReport(**report["compatibility"]))

    _section("下一步")
    if report["preflight"]["can_run_location_test"]:
        print("  可以开始定位测试，例如：")
        print(f"    watch-hypertension-assistant start --region hk --hold {DEFAULT_HOLD_SECONDS}")
    else:
        print("  先解决上面标注为 [阻断] 的项目，再开始定位测试。")
    print("  无论定位测试结果如何，功能是否可用都只能在健康 App 中核验：")
    print("    watch-hypertension-assistant guide")
    return 0


def _cmd_start(assistant: Assistant, args: argparse.Namespace) -> int:
    result = assistant.start_test(args.region, args.hold)
    if args.json:
        _emit_json(result)
        return 0 if result["started"] else 1

    region = result["region"]
    _section(f"定位测试 · {region['label']} · {region['city']}")
    print(f"坐标（固定预设）：{region['latitude']}, {region['longitude']}")
    if result.get("hold_note"):
        print(f"注意：{result['hold_note']}")
    print()
    print(f"※ {result['region_warning']}")

    if not result["started"]:
        print()
        print(f"未启动：{result['reason']}")
        for item in result.get("blocking_items", []):
            print(f"  [阻断] {item['title']}：{item['detail']}")
        return 1

    session = result["session"]
    print()
    print(f"已启动，模拟定位在手机上生效（剩余约 {int(session.get('remaining') or result['hold_seconds'])} 秒）。")
    print()
    print("现在请在 iPhone 上做这两件事：")
    print("  1. 打开「地图」App，确认蓝点已在你选择的地区。")
    print("  2. 按下面的步骤核验功能状态——定位改动不会改变功能状态。")
    print()
    print(f"※ {result['location_test_does_not_imply']}")
    print()
    print("到时间或需要提前结束，运行：watch-hypertension-assistant stop")
    return 0


def _cmd_stop(assistant: Assistant, as_json: bool) -> int:
    result = assistant.stop_test()
    if as_json:
        _emit_json(result)
        return 0

    _section("已停止定位")
    print(result["restore_prompt"])
    print()
    print("恢复确认清单：")
    for item in result["restore_checklist"]:
        print(f"  [ ] {item}")
    print()
    print(f"※ {guide.CORE_WARNING}")
    return 0


def _cmd_status(assistant: Assistant, as_json: bool) -> int:
    session = assistant.session()
    if as_json:
        _emit_json(session.to_dict())
        return 0
    _section("当前会话")
    print(f"状态：{session.state}")
    if session.latitude is not None:
        print(f"坐标：{session.latitude}, {session.longitude}")
    if session.remaining is not None:
        print(f"剩余：{int(session.remaining)} 秒")
    if session.message:
        print(f"说明：{session.message}")
    if session.error:
        print(f"错误：{session.error}")
    return 0


# ---------------------------------------------------------------- 参数


def _tri(value: bool | None) -> bool | None:
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watch-hypertension-assistant",
        description=(
            "Apple Watch 高血压通知兼容性与设置测试助手。"
            "通过已有 DVT 定位引擎做固定地区定位测试，并指导在健康 App 中人工核验。"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--engine-url",
        default=None,
        help="直接指定运行中的引擎地址（如 http://127.0.0.1:8899），不自动拉起引擎。",
    )

    sub = parser.add_subparsers(dest="command")

    # 顶层默认值：不带子命令时直接当 check 用，不会因缺字段崩掉。
    parser.set_defaults(
        watch=None,
        watchos=None,
        ios=None,
        age=None,
        hypertension=None,
        pregnant=None,
        wrist_detection=None,
        json=False,
        region=None,
        hold=DEFAULT_HOLD_SECONDS,
    )

    def add_compat_flags(target: argparse.ArgumentParser) -> None:
        target.add_argument("--watch", default=None, help="机型 id，见 `regions`/`families` 输出")
        target.add_argument("--watchos", default=None, help="watchOS 版本，如 26.1")
        target.add_argument("--ios", default=None, help="iPhone 的 iOS 版本，如 26.1")
        target.add_argument("--age", type=int, default=None, help="用户年龄")
        target.add_argument(
            "--hypertension",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="是否曾被诊断高血压",
        )
        target.add_argument(
            "--pregnant", action=argparse.BooleanOptionalAction, default=None, help="是否处于妊娠期"
        )
        target.add_argument(
            "--wrist-detection",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="腕部检测是否开启",
        )

    p_check = sub.add_parser("check", help="完整检查：环境 + 前置条件 + 兼容性（不启动定位）")
    add_compat_flags(p_check)
    p_check.add_argument("--json", action="store_true", help="输出 JSON")

    p_env = sub.add_parser("env", help="只检查平台与引擎")
    p_env.add_argument("--json", action="store_true")

    p_devices = sub.add_parser("devices", help="只检查 USB 设备")
    p_devices.add_argument("--json", action="store_true")

    p_regions = sub.add_parser("regions", help="列出四个地区预设")
    p_regions.add_argument("--json", action="store_true")

    p_compat = sub.add_parser("compat", help="只做兼容性检查")
    add_compat_flags(p_compat)
    p_compat.add_argument("--json", action="store_true")

    p_families = sub.add_parser("families", help="列出可比对的机型选项")
    p_families.add_argument("--json", action="store_true")

    p_start = sub.add_parser("start", help="按地区预设启动定位测试")
    p_start.add_argument("--region", required=True, help="地区预设：us / hk / fr / jp")
    p_start.add_argument(
        "--hold", type=int, default=DEFAULT_HOLD_SECONDS, help=f"保持秒数（默认 {DEFAULT_HOLD_SECONDS}）"
    )
    p_start.add_argument("--json", action="store_true")

    p_stop = sub.add_parser("stop", help="停止定位并恢复真实位置")
    p_stop.add_argument("--json", action="store_true")

    p_status = sub.add_parser("status", help="查询当前会话")
    p_status.add_argument("--json", action="store_true")

    p_guide = sub.add_parser("guide", help="健康 App 人工核验指引")
    p_guide.add_argument("--json", action="store_true")

    return parser


def _cmd_families(as_json: bool) -> int:
    payload = [
        {
            "id": item["id"],
            "label": item["label"],
            "supported": item["supported"],
            "note": item.get("note", ""),
        }
        for item in compat.families()
    ]
    if as_json:
        _emit_json({"families": payload})
        return 0
    _section("机型选项")
    for item in payload:
        if item["supported"] is True:
            flag = "[支持]"
        elif item["supported"] is False:
            flag = "[不支持]"
        else:
            flag = "[未知]"
        print(f"  {flag} {item['id']:<9} {item['label']}")
        if item["note"]:
            print(f"           {item['note']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # 必须在任何输出之前执行：argparse 的报错信息本身也可能含非 ASCII。
    _ensure_utf8_when_redirected()
    parser = build_parser()
    args = parser.parse_args(argv)
    # 不带子命令时默认执行完整检查。为了让 check 的参数有默认值，
    # 顶层解析器统一 set_defaults（见 build_parser），避免拿到缺字段的 Namespace。
    command = args.command or "check"

    try:
        if command == "regions":
            return _cmd_regions(args.json)
        if command == "families":
            return _cmd_families(args.json)
        if command == "compat":
            return _cmd_compat(args)
        if command == "guide":
            payload = guide.render()
            if args.json:
                _emit_json(payload)
            else:
                _print_guide()
            return 0

        assistant = Assistant(engine_url=args.engine_url)

        if command == "check":
            return _cmd_check(assistant, args)
        if command == "env":
            return _cmd_env(assistant, args.json)
        if command == "devices":
            return _cmd_devices(assistant, args.json)
        if command == "start":
            return _cmd_start(assistant, args)
        if command == "stop":
            return _cmd_stop(assistant, args.json)
        if command == "status":
            return _cmd_status(assistant, args.json)
    except AdapterUnavailable as exc:
        print(f"错误：{exc}", file=sys.stderr)
        if exc.hint:
            print(f"建议：{exc.hint}", file=sys.stderr)
        return 2
    except AdapterError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
