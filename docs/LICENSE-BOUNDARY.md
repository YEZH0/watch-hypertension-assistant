# MIT 与 GPL 的许可证边界

这个项目同时接触 MIT 与 GPL-3.0-only 两种代码。边界必须写清楚，否则一次不小心的
`import` 就可能让整个项目被迫变成 GPL。

## 事实：旧项目是分层许可的

| 旧项目位置 | 许可证 |
|---|---|
| `ios-location-studio` 根目录（含 Windows 引擎） | MIT |
| `ios-location-studio` 的 `macos/` 子项目 | **GPL-3.0-only** |

macOS 子项目是 GPL，不是因为它自己想，而是因为它 vendor 了
`aur3l14no/accessory-location`（GPL-3.0-only），GPL 的 copyleft 要求整体同许可。
旧项目自己的 `macos/THIRD_PARTY_NOTICES.md` 已经如实写明这一点。

## 本项目的选择

```
watch-hypertension-assistant/
├── LICENSE              → MIT，但只覆盖下列目录
├── assistant/           → MIT
├── windows/             → MIT
├── agent/ docs/ tests/  → MIT
└── macos/               → GPL-3.0-only，有自己的 LICENSE
```

**根目录的 MIT 不覆盖 `macos/`。** 这是项目的硬约定，PR 里会被检查。

## 三条必须遵守的规则

### 规则 1：不复制 GPL 代码进 MIT 目录

以下行为都是禁止的：

* 把 `macos/src/location_studio_mac/*.py` 复制到 `assistant/`
* 把 `macos/vendor/accessory-location/` 的任何文件搬进来
* 从 MIT 目录 `import location_studio_mac`
* 把 GPL 的代码片段粘贴进 MIT 文件（哪怕只有几十行）

一旦发生，该 MIT 文件就变成 GPL 衍生作品，整个项目的一致性就被破坏了。

### 规则 2：跨许可证只允许进程间调用

允许：

```
assistant/adapters/macos.py  ──HTTP──▶  127.0.0.1:8900  ──▶  macos/ (GPL)
        (MIT)                                                   (GPL-3.0-only)
```

禁止：

```
assistant/adapters/macos.py  ──import──▶  location_studio_mac   ❌
```

理由：HTTP JSON 消息通信是两个独立程序之间的正常交互，不形成单一组合作品。
`import` / 链接则会把两者绑成一个程序，触发 copyleft。

### 规则 3：GPL 目录保持完整的 GPL 义务

`macos/` 里的代码：

* 必须保留 `LICENSE`（GPL-3.0 全文）
* 必须保留上游版权声明与 `THIRD_PARTY_NOTICES`
* 分发时必须提供完整对应源码
* 不得附加额外限制

## Windows 方向没有这个问题

Windows 引擎是 MIT，本仓库也是 MIT，法律上其实可以直接 import。
但项目仍然选择 HTTP 调用，原因是工程上的：

* 旧项目能独立发版，不必为了新项目改它；
* 不产生版本耦合（旧项目升级不需要重装新项目）；
* 用户已经装好了旧引擎，复用它就是最快路径。

**用 HTTP 不是许可证逼出来的妥协，而是本来就更好的设计。**

## 审查清单

提 PR 前自查：

- [ ] 没有把 `macos/` 的任何代码复制到 MIT 目录
- [ ] MIT 目录没有 `import location_studio_mac` 或 `accessory_location`
- [ ] 新增文件放在了正确的目录（macOS 相关 → `macos/`）
- [ ] 没有改动 `macos/LICENSE` 或上游通知文件
- [ ] `NOTICE.md` 已同步（若引入了新的上游依赖）

## 免责

以上是工程层面的判断，不是法律意见。如果要公开分发**二进制**（本项目明确不做），
请先自行完成 GPL 合规审查。
