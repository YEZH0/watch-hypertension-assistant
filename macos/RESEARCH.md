# 定位采纳调查与 DVT 对照 · 2026-11-17

执行者：本聊天 AI Agent；开发自测及研究，非独立 QA/审计结论。

> 本文记录独立实验阶段；后续已将DVT接入GUI并获手机成功/恢复确认，当前用法以README和TEST_REPORT第五轮为准。

## 实际结论

- 原有 iAP2 仍未取得稳定位置采纳，不能宣称已修复。
- 独立 DVT 开发者定位测试成功：90 秒纽约 40.7128,-74.0060；
  老板在手机确认蓝点移动到纽约，并确认结束、断开 USB 后真实位置正常。
- 现有 GUI 和默认引擎保持 iAP2；交付独立 opt-in 准备/测试脚本，尚未集成 GUI。

## iAP2 排除与证据

1. 本地最初成功的上游目录为 commit 8a13296，源码与 Mac vendor 一致，上游无新提交。
   Mac lock 部分间接依赖较新，核心 pymobiledevice3 9.40.0 与 cryptography 50.0.2 相同。
2. 手机与 Mac 的 epoch 时间差约 0.02 秒。独立检查 NMEA checksum、纽约坐标往返及边界通过。
3. 第一轮原始环境 90 秒认证成功，但没有订阅，0 坐标发送；不能用此轮证明采纳失败。
4. 手机前台地图再次请求后，原始上游环境第二轮 90 秒，认证、订阅成功，53 个定位包 ACK；
   老板反馈仍在真实位置。对照排除了“只有 PyInstaller/GUI 封装才失败”的假设。
5. 实际订阅参数：0、0x8001、0x8002 均为 250 ms。当前 1 Hz 发送满足此最小间隔。
   上游遗漏参数 0 的处理值得另议，但本次数据不支持它是失败根因；未修改协议。
6. 同时只读统计手机 syslog：locationd 7317 行、accessoryd 755 行、NMEA 转发标记 106、
   locationd 中 NMEA 提及 592、fusion 标记 25、locationd reject/invalid 关键词 66。
   只输出聚合计数，未保存或上传原始日志、坐标、标识或凭据。
   这些计数支持 NMEA 已进入手机处理链；关键词不能证明具体拒绝原因或因果关系。
   对照无发送基线 10 秒：locationd 219、accessoryd 21、转发标记和 fusion 均为 0。

## 研究来源与限制

- Apple isProducedByAccessory：外部配件来源标识，不能据此证明系统已选中本次位置。
  https://developer.apple.com/documentation/corelocation/cllocationsourceinformation/isproducedbyaccessory
- xcertplay 源码 Iap2LocationSubscription.kt，研究 commit 1298fb35e29ee30e7bd849cb0e751b52aa22a13f：
  参数 0 整体间隔与 0x8001.. 各句间隔分别处理。
  https://github.com/shilapi/xcertplay/blob/1298fb35e29ee30e7bd849cb0e751b52aa22a13f/shared/src/main/java/com/shilapi/xcertplay/transport/Iap2LocationSubscription.kt
- CPC200 固件研究记录 accessoryd → locationd 转发与位置融合，作为日志标记的研究线索，
  其硬件/iOS/CarPlay 环境与本机不同，不能当作本机根因证明。
  https://github.com/lvalen91/CPC200-CCPA_resources/blob/main/documentation/02_Protocol_Reference/usb_protocol.md
- 上游当前无开放 issue，也没有找到能据此承诺修复当前设备采纳的官方补丁。

## DVT 授权与执行

老板明确批准独立 DVT 测试及必要 Apple 票据请求：ECID、芯片/主板编号、nonce、镜像摘要；
不发送位置或 MFi 私钥给票据服务器，不替换默认 iAP2，不修改 Windows。
只读发现：手机 DeveloperModeStatus=true，Personalized 开发者镜像原先未挂载，
本机已安装完整 Xcode 的 iOS_DDI，镜像 manifest 支持该机型。

初始第三方 mounter 准备尝试未成功：Python CA 校验失败，后续服务返回 NotPairedError。
发现其默认 TSS HTTP/verify=False 后未沿用该传输；曾尝试强制 HTTPS 验证且未绕过失败。
最终采用 Apple 官方 devicectl --auto-mount-ddis，返回 0 与 ddiMetadata，完成准备。
交付的 prepare_dvt.py 仅使用此官方路径，无自定义 TSS 或关闭证书验证。
临时 TLS 排查依赖未进入项目 lock/运行依赖。

通过同一 Mac 独立虚拟环境运行 userspace RSD tunnel → DvtProvider → LocationSimulation：
- dvt_tunnel_connected
- dvt_set_sent（人工确认前始终 phone_location_verified=false）
- 老板确认纽约位置生效
- 90 秒到期：dvt_clear_sent、dvt_session_closed，退出码 0
- 老板确认已恢复真实位置
- 进程扫描无测试会话/认证 helper 残留

DVT 发送使用额外沙箱：只允许回环 IP 与本地 USB 所需 Unix 通信；
实际验证外部 1.1.1.1:443 被拒、本机回环 listener 可用。
不下载身份、不接触 MFi 私钥、不更改安全设置。开发者镜像挂载可保留，不能宣称已还原所有开发状态。

## 交付边界

本轮增加 scripts/prepare_dvt.py、scripts/test_dvt.py、scripts/dvt-local-only.sb；
新增离线测试覆盖官方工具输出脱敏、DVT 正常到期及 set 异常后的 clear/上下文关闭。
本地共 51 项通过。仅 Mac 子目录修改，现有 .app 二进制未改动，PR 保持草稿。
后续如集成 GUI，应清楚区分两种路线、首次 Apple 数据流同意、手机验证与恢复状态。
