# CI 现状与维护说明

## 当前状态：已启用 ✅

工作流文件：`.github/workflows/main.yml`
运行记录：https://github.com/YEZH0/watch-hypertension-assistant/actions

矩阵：`windows-latest` / `ubuntu-latest` × Python `3.11` / `3.12` / `3.13`，共 6 个 job。
每个 job 依次执行：安装固定版本 dev 依赖 → `ruff check` → `pytest -q` → CLI 冒烟。

---

## 为什么当初要用网页手动建（踩过的坑，写下来免得重复）

GitHub 有一条硬规则：

> **任何推送到 `.github/workflows/` 下的文件，所用 Personal Access Token 必须带 `workflow` scope。**

只有 `repo` scope 的令牌会被直接拒绝，报错长这样：

```
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - refusing to allow a Personal Access Token to create or update
          workflow `.github/workflows/ci.yml` without `workflow` scope
```

这条规则判定的是**整个推送**是否合法，不是逐个文件判定。所以"只推那一个文件"、"用 API 删除"、"改名绕过"全部无效 —— 只要路径沾到 `.github/workflows/`，就需要 `workflow` scope。

浏览器网页操作不受此限制，因为用的是已登录的会话，不是令牌。

---

## 另一个坑：文件名输入框会重复拼路径

通过 `.../new/main/.github/workflows` 这类地址进入新建页时，URL 里已经带了目录。
此时如果在文件名框里**又完整输入** `.github/workflows/ci.yml`，GitHub 会把两段拼起来，结果变成：

```
.github/workflows/.github/workflows/.github/workflows/.github/workflows/ci.yml   ← 错误
```

**正确做法**：从 Actions 页面的 `set up a workflow yourself →` 进入，
文件名框左侧已经固定显示 `.github / workflows`，只填 `main.yml` 即可。

---

## 如果你想重新创建（例如换一台机器、或误删）

方式 A：网页新建，不需要任何令牌

1. 打开 https://github.com/YEZH0/watch-hypertension-assistant/actions
2. 点任一工作流 → 右上 **New workflow** → 找 **set up a workflow yourself**
3. 文件名只填 `main.yml`，正文粘贴本文件下方 YAML
4. `Commit changes…` → 选 `Commit directly to the main branch` → 点红色 `Bypass rules and commit changes`
   （红色是因为 main 有分支保护，owner 绕过属正常操作）

方式 B：用带 `workflow` scope 的令牌推送

生成令牌时用这个链接，scope 会预先勾好 `repo` + `workflow`：

```
https://github.com/settings/tokens/new?scopes=repo,workflow&description=whc-ci
```

拿到后由 Agent 推送即可，用完立即撤销。

---

## 工作流正文（与远端 `main.yml` 一致）

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

---

## CI 跑什么、不跑什么

| 步骤 | 作用 |
|---|---|
| `pip install -e ".[dev]"` | 只装固定版本的 dev 依赖（pytest / ruff）。运行时代码零第三方依赖 |
| `ruff check` | 代码规范与未使用导入 |
| `pytest -q` | 155 项测试，含本地假引擎驱动的 HTTP 适配器端到端验证 |
| CLI 冒烟 | 四个只读子命令必须跑通，防止打包 / 导入回归 |

**CI 不接触任何真实设备**，不需要 USB、不需要 iPhone、不需要引擎在运行。
所有涉及设备的路径都由 `tests/conftest.py` 里的假引擎（标准库 `http.server`）接管。

---

## macOS job 何时启用

`macos/` 目前只是契约占位（见 [`ADAPTER-CONTRACT.md`](./ADAPTER-CONTRACT.md)），没有可执行的桥接实现。
此时加 macOS job 只会得到一个必然失败的红叉，没有信息量。

Mac Agent 在 `feat/macos` 分支完成桥接后，把 `matrix.os` 改成：

```yaml
os: [windows-latest, ubuntu-latest, macos-latest]
```

其余步骤无需改动。
