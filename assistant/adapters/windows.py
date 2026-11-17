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
        """查找已安装的引擎命令行入口。"""
        for candidate in (ENGINE_NAME, f"{ENGINE_NAME}.exe"):
            found = shutil.which(candidate)
            if found:
                return [found]
        # 允许以已安装模块的形式存在（pip install 过旧项目）。
        probe = subprocess.run(
            [sys.executable, "-c", "import ios_location_studio"],
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            return [sys.executable, "-m", "ios_location_studio"]
        return None

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
