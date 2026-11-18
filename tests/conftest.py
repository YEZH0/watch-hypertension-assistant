"""测试夹具：一个模拟 ios-location-studio 引擎的本地 HTTP 服务。

用真实 HTTP 而不是 mock，是为了同时验证请求序列化、状态码处理、JSON 解析
这几条容易出错的路径。假引擎的行为与真实引擎的接口约定一一对应。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


class FakeEngineState:
    def __init__(self) -> None:
        self.devices: list[dict[str, Any]] = [
            {
                "udid": "00008110-TEST-UDID",
                "name": "Test iPhone",
                "ios_version": "26.1",
                "build": "23B80",
                "model": "iPhone17,3",
            }
        ]
        self.session_state = "idle"
        # 保持中的会话还剩下多少秒；测试改这个值来模拟「会话已到期」。
        self.session_remaining: float = 120.0
        self.last_payload: dict[str, Any] | None = None
        self.fail_simulate_with: int | None = None
        self.calls: list[tuple[str, str]] = []


def _make_handler(state: FakeEngineState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:  # 静默，避免污染测试输出
            return

        def _json(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _session(self) -> dict[str, Any]:
            active = state.session_state == "active"
            return {
                "state": state.session_state,
                "latitude": 22.2819 if active else None,
                "longitude": 114.1588 if active else None,
                "remaining": state.session_remaining if active else None,
                "message": "模拟定位已生效" if active else "",
                "error": None,
            }

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
            state.calls.append(("GET", self.path))
            if self.path == "/api/health":
                self._json(200, {"ok": True, "version": "0.1.0"})
            elif self.path == "/api/devices":
                self._json(
                    200,
                    {
                        "connected": bool(state.devices),
                        "devices": state.devices,
                        "error": None,
                    },
                )
            elif self.path == "/api/status":
                self._json(200, {"session": self._session()})
            else:
                self._json(404, {"detail": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            state.calls.append(("POST", self.path))
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._json(400, {"detail": "bad json"})
                return

            if self.path == "/api/simulate":
                state.last_payload = payload
                if state.fail_simulate_with:
                    self._json(state.fail_simulate_with, {"detail": "引擎内部错误"})
                    return
                if not state.devices:
                    self._json(409, {"detail": "未检测到 USB 连接的 iPhone。"})
                    return
                state.session_state = "active"
                self._json(200, {"session": self._session()})
            elif self.path == "/api/stop":
                state.session_state = "idle"
                self._json(200, {"session": self._session()})
            else:
                self._json(404, {"detail": "not found"})

    return Handler


@pytest.fixture()
def fake_engine():
    """启动假引擎，返回 (state, base_url)。"""
    state = FakeEngineState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield state, f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
