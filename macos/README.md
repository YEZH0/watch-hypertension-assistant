# Watch Hypertension Assistant — macOS V1.1 准备分支

复用原 DVT/USB/停止清理实现，不重写定位协议。只发布源码，不制作 APP/DMG。
GPL-3.0-only，无担保，许可证见 LICENSE；完整来源与依赖声明见 THIRD_PARTY_NOTICES.md。
位置模拟不能保证启用地区受限的高血压通知，不得绕过设备或医学使用条件。

## 当前状态与依赖

V1 原接入位于 `feat/macos` / PR #1，尚未合并，保持独立。
本 V1.1 分支 `feat/guided-flow-macos` 依赖 PR #1，已同步 main @ 1cec2a7。
Issue #2 要求 Windows Agent 先发布公共 wizard 的阶段/交互契约；当前尚无该契约。
本分支只转发已安装的公共 wizard，不自行实现状态机；缺失时明确退出且不发送坐标。
现阶段可由 AI Agent 严格按 [完整操作提示词](../agent/macos-install-prompt.md)逐项引导，不能把此准备分支称为全平台 V1.1 验收完成。
根 README/AGENTS/公共教程的链接入口由 Windows Agent 负责协调，本分支不覆盖公共文件。

## 源码安装与检查

先说明将从官方来源安装 Python/依赖、在 macos/.venv 建隔离环境，并取得用户安装授权。
需要 macOS、Git、uv、Python（uv 可安装 3.13）、USB 数据线；首次开发者镜像准备可能需要完整 Xcode。
不要用未知远程脚本，不关闭系统安全设置。

```sh
git clone https://github.com/YEZH0/watch-hypertension-assistant.git
cd watch-hypertension-assistant
# 未合并前的评审版本，先明确告知用户：
git switch feat/guided-flow-macos
zsh macos/scripts/install.command
macos/.venv/bin/python -m location_studio_mac.doctor
```

doctor 仅检查系统、依赖、沙箱与 devicectl，不访问 USB、不请求 Apple 票据、不证明设备已授权。
Mac 有 PySide6、pymobiledevice3 等依赖，不是“零第三方依赖”。公共助手与 GPL 桥接分进程，通过本机 HTTP 通信。
完整 Xcode 可从 Apple 官方渠道安装，初始化/组件下载需用户处理；devicectl 不可用时显示提示，不静默更改开发工具设置。

## 完整手机旅程（必须等待人工确认）

以下 0–8 对应 Issue #2 旅程编号，不是另立的机器阶段 ID。
命令统一使用 `macos/.venv/bin/python -m location_studio_mac.assistant`，下文简称 MAC。
公共契约发布后入口为 `MAC wizard`；现阶段缺失会明确提示，不退化为自动 start。

| 阶段 | 操作与继续条件 |
|---|---|
| 0 告知与资格 | 暂时模拟位置会影响其他 App，仅用于本人/已授权设备。用户按 Apple 官方要求自查机型、系统、腕部检测与医学使用资格；不符合者只读核验/退出，不提供绕过。 |
| 1 安装 | 完成上述源码安装和 doctor，继续后续手机步骤，不能停在 check。 |
| 2 USB | 只连一部 iPhone、解锁、信任电脑，人工检查开发者模式；`MAC env`、`MAC devices`。无设备/多设备不发送坐标。 |
| 3 真实基线 | 设置→隐私与安全性→定位服务开启，允许苹果地图定位/精确位置；地图点击当前位置。**本次用户确认蓝点在真实所在地后才能继续**，不记录地址。 |
| 4 地区授权 | `MAC regions` 展示 us/hk/fr/jp 和坐标，用户明确选择并同意后才 `MAC start --region 所选代码 --hold 180`。不得代选。 |
| 5 地图核验 | `MAC status` 看剩余时间；让用户回苹果地图点击当前位置，选择已移动/未移动/不确定。active 只表示下发请求，不能当作手机采纳证据。 |
| 6 健康核验 | 先显示剩余时间；按 Apple 官方健康 App 流程核验并由用户确认设置结果。入口可见不等于设置完成，模拟结果不决定功能资格。 |
| 7 停止恢复 | 完成/取消/超时/异常均 `MAC stop`、`MAC status`；用户在地图确认已恢复/未恢复/不确定。idle 不证明真实位置恢复。 |
| 8 分项报告 | 安装、引擎、DVT 请求、地图、健康 App 设置、真实定位恢复各自报告；未确认写未知，不输出一键成功。 |

