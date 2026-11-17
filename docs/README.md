# 文档索引

| 文档 | 内容 | 什么时候看 |
|---|---|---|
| [../README.md](../README.md) | 项目总览、能力边界、快速开始 | 第一次接触 |
| [TUTORIAL.md](TUTORIAL.md) | 从零到完成一次完整测试 | 准备实际使用 |
| [FAQ.md](FAQ.md) | 常见问题与误用 | 遇到疑问 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层、数据流、设计决定 | 想改代码 |
| [ADAPTER-CONTRACT.md](ADAPTER-CONTRACT.md) | 五个 HTTP 接口规格 | 接入新平台 / Mac Agent |
| [LICENSE-BOUNDARY.md](LICENSE-BOUNDARY.md) | MIT 与 GPL 的边界 | 提交任何代码前 |
| [DEPENDENCIES.md](DEPENDENCIES.md) | 依赖清单与策略 | 装环境 / 升级依赖 |
| [CI-SETUP.md](CI-SETUP.md) | 启用 GitHub Actions（含手动建文件步骤） | 首次 fork / 令牌权限不足 |
| [MEDICAL-SAFETY.md](MEDICAL-SAFETY.md) | 医疗安全边界 | 想理解为什么这么设计 |

## 三分钟了解这个项目

1. 定位协议**不是**本项目写的，全部来自已完成的 `ios-location-studio` 引擎。
2. 本项目通过**本机 HTTP** 调用引擎，不复制代码——这是许可证与解耦的双重要求。
3. 助手给不出"功能已开通"的结论，因为它在结构上**不可能知道**。
4. 四个地区预设是固定的，不支持自由经纬度。
5. 定位测试成功与高血压通知可用，是两件无关的事。

## 按角色的阅读路径

**普通用户**
README → TUTORIAL → FAQ

**想贡献代码**
LICENSE-BOUNDARY → ARCHITECTURE → ADAPTER-CONTRACT

**Mac Agent**
ADAPTER-CONTRACT → LICENSE-BOUNDARY → `../macos/README.md` → `../tests/conftest.py`

**审查 PR 的人**
LICENSE-BOUNDARY 的审查清单 + `../.github/pull_request_template.md`
