# Agent 提示词索引

本项目提供两套 AI Agent 提示词，分别对应 Windows 与 macOS。

| 文件 | 用途 | 给谁用 |
|---|---|---|
| [windows-install-prompt.md](windows-install-prompt.md) | 本机安装 + 验证 + 首次检查 | 终端用户 / 其 AI Agent |
| [macos-install-prompt.md](macos-install-prompt.md) | 用法 A：开发桥接接口<br>用法 B：本机安装验证 | Mac Agent<br>终端用户 |

## 怎么用

1. 打开对应文件；
2. 复制其中 ````text` 代码块里的全部内容；
3. 粘贴到你的 AI Agent 对话框（Claude Code、Cursor、WorkBuddy 等）；
4. Agent 会逐步执行，每步都有检查点。

## 两套提示词共同的内置约束

两份提示词都把下面这些写死在指令里，防止 Agent"自作聪明"：

* 不修改 `assistant/` 源码来掩盖问题
* 不声称"高血压通知已开通/已验证"
* 不绕过医疗适用条件
* 不打包 EXE / APP / DMG
* 不提交或上传设备序列号、Apple ID、证书、私钥
* 不下载来源不明的第三方程序
* 用户拒绝安装依赖时不偷偷绕过

## 注意

Agent 执行 pip 安装、启动引擎进程等操作会改动你的机器。建议：

* 先看一遍提示词内容再交给 Agent；
* 使用虚拟环境隔离 Python 依赖；
* 涉及安装第三方项目时，自己确认许可证（见 [../docs/LICENSE-BOUNDARY.md](../docs/LICENSE-BOUNDARY.md)）。

## 手动安装

不想用 Agent 的话，直接看 [../docs/TUTORIAL.md](../docs/TUTORIAL.md)。
