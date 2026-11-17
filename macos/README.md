# macOS 适配器（待 Mac Agent 实现）

> **状态：契约已冻结，实现待完成。**
> 本目录由 Mac Agent 从 `main` 创建 `feat/macos` 分支后负责，Windows Agent 不修改本目录内容。

## 许可证：GPL-3.0-only

本目录（含未来新增的所有文件）为 **GPL-3.0-only**，因为 macOS 引擎 vendor 了
`aur3l14no/accessory-location`（GPL-3.0-only）。

* `macos/LICENSE` 是 GPL-3.0 全文，**不得删除或修改**。
* 本目录的 GPL **不覆盖**仓库其他部分；根目录的 MIT 也**不覆盖**本目录。
* 不要把本目录的任何代码复制到 `assistant/`。详见 `docs/LICENSE-BOUNDARY.md`。

## 要做什么

在 `macos/` 下提供一个桥接进程，让助手核心通过 HTTP 复用现有 DVT 实现：

```bash
python -m location_studio_mac.bridge --host 127.0.0.1 --port 8900
```

它必须暴露五个接口（完整规格见 `docs/ADAPTER-CONTRACT.md`）：

| 接口 | 说明 |
|---|---|
| `GET /api/health` | `{"ok": true, "version": "..."}` |
| `GET /api/devices` | `{"connected": bool, "devices": [...]}` |
| `GET /api/status` | `{"session": {...}}` |
| `POST /api/simulate` | 请求体 `{latitude, longitude, hold_seconds}` |
| `POST /api/stop` | 停止并恢复 |

## 必须遵守的约束

1. **不重写定位协议。** 复用 `macos/` 内既有的 `dvt_*` worker 命令与 `sandbox-exec`
   沙箱配置，桥接层只做协议转换。
2. **DVT 是默认路线。** iAP2 保留为实验性选项，默认不启用，不参与自动判定。
   iAP2 历史上存在"有 ACK 却不采纳位置"的记录，不能承诺生效。
3. **不是所有成功都叫成功。** worker 的 `dvt_set_sent` 只表示请求已发送。
   会话进入 `active` 才可以认为模拟定位在下发中。仍然不能等同于手机上已验证。
4. **不泄露设备信息。** 不要把设备标识、ECID、票据、原始工具日志放进 HTTP 响应
   或日志。参考旧实现：错误事件只保留 `type`，丢弃 detail。
5. **GPL 材料不外流。** 证书、私钥、配对记录不进入本目录，也不进入任何响应。

## 会话状态语义

`state` 只允许：`idle` / `connecting` / `active` / `stopping` / `error`

| 状态 | 含义 |
|---|---|
| `connecting` | 正在建立 DVT 隧道 |
| `active` | 已下发模拟坐标，保持中 |
| `stopping` | 正在清除并关闭隧道 |
| `idle` | 已停止 |
| `error` | 失败，`error` 字段说明原因 |

**禁止**在响应里出现任何 `hypertension_*`、`compatible`、`enabled` 之类的字段。

## 自检

从仓库根目录：

```bash
python -m assistant --engine-url http://127.0.0.1:8900 env
python -m assistant --engine-url http://127.0.0.1:8900 devices
python -m assistant --engine-url http://127.0.0.1:8900 check
python -m assistant --engine-url http://127.0.0.1:8900 start --region hk
python -m assistant --engine-url http://127.0.0.1:8900 stop
```

五条全部正常返回 = 接入完成。**助手核心不需要任何改动。**

## 测试要求

在 `macos/` 内至少覆盖：

* 桥接能启动并响应 `/api/health`；
* 无设备时 `/api/simulate` 返回 `409` 而非崩溃；
* `state` 只输出合法枚举；
* `stop` 之后回到 `idle`；
* 响应与日志中不含设备标识符。

`tests/conftest.py` 里的假引擎可以直接复用为桩实现。

## 改动范围

* ✅ `macos/**`
* ✅ `.github/workflows/` 新增 macOS job
* ❌ `assistant/**`（契约已冻结；确需修改请先与 Windows Agent 确认并提 issue）
* ❌ `windows/**`

全部改动通过 PR 合并，未经维护者确认不得合并到 `main`。
