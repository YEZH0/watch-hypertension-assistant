## 这个 PR 做了什么

<!-- 一句话说明目的 -->

## 改动范围

<!-- 勾选涉及的部分，未涉及的直接删掉 -->

- [ ] `assistant/` 助手核心（Windows Agent 主要负责）
- [ ] `windows/` Windows 适配器
- [ ] `macos/` macOS 实现（Mac Agent 主要负责）
- [ ] `docs/` 文档
- [ ] `tests/` 测试

## 必须自查的项目

- [ ] 没有复制旧项目（`ios-location-studio`）的定位协议源码
- [ ] 没有修改 `main` 上的无关文件
- [ ] 没有新增"功能已开通/已生效"这类断言
- [ ] 没有提交证书、私钥、Apple ID、设备序列号
- [ ] `python -m pytest -q` 全绿
- [ ] `python -m ruff check assistant tests` 通过
- [ ] 若新增地区预设：确认仍只有四个固定预设，且未引入自由经纬度输入

## 影响面

<!-- 是否影响另一平台的适配器？是否需要对方 Agent 同步？ -->
