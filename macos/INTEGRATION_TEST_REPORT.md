# Mac 整合测试记录（2026-11-17）

来源：ios-location-studio feat/macos-iap2 @ 9f978d21370ad4d67ff9f4d59d0c0f1e254c9b55。
新仓库基线 main @ 963e097940c02edc66ae500d025d489cd3d77f90。

- macOS / arm64，Python 3.13.14；uv sync 成功，公共助手 editable 安装成功。
- 原始 Mac suite：55 passed；新增桥接 suite 后：59 passed。
- 新测试覆盖固定四预设、DVT 路线、时长限制、停止、连接中取消、无设备 409、脱敏、HTTP health、拒绝浏览器 Origin。
- 初次合跑因测试先创建 QCoreApplication 导致旧 QWidget 测试退出；测试夹具改用 QApplication 后全部通过。生产桥接仍使用 QCoreApplication。
- 实际 HTTP 桥接在 127.0.0.1:18900 启动成功；公共助手 env 在线、devices 正常返回未识别 iPhone、status idle、stop idle。
- 没有可用的已信任 USB iPhone，未发送定位坐标。新桥接的实机定位、开发者模式启用、停止清理和真实 GPS 恢复均未验证。
- 高血压通知可用性/开通状态未验证，任何定位下发事件都不能作为该功能可用证据。
- 原有 dvt.py、engine.py、worker.py 与来源逐字一致；iAP2 保留但未启用。旧 TEST_REPORT.md 是历史证据。
- 不构建、不发布 EXE、APP、DMG；不改原项目或 PR #2。

当前限制：USB 识别成功不代表开发者模式就绪（由原 DVT worker 在启动时阻断）；手表机型、健康资格、App 入口与真实定位恢复仍需人工核对。
公共许可证边界文档对“HTTP 自动解决 GPL”的绝对表述建议维护者复核，本次不改公共文件。
公共机型/地区数据的所有动态可用性陈述需维护者持续核验，本模块不将预设等同于功能保证。
