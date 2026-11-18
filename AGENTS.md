# AGENTS.md —— 交给 AI Agent 之后，先读这一份

> **你（AI Agent）现在拿到的是一个仓库链接。**
> 这份文件告诉你：这个仓库能做什么、不能做什么、以及从「安装」到「用户在 iPhone 上完成核验」
> 的完整流程该怎么带着用户一步步走完。
>
> 只读这一份就够启动；细节在 `README.md`、`docs/TUTORIAL.md`、`docs/FAQ.md`、
> `docs/ADAPTER-CONTRACT.md`。**但不要只读 README 就以为流程到此结束**——
> README 只覆盖到「能跑起来」，用户旅程还有一大半在手机上。

---

## 1. 这个仓库是什么

| 项目 | 内容 |
|---|---|
| 作用 | 通过**已有的** DVT 定位引擎做固定地区预设的定位测试，并引导用户在 iPhone 健康 App 里**自行核验** Apple Watch 高血压通知功能 |
| 不是什么 | 不是定位协议实现，不是「一键开通医疗功能」工具，不是医疗设备 |
| 运行时依赖 | 零第三方包，只要 Python 3.11+；定位能力来自外部引擎（独立仓库） |
| 支持平台 | Windows（DVT）、macOS（DVT；iAP2 为实验路径）。不支持 Linux |
| 许可证 | 根目录与 `assistant/` 为 MIT；`macos/` 为 GPL-3.0-only，**不得**跨目录复制或 import |

### 结构速查

```
assistant/          跨平台助手核心（MIT）
  wizard.py         ← 0–8 阶段向导（你应该主要用它驱动流程）
  cli.py            命令行入口
  workflow.py       引擎调用编排
  guide.py          健康 App 核验 + 恢复步骤文案
  compat.py         兼容性三值结论
  regions.py        四个固定地区预设
  adapters/         引擎 HTTP 适配器（唯一交界）
windows/            Windows 适配说明
macos/              macOS 桥接（GPL-3.0-only，由 Mac Agent 维护）
agent/              两套「把整段提示词复制给 Agent」的模板
docs/               教程、FAQ、架构、适配器契约、依赖、许可证边界
tests/              自动化测试（143 项）
```

---

## 2. 三条不可违反的规则

违反其中任何一条，这次协助就是失败的——即使命令都跑通了。

### 规则 1：`active` 不等于成功，永远不许合并三个状态

| 状态 | 含义 | 谁能确认 |
|---|---|---|
| `engine_active` | 引擎建立了会话并下发了模拟请求 | 助手可读 |
| `map_location` | 苹果地图里的蓝点是否真的到了测试点 | **只有用户看手机** |
| `health_feature` | 健康 App 里卡片是否存在 / 是否已完成设置 | **只有用户在健康 App 里** |

**不许**说「定位成功，说明高血压通知已开通」。定位只改手机报告的坐标；
功能可用性取决于机型、系统版本、Apple ID 地区与用户的医疗适用条件。

**不许**把 `start` 返回的 `started: true` 报告成「位置已改好」。
正确表述：「引擎已接受请求（active），手机是否采用需要你在苹果地图里确认」。

**注意引擎自己的措辞**：直接调 `/api/status` 或看 `http://127.0.0.1:8899/` 控制台，
会看到「模拟定位已生效」「已停止，真实定位已恢复」。这两句是引擎的过度断言——
它没有手机端的回执。报告给用户时必须改写成「引擎已下发 / 已停止」，
不要原样转述，更不要当成地图已变化或位置已恢复的证据。

### 规则 2：手机上的每一步都必须停下来等用户明确回答

以下四件事你无法代做，必须由用户自己确认后你才能继续：

1. 真实位置基线（改动前蓝点就在真实位置）；
2. 选哪个地区预设（固定四选一，不能替用户默认）；
3. 地图蓝点到底动没动；
4. 真实位置是否已恢复。

不要用「已连接」「应该好了」代替用户的回答。用户说「不确定」时，如实记为未核验。

### 规则 3：不提供任何绕过

- 年龄 < 22、已确诊高血压、处于妊娠期、腕部检测未开 → 只如实报告，**不给变通方案**；
- 只支持 `us / hk / fr / jp` 四个预设，**不提供自由经纬度输入**，不要用脚本曲线实现；
- 不改定位来「解锁地区功能」——这做不到，也不该做；
- 不上传、不落盘、不打印设备序列号、Apple ID、证书、私钥。

