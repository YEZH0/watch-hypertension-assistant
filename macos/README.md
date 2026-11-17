# Watch Hypertension Assistant — macOS

本目录 GPL-3.0-only，无担保；完整许可证见 LICENSE，可按该许可证复制和修改。
仅提供源码。使用公共助手的简洁命令行界面，不制作 APP/DMG。

工具会暂时模拟 iPhone 位置，不能保证启用地区受限的高血压通知功能。
不得绕过设备、年龄或健康资格要求。定位请求下发不等于手机已采纳，更不等于健康功能已开通。

## 源码安装

需要 macOS、USB 数据线、Python 3.13（uv 可安装）、uv；首次开发者镜像准备需要完整 Xcode。

```sh
git clone https://github.com/YEZH0/watch-hypertension-assistant.git
cd watch-hypertension-assistant
# 合并前验证版本：git switch feat/macos
zsh macos/scripts/install.command
macos/.venv/bin/python -m assistant --help
```

安装脚本只安装 Python 依赖与公共助手，不触碰设备设置，不下载 MFi 身份。
公共助手和 GPL 桥接使用同一解释器但分进程运行；公共助手通过 HTTP 调用，未改动 assistant/。

## 使用

```sh
macos/.venv/bin/python -m assistant env
macos/.venv/bin/python -m assistant devices
macos/.venv/bin/python -m assistant check
macos/.venv/bin/python -m assistant guide
```

连接且只连接一部 iPhone。解锁手机，按提示信任电脑；在“设置 → 隐私与安全性 → 开发者模式”启用并按手机提示重启确认。
设备识别不等于开发者模式就绪；DVT worker 启动时检查该状态，未满足会阻断。
首次连接若 DVT 镜像未准备好，先打开 Xcode 完成设备准备。
也可在明确同意 devicectl 向 Apple 请求设备开发者镜像票据后执行：

```sh
macos/.venv/bin/python -m location_studio_mac.app --worker dvt_prepare --allow-apple-ticket
```

此准备沿用旧流程，可能与 Apple 联网，不能静默代用户同意。普通 DVT 测试使用既有本地网络限制沙箱。

核对 Apple 当前官方说明：<https://support.apple.com/en-us/117296> 和 <https://www.apple.com/watchos/feature-availability/>。
在 iPhone Watch App“通用 → 关于本机”确认机型和系统；在健康 App 确认年龄及使用资格，开启腕部检测。
助手无法通过 USB 自动读取配对手表的健康功能资格；不确定的条件须人工确认，不应当成通过。

完成资格核对后，选择固定预设之一：

```sh
macos/.venv/bin/python -m assistant start --region hk
# 其他选项：us、fr、jp；最长 180 秒，不开放地图或任意坐标。
macos/.venv/bin/python -m assistant status
macos/.venv/bin/python -m assistant stop
```

在 iPhone 地图检查是否采纳测试位置；再在健康 App“头像 → 健康检查清单”查找高血压通知，按当前 App 指引核验。
不可把没有显示功能解释为定位失败，也不可把定位成功报告为功能开通。功能不是即时血压测量。
停止或自动到期后，worker 尝试 clear 并关闭会话；请在地图确认真实定位。若未恢复，拔线等待 GPS 更新，必要时重启后复查。
异常退出、clear 失败、强杀、睡眠、断线情况下不能承诺恢复，须人工核验。

## 实现、来源与验证

旧分支 `feat/macos-iap2` 固定来源提交 `9f978d21370ad4d67ff9f4d59d0c0f1e254c9b55`。
原样保留 src/location_studio_mac 的 DVT、Engine、worker 及实验性 iAP2，桥接只调用 DVT。
旧 app.py 地图 GUI 仅为来源参考，不是新助手入口，不建议运行。
完整 vendor 源码、LICENSE、THIRD_PARTY_NOTICES 保留；TEST_REPORT.md 与 RESEARCH.md 是旧项目历史证据，不能代表本项目实机通过。
2026-11-17 新增 bridge.py、测试、安装及文档，未修改旧定位实现。
不应将 HTTP 进程边界直接视为最终法律结论；发行者仍须履行 GPL 源码和声明义务。

桥接手动启动：`macos/.venv/bin/python -m location_studio_mac.bridge --host 127.0.0.1 --port 8900`。
仅监听 IPv4 回环；拒绝浏览器 Origin，设备句柄为临时别名，不返回真实 UDID；不记录原始 worker 日志。
同机进程仍可调用桥接。退出桥接时会尝试停止 worker。实验性 iAP2 无默认入口，不承诺生效。

```sh
cd macos
uv run --no-sync pytest -q
```

新项目测试和实机覆盖见 INTEGRATION_TEST_REPORT.md。
