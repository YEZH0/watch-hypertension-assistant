# Mac 与共享 wizard 的实际契约

2026-11-18 整合 `feat/guided-flow-windows @ 0bc5750019d2550ec511340f76b261f850bcb2d8`，不是重写公共流程。该分支与 Mac PR #1/#3 均待维护者审核。

在仓库根目录，以 `macos/.venv/bin/python -m location_studio_mac.assistant` 为 MAC：

```sh
# 只读流程定义：
MAC wizard --plan --json
# 每一条只在用户确实作出相应确认后执行，不可整段自动跑：
MAC wizard --answer accept --json
MAC wizard --answer ready --json
MAC wizard --answer connected --json
MAC wizard --answer confirmed --json
MAC wizard --answer us --json       # 此处只是例子，必须由用户选地区
MAC wizard --answer moved --json    # 或 not_moved / unsure
MAC wizard --answer setup_done --json # 或 card_absent / eligibility_blocked / not_checked
MAC wizard --answer restored --json # 或 not_restored / unresolved
MAC wizard --status --json
```

MAC 是文档简称，执行时替换为完整 Python 命令；不需要创建 shell alias。
阶段按顺序为 safety/environment/usb/baseline/region/simulate/health/restore/report。
全局 `--engine-url http://127.0.0.1:8900` 放在 wizard 前；`--state-file` 放在 wizard 后。
可为本轮选择私有 scratch 路径，避免向导进度进入源码仓库；最终按隐私要求删除临时进度，不上传健康设置结果。

返回 exit_code=0 才继续。被阻断则停留当前阶段处理；不根据 next 字段自动替用户确认。
资格信息可以不填写，此时保持未知/需人工核对，不代填健康资料；明确不符合医疗要求时不提供绕过。
地图 moved、健康 setup_done、恢复 restored 三者只能分别使用用户实际自述，不能由 active 推断。
健康阶段提交回答会调用既有 stop；恢复阶段仍必须再由用户看地图确认。进入健康前看 status 剩余时间，到期后仍可按官方流程只读核验，不自动续时。
入口可见但设置未完成/无法确定时用 not_checked，并在对话中精确说明；不得为了凑齐向导而提交 setup_done。
Ctrl+C/异常尽力 stop，结果不能证明手机恢复。手动取消也必须走停止和恢复确认。

隐私：公共向导保存类别化流程进度（含用户自述设置结果），默认不是“完全无持久化”；不要打印/上传状态文件。需零留存时使用本轮临时路径并在最终汇报后删除。不得写入年龄、诊断、妊娠、真实地址、序列号或认证材料。

恢复阶段的第一条用户可见提示必须直接展示完整路径与约 10 秒关开操作，不能只存在 stderr/JSON 日志中：若地图未恢复，进入“设置→隐私与安全性→定位服务”，关闭约 10 秒再打开，然后回地图确认。不将该操作当作所有设备必需或立即恢复保证。