---

## 3. 全流程（0–8）。这是你要带用户走完的路径

先跑一次拿到机器可读的流程定义：

```bash
python -m assistant wizard --plan --json
```

输出里有每一步的 `id`、目的、以及该步接受的 `answers`。**以实际输出为准**，
下面是同一份内容的说明版。

| 步 | 阶段 id | 要做的事 | 通过条件 | 会改位置吗 |
|---|---|---|---|---|
| 0 | `safety` | 安全告知 + Apple 官方资格核对（机型/系统/腕部检测/年龄/诊断/妊娠/地区） | 用户 `accept`，且结论不是「资格不满足」 | 否 |
| 1 | `environment` | 检查 Python、引擎是否在线 | 引擎 `/api/health` 可达 | 否 |
| 2 | `usb` | 数据线连接、解锁、点信任、只连一台 | 引擎枚举到恰好 1 台设备 | 否 |
| 3 | `baseline` | 用户打开地图确认蓝点=真实位置 | 用户 `confirmed` | 否 |
| 4 | `region` | 用户从 `us/hk/fr/jp` 里选一个 | 用户明确给出地区 + 引擎返回 active | **是** |
| 5 | `simulate` | 用户回地图看蓝点，回答 `moved/not_moved/unsure` | 用户给出回答（任何回答都算通过，但要如实记录） | 否 |
| 6 | `health` | 用户在健康 App 里核验，回答 `setup_done/card_absent/eligibility_blocked/not_checked` | 用户给出回答 | 否（并在这一步**停止会话**） |
| 7 | `restore` | 用户确认蓝点已回到真实位置 | `restored` / `not_restored` / `unresolved` | 否 |
| 8 | `report` | 分项汇报，不合并成「成功」 | — | 否 |

### 驱动方式（二选一）

**A. 用户自己在他的终端里交互**（推荐给有电脑操作能力的用户）

```bash
python -m assistant wizard
```

向导会一次显示一个阶段，等用户输入编号。你只需要告诉他运行这条命令。

**B. 你通过命令行逐步驱动**（推荐给由你代跑的用户）

```bash
# 看当前该做什么（只读，不会推进）
python -m assistant wizard --json

# 提交用户的口头确认
python -m assistant wizard --answer accept --json
python -m assistant wizard --answer ready --json
python -m assistant wizard --answer connected --json
python -m assistant wizard --answer confirmed --json
python -m assistant wizard --answer hk --json        # 必须由用户选，不能默认
python -m assistant wizard --answer moved --json
python -m assistant wizard --answer setup_done --json
python -m assistant wizard --answer restored --json

# 查进度 / 从头再来
python -m assistant wizard --status --json
python -m assistant wizard --reset
```

要点：

- 每次 `--answer` 都会输出 `outcome`、`exit_code`、`next`（下一阶段的完整说明）。
  `exit_code` 为 0 才继续；`1` 表示被阻断，先解决问题再重复同一命令；`3` 表示用户放弃。
- **其他命令的退出码也要分清**：`0` 成功；`1` 是环境被阻断（引擎没连上、设备不可见）；
  `2` 是参数用错（例如 `--region tokyo` 不存在）。
  看到 `1` 去解决环境，看到 `2` 才去改参数——**不要看到非零就重试同一条命令**。
- 非交互调用（没有终端输入）时，`wizard` **只报告当前阶段，不会自己往下走**。
  这是刻意的：流程推进必须对应一次真实的人类确认。
- 进度存在 `.whc-wizard-state.json`（默认当前目录）。里面**不含**年龄、诊断、妊娠、
  经纬度、设备标识符，可以放心保留；也可以随时 `--reset`。

### 阶段 0 的资格核对怎么填

```bash
python -m assistant wizard --answer accept \
  --watch series10 --watchos 26.1 --ios 26.1 \
  --age 30 --no-hypertension --no-pregnant --wrist-detection
```

不填也可以，结论会是「仍需人工核验」（`needs_manual_verification`），流程继续。
结论只有三种：`model_unsupported` / `eligibility_blocked` / `needs_manual_verification`。
**没有「已开通」这个取值**，这是类型层面就禁止的。

`eligibility_blocked` 时向导会直接停在阶段 0 并且拒绝进入定位阶段（双重校验）。
此时只引导用户做只读检查与阅读说明，不要试图继续。

