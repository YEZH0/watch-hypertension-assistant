# 适配器契约

这是 **Windows Agent 与 Mac Agent 之间唯一需要共同遵守的接口**。
只要满足这份契约，助手核心不需要任何改动就能驱动新平台。

## 为什么用 HTTP 而不是 import

1. **不复制代码**——旧项目保持完全独立，可单独发版。
2. **许可证隔离**——macOS 引擎是 GPL-3.0-only，本仓库是 MIT。进程间调用不产生衍生作品；`import` 会。
3. **旧项目已经具备**——Windows 引擎本身就是 FastAPI 服务，接口已经存在，无需新开发。

## 接口规格

引擎必须监听**本机回环地址**（强制要求，非回环地址会被适配器直接拒绝）。
所有响应为 JSON，`Content-Type: application/json`。

### `GET /api/health`

```json
{ "ok": true, "version": "0.1.0" }
```

* `ok` 必须为 `true` 才认为引擎在线。
* `version` 可选，用于展示。

### `GET /api/devices`

```json
{
  "connected": true,
  "devices": [
    { "udid": "…", "name": "iPhone", "ios_version": "26.1", "model": "iPhone17,3" }
  ],
  "error": null
}
```

* `udid` 是设备句柄，适配器只在内存中使用，**不写入日志、不进入任何对外输出**。
* 无设备时返回 `connected: false` 和空数组，不要返回 5xx。
* `error` 用于说明"为什么没检测到"，会被原样展示给用户。

### `POST /api/simulate`

请求：

```json
{ "latitude": 22.2819, "longitude": 114.1588, "hold_seconds": 180 }
```

响应：

```json
{ "session": { "state": "active", "latitude": 22.2819, "longitude": 114.1588,
               "remaining": 180.0, "message": "模拟定位已生效", "error": null } }
```

* `state` 只能是 `idle` / `connecting` / `active` / `stopping` / `error`。
* **只有 `active` 才算启动成功。**
* 无设备时返回 `409`；引擎内部失败返回 `5xx`。适配器会把 `detail` 提取出来展示。

### `POST /api/stop`

```json
{ "session": { "state": "idle", "message": "已停止，真实定位已恢复" } }
```

停止后必须尝试清除模拟定位。即使清除请求失败，关闭隧道本身也应恢复真实 GPS。

### `GET /api/status`

```json
{ "session": { "state": "idle" } }
```

用于轮询当前会话状态，字段与上面一致。

## 字段语义红线

| 字段 | 允许的语义 | 禁止的语义 |
|---|---|---|
| `state: active` | 引擎已下发模拟定位 | ❌ 手机上的健康功能已生效 |
| `remaining` | 会话剩余秒数 | ❌ 功能生效倒计时 |
| `message` | 引擎侧操作说明 | ❌ 兼容性结论 |

适配器层**不得**返回任何形如 `hypertension_enabled` 的字段。
`CompatVerdict` 只有三值，且 `assistant/workflow.py` 的
`FEATURE_STATUS_UNVERIFIED` 是唯一允许的功能状态表述。

## Mac Agent 的实现要求

在 `macos/` 下提供可被以下命令启动的桥接进程：

```bash
python -m location_studio_mac.bridge --host 127.0.0.1 --port 8900
```

它需要：

1. 复用 `macos/` 内既有的 DVT 实现作为默认路线（`dvt_*` worker 命令）。
2. iAP2 仅作为实验性选项保留，**不参与自动判定**，默认不启用。
3. 通过 `sandbox-exec` 与既有 worker 子进程交互，不重写协议。
4. 保持 GPL-3.0-only 许可，`macos/LICENSE` 不得改动。

桥接进程内部可以直接使用 GPL 代码，因为它在 `macos/` 之内。助手核心只通过 HTTP 与它通信。

## 自检方法

```bash
# 从仓库根目录
python -m assistant --engine-url http://127.0.0.1:8900 env
python -m assistant --engine-url http://127.0.0.1:8900 devices
python -m assistant --engine-url http://127.0.0.1:8900 check
python -m assistant --engine-url http://127.0.0.1:8900 start --region hk
python -m assistant --engine-url http://127.0.0.1:8900 stop
```

五条命令都能正常返回，即视为接入完成。

## 测试要求

在 `macos/` 内至少覆盖：

* 桥接进程能正常启动并响应 `/api/health`；
* 无设备时 `/api/simulate` 返回 409 而不是崩溃；
* `state` 只输出合法枚举值；
* 会话停止后 `state` 回到 `idle`。

参考 `tests/conftest.py` 里的假引擎实现——它可以被直接复用为 macOS 桥接的测试桩。
