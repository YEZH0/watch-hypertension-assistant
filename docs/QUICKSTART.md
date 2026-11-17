# 5 分钟快速开始

只想知道「怎么跑起来」看这一页。完整流程与手机上的每一步，看 [TUTORIAL.md](TUTORIAL.md)；
把仓库链接交给 AI Agent 的情况，请让它先读仓库根目录的 [AGENTS.md](../AGENTS.md)。

---

## 0. 前提

| 项目 | 要求 |
|---|---|
| 电脑 | Windows 10/11 或 macOS（不支持 Linux） |
| Python | 3.11+ |
| iPhone | 用**数据线**连接，已解锁、已「信任此电脑」 |
| 定位引擎 | 已安装独立项目 `ios-location-studio`（本仓库不含它） |

---

## 1. 装助手

```bash
git clone https://github.com/YEZH0/watch-hypertension-assistant.git
cd watch-hypertension-assistant
python -m venv .venv
# Windows 用 .venv\Scripts\activate；macOS 用 source .venv/bin/activate
pip install -e ".[dev]"
```

运行时零第三方依赖；`[dev]` 只装 `pytest` 与 `ruff`，版本已固定。

---

## 2. 看引擎在不在

```bash
python -m assistant env
```

看到 `引擎：windows-dvt · 在线` 就可以往下走。显示「不可用」时按提示处理，
或手动启动引擎后用 `--engine-url http://127.0.0.1:8899` 指过来。

---

## 3. 走完全流程（推荐）

```bash
python -m assistant wizard
```

向导会一次显示一个阶段，共 9 步（0–8）。**每一步都会停下来等你确认**，
包括三件它替你做不了的事：

1. 改动前，你的真实位置基线是否正常；
2. 改动后，苹果地图里的蓝点到底动了没有；
3. 结束后，真实位置是否已经恢复。

看不懂某一步在说什么时，先跑：

```bash
python -m assistant wizard --plan        # 看整条流程
python -m assistant wizard --json        # 看当前这一步要做什么
```

---

## 4. 只想手动跑也行

```bash
python -m assistant check                      # 只读：环境 + 前置 + 兼容性
python -m assistant devices                    # 看手机连上没有
python -m assistant start --region hk          # 下发香港中环坐标（默认保持 180 秒）
python -m assistant status                     # 会话还在不在
python -m assistant guide                      # 健康 App 怎么核验
python -m assistant stop                       # 停止 + 恢复位置指引
```

手动路径少了「确认」这层保护，所以要自己保证顺序：
**先确认真实位置 → 再 start → 看地图 → 核验健康 App → stop → 再确认位置恢复**。

---

## 5. 三件最容易搞错的事

**① `active` 不是成功。**
`start` 输出「引擎已接受请求」只说明引擎把请求发出去了。
手机有没有采用这个坐标，只有你看苹果地图才知道。

**② 定位测试不能开通功能。**
把 GPS 改到香港，不会让你的高血压通知变成可用。功能区域取决于 Apple ID 地区与 iPhone 区域设置。
四个预设只用于**定位链路测试**。

**③ 恢复位置先别急着改系统设置。**
先回地图点一次定位；还不对再拔线；还不对才考虑关闭定位服务约 10 秒再开。
「必须关 10 秒」不是普遍规律——已恢复的人做这一步只是白白打断别的 App。

---

## 之后

- 出错、蓝点没动、找不到健康卡片 → [FAQ.md](FAQ.md)
- 完整八阶段 + 每步的排查细节 → [TUTORIAL.md](TUTORIAL.md)
- 为什么这么设计（医疗边界）→ [MEDICAL-SAFETY.md](MEDICAL-SAFETY.md)