预设与公共 regions.json 一致：美国纽约 `(40.758,-73.9855)`、中国香港 `(22.2819,114.1588)`、法国巴黎 `(48.8584,2.2945)`、日本东京 `(35.6595,139.7005)`。
没有自由坐标/地图选点入口。引擎测试最长 180 秒，等待用户操作可能超时；到期安全结束，不自动续时。再测须重新确认基线、地区与授权。

### USB、开发者模式与镜像

开发者模式在 iPhone 设置→隐私与安全性，由用户按系统提示重启并确认。能识别 USB 不代表开发者模式已就绪。
DVT worker 会在启动时检查；缺失则阻断，桥接给出中文提示。服务不可用时先用 Xcode 完成设备准备。
只有明确说明可能向 Apple 发送设备开发者镜像票据并取得用户同意，才可执行原流程：

```sh
macos/.venv/bin/python -m location_studio_mac.app --worker dvt_prepare --allow-apple-ticket
```

不请求 MFi 身份，不导入证书、私钥、配对记录；普通 DVT worker 沿用已有 sandbox-exec 沙箱。

### 蓝点未移动与恢复缓慢

蓝点未移动先查会话是否 active/剩余时间、线缆、解锁、地图定位/精确位置权限、当前位置刷新。
只有合理且用户同意时，才建议切换定位服务约 10 秒；这可能使模拟失效，不保证测试成功。
**不能因 set_sent、active、iAP2 ACK 或计时器就写“手机位置已成功”。**

停止后先回地图点当前位置，由用户确认；仍显示测试位置时，先断开 USB、等待更新、重开地图。
若仍未恢复且用户同意，可进入设置→隐私与安全性→定位服务，关闭约 10 秒后重新开启，再核验。
此为条件性排查，不是所有设备必做步骤，也不保证立即恢复。仍异常时考虑重启并复查或联系 Apple 支持。
无论 clear 是否请求成功、idle、正常退出或强杀，都不能替代人工恢复确认。

### 健康 App 核验

官方入口通常为：健康 App→右上角头像→健康核对清单（Health Checklist）→高血压通知。
版本/语言可能有菜单差异。按系统提示如实核对资格和设置，不代填；用户可只报告设置结果，不披露健康状况。
卡片不存在或无法设置可能有多种原因；逐项核对型号、系统、地区与资格，不推断唯一原因。
[Apple 官方说明](https://support.apple.com/en-us/117296)与[地区可用性](https://www.apple.com/watchos/feature-availability/)为准。
入口可见、设置完成、收到通知是不同状态；本工具不是血压计或诊断工具。

## 验证与来源

```sh
cd macos
uv run --no-sync pytest -q
# 公共助手测试从根目录：
# macos/.venv/bin/python -m pytest tests -q
```

来源 `ios-location-studio feat/macos-iap2 @ 9f978d21370ad4d67ff9f4d59d0c0f1e254c9b55`。
原 DVT、Engine、worker 与完整 accessory-location vendor 保留。旧 app.py 为参考 GUI，不是新助手入口。
iAP2 仅实验，不默认启用，不把 ACK 当作地图采纳证据。LICENSE 与版权声明不得删除或混入 MIT 模块。
HTTP 进程边界不应被当成最终法律结论；发行者仍须履行 GPL 对应源码与声明义务。
历史证据见 INTEGRATION_TEST_REPORT.md；本轮审核与 V1.1 未完成项见 V1_1_VALIDATION.md。
不上传设备标识、原始日志、票据、健康信息、私钥或真实位置。
