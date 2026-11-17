# 架构说明

一句话：**助手不实现定位，只编排既有引擎并如实报告。**

## 分层

```
┌──────────────────────────────────────────────────────────┐
│  CLI (assistant/cli.py)                                  │
│  人读文本 / --json 机器读                                  │
├──────────────────────────────────────────────────────────┤
│  主流程 (assistant/workflow.py)                           │
│  平台识别 → 前置检查 → 兼容性 → 地区预设 → 启动/停止       │
├──────────────────────┬───────────────────────────────────┤
│  兼容性 (compat.py)   │  前置检查 (preflight.py)           │
│  三值结论，不猜       │  引擎 / USB / 设备条件             │
├──────────────────────┴───────────────────────────────────┤
│  适配器契约 (adapters/base.py — LocationEngine Protocol)  │
├──────────────────────┬───────────────────────────────────┤
│  Windows 适配器       │  macOS 适配器                      │
│  自动发现/拉起引擎     │  委托 macos/ 桥接                  │
├──────────────────────┴───────────────────────────────────┤
│  HttpLocationEngine — 共用 HTTP 客户端（回环强制）         │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP JSON (127.0.0.1)
        ┌──────────────┴──────────────┐
        ▼                             ▼
  ios-location-studio            macos/ 桥接进程
  (MIT, FastAPI)                 (GPL-3.0-only)
        │                             │
        ▼                             ▼
   pymobiledevice3 DVT          pymobiledevice3 DVT
```

## 为什么是这个架构

需求里写了「优先采用独立适配器调用，避免直接复制整个旧仓库」。落实到技术选择上：

1. **Windows 引擎已经是 HTTP 服务。** 它的 `server.py` 直接暴露 `/api/simulate`、
   `/api/stop`、`/api/devices`。不需要新写任何接口就能复用。
2. **macOS 引擎是 GUI 应用。** 它没有 HTTP 接口，但有一个 `--worker` 子进程模式
   会输出 NDJSON 事件。所以 Mac Agent 需要加一层薄桥接，把 worker 包成同样的 HTTP 接口。
3. **两个平台共用同一个客户端。** `HttpLocationEngine` 一份代码，平台差异只在
   「怎么把引擎叫起来」（`_launch()`）。

结果：助手核心对平台完全无感，新增平台只需实现一套 HTTP 接口。

## 关键设计决定

### 平台差异只在 `_launch()`

`WindowsLocationEngine._launch()` 用 `shutil.which` / `import` 探测旧引擎并
`Popen` 拉起；`MacOSLocationEngine._launch_bridge()` 探测 `location_studio_mac.bridge`。

除此之外两个类没有任何不同——都继承 `HttpLocationEngine`。

### 强制回环

`assert_loopback()` 在构造时就拒绝非 `127.0.0.1` / `localhost` / `::1` 的地址。
这不是可配置项。理由：设备控制面不该暴露到局域网，坐标也不该被发到远端。

### 零运行时依赖

只用标准库。用户机器上不需要为了跑一个检查脚本而安装 `requests` 之类的包。
HTTP 客户端基于 `urllib.request`，够用且没有供应链风险。

### 数据是快照，不是真理

`assistant/data/*.json` 里的机型、版本、地区可用性都带 `verified_on` 和 `sources`。
报告输出里也会带上。这是为了让用户知道"这是某天核对的快照，请以 Apple 官方为准"。

Apple 按监管进度调整可用性（日本 2025-12 才上线，大陆至今没有），硬编码成
"权威事实"会误导人。

### 三值结论

`CompatVerdict` 只有三个值，没有"支持"这个正向结论。
这不是过度谨慎，是因为工具有**结构性无知**：它不知道你的手表型号、不知道你的
健康状态、不知道健康 App 里的实际状态。

用类型系统表达"我不知道"，比在文档里写一句"仅供参考"有效得多。

## 数据流：一次 `start`

```
CLI start --region hk
  └─ Assistant.start_test("hk", 180)
       ├─ regions.get("hk")                   固定预设，无自由坐标
       ├─ Assistant.preflight()
       │    ├─ engine.probe()                 GET /api/health
       │    └─ engine.list_devices()          GET /api/devices
       ├─ 不满足 → 返回 started=False + 阻断项（带上全部警告）
       └─ 满足 → engine.start_location(22.2819, 114.1588, 180)
                 └─ POST /api/simulate
                      └─ 返回包含 "location_test_does_not_imply" 的结果
```

注意最后一行：**成功路径也强制携带否定声明。** 用户在成功的兴奋情绪下最容易误读，
所以警告必须出现在成功结果里，而不是只出现在文档里。

## 测试策略

| 层次 | 方式 |
|---|---|
| HTTP 适配器 | 真实 `http.server` 假引擎（`tests/conftest.py`），走真实网络栈 |
| 兼容性 | 参数化覆盖所有阻断组合 + 序列化后扫描禁用词 |
| 主流程 | 假引擎 + 断言"不下发坐标"等负向行为 |
| CLI | 覆盖退出码、JSON 可解析、死引擎不崩溃 |

不 mock 传输层，是为了让请求序列化、状态码映射、JSON 解析这些真实易错点被覆盖。

`tests/conftest.py` 的假引擎可以直接被 Mac Agent 复用为桥接测试桩。

## 扩展点

| 想做的事 | 改哪里 |
|---|---|
| 加平台（如 Linux） | 实现 `adapters/xxx.py` + 在 `registry.create_adapter` 注册 |
| 加地区预设 | 改 `data/regions.json`（需维护者确认，第一版锁四个） |
| 更新兼容性事实 | 改 `data/watch_compat.json`，同步 `verified_on` 与 `sources` |
| 加机型 | 改 `data/watch_compat.json` 的 `families` |

## 明确不做的事

* 不实现 DVT / iAP2 协议
* 不做 Web UI（第一版只有 CLI，最小可用）
* 不做二进制打包
* 不做多设备并发
* 不做自由经纬度输入
* 不做健康数据读取
