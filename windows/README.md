# Windows 适配器

复用已完成的 DVT 引擎，**不复制任何源码**。

## 对应的旧项目成果

* 仓库：https://github.com/YEZH0/ios-location-studio
* 分支：`fix/windows-stabilization`
* 许可证：MIT
* 文件：`assistant/adapters/windows.py`（本仓库内，只做 HTTP 客户端）

## 复用方式

旧项目的 Windows 引擎本身就是 FastAPI 服务，已经暴露了稳定接口：

| 接口 | 用途 |
|---|---|
| `GET /api/health` | 引擎是否在线 |
| `GET /api/devices` | USB 设备清单 |
| `GET /api/status` | 当前会话 |
| `POST /api/simulate` | 下发模拟定位 |
| `POST /api/stop` | 停止并恢复 |

本适配器就是这五个接口的客户端。**没有一行 DVT 协议代码。**

## 引擎发现顺序

1. 显式 `--engine-url` → 直接用，不自动启动（纯客户端模式）
2. 依次探测 `127.0.0.1:8899` … `8903` 上是否已有引擎在跑
3. 都没有 → 查找本机已安装的入口（`ios-location-studio` 命令，或 `python -m ios_location_studio`）
4. 找到就 `Popen` 拉起（`--no-browser`，不接管输出）
5. 等待就绪，最多 25 秒

找不到引擎时会给出可执行的安装命令，不会静默失败。

## 安装引擎

```bash
pip install "git+https://github.com/YEZH0/ios-location-studio.git@fix/windows-stabilization"
```

或者按旧项目的 README 装好，只要能跑 `ios-location-studio` 命令即可。

## 手动指定引擎

如果引擎在非默认端口：

```bash
python -m assistant --engine-url http://127.0.0.1:9000 check
```

## 本目录内容

| 文件 | 说明 |
|---|---|
| `README.md` | 本文件 |
| `config.example.toml` | 本地配置样例（可选，非必需） |

本目录**不含引擎代码**。请不要把旧项目源码复制到这里。

## 验证接入

```bash
python -m assistant env         # 引擎在线
python -m assistant devices     # 能看到手机
python -m assistant check       # 完整检查
```

## 已知限制

| 限制 | 说明 |
|---|---|
| 只支持 USB | Wi-Fi 连接的设备枚举不到，DVT 也需要 USB |
| 单设备 | 检测到多台时拒绝继续，避免改错手机 |
| 端口范围固定 | 8899–8903；超出请用 `--engine-url` |
| 不管理引擎生命周期 | 拉起的进程由用户自己的系统管理，`stop` 只停止会话，不杀进程 |

## 修改本适配器时

* 只改 `assistant/adapters/windows.py` 和本目录
* 不要改 `assistant/adapters/base.py`（那是与 Mac Agent 的共同契约，改动需双方确认）
* 不要改 `assistant/adapters/http_engine.py` 的接口语义（会影响 macOS）
* 跑完 `python -m pytest -q` 再提 PR
