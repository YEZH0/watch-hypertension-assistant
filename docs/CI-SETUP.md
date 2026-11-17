# 启用 CI（一次性手动步骤）

## 为什么需要手动建

GitHub 有一条仓库规则：**任何包含 `.github/workflows/` 文件的推送，令牌必须带 `workflow` scope**。
本仓库初始化时用的令牌只有 `repo` scope，所以 `ci.yml` 被远端拒绝了。
代码本身没问题，纯粹是令牌权限问题，与仓库内容无关。

有两种解决方式，任选其一。

---

## 方式 A：网页上直接新建（最快，30 秒）

不需要任何令牌，用你已登录的浏览器会话即可。

1. 打开 https://github.com/YEZH0/watch-hypertension-assistant/new/main/.github/workflows
   （如果提示目录不存在，就先打开仓库首页 → **Add file** → **Create new file**）
2. 文件名填：`.github/workflows/ci.yml`
3. 把下面这段完整粘进编辑区：

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test:
    name: test (${{ matrix.os }} / py${{ matrix.python-version }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest]
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install (pinned dev deps only)
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"

      - name: Lint
        run: python -m ruff check assistant tests

      - name: Test
        run: python -m pytest -q

      - name: Smoke test CLI
        run: |
          python -m assistant regions
          python -m assistant families
          python -m assistant guide
          python -m assistant compat --watch series10 --watchos 26.1 --ios 26.1 --age 30
```

4. 底部选 **Commit directly to the `main` branch** → **Commit changes**

提交后会自动触发第一次运行，6 个 job（Windows/Ubuntu × Python 3.11/3.12/3.13）。

---

## 方式 B：给一个带 workflow scope 的令牌

1. 打开 https://github.com/settings/tokens/new
2. Note 填 `whc-ci-push`
3. Expiration 选 **7 days**
4. **同时勾选 `repo` 和 `workflow`**（`workflow` 在列表偏下的位置，不要漏）
5. Generate → 复制 `ghp_` 开头的字符串，发给 Agent

Agent 会用这个令牌把本地已准备好的 `ci/github-actions` 分支推上去。
推送完成后**立即删除令牌**：https://github.com/settings/tokens

---

## 说明：为什么 macOS job 还没启用

`macos/` 目前只是契约占位（见 [`ADAPTER-CONTRACT.md`](./ADAPTER-CONTRACT.md)），
没有可执行的桥接实现。此时加一个 macOS job 只会得到必然失败的红叉，没有信息量。

Mac Agent 在 `feat/macos` 分支完成桥接后，在同一个 `ci.yml` 的 `matrix.os` 里
加上 `macos-latest` 即可，其余步骤无需改动。

---

## CI 跑什么

| 步骤 | 作用 |
|---|---|
| `pip install -e ".[dev]"` | 安装固定版本的 dev 依赖（pytest / ruff），运行时代码零第三方依赖 |
| `ruff check` | 代码规范与未使用导入 |
| `pytest -q` | 85 项测试，含用假引擎做的 HTTP 适配器端到端验证 |
| CLI 冒烟 | 四个只读子命令必须能跑通，防止打包/导入回归 |

CI 不接触任何真实设备，不需要 USB、不需要 iPhone。所有涉及设备的测试都用
`tests/conftest.py` 里的本地假引擎（标准库 `http.server`）替代。
