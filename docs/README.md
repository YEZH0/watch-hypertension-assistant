# 文档索引

| 文档 | 内容 | 什么时候看 |
|---|---|---|
| [../AGENTS.md](../AGENTS.md) | **AI Agent 入口**：0–8 全流程、硬约束、失败矩阵、汇报模板 | 只拿到仓库链接时 |
| [../README.md](../README.md) | 项目总览、能力边界、命令一览 | 第一次接触 |
| [QUICKSTART.md](QUICKSTART.md) | 5 分钟跑起来 | 只想先跑通 |
| [TUTORIAL.md](TUTORIAL.md) | 0–8 阶段完整教程（含手机上的人工确认） | 准备实际使用 |
| [FAQ.md](FAQ.md) | 常见问题、误用、向导与恢复排查 | 遇到疑问 |
| [MEDICAL-SAFETY.md](MEDICAL-SAFETY.md) | 医疗安全边界 | 想理解为什么这么设计 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层、数据流、设计决定 | 想改代码 |
| [ADAPTER-CONTRACT.md](ADAPTER-CONTRACT.md) | 五个 HTTP 接口规格 | 接入新平台 / Mac Agent |
| [LICENSE-BOUNDARY.md](LICENSE-BOUNDARY.md) | MIT 与 GPL 的边界 | 提交任何代码前 |
| [DEPENDENCIES.md](DEPENDENCIES.md) | 依赖清单与策略 | 装环境 / 升级依赖 |
| [CI-SETUP.md](CI-SETUP.md) | CI 现状、维护方式与历史踩坑 | 想改工作流 / 排查权限 |

## 三分钟了解这个项目

1. 定位协议**不是**本项目写的，全部来自已完成的 `ios-location-studio` 引擎。
2. 本项目通过**本机 HTTP** 调用引擎，不复制代码——这是许可证与解耦的双重要求。
3. 助手给不出"功能已开通"的结论，因为它在结构上**不可能知道**。
4. 四个地区预设是固定的，不支持自由经纬度。
5. 引擎 `active`、手机地图位置、健康功能状态是**三个互相独立的状态**，不能互相推断。
6. `wizard` 把这条链路拆成 0–8 阶段，每一处需要人看手机的地方都会停下等确认。

## 按角色的阅读路径

**普通用户**
QUICKSTART → TUTORIAL → FAQ

**把仓库交给 AI Agent 的人**
AGENTS.md（让 Agent 读这一份即可，必要时再补 TUTORIAL / FAQ）

**想贡献代码**
LICENSE-BOUNDARY → ARCHITECTURE → ADAPTER-CONTRACT

**Mac Agent**
ADAPTER-CONTRACT → LICENSE-BOUNDARY → `../macos/README.md` → `../tests/conftest.py`
另外 `../assistant/wizard.py` 的 `STAGES` 与回答取值是跨平台共享契约，需保持一致。

**审查 PR 的人**
LICENSE-BOUNDARY 的审查清单 + `../.github/pull_request_template.md`
