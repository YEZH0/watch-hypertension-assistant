# watch-hypertension-assistant

[![CI](https://github.com/YEZH0/watch-hypertension-assistant/actions/workflows/main.yml/badge.svg)](https://github.com/YEZH0/watch-hypertension-assistant/actions/workflows/main.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

Apple Watch **高血压通知**兼容性与设置测试助手。

通过**已有的** DVT 定位引擎（Windows / macOS）执行固定地区预设的定位测试，
并在 iPhone 健康 App 中指导你**自行核验**功能是否真的可用。

> 本项目是**代码整合**项目，不是重新开发项目。定位协议一行都没有重写。

---

## 把仓库链接发给 AI Agent？让它先读这两份

| 你的情况 | 该读什么 |
|---|---|
| 你（或你的 AI Agent）手上只有这个仓库 URL | **[AGENTS.md](AGENTS.md)** ← 从这里开始 |
| 你自己动手，只想快点跑起来 | [docs/QUICKSTART.md](docs/QUICKSTART.md) |
| 想一步步走完，包括手机上要做的事 | [docs/TUTORIAL.md](docs/TUTORIAL.md) |
| 想知道真机上到底跑通没有、哪些路径还没验证 | [docs/WINDOWS-TEST-REPORT.md](docs/WINDOWS-TEST-REPORT.md) |

**一句提示词就够：**

> 读 https://github.com/YEZH0/watch-hypertension-assistant 的 `AGENTS.md`，
> 按里面的 0–8 阶段带我走完整个流程。每一步都要先告诉我手机上该做什么，
> 等我明确回答之后再继续。

仓库里没有任何需要你去执行的神秘远程脚本：所有命令都是本仓库的
`python -m assistant …` 子命令，安装只依赖 `pyproject.toml` 里固定版本的 `pytest`/`ruff`。

---

## 这个工具能做什么 / 不能做什么

请先看清这条分界，它决定了整个项目的设计：

| | 说明 |
|---|---|
| ✅ 能做 | 检查平台与引擎状态、检查 USB 与设备条件 |
| ✅ 能做 | 按 Apple 公开资料判断**机型/系统**是否在支持范围内 |
| ✅ 能做 | 如实报告你**不满足**的医疗适用条件（年龄、已确诊、妊娠、腕部检测） |
| ✅ 能做 | 用四个固定地区预设执行定位测试，并安全停止 |
| ✅ 能做 | 按 0–8 阶段引导你走完流程，每一步等你确认，随时可中断 |
| ✅ 能做 | 给出健康 App 里逐步核验的清单，并分项汇报结果 |
| ❌ 不能做 | 判断"高血压通知是否已开通"——只有你在健康 App 里看到的才算 |
| ❌ 不能做 | 查询你的手表型号、watchOS 版本、是否患病——只能由你自己填写 |
| ❌ 不能做 | 通过改定位来"开通"某个地区的健康功能 |
| ❌ 不能做 | 为不满足医疗条件的人提供任何变通方案 |

**三个状态互相独立，任何一个都不能推断下一个：**

| 状态 | 含义 | 谁能确认 |
|---|---|---|
| 引擎 `active` | 引擎建立了会话并下发了模拟请求 | 助手可读 |
| 手机地图位置 | 苹果地图里的蓝点是否真的到了测试点 | 只有你看手机 |
| 健康功能状态 | 健康 App 里的卡片是否存在 / 是否已完成设置 | 只有你在健康 App 里 |

**引擎 `active` ≠ 手机采用了坐标 ≠ 高血压通知已开通。** 这三件事没有因果关系。
定位模拟只改变手机报告的地理坐标；功能是否可用取决于机型、系统版本、
Apple ID 地区与你的身体状况。工具会在每一处输出反复提醒这一点，并有自动化测试守着。

---

## 三条开始的路

### A. 交互式全流程（推荐）

```bash
python -m assistant wizard
```

9 个阶段（0–8），每步停下来等你确认：安全告知与资格核对 → 环境 → USB → 真实位置基线 →
地区预设 → 手机地图验证 → 健康 App 核验 → 停止与恢复 → 分项汇报。
Ctrl+C 或输入 `q` 随时退出，退出时会尽力停止会话并给出恢复指引。

```bash
python -m assistant wizard --plan          # 先看整条流程，不做任何动作
python -m assistant wizard --status        # 看走到哪一步
python -m assistant wizard --reset         # 从头再来
```

### B. 让 AI Agent 代跑（同样停在每个确认点）

```bash
python -m assistant wizard --json                    # 当前阶段该做什么
python -m assistant wizard --answer confirmed --json # 提交用户的口头确认
```

非交互调用时向导**只报告、不推进**——流程推进必须对应一次真实的人类确认。

### C. 手动逐步执行

```bash
python -m assistant env                                  # 1. 引擎在不在
python -m assistant check --watch series10 --watchos 26.1 --ios 26.1 --age 30
python -m assistant devices                              # 2. 手机连上没有
python -m assistant start --region hk                    # 3. 下发坐标（先确认真实位置！）
python -m assistant guide                                # 4. 健康 App 核验
python -m assistant stop                                 # 5. 停止 + 恢复指引
```

> 手动路径少了「确认」这层保护。必须自己保证顺序：**先确认真实位置 → 再 start →
> 看地图 → 核验健康 App → stop → 再确认位置恢复。**

---

## 结束之后：位置怎么恢复

`stop` 只能保证引擎不再下发坐标。**手机上的位置是否回来，它看不到。**

按顺序来，前一步有效就不必做后面的：

1. 打开苹果地图，点一下定位按钮 —— 多数情况到这里就恢复了；
2. 还在测试点：拔掉 USB 数据线，确认 `status` 显示 `idle`；
3. 还没恢复：关闭「定位服务」总开关约 10 秒再打开，重开地图确认；
4. 还没恢复：重启 iPhone 再看一次。

> **第 3 步不是所有人都必须做。** 关定位服务确实能清缓存，但它会打断正在导航、
> 正在记录轨迹的 App。历史版本把这一步写成「不关 10 秒就一定恢复不了」，
> 那属于没有依据的绝对化表述，已改正。详见 [docs/FAQ.md](docs/FAQ.md)。

---

## 安装

本助手**运行时零第三方依赖**，只用 Python 标准库。定位能力来自外部引擎。

```bash
git clone https://github.com/YEZH0/watch-hypertension-assistant.git
cd watch-hypertension-assistant
pip install -e ".[dev]"     # 仅装测试工具，版本固定
```

然后需要已有的定位引擎（不会自动帮你装，也不会替你下载第三方程序）：

* **Windows**：`ios-location-studio` 的 `fix/windows-stabilization` 分支
* **macOS**：`ios-location-studio` 的 `feat/macos-iap2` 分支

详细步骤见 [docs/TUTORIAL.md](docs/TUTORIAL.md) 和 [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)。

---

## 命令一览

| 命令 | 作用 |
|---|---|
| `wizard` | **0–8 阶段引导**：每步等确认，可中断、可继续 |
| `wizard --plan` / `--status` / `--reset` | 看流程 / 看进度 / 清空进度 |
| `wizard --answer <value> [--stage <id>]` | 提交某一阶段的确认（Agent / 脚本用） |
| `env` | 平台识别 + 引擎探测 |
| `devices` | 列出 USB 连接的 iPhone（不输出序列号） |
| `regions` | 列出四个固定地区预设 |
| `families` | 列出可用于比对的机型选项 |
| `compat` | 只做兼容性检查 |
| `check` | 完整检查（默认命令，不启动定位） |
| `start --region hk [--hold 180]` | 按预设启动定位测试 |
| `stop` | 停止定位，给出**分级**恢复步骤 |
| `status` | 查询当前会话 |
| `guide` | 健康 App 人工核验指引 |

所有命令都支持 `--json`，便于脚本或 AI Agent 读取。

全局参数 `--engine-url http://127.0.0.1:8899` 可直接指定运行中的引擎，跳过自动发现
（必须写在子命令之前）。

### 会话时长

默认 180 秒，可用 `--hold` 调整，实际范围 60–180 秒（上限是引擎的硬约束：
`POST /api/simulate` 对 `hold_seconds > 180` 直接返回 422）。
请求值被夹到区间时会明确告诉你实际生效值，不会静默改写。

到时间自动停止是**正常结束**，不是测试失败；之后照常做健康 App 核验与位置恢复确认。

---

## 四个地区预设

固定为美国、中国香港、法国、日本，**不提供自由经纬度输入**。

| id | 地区 | 城市 |
|---|---|---|
| `us` | 美国 | 纽约 · 时代广场 |
| `hk` | 中国香港 | 香港 · 中环 |
| `fr` | 法国 | 巴黎 · 埃菲尔铁塔 |
| `jp` | 日本 | 东京 · 涩谷十字路口 |

⚠️ **定位 ≠ 区域可用性。** 把手机定位切到香港，不会让你的健康功能变成香港可用。
功能区域由配对 iPhone 的区域设置与 Apple ID 所属地区决定，和 GPS 坐标无关。
这四个预设只用于定位链路测试。

---

## 项目结构

```
AGENTS.md            把仓库链接交给 AI Agent 时的入口：0–8 全流程与硬约束
assistant/            助手核心（跨平台，MIT）
  wizard.py           0–8 阶段向导（可中断、可继续、异常必清理）
  adapters/           定位引擎适配器 —— 唯一与旧项目交界的地方
  data/               地区预设与兼容性事实表（带来源与核验日期）
windows/              Windows 适配器说明（复用 DVT 引擎）
macos/                macOS 桥接（GPL-3.0-only，由 Mac Agent 维护）
agent/                Windows / Mac 两套 AI Agent 提示词
docs/                 快速开始、教程、FAQ、架构、依赖、许可边界、适配器契约
tests/                自动化测试（143 项）
```

文档索引见 [docs/README.md](docs/README.md)。

---

## 数据与隐私

* 进度文件 `.whc-wizard-state.json` 只存「流程走到哪」与「用户自述的核验结论」，
  **不含**年龄、诊断、妊娠状态、经纬度、设备标识符；可随时 `--reset` 删除。
* 不上传任何数据。引擎只监听 `127.0.0.1`，适配器拒绝非回环地址。
* 不采集、不落盘、不上传设备序列号、Apple ID、证书或私钥。
* 不打包 EXE / APP / DMG，只发布源码。
* 依赖固定版本，不下载未经验证的第三方程序。
* 不自动修改开发者模式等安全设置。

---

## 许可证

**分层许可，请务必看清：**

* 本仓库根目录与 `assistant/`：**MIT**
* `macos/` 子项目：**GPL-3.0-only**（因为 vendor 了 GPL 的 `accessory-location`）
* 旧项目 `ios-location-studio` 保持独立，未被修改

两套引擎通过**本机 HTTP 进程间调用**协作，不发生代码复制，因此不产生衍生作品。
详见 [docs/LICENSE-BOUNDARY.md](docs/LICENSE-BOUNDARY.md) 与 [NOTICE.md](NOTICE.md)。

---

## 免责声明

本项目仅用于**你本人拥有或已获授权**的设备的兼容性测试与学习研究。

本工具不提供医疗建议，不能诊断、治疗或管理高血压。Apple Watch 高血压通知
是筛查提醒功能，不是诊断工具，没有收到提醒也不代表血压正常。如有健康疑虑，
请咨询具备资质的医疗专业人员。

Apple 官方依据：<https://support.apple.com/en-us/117296> ·
<https://www.apple.com/watchos/feature-availability/>

本项目与 Apple Inc. 无关联，未获其背书。

---

## 协作约定

* 全部改动通过 Pull Request 合并；**未经维护者确认不得修改或合并 `main`**。
* Windows 相关改动只碰 `windows/`、`assistant/` 与公共文档。
* macOS 相关改动只碰 `macos/`（由 Mac Agent 从 `main` 创建 `feat/macos`）。
* 两个 Agent 不重复开发、不覆盖对方分支。
* 改动公共流程（阶段 id、`--answer` 取值、JSON 字段）前先开 issue 对齐，Mac 侧要跟着改。
