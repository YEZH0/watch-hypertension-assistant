# macOS 验证记录 · 2026-11-17

实际执行者：本聊天 AI Agent；开发自测，不是独立 QA / 审计通过结论。
环境：macOS 27.0.1 (26A434), arm64, Python 3.13.14, uv 0.13.8。

## 内部核验

- `uv sync --locked` 成功；独立 macos 虚拟环境与锁文件。
- `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest -q`：48 passed。
- 其中上游 37 项，新增 11 项覆盖坐标边界、ACK 与人工验证分离、Qt 界面离线状态、
  模拟设备事件、错误脱敏、重复启动阻断、SIGINT 停止、超时与认证子进程清理。
- 26 个上游 tracked 文件与固定版本逐字节一致。
- Qt 离屏界面实际渲染并检查：主窗口、坐标选择、状态与验证按钮可见。
  原生 macOS 缩放 / VoiceOver 及不同屏幕尺寸尚未完整验证。
- PyInstaller 首次生成 arm64 .app；打包工作进程成功执行设备检测。
  首次源码归档因 HEAD 尚不包含新文件失败，已调整为提交源码后重建。
- 沙箱工作进程当前无设备时正确拒绝启动 probe，没有发送坐标。
- 完整 Qt 安装与依赖构建较大；后续可评估仅使用 Essentials 精简发行体积。

## 实机范围

老板提供：此前上游 CLI 同一聊天完成纽约坐标测试，并确认恢复真实定位。
该记录不替代新 Mac 应用验收。新应用不自动据此标记验证成功。
本轮新应用 Engine（Qt 控制器 + 受沙箱限制的上游 worker）实机记录：
- iPhone 15 / iOS 27.0.1：重新插拔后 USB/CarKit、识别、认证成功。probe 正常退出，坐标发送 0。
- send：40.7128, -74.0060，180 秒，95 个定位包 ACK，正常到期退出，退出码 0。
- 老板两次反馈仍在真实位置，且确认已经切换定位服务仍未改变：本轮位置采纳验证不通过。
- 停止后进程扫描未见 worker/helper 残留；未变更系统配置或核心协议。
- 首次测试未覆盖独立 GUI；后续打包版测试见下一节。
- 老板已确认断开 USB，苹果地图真实位置正常。

## 发布门禁

源码只在 macos/ 和指定 Mac workflow。Windows、根公共文件未修改。
未完成独立 QA、安全 / 法律 / 依赖源码发行审查、Developer ID 签名、公证、Intel 测试。
CI workflow 已提供；本次观察到 Mac PR workflow 被取消，不能计为通过。
本地最终 PyInstaller 构建成功，约 186 MB；codesign 显示 ad-hoc、无 TeamIdentifier。
打包目录扫描 .p7b/.pk8 数量为 0。仅草稿 PR，不代表可正式发布。
Git HTTPS 缺少本机凭据，使用已连接 GitHub 插件上传分支；本地与远程代码树保持一致。

## 第二轮：打包 .app 真实桌面测试

2026-11-17，实际通过 macOS 桌面界面操作既有 arm64 .app，非源码测试替代。
- USB 检测：界面显示 iPhone15,4 / iOS 27.0.1 已配对。
- GUI probe：识别已接受、认证成功、订阅可见，ACK 0；限时结束后工作进程退出。
- GUI send：纽约 40.7128,-74.0060，设置 180 秒；界面出现认证、订阅及 ACK，最后观测计数 60。
- 老板反馈仍在真实位置。本轮未再次切换定位服务：此前相同设备排查已验证切换后仍不采纳。
  因此本轮定位采纳不通过，不能把 GUI 运行正常或 ACK 当成功。
- 手动停止按钮：会话提前停止，界面显示“会话已停止”“工作进程已退出”，无后台定位任务。
- 恢复保护：未确认恢复时点击开始，弹出“请先完成上次会话的真实定位恢复确认”，无新发送会话。
- 老板确认已拔线、真实位置正常后，操作恢复确认按钮，界面显示“恢复：用户已确认”。
- 正常关闭窗口后 macOS 应用清单显示 isRunning=false；进程扫描未发现 app/worker/helper 残留。
- 本轮离线测试复跑：48 passed in 1.40s。未修改实现、上游协议或 Windows 文件。

结论：打包版 GUI 的连接、probe、发送链路、手动停止、恢复保护/确认及关闭路径已有实测；
实际定位采纳仍不通过。其他设备、Intel、VoiceOver、异常断电/休眠等尚未验收。

