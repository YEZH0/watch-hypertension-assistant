"""Windows 适配器：复用已完成的 DVT 引擎。

已完成的 Windows 成果在 ``YEZH0/ios-location-studio`` 的
``fix/windows-stabilization`` 分支，其引擎对外就是 FastAPI 的 JSON 接口。

本适配器只做三件事：
1. 找到引擎（已在运行的 / 本机已安装的）；
2. 需要时以子进程方式拉起 ``ios-location-studio`` 并等待其就绪；
3. 把调用转发给 ``HttpLocationEngine``。

**不含任何 DVT 协议代码**，也没有复制旧仓库的任何源文件。
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time

from .base import AdapterUnavailable, EngineStatus
from .http_engine import HttpLocationEngine

ENGINE_NAME = "ios-location-studio"
# 旧引擎 CLI 的默认端口，被占用时会自动 +1，所以这里也顺延探测几个。
DEFAULT_PORTS = (8899, 8900, 8901, 8902, 8903)
LAUNCH_WAIT_SECONDS = 25.0


class WindowsLocationEngine(HttpLocationEngine):
    """Windows 平台：调用旧项目已完成的 DVT 引擎。"""

    name = "windows-dvt"

    def __init__(self, base_url: str | None = None) -> None:
        super().__init__(base_url or f"http://127.0.0.1:{DEFAULT_PORTS[0]}", platform="windows")
        # 探测失败的原因，用来把「未找到」换成「找到了但为什么起不来」。
        self._entrypoint_issues: list[str] = []

    # ------------------------------------------------------------ 引擎发现

    def _candidate_urls(self) -> list[str]:
        urls = [self.base_url]
        urls += [f"http://127.0.0.1:{p}" for p in DEFAULT_PORTS]
        seen: set[str] = set()
        ordered: list[str] = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                ordered.append(url)
        return ordered

    def _existing_entrypoint(self) -> list[str] | None:
        """查找**能真正跑起来**的引擎命令行入口。

        只查 ``shutil.which`` 是不够的。editable 安装（``pip install -e``）在某些
        环境下生成的路径钩子不生效：入口脚本存在，但一执行就
        ``ModuleNotFoundError: No module named 'ios_location_studio'``。
        这种情况下继续 Popen 会白等到超时，最后报「已启动但在等待时间内未就绪」，
        用户会去查 USB、查端口、查防火墙——全错方向。

        所以这里对每个候选入口真跑一次 ``--version``，起不来的当场记下原因。
        """
        self._entrypoint_issues = []

        seen_paths: set[str] = set()
        for candidate in (ENGINE_NAME, f"{ENGINE_NAME}.exe"):
            found = shutil.which(candidate)
            # Windows 上 which("x") 与 which("x.exe") 往往指向同一个文件，
            # 去重避免同一次失败被验证两遍、报告两遍。
            if not found or found in seen_paths:
                continue
            seen_paths.add(found)
            issue = self._verify_entrypoint([found])
            if issue is None:
                return [found]
            self._entrypoint_issues.append(issue)

        # 候选二：以已安装模块的形式存在（pip install 过旧项目）。
        module_command = [sys.executable, "-m", "ios_location_studio"]
        issue = self._verify_entrypoint(module_command)
        if issue is None:
            return module_command
        self._entrypoint_issues.append(issue)
        return None

    @staticmethod
    def _verify_entrypoint(command: list[str]) -> str | None:
        """跑一次 ``--version`` 验证入口可用。可用返回 None，否则返回原因。"""
        try:
            probe = subprocess.run(  # noqa: S603 - 参数固定，无 shell
                [*command, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except OSError as exc:
            return f"{' '.join(command)} 无法执行：{exc}"
        except subprocess.TimeoutExpired:
            return f"{' '.join(command)} 在 15 秒内没有响应。"

        if probe.returncode == 0:
            return None

        detail = f"{probe.stderr or ''}{probe.stdout or ''}".strip().splitlines()
        reason = detail[-1] if detail else f"退出码 {probe.returncode}"

        # 老版本引擎可能没有 --version。不能因此判定「不可用」，
        # 退回「存在即可用」，由后面的等待就绪流程去暴露真正问题。
        if probe.returncode == 2 and ("unrecognized arguments" in reason or "--version" in reason):
            return None

        if "No module named" in reason:
            return (
                f"{' '.join(command)} 存在但导入失败：{reason}。"
                "这属于 editable 安装的路径钩子未生效，不等于引擎没装。"
                "可以手动启动：PYTHONPATH=src python -m ios_location_studio "
                "--no-browser --port 8899，然后加 "
                "--engine-url http://127.0.0.1:8899 重试。"
            )
        return f"{' '.join(command)} 无法启动：{reason}"

    # ------------------------------------------------------------ 生命周期

    def probe(self) -> EngineStatus:
        """先看有没有已经跑起来的引擎；没有再尝试启动一个。"""
        for url in self._candidate_urls():
            self.base_url = url
            status = super().probe()
            if status.available:
                return status

        # 没有在运行的实例，尝试拉起。
        launch_error = self._launch()
        if launch_error:
            return EngineStatus(
                available=False,
                platform="windows",
                engine=self.name,
                endpoint=self.base_url,
                detail=launch_error,
            )

        deadline = time.monotonic() + LAUNCH_WAIT_SECONDS
        while time.monotonic() < deadline:
            for url in self._candidate_urls():
                self.base_url = url
                status = super().probe()
                if status.available:
                    return status
            time.sleep(0.5)

        return EngineStatus(
            available=False,
            platform="windows",
            engine=self.name,
            endpoint=self.base_url,
            detail="已启动引擎进程，但在等待时间内未就绪。",
        )

    def _launch(self) -> str | None:
        """以子进程方式启动引擎。返回 None 表示启动成功，否则返回原因。"""
        entrypoint = self._existing_entrypoint()
        if entrypoint is None:
            # 有原因就说原因：笼统的「未找到」会让用户重装一个其实已经装好的东西。
            if self._entrypoint_issues:
                return "找不到能启动的 " + ENGINE_NAME + " 入口。" + "；".join(self._entrypoint_issues)
            return (
                f"未找到 {ENGINE_NAME}。请先安装已完成的 Windows 版本："
                "pip install git+https://github.com/YEZH0/ios-location-studio.git@fix/windows-stabilization"
            )

        port = self._first_free_port()
        command = [*entrypoint, "--no-browser", "--port", str(port)]
        try:
            # 不接管输出，避免父进程退出时被管道阻塞；不打开浏览器。
            subprocess.Popen(  # noqa: S603 - 参数固定，无 shell
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        except OSError as exc:
            return f"启动引擎失败：{exc}"

        self.base_url = f"http://127.0.0.1:{port}"
        return None

    @staticmethod
    def _first_free_port() -> int:
        for port in DEFAULT_PORTS:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.3)
                if probe.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        raise AdapterUnavailable(
            "8899-8903 端口全部被占用。",
            hint="请关闭占用端口的程序，或用 --engine-url 直接指定运行中的引擎。",
        )
