# Agent 提示词索引

本项目提供两套 AI Agent 提示词，分别对应 Windows 与 macOS。

| 文件 | 用途 | 给谁用 |
|---|---|---|
| [windows-install-prompt.md](windows-install-prompt.md) | 安装 + 验证 + **0–8 全流程引导** + 分项汇报 | 终端用户 / 其 AI Agent |
| [macos-install-prompt.md](macos-install-prompt.md) | 用法 A：开发桥接接口<br>用法 B：本机安装验证 | Mac Agent<br>终端用户 |

> **只给仓库链接、连提示词都不想写？** 让 Agent 先读仓库根目录的
> [../AGENTS.md](../AGENTS.md)，那里有同样的完整流程与硬约束。

## 怎么用

1. 打开对应文件；
2. 复制其中 ````text` 代码块里的全部内容；
3. 粘贴到你的 AI Agent 对话框（Claude Code、Cursor、WorkBuddy 等）；
4. Agent 会逐步执行，每步都有检查点，需要你看手机的地方它会停下来问。

## 两套提示词共同的内置约束

两份提示词都把下面这些写死在指令里，防止 Agent"自作聪明"：

* 不修改 `assistant/` 源码来掩盖问题
* 不声称"高血压通知已开通/已验证/已生效"
* 不把引擎 `active` 当作"位置已改好"的证据
* 不绕过医疗适用条件
* 不在用户没明确回答时推进阶段
* 不打包 EXE / APP / DMG
* 不提交或上传设备序列号、Apple ID、证书、私钥
* 不下载来源不明的第三方程序、不执行仓库外的远程脚本
* 用户拒绝安装依赖时不偷偷绕过

## 为什么 Windows 提示词变长了

历史版本的提示词以「安装完 + `pytest` + 跑一次 `check` + 给出下一条命令」结束。
真实用户按它做完之后，最容易漏掉的正好是最关键的三件事：

1. 改动前没确认真实位置基线 → 后面无法判断蓝点是否真的动了；
2. `start` 返回 active 就以为成功了 → 没去地图上看；
3. 没在健康 App 里核验 → 把「跑完了」当成「功能可用」。

现在提示词把 0–8 阶段和这三处确认写进去了，并明确要求 Agent 停下等回答。

## 注意

Agent 执行 pip 安装、启动引擎进程等操作会改动你的机器。建议：

* 先看一遍提示词内容再交给 Agent；
* 使用虚拟环境隔离 Python 依赖；
* 涉及安装第三方项目时，自己确认许可证（见 [../docs/LICENSE-BOUNDARY.md](../docs/LICENSE-BOUNDARY.md)）。

## 手动安装

不想用 Agent 的话，直接看 [../docs/QUICKSTART.md](../docs/QUICKSTART.md) 与
[../docs/TUTORIAL.md](../docs/TUTORIAL.md)。
