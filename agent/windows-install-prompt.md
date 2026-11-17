# Windows AI Agent 自动安装提示词

把下面整段内容复制给你的 AI Agent（Claude Code / Cursor / WorkBuddy 等）。
它会在本机完成安装、验证与首次检查。

---

## 提示词（复制以下全部内容）

````text
你是一个 Windows 环境安装助手。请按以下步骤依次执行，每步都检查结果，失败就停下并说明原因。

【项目信息】
- 项目：watch-hypertension-assistant（Apple Watch 高血压通知兼容性测试助手）
- 仓库：https://github.com/YEZH0/watch-hypertension-assistant
- 它不实现定位协议，只通过本机 HTTP 调用已完成的 ios-location-studio 引擎。
- 运行时零第三方依赖，只需要 Python 3.11+。

【第 1 步：检查 Python】
运行 `python --version`。
要求 3.11 或更高。低于 3.11 就停止，提示用户升级 Python，不要尝试自动安装 Python 本体。

【第 2 步：克隆项目】
git clone https://github.com/YEZH0/watch-hypertension-assistant.git
cd watch-hypertension-assistant

如果目录已存在，先 `git pull` 更新，不要删除已有目录。

【第 3 步：安装（仅开发依赖）】
python -m pip install -e ".[dev]"

注意：这是可编辑安装，"点击"路径依赖当前目录，不要移动目录位置。
如果 pip 报权限问题，建议用户使用虚拟环境：
  python -m venv .venv
  .venv\Scripts\activate
然后重新执行安装。

【第 4 步：检查定位引擎】
python -m assistant env

判断结果：
- 若显示"引擎：… 在线" → 跳到第 6 步。
- 若显示"不可用" → 继续第 5 步。

【第 5 步：安装定位引擎（需用户同意后才执行）】
先向用户说明：需要安装已完成的 ios-location-studio 以提供 DVT 定位能力，
它是 MIT 许可的独立项目，本助手不包含它。
用户同意后执行：
python -m pip install "git+https://github.com/YEZH0/ios-location-studio.git@fix/windows-stabilization"
然后重新执行 python -m assistant env 确认在线。

如果用户不同意安装，或安装失败：
告知用户仍可用 --engine-url 连接手动启动的引擎，或仅使用兼容性检查功能
（python -m assistant compat --help）。不要伪装成功。

【第 6 步：运行自检】
python -m pytest -q
要求全部通过。有失败就贴出失败用例，不要跳过。

【第 7 步：首次使用检查】
python -m assistant check

把输出原样展示给用户，并特别强调：
- [阻断] 项需要用户自己解决（比如没连手机）。
- 兼容性结论即使全部通过，也只代表"没发现阻断项"，不代表功能已开通。

【第 8 步：告诉用户下一步】
如果检测到手机且前置检查通过，提示用户可以：
  python -m assistant start --region hk
结束后必须提示：
  python -m assistant stop
  python -m assistant guide

【重要约束 — 必须遵守】
1. 绝对不要修改 assistant/ 下的任何源码来"修复"问题。遇到问题如实报告。
2. 绝对不要声称"高血压通知已开通/已验证"。这个结论只能由用户在 iPhone 健康 App 里得出。
3. 不要尝试绕过医疗适用条件（年龄 22+、未确诊高血压、非妊娠期、腕部检测）。
4. 不要打包 EXE 或生成安装程序。
5. 不要提交或上传设备序列号、Apple ID、证书、私钥。
6. 不要下载来源不明的第三方工具。
7. 用户拒绝安装依赖时，不要用替代方案偷偷绕过。

【完成后请汇报】
- Python 版本
- 项目所在路径
- 引擎是否在线、端口
- 是否检测到设备
- pytest 结果
- 兼容性检查的结论
- 建议用户执行的下一步命令
````

---

## 预期结果

安装顺利时，`python -m assistant env` 大致会输出：

```
── 运行环境 ───────────────────────────────────────
平台：Windows（windows）
引擎：windows-dvt · 在线
地址：http://127.0.0.1:8899
```

## 如果 Agent 卡住了

| 现象 | 处理 |
|---|---|
| Python 版本不够 | 手动装 3.11+，不要用 Agent 自动装 Python |
| pip 装不上 | 用虚拟环境重试 |
| 引擎始终不可用 | 手动跑一次 `ios-location-studio --no-browser`，看报错 |
| pytest 有失败 | 把失败用例贴出来，不要忽略 |
