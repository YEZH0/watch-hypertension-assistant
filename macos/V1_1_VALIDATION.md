# PR #1 审核与 V1.1 Mac 验证（2026-11-17）

## 依赖和边界

- 已完整读取 Issue #2 正文；读取时评论为空。已在该 Issue 提交公共契约协调请求。
- PR #1：open、draft、未合并，可合并；来源 feat/macos @ 50d838c。当前为开发负责人自审，非独立 QA/法律审计，不自动批准或合并。
- 原 PR #1 落后 main @ 1cec2a7 一个公共提交。原分支未覆盖；新分支 feat/guided-flow-macos 以 PR #1 为基础合入该 main。
- 远端尚无 guided-flow-windows 分支/公共 wizard 契约；main 无 wizard。Mac 不定义竞争性状态机，不修改公共模块。
- 本分支 diff 仅 macos/** 和 Mac 负责的 agent/macos-install-prompt.md、既有 agent/macos.md 兼容指引。
- PR 应依赖 PR #1；公共契约稳定后仍需同步并做真正 wizard 集成验证，未达成 V1.1 全部验收。

## 原 PR #1 自审结果

| 检查 | 结论/处理 |
|---|---|
| DVT/USB/停止协议复用 | engine.py、dvt.py、worker.py 与 PR #1 完全一致，没有重写。 |
| 异常退出状态 | 发现非零 process_exit 被忽略，可能回到 idle；本分支改为 error，保留“清理未确认”和恢复提示。 |
| 未下发便退出 | 连接中 worker 正常退出但无 set_sent，现在返回 error/503，不宣称启动成功。 |
| 设备检测竞争 | PR #1 已修复等待 worker 退出才返回设备结果；本轮回归通过。 |
| 开发者模式/镜像 | 保留既有 worker 检查，桥接只映射安全中文提示；不自动开启设置/请求票据。 |
| 请求成功的含义 | 仅 DVT 请求，不提升地图/健康/GPS 状态。公共 CLI 过强文案已在 Issue 协调，由 Windows 负责。 |
| 取消/超时/退出 | 继续复用 Engine stop/guard，补充合成 worker 测试、HTTP 超时触发 stop、桥接 SIGTERM 清理测试。 |
| iAP2 | 仅保留来源参考，默认不启用，ACK 不作为手机采纳证据。 |
| GPL 与敏感文件 | macos/LICENSE、vendor、版权声明保留，无改动；tracked 文件无私钥/证书扩展名。未上传设备标识/票据/健康资料。 |

这些缺陷修复在 V1.1 独立 PR 中，原 PR 不应被视为已经包含这些补丁。建议维护者先评审修复和合并顺序。

## 本轮环境与自动验证

MacBook Air / Apple M4（Mac16,12），macOS 27.0.1 arm64，Python 3.13.14。
复用现有隔离环境，不安装/改变不相关系统软件。PySide6 6.12.0，pymobiledevice3 9.40.0。

- doctor 实际执行成功：macOS、Python、包元数据、sandbox-exec、Xcode devicectl 检查通过。未访问 USB，不表示手机授权已通过。
- install.command：本轮语法检查通过；V1 原安装实际成功的证据见 INTEGRATION_TEST_REPORT.md。本轮未重建全新机器安装环境。
- Mac 本轮最终 suite：71 passed；zsh macos/scripts/check.command 整体验证。
- 公共助手 suite：97 passed（main @ 1cec2a7）。
- 合成 worker 测试真实运行 QProcess + sandbox-exec：自然到期、主动停止、看门狗、非零崩溃；不访问 USB、不调用定位协议。
- 独立桥接进程 SIGTERM 测试：HTTP active 后终止桥接，合成 worker 收到停止并写入清理标记，桥接正常退出；不代表手机恢复。
- HTTP 请求等待超时测试：返回 504 并发出 /api/stop，不能伪造清理或恢复成功。
- 启动器 Ctrl+C 请求 stop；缺公共 wizard 时安全退出，不发送请求；模拟公共 wizard 存在时参数原样转发。真实公共 wizard 尚未验证。
- 根 CI 配置归公共负责人；本分支仅提供 macos/scripts/check.command，不新增根工作流。Mac GitHub CI 尚未配置/运行，不能标为通过。

## 实机证据分层

| 项目 | V1 历史证据 | 本轮 V1.1 |
|---|---|---|
| iPhone USB / DVT | 前次识别 iPhone、iOS 27.0.1，DVT 下发通过 | 用户明确选择“暂不进行实机定位测试”，未重新核验 USB/开发者模式 |
| 真实位置基线 | V1 没有按本次新门槛单独记录 | 未确认，不允许发送 |
| 美国定位 | 操作者曾确认地图到纽约 | 未发送，不沿用为本轮通过 |
| 手动 stop / 恢复 | V1 stop idle，操作者后续确认真实位置恢复 | 未实机复测 |
| 超时、取消、异常 | 旧证据覆盖有限 | 仅合成 worker 自动验证；实机未知 |
| 香港/法国/日本 | 固定预设单元测试 | 未逐项实机发送 |
| 健康 App 设置完成 | 不采集/发布个人健康 App 结果；入口可见不等于设置完成 | 未完成本轮人工核验，不宣称开通 |

本轮没有访问或保存真实地址、健康状况、UDID、配对记录或认证材料。

## 后续必须完成

1. Windows Agent 在 Issue #2 发布公共 wizard PR、稳定阶段 ID、JSON/继续/取消与清理契约，并安排根入口和 Mac CI。
2. Mac 同步该契约，实测同一 wizard 及既有五个 HTTP 接口，不增加本地状态机。
3. 在用户重新确认地图真实基线、选择地区并明确授权后，再做 V1.1 完整手机流程；按地图/健康设置/恢复分项确认。
4. 完成真机超时、取消、异常及恢复记录；未知项不得标为成功。
5. 用户审核，按依赖顺序合并；本 Agent 不合并 main。

官方资料核对：2026-11-17 通过 Apple 官方检索结果核对 117296 的要求与 Health Checklist 步骤（页面直连返回 429）；地区可用性页面可读取。文档指向官方当前版本，未改公共机型/地区数据库。


## 2026-11-18 共享向导实测更新

已整合 Windows 公共引导分支 0bc5750（未合并 main）；同一 wizard 从 safety 到 report 全部阶段实际执行，没有新建 Mac 状态机。旧文中“无公共契约”等描述是 11 月 17 日的准备状态，现由本节更新。

MacBook Air M4、macOS 27.0.1 arm64、Python 3.13.14，现有隔离环境 doctor 通过。同步后 Mac 71 项、公共流程 143 项测试通过。

本轮用户重新确认苹果地图真实位置基线、明确选择并授权美国预设；共享 wizard 检测到单部 iPhone。DVT 请求 active，用户确认地图采纳纽约测试点；向导健康阶段之后自动 stop，返回 stop_ok true，status idle、error null。用户反馈手动关闭定位服务、等待约 10 秒后重新开启，才恢复真实位置；按该反馈完成 restore 阶段，最终 report。完整恢复路径必须在恢复阶段第一条用户可见提示直接显示，不能隐藏在日志中；未恢复时使用，不承诺立即恢复。

个人健康 App 设置结果仅在本轮私有对话中汇报，不写入公开记录。临时向导状态文件在 report 后已删除，不上传。USB 设备标识、健康资料、真实地址及认证材料未保存到仓库。

本轮验证了启动、地图人工采纳、共享向导停止与人工恢复；没有覆盖真实手机的自动到期、主动取消、异常断线/断电或进程强杀。此类场景仍只有合成 worker 覆盖，不能标为实机通过。未重新在全新 Mac 上安装，GitHub Mac CI 仍未配置/验证。不自动合并 main。
