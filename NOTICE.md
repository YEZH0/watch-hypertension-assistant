# NOTICE · 来源与许可边界

本项目是代码整合项目。所有定位能力来自既有项目，本项目只做编排与如实报告。

## 分层许可总览

| 路径 | 许可证 | 原因 |
|---|---|---|
| 仓库根目录 | MIT | 本项目的编排、检查、文档代码 |
| `assistant/` | MIT | 助手核心，零第三方运行时依赖 |
| `windows/` | MIT | 仅说明与配置样例，不含引擎代码 |
| `agent/` `docs/` `tests/` | MIT | 文档与测试 |
| `macos/` | **GPL-3.0-only** | 由 Mac Agent 实现，将引用 GPL 的 `accessory-location` |

`macos/` 拥有自己的 `LICENSE` 文件。根目录的 MIT 许可**不覆盖** `macos/`。

## 上游依赖项目

### 1. ios-location-studio（Windows 引擎）

* 仓库：https://github.com/YEZH0/ios-location-studio
* 使用分支：`fix/windows-stabilization`
* 许可证：MIT
* 复用方式：**本机 HTTP 进程间调用**，不复制源码

Windows 引擎本身是 FastAPI 服务，已暴露稳定的 JSON 接口。
本助手作为客户端调用它，两个项目各自独立发版。

### 2. ios-location-studio（macOS 引擎）

* 仓库：https://github.com/YEZH0/ios-location-studio
* 使用分支：`feat/macos-iap2`
* 许可证：GPL-3.0-only
* 复用方式：**本机 HTTP 进程间调用**，不复制源码

macOS 子项目 vendor 了 `aur3l14no/accessory-location`（GPL-3.0-only），
因此整体为 GPL-3.0-only。本助手不 import 它的任何模块。

### 3. aur3l14no/accessory-location

* 仓库：https://github.com/aur3l14no/accessory-location
* 许可证：GPL-3.0-only
* 固定上游提交：`8a13296a3d81dae18ad4481e7a9eca913c2c644f`
* 关系：本项目**不直接包含**该代码。它只存在于旧 macOS 子项目中。

## 为什么进程间调用不构成 GPL 传染

GPL 的 copyleft 义务作用于「衍生作品」——即包含 GPL 代码、与之链接形成单一程序的作品。
本项目与 macOS 引擎之间：

* 无源码复制；
* 无 `import` / 动态链接 / 静态链接；
* 仅通过本机回环网络上的 JSON 消息通信，是**两个独立程序**。

因此本仓库 MIT 部分可以保持 MIT。`macos/` 目录内的实现对 GPL 组件的使用仍受
GPL-3.0-only 约束。

> 这是工程判断，不是法律意见。公开分发二进制之前请自行做合规审查。

## 本项目自身的数据来源

| 数据 | 来源 | 核验日期 |
|---|---|---|
| 高血压通知支持机型与系统版本 | Apple 官方支持文档 https://support.apple.com/en-us/123002 | 2026-11-17 |
| 各地区可用性 | Apple watchOS 功能可用性页面与公开报道 | 2026-11-17 |

这些数据以 JSON 快照形式存放在 `assistant/data/`，是**快照而非权威来源**。
Apple 会按监管进度调整。最终以官方页面与 iPhone 健康 App 实际显示为准。

## 未包含的内容

以下内容**从未**被纳入本仓库，也不应被提交：

* MFi 证书、私钥、配对记录
* Apple ID 凭据
* 设备序列号 / UDID / ECID
* 任何用户健康数据
* 打包好的 EXE / APP / DMG