---

## 4. 逐阶段操作手册

### 阶段 0 · safety

```bash
python -m assistant check --json          # 只读：环境 + 前置 + 兼容性
python -m assistant wizard --json         # 看向导当前阶段
```

对用户要讲清三件事：会临时改变手机位置（地图/外卖/打卡会受影响）；只能用在本人或已授权设备；
不满足医疗适用条件时本工具不会给绕行办法。用户明确同意后：

```bash
python -m assistant wizard --answer accept --json
```

### 阶段 1 · environment

```bash
python -m assistant env --json
```

- `engine.available == true` → `--answer ready`
- 否则 → 按 `engine.hint` 引导。典型原因：引擎没装、没启动、端口不是 8899。
  引擎可从手动启动的实例接入：`python -m assistant --engine-url http://127.0.0.1:8899 env`

**不要**自动 `pip install` 任何来源不明的包；安装第三方引擎必须先说明来源并取得用户同意。

### 阶段 2 · usb

```bash
python -m assistant devices --json
```

要求：**恰好 1 台**设备。0 台 → 停在这一步排查（数据线/解锁/信任/换口），**不要**下发坐标。
多台 → 让用户只留目标手机，不要替他挑。

```bash
python -m assistant wizard --answer connected --json
```

### 阶段 3 · baseline

让用户做：设置 → 隐私与安全性 → 定位服务（总开关开）→ 地图（允许定位、精确位置开）→
打开苹果地图点定位按钮 → 确认蓝点就在自己所在的地方。

```bash
python -m assistant wizard --answer confirmed --json     # 用户确实确认了才发
python -m assistant wizard --answer not_yet --json       # 停在原地，不推进
```

### 阶段 4 · region

先把四个预设摆给用户（坐标 + 说明），由用户选：

```bash
python -m assistant regions --json
python -m assistant wizard --answer hk --json            # hk 是用户选的
```

**不要**替用户选、不要在用户没确认时发坐标。此时引擎开始保持模拟。

### 阶段 5 · simulate

让用户保持连线，回苹果地图点一次定位按钮，看蓝点。

```bash
python -m assistant wizard --answer moved --json         # 蓝点到了测试点
python -m assistant wizard --answer not_moved --json     # 蓝点没动
python -m assistant wizard --answer unsure --json        # 没看清
```

`not_moved` 时按顺序排查（向导也会打印）：数据线/换口 → 解锁与信任弹窗 → 定位服务与地图权限 →
`python -m assistant status --json` 看会话是否还 active → 地图里重新点定位 → 把地图从后台划掉重开。

只有在以上都无效、且用户同意时，才提「关闭定位服务约 10 秒再打开」——
这是**条件性**排查手段，可能让当前模拟失效，不是所有人都必须做的一步。

### 阶段 6 · health

```bash
python -m assistant guide --json
```

给用户的路径：健康 App → 右上角头像 → 健康核对清单 → 高血压通知 → 按提示如实填写
（年龄、是否确诊、是否妊娠）→ 完成；并确认腕部检测已开启（Watch App → 密码 → 腕部检测）。

然后让用户如实回报：

| 用户看到 | 回答 |
|---|---|
| 卡片存在且已完成设置 | `setup_done` |
| 找不到卡片 | `card_absent` |
| 进入了但系统说我不符合条件 | `eligibility_blocked` |
| 还没去看 | `not_checked` |

**`card_absent` 不是单一原因**。可能项：iOS/watchOS 版本、手表型号、Apple ID 地区或 iPhone 区域设置、
系统刚更新卡片未刷新、菜单在不同版本/语言下位置不同。逐项核对 + 给官方链接，不要下断言。
官方依据：<https://support.apple.com/en-us/117296> 、
<https://www.apple.com/watchos/feature-availability/>

回答后向导会**立刻停止会话**（这一步不依赖用户记得去 stop）。
`setup_done` 只代表「用户自述设置完成」，不代表已生效：需要佩戴满 30 天、其中至少 14 天有效数据
才可能产生首次提醒。

### 阶段 7 · restore

```bash
python -m assistant wizard --answer restored --json
python -m assistant wizard --answer not_restored --json      # 继续排查，停在原地
python -m assistant wizard --answer unresolved --json        # 试过仍不对，如实记为未恢复
```

排查顺序（前一步有效就不做后面的）：

