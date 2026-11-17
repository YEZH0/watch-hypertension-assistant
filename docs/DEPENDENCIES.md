# 依赖说明

本项目**运行时零第三方依赖**。这是刻意的选择：定位助手需要在用户机器上
直接跑，每多一个依赖就多一份未经验证第三方代码的风险。

## 本仓库自身的依赖

### 运行时

无。只用 Python 标准库：

| 用途 | 模块 |
|---|---|
| HTTP 调用引擎 | `urllib.request` |
| 数据模型 | `dataclasses` |
| 数据文件 | `json` |
| 命令行 | `argparse` |
| 平台识别 | `sys` / `platform` |
| 版本比较 | 内置字符串处理 |

### 开发与测试（固定版本）

```toml
dev = [
  "pytest==8.3.4",
  "ruff==0.8.4",
]
```

为什么固定版本：避免 `pip install` 时解析到未经验证的新版本，导致行为漂移。
这两个包只在开发时用，用户运行时不需要。

### Python 版本

`>=3.11`。用到 `X | None` 类型语法、`argparse.BooleanOptionalAction`。

---

## 外部引擎的依赖（不由本仓库管理）

本助手通过 HTTP 调用外部引擎，**不安装、不管理、不下载**它们的依赖。
这样做有两个好处：旧项目可以独立升级；本项目不会因为上游依赖变动而失效。

### Windows 引擎（`fix/windows-stabilization`）

| 依赖 | 用途 |
|---|---|
| `pymobiledevice3` | DVT 通道与 usbmux 设备枚举 |
| `fastapi` + `uvicorn` | 提供本助手调用的 HTTP 接口 |
| `pydantic` | 请求校验 |

安装：

```bash
pip install "git+https://github.com/YEZH0/ios-location-studio.git@fix/windows-stabilization"
```

### macOS 引擎（`feat/macos-iap2`）

| 依赖 | 用途 |
|---|---|
| `PySide6` | 桌面 GUI |
| `pymobiledevice3` | DVT 通道 |
| `accessory-location`（vendor，GPL-3.0-only） | iAP2 实验路线 |

安装见旧项目 `macos/README.md`，使用 `uv sync --locked`。

⚠️ macOS 引擎是 **GPL-3.0-only**，与本节无关但必须清楚：见 [LICENSE-BOUNDARY.md](LICENSE-BOUNDARY.md)。

---

## 依赖策略

| 原则 | 做法 |
|---|---|
| 固定版本 | `pyproject.toml` 里所有依赖都写 `==` |
| 不下载未验证程序 | 不提供任何"一键下载安装"脚本 |
| 不引入不必要的库 | 能用标准库就不加依赖 |
| 不锁死上游 | 引擎走 HTTP，不把它写进 `dependencies` |
| 不静默升级 | CI 只装固定版本，不使用 `--upgrade` |

## 升级依赖的流程

1. 改 `pyproject.toml` 里的版本号；
2. 本地 `pip install -e ".[dev]"`；
3. `python -m pytest -q` 全绿；
4. `python -m ruff check assistant tests` 通过；
5. 提 PR，说明升级原因与影响面。

不允许在 PR 里顺手升级依赖却不说明原因。

## 供应链安全

* 全部依赖来自 PyPI 或 GitHub 官方仓库。
* 不引入任何需要运行 `curl | sh` 的安装方式。
* 引擎地址强制回环，杜绝"把坐标发到某个远端服务"的可能。
* 不在仓库里保存证书、私钥、令牌。

## 许可证兼容性

| 依赖 | 许可证 | 与本项目 MIT 的关系 |
|---|---|---|
| `pytest` | MIT | 兼容 |
| `ruff` | MIT | 兼容 |
| `pymobiledevice3` | GPL-3.0 | 通过 HTTP 调用，不链接 |
| `accessory-location` | GPL-3.0-only | 仅存在于 `macos/`，不链接 |

因为本仓库不链接任何 GPL 代码，MIT 许可成立。细节见 [LICENSE-BOUNDARY.md](LICENSE-BOUNDARY.md)。