## 第三轮：原始 iAP2 调查与独立 DVT 成功

详见 RESEARCH.md。原始环境 90 秒 iAP2 对照 53 个 ACK，手机未采用；
时间差、NMEA 编码和实际请求间隔均未发现足以解释本轮失败的证据。
手机日志计数支持 NMEA 已转交定位链，仍未定位具体根因。
经老板明确批准 DVT 与必要 Apple 票据请求后，官方 devicectl 准备成功；
独立 DVT 90 秒纽约测试中老板确认蓝点生效，clear/隧道关闭后确认真实位置正常。
本轮 51 passed in 1.86s。GUI 仍是 iAP2，不能将 DVT 成功写成现有 GUI 已修复。

## 第四轮：对标 Windows UI

只读参考 origin/fix/windows-stabilization @ 0bcf9b3 的UI与品牌色，Windows文件未变。
Mac调整为侧栏控制台＋离线世界选点，固定开始/停止、折叠认证/日志、1/3分钟快捷档、
坐标复制、快捷城市、标记同步和缩放。保留全部原有定位安全确认及自定义时长。
1160×820与940×640（展开日志）实际离屏渲染检查；机械样式检测无发现，不能替代人工/独立QA。
新增交互回归覆盖城市、时长、自定义档、无效坐标、缩放与投影往返；52 passed in 1.97s。
本轮离线回归不发送坐标；新版 .app 已在真实桌面启动并确认地图资源加载。
桌面检测到用户并发进行设备/通信操作，不计为本轮自动定位验收；iAP2/DVT结论保持此前记录。

## 第五轮：修复 GUI 仍使用 iAP2，接入 DVT 并实机成功

老板反馈“软件能打开，但手机位置不变”。原因之一是此前只交付UI优化，GUI默认仍为iAP2，
已成功的DVT独立脚本尚未接入GUI。本轮将DVT作为推荐默认路线，保留iAP2实验选项。
准备、通道检查、发送、清除与异常退出由共享 location_studio_mac/dvt.py 实现，脚本和GUI不再分叉。
准备前显示Apple数据流授权；发送走回环受限沙箱，不读MFi材料，默认测试最长180秒。

实际发现并修复两项打包/检测缺陷：
- 打包DVT导入链缺少apple_compress元数据导致启动即退出；改为递归收集pymobiledevice3依赖元数据，
  worker导入异常改为脱敏事件，GUI明确显示失败，不只隐藏到stderr。
- 传统Personalized镜像查询返回false，错误阻断已由官方devicectl准备的可用DVT服务；
  去掉此不可靠前置阻断，保留开发者模式检查，以实际DVT服务连接判断可用性。

本地54项测试通过，含GUI默认DVT/无MFi启动、沙箱命令路由、DVT正常与异常clear/关闭。
最终打包worker的dvt_probe返回dvt_tunnel_connected、dvt_probe_succeeded，退出0，未发坐标。
随后通过真实桌面 .app 按钮运行纽约40.7128,-74.0060，设置180秒：
- GUI显示DVT通道已连接、坐标请求已发送；老板明确回复“成功了”。
- 记录手机人工成功后，手动停止；日志显示dvt_clear_sent、dvt_session_closed、process_exit。
- 老板确认已断开USB，真实位置正常；最终GUI显示手机改变和恢复均为用户已确认。
- 这次是打包GUI实际成功，不能与此前仅独立脚本成功混淆。

本轮未修改Windows、根公共文件或上游iAP2核心协议；不宣称iAP2已修复。
仍缺其他机型/Intel/VoiceOver/休眠断电等覆盖，独立QA、安全/发行审查、签名公证待完成。

## 上传前 CI 隔离修复

远程根CI在Ubuntu/Python3.11–3.13失败，日志显示其根目录pytest误收集macos/scripts、
macos/tests及vendor测试，而根环境未安装location_studio_mac/PySide6/accessory_location。
新增macos/conftest.py：仅当由祖先项目启动pytest时隔离Mac子项目；从macos/运行仍完整收集。
未改根CI、根pyproject或Windows测试。新增边界测试，远程重跑结果另行核验。
Mac专用PR工作流此前被取消，不能宣称远程Mac CI已通过。
本地复核：Mac独立环境55项通过；从仓库根以--rootdir=.对macos执行collect-only，
正确收集0项。该收集检查不代表根项目所有测试通过，需远程CI验证。