1. 苹果地图点一次定位按钮；
2. 拔掉数据线，确认 `status` 为 idle；
3. 关闭定位服务约 10 秒再打开，重开地图；
4. 重启 iPhone。

同时提醒：如果用户还在别的会话里跑着定位，也可能顶掉本次模拟。

### 阶段 8 · report

```bash
python -m assistant wizard --status --json
```

`report.lines` 是五行分项结论。汇报时**逐条**转述，「未知」就写未知。

---

## 5. 失败与异常处理矩阵

| 现象 | 判定 | 该做什么 |
|---|---|---|
| `wizard --answer` 返回 `exit_code: 1` 且 `outcome: blocked` | 该阶段未通过 | 按 `items` / `notes` 修，重复同一命令；**不要**跳到下一阶段 |
| 引擎不可用 | 环境问题 | 引导装/启动引擎，或用 `--engine-url` 指向已运行实例 |
| 0 台设备 | 连接问题 | 数据线/解锁/信任/换口；设备可见前不下发坐标 |
| 多台设备 | 有意拒绝 | 只留一台 |
| 地图蓝点没动 | 手机端问题 | 阶段 5 的排查顺序；不要靠重复 `start` 硬试 |
| 会话到期（`remaining` 归零） | **正常**，不是失败 | 记为正常结束，继续健康 App 核验与恢复确认 |
| 找不到健康卡片 | 原因未知 | 列可能原因 + 官方链接，不下结论、不给绕过 |
| 用户中途退出 / Ctrl+C | 需要清理 | 向导会自动尽力 `stop`；随后仍要让用户确认位置恢复 |
| `stop` 失败 | 会话可能还在 | 让用户重跑 `python -m assistant stop`，并检查是否还有别的调试工具占用设备 |
| 恢复不了 | 如实记录 | 走完 4 级排查，报 `restore_result: not_confirmed`，**不要**写「已恢复」 |

任何情况下都不要出现「崩了但模拟还在跑」：向导在异常路径上一定会尝试 `stop`。

---

## 6. 旧命令仍然可用（不要在 README 之外发明参数）

| 命令 | 用途 |
|---|---|
| `python -m assistant env [--json]` | 平台 + 引擎探测 |
| `python -m assistant devices [--json]` | 列出 USB 设备（不含序列号） |
| `python -m assistant regions [--json]` | 四个地区预设 |
| `python -m assistant families [--json]` | 机型选项 |
| `python -m assistant compat … [--json]` | 只做兼容性检查 |
| `python -m assistant check … [--json]` | 完整检查（默认命令，不启动定位） |
| `python -m assistant start --region hk [--hold 180] [--json]` | 直接启动一次定位测试 |
| `python -m assistant stop [--json]` | 停止 + 恢复指引 |
| `python -m assistant status [--json]` | 当前会话 |
| `python -m assistant guide [--json]` | 健康 App 核验指引 |
| `python -m assistant wizard …` | 0–8 阶段引导（推荐） |

全局参数 `--engine-url <url>` 必须写在子命令**之前**。
`start` 直接调用不会经过用户确认 —— 只有用户明确要求跳过向导时才用它，
并且你仍然要人工完成阶段 5–7 的三次确认。

---

## 7. 交付汇报模板

结束时按这 6 项分开汇报，缺的写「未知」：

```
1. 安装与环境：Python 版本 / 项目路径 / 引擎是否在线与端口
2. 设备连接：是否检测到 1 台 iPhone（不写序列号）
3. 模拟请求：是否由引擎接受（active）；测试点 id
4. 手机地图位置：用户确认已移动 / 未移动 / 不确定 / 未核验
5. 健康 App 功能：用户自述已完成设置 / 找不到卡片 / 资格不满足 / 未核验
6. 真实位置恢复：用户确认已恢复 / 未确认 / 未核验
```

**不要**写「高血压通知已开通」「一键成功」「已验证可用」。这三句话本工具无法产出。

---

## 8. 协作约束（如果你要提 PR）

- 全部改动走 Pull Request，**未经维护者确认不得修改或合并 `main`**；
- Windows 相关只碰 `assistant/`、`windows/`、公共文档；`macos/` 由 Mac Agent 负责，不要动；
- `macos/` 是 GPL-3.0-only：只能进程间 HTTP 调用，禁止复制或 `import`；
- 改公共流程（阶段 id、`--answer` 取值、JSON 字段）前先开 issue 对齐，Mac 侧要跟着改。
