# Windows 真机实测报告

最近一次：2026-11-18 · 分支 `feat/guided-flow-windows` · PR [#4](https://github.com/YEZH0/watch-hypertension-assistant/pull/4)

这份报告记录的是**在真实设备上跑完整流程**的结果，包括过程中撞到的问题。
它不代表功能已验证通过——本项目的核心结论永远只能是「需要你自己核验」。

---

## 一、环境

| 项 | 值 |
|---|---|
| 设备 | iPhone 15（`iPhone15,4`） |
| 系统 | iOS 27.0.1（24A446） |
| 定位引擎 | `ios-location-studio` 0.1.0，`http://127.0.0.1:8899` |
| 引擎依赖 | pymobiledevice3 11.59.0 / FastAPI 0.163.2 / uvicorn 0.54.0 |
| 引擎运行环境 | Python 3.11 独立 venv |
| 助手运行环境 | Python 3.13，运行时零第三方依赖 |
| 主机 | Windows 11，USB 直连（非 Wi-Fi 连接） |

引擎启动方式：

```bash
PYTHONPATH=src python -m ios_location_studio --no-browser --port 8899
```

> 已知安装问题：某些环境下 `pip install -e .` 生成的 `.pth` 钩子不生效，
> `ios-location-studio.exe` 会报 `ModuleNotFoundError: No module named 'ios_location_studio'`。
> 用上面的 `PYTHONPATH=src -m` 方式可以直接绕开。属于引擎仓库的安装体验问题。
>
> 助手侧已针对这种情况做了处理：探测入口时会先跑一次 `--version`，起不来的当场
> 记下原因并给出上面的启动命令，不再白等 25 秒后报「未在等待时间内就绪」。
> 见 [FAQ](FAQ.md) 的 `No module named 'ios_location_studio'` 条目与
> `tests/test_windows_adapter.py` 的六个用例。

---

## 二、完整 0–8 流程

用 `--state-file` + `--answer` 逐阶段驱动。四个只有人才能回答的节点由真实用户确认后继续。

| 阶段 | 实测结果 |
|---|---|
| 0 safety | 7 项资格条件（机型 / watchOS / iOS / 年龄 / 诊断 / 妊娠 / 腕部检测）全部如实列为「待确认」，未猜测 |
| 1 environment | 引擎在线 |
| 2 usb | `/api/devices` 返回 1 台设备，通过 |
| 3 baseline | 用户确认地图蓝点 = 真实位置 |
| 4 region | 选 `hk`，引擎 `state=active`，`22.2819, 114.1588` |
| 5 simulate | **用户确认蓝点已移到香港中环** |
| 6 health | 用户自述卡片存在且已完成设置；回答后会话自动 stop |
| 7 restore | **用户确认蓝点已回到真实位置** |
| 8 report | 五项分列输出，无「整体成功」字段 |

第二轮改用 `jp` 复验：**用户确认蓝点已到东京**，随后确认已回真实位置。

---

## 三、实测暴露并修复的缺陷

这四个问题在 **143 项测试全绿**的情况下照样发生——测试只覆盖顺利路径，
没人检查阶段性输出说了什么。

### 1. 最后一步答完看不到报告

`_resolution()` 在 `stage == "report"` 时只写 `payload["report"]`，不写 `payload["next"]`，
而 CLI 的渲染分支要求 `next` 存在才触发。结果 `--answer restored` 只打印
「第 7 步已完成」就退出，用户必须再跑一次 `--status` 才能看到报告。

分五次命令行驱动时，流程在用户眼里是断的。

**修复**：终点阶段同样返回 `next`。

### 2. 会话停了但没告诉用户

`_submit_health()` 只在 `stop` **失败**时追加 warning，成功时一个字都不吐。

但用户答完这一阶段立刻被要求去看地图——分不清蓝点不动是因为「已经恢复了」
还是「根本没停下」。这是安全层面的歧义。

**修复**：stop 成功时明确输出「模拟会话已停止（引擎已无活跃会话）。
这只保证引擎不再下发坐标；手机上蓝点是否回去，仍需你去地图确认。」

### 3. 会话剩余时间念的是旧快照

`describe()` 读的是进度文件里的 `session_remaining`，那是下发那一刻存下的 180 秒，
之后再没更新。实测在 T+25 秒仍显示「剩余约 180 秒」。

**修复**：`simulate` / `health` 阶段实时读 `/api/status`：

- 还有剩余 → 报真实秒数（实测 T+0 = 178 秒，T+25 = 149 秒）
- 已不在 active → 说「已经结束」，不说「还剩 0 秒」
- 读不到（引擎掉线）→ 什么都不说，不编数字

仍保持只读：有测试断言这两个阶段只产生 `GET /api/status`。

### 4. 报告把「已接受过」写成「已接受（active）」

报告在流程末尾生成，那时会话早停了。「引擎已接受（active）」会被读成「现在还在跑」，
而这个误解直接指向下一步的错误判断。

**修复**：改为「引擎已接受过模拟请求（active），测试点 jp；会话已停止」；
停止失败时如实写「停止失败，可能仍在保持模拟，请手动 stop」。

---

## 四、引擎侧的过度断言（不属于本项目）

引擎 `/api/status` 的 `message` 字段是：

- 下发后：`模拟定位已生效`
- 停止后：`已停止，真实定位已恢复`

两句都是引擎**无法验证**的断言——DVT 通道没有手机端回执。

助手会在自己的输出里改写这两句，但直接打开 `http://127.0.0.1:8899/` 控制台的人
仍会看到原文。因此 `AGENTS.md` 规则 1 与 [FAQ](FAQ.md) 都写明：转述时不得原样照抄，
两边不一致时以手机地图为准。

引擎仓库未做改动。

---

## 五、如何复现这份测试

前置：iPhone 用数据线连接、已解锁并信任本机；引擎在 `8899` 运行。

```bash
# 1. 逐阶段驱动（每一步都要你亲自确认后才继续）
python -m assistant --engine-url http://127.0.0.1:8899 wizard

# 2. 或者用单步方式，适合脚本 / AI Agent
python -m assistant --engine-url http://127.0.0.1:8899 wizard --answer accept
python -m assistant --engine-url http://127.0.0.1:8899 wizard --answer ready
python -m assistant --engine-url http://127.0.0.1:8899 wizard --answer connected
python -m assistant --engine-url http://127.0.0.1:8899 wizard --answer confirmed
python -m assistant --engine-url http://127.0.0.1:8899 wizard --answer hk
# ↑ 到这一步手机位置会改变，去地图确认后如实回答
python -m assistant --engine-url http://127.0.0.1:8899 wizard --answer moved
python -m assistant --engine-url http://127.0.0.1:8899 wizard --answer setup_done
python -m assistant --engine-url http://127.0.0.1:8899 wizard --answer restored
```

报告里的每一项都要按实际看到的内容填。**不确定就填 `unsure`**，
不要为了走完流程而猜。

---

## 六、本报告未覆盖的路径

以下都没有验证过，不做推断：

1. **会话时长耗尽的自然到期路径** —— 两轮都在 180 秒内手动答完。
2. **多设备同时连接的拒绝路径** —— 现场只有一台 iPhone。
3. **健康 App 实际产生通知** —— 需要佩戴满 30 天、其中至少 14 天有效数据，远超一次测试的范围。
4. **macOS 平台** —— 本报告只覆盖 Windows。
5. **不同 iOS 版本的差异** —— 只在 iOS 27.0.1 上验证过。

有设备条件时欢迎补充这些路径的结果。
