"""基于 HTTP 的引擎调用客户端。

为什么不直接 import 旧仓库？

旧项目的 Windows 引擎本身就是一个 FastAPI 服务，已经把这套能力暴露成稳定的
JSON 接口（``/api/health`` ``/api/devices`` ``/api/simulate`` ``/api/stop``）。
所以正确做法是**作为客户端去调用**，而不是把源码复制进来：

* 不复制、不修改旧项目的任何定位协议代码（第二阶段要求）；
* 旧项目保持完全独立，可以单独发版（第二阶段要求）；
* 许可证上只发生「进程间调用」，不产生衍生作品（第二阶段要求）。

同一份客户端同时服务 Windows 与 macOS，平台的差异只在「怎么把引擎叫起来」。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from .base import (
    AdapterError,
    AdapterUnavailable,
    Device,
    EngineStatus,
    Inventory,
    SessionSnapshot,
)

DEFAULT_TIMEOUT = 5.0
# 建立 DVT 隧道可能要几十秒，旧引擎内部超时是 40s，这里留出余量。
START_TIMEOUT = 60.0
STOP_TIMEOUT = 30.0

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def assert_loopback(url: str) -> None:
    """拒绝非本机地址。

    引擎只可能监听本机回环：既避免把设备控制面暴露到局域网，
    也避免用户被诱导把坐标发往远端服务器。
    """
    host = urlparse(url).hostname
    if host not in _LOOPBACK_HOSTS:
        raise AdapterUnavailable(
            f"引擎地址必须是本机回环地址，当前为 {host!r}。",
            hint="请把 --engine-url 设置为 http://127.0.0.1:<端口>。",
        )


class HttpLocationEngine:
    """按统一接口对 HTTP JSON API 做薄封装。

    子类只需要覆写 ``probe``（决定引擎从哪来、怎么启动），
    其余的调用逻辑完全共用。
    """

    name = "http"

    def __init__(self, base_url: str, *, platform: str = "unknown") -> None:
        assert_loopback(base_url)
        self.base_url = base_url.rstrip("/")
        self.platform = platform

    # ---------------------------------------------------------------- 传输

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - 已强制回环
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = _extract_detail(exc)
            raise AdapterError(f"引擎返回 HTTP {exc.code}：{detail}") from exc
        except urllib.error.URLError as exc:
            raise AdapterUnavailable(
                f"无法连接定位引擎 {self.base_url}：{exc.reason}",
                hint="请确认引擎已启动，或先用 probe 自动拉起。",
            ) from exc
        except TimeoutError as exc:
            raise AdapterUnavailable(f"定位引擎响应超时（{timeout:.0f}s）。") from exc

        if not body.strip():
            return {}
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AdapterError("引擎返回了非 JSON 响应，可能命中了其他本地服务。") from exc
        return parsed if isinstance(parsed, dict) else {"data": parsed}

    # ---------------------------------------------------------------- 接口

    def probe(self) -> EngineStatus:
        try:
            health = self._request("GET", "/api/health", timeout=3.0)
        except AdapterError as exc:
            return EngineStatus(
                available=False,
                platform=self.platform,
                engine=self.name,
                endpoint=self.base_url,
                detail=str(exc),
            )
        return EngineStatus(
            available=bool(health.get("ok")),
            platform=self.platform,
            engine=self.name,
            version=str(health.get("version")) if health.get("version") else None,
            endpoint=self.base_url,
            detail="引擎在线",
        )

    def list_devices(self) -> Inventory:
        payload = self._request("GET", "/api/devices")
        raw_devices = payload.get("devices") or []
        devices: list[Device] = []
        for item in raw_devices:
            if not isinstance(item, dict):
                continue
            handle = item.get("udid")
            if not handle:
                continue
            devices.append(
                Device(
                    handle=str(handle),
                    name=item.get("name"),
                    ios_version=item.get("ios_version"),
                    model=item.get("model"),
                )
            )
        return Inventory(
            connected=bool(payload.get("connected")) or bool(devices),
            devices=tuple(devices),
            error=payload.get("error"),
        )

    def start_location(
        self, latitude: float, longitude: float, hold_seconds: int | None
    ) -> SessionSnapshot:
        payload = {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "hold_seconds": hold_seconds,
        }
        response = self._request("POST", "/api/simulate", payload, timeout=START_TIMEOUT)
        return _parse_session(response.get("session"))

    def stop_location(self) -> SessionSnapshot:
        response = self._request("POST", "/api/stop", timeout=STOP_TIMEOUT)
        return _parse_session(response.get("session"))

    def session(self) -> SessionSnapshot:
        response = self._request("GET", "/api/status")
        return _parse_session(response.get("session"))


def _parse_session(raw: Any) -> SessionSnapshot:
    if not isinstance(raw, dict):
        return SessionSnapshot(state="error", error="引擎未返回会话信息")
    state = raw.get("state")
    if state not in ("idle", "connecting", "active", "stopping", "error"):
        state = "error"
    return SessionSnapshot(
        state=state,
        latitude=raw.get("latitude"),
        longitude=raw.get("longitude"),
        remaining=raw.get("remaining"),
        message=str(raw.get("message") or ""),
        error=raw.get("error"),
        # 只有引擎明确进入 active 才认为模拟定位在生效。
        location_active=(state == "active"),
    )


_FIELD_LABELS = {
    "hold_seconds": "会话时长（秒）",
    "latitude": "纬度",
    "longitude": "经度",
    "udid": "设备标识",
}


def _humanize_validation(items: list[Any]) -> str:
    """把 Pydantic 的 422 校验错误翻成用户能读懂的中文。

    引擎原样返回的是英文，形如
    「Input should be less than or equal to 180」，还带着 loc/ctx 结构。
    直接抛给用户既看不懂，也看不出是自己参数的哪一项出的问题。
    """
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        loc = [str(x) for x in (item.get("loc") or []) if str(x) != "body"]
        field = loc[-1] if loc else ""
        label = _FIELD_LABELS.get(field, field or "请求参数")
        ctx = item.get("ctx") or {}
        err_type = str(item.get("type") or "")

        if err_type == "less_than_equal" and "le" in ctx:
            parts.append(f"{label}不能大于 {ctx['le']:g}")
        elif err_type == "greater_than_equal" and "ge" in ctx:
            parts.append(f"{label}不能小于 {ctx['ge']:g}")
        elif err_type == "missing":
            parts.append(f"缺少必填参数：{label}")
        else:
            msg = str(item.get("msg") or "").strip()
            parts.append(f"{label}：{msg}" if msg else label)

    return "；".join(dict.fromkeys(parts))


def _extract_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", "replace")
        parsed = json.loads(body)
    except Exception:  # noqa: BLE001 - 错误详情本身不允许影响主流程
        return f"HTTP {exc.code}"
    if isinstance(parsed, dict):
        detail = parsed.get("detail") or parsed.get("session") or parsed
        # FastAPI 的 422 校验错误是 list[dict]，优先翻译成中文。
        if isinstance(detail, list) and all(isinstance(x, dict) for x in detail):
            readable = _humanize_validation(detail)
            if readable:
                return readable
        return json.dumps(detail, ensure_ascii=False)[:300]
    if isinstance(parsed, list):
        readable = _humanize_validation(parsed)
        if readable:
            return readable
    return str(parsed)[:300]
