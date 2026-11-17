# watch-hypertension-assistant

[![CI](https://github.com/YEZH0/watch-hypertension-assistant/actions/workflows/main.yml/badge.svg)](https://github.com/YEZH0/watch-hypertension-assistant/actions/workflows/main.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

Apple Watch **高血压通知**兼容性与设置测试助手。

通过**已有的** DVT 定位引擎（Windows / macOS）执行固定地区预设的定位测试，
并在 iPhone 健康 App 中指导你**自行核验**功能是否真的可用。

> 本项目是**代码整合**项目，不是重新开发项目。定位协议一行都没有重写。

---

## 这个工具能做什么 / 不能做什么

请先看清这条分界，它决定了整个项目的设计：

| | 说明 |
|---|---|
| ✅ 能做 | 检查平台与引擎状态、检查 USB 与设备条件 |
| ✅ 能做 | 按 Apple 公开资料判断**机型/系统**是否在支持范围内 |
| ✅ 能做 | 如实报告你**不满足**的医疗适用条件（年龄、已确诊、妊娠、腕部检测） |
| ✅ 能做 | 用四个固定地区预设执行定位测试，并安全停止 |
| ✅ 能做 | 给出健康 App 里逐步核验的清单 |
| ❌ 不能做 | 判断"高血压通知是否已开通"——只有你在健康 App 里看到的才算 |
| ❌ 不能做 | 查询你的手表型号、watchOS 版本、是否患病——只能由你自己填写 |
| ❌ 不能做 | 通过改定位来"开通"某个地区的健康功能 |
| ❌ 不能做 | 为不满足医疗条件的人提供任何变通方案 |

**定位测试成功 ≠ 高血压通知已开通。** 这两件事没有任何因果关系。
定位模拟只改变手机报告的地理坐标；健康功能是否可用取决于机型、系统版本、
Apple ID 地区与你的身体状况。工具会在每一处输出反复提醒这一点，并有自动化测试守着。

---

## 三步开始

```bash
# 1. 环境与引擎检查（不需要连手机）
python -m assistant env

# 2. 完整检查：引擎 + USB + 兼容性
python -m assistant check --watch series10 --watchos 26.1 --ios 26.1 --age 30

# 3. 按地区预设启动定位测试（连上 iPhone 之后）
python -m assistant start --region hk
```

结束后一定要：

```bash
python -m assistant stop     # 停止定位，并给出恢复真实位置的步骤
python -m assistant guide    # 在健康 App 里实际核验
```

> **停止后位置不会自己回来。** iOS 会缓存上一次的定位结果，必须到
> 「设置 → 隐私与安全性 → 定位服务」把总开关**关闭 10 秒**再打开，蓝点才会回到真实位置。
> `stop` 会把这几步完整打印出来。

---

## 安装

本助手**运行时零第三方依赖**，只用 Python 标准库。定位能力来自外部引擎。

```bash
git clone https://github.com/YEZH0/watch-hypertension-assistant.git
cd watch-hypertension-assistant
pip install -e ".[dev]"     # 仅装测试工具，固定版本
```

然后需要已有的定位引擎（不会自动帮你装，也不会替你下载第三方程序）：

* **Windows**：`ios-location-studio` 的 `fix/windows-stabilization` 分支
* **macOS**：`ios-location-studio` 的 `feat/macos-iap2` 分支

详细步骤见 [docs/TUTORIAL.md](docs/TUTORIAL.md) 和 [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)。

---

## 命令一览

| 命令 | 作用 |
|---|---|
| `env` | 平台识别 + 引擎探测 |
| `devices` | 列出 USB 连接的 iPhone（不输出序列号） |
| `regions` | 列出四个固定地区预设 |
| `families` | 列出可用于比对的机型选项 |
| `compat` | 只做兼容性检查 |
| `check` | 完整检查（默认命令，不启动定位） |
| `start --region hk` | 按预设启动定位测试 |
| `stop` | 停止定位，并给出恢复真实位置的步骤（含关闭定位服务 10 秒） |
| `status` | 查询当前会话 |
| `guide` | 健康 App 人工核验指引 |

所有命令都支持 `--json`，便于脚本或 AI Agent 读取。

全局参数 `--engine-url http://127.0.0.1:8899` 可直接指定运行中的引擎，跳过自动发现。

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
assistant/            助手核心（跨平台，MIT）
  adapters/           定位引擎适配器 —— 唯一与旧项目交界的地方
  data/               地区预设与兼容性事实表（带来源与核验日期）
windows/              Windows 适配器说明（复用 DVT 引擎）
macos/                macOS 契约占位，由 Mac Agent 实现（GPL-3.0-only）
agent/                Windows / Mac 两套 AI Agent 自动安装提示词
docs/                教程、依赖、FAQ、许可边界、适配器契约
tests/               自动化测试
```

---

## 许可证

**分层许可，请务必看清：**

* 本仓库根目录与 `assistant/`：**MIT**
* `macos/` 子项目：**GPL-3.0-only**（因为 vendor 了 GPL 的 `accessory-location`）
* 旧项目 `ios-location-studio` 保持独立，未被修改

两套引擎通过**本机 HTTP 进程间调用**协作，不发生代码复制，因此不产生衍生作品。
详见 [docs/LICENSE-BOUNDARY.md](docs/LICENSE-BOUNDARY.md) 与 [NOTICE.md](NOTICE.md)。

---

## 安全与隐私

* 不上传任何数据。引擎只监听 `127.0.0.1`，适配器拒绝非回环地址。
* 不采集、不落盘、不上传设备序列号、Apple ID、证书或私钥。
* 不打包 EXE / APP / DMG，只发布源码。
* 依赖固定版本，不下载未经验证的第三方程序。
* 不自动修改开发者模式等安全设置。

---

## 免责声明

本项目仅用于**你本人拥有或已获授权**的设备的兼容性测试与学习研究。

本工具不提供医疗建议，不能诊断、治疗或管理高血压。Apple Watch 高血压通知
是筛查提醒功能，不是诊断工具，没有收到提醒也不代表血压正常。如有健康疑虑，
请咨询具备资质的医疗专业人员。

本项目与 Apple Inc. 无关联，未获其背书。

---

## 协作约定

* 全部改动通过 Pull Request 合并；**未经维护者确认不得修改或合并 `main`**。
* Windows 相关改动只碰 `windows/` 与 `assistant/`。
* macOS 相关改动只碰 `macos/`（由 Mac Agent 从 `main` 创建 `feat/macos`）。
* 两个 Agent 不重复开发、不覆盖对方分支。
