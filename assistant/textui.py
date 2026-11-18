"""终端输出的最小公共格式。

单独抽出来是因为 ``cli`` 与 ``wizard`` 都要用同一套分节线、状态标记，
而这些格式一旦不一致，用户会以为是两个不同工具的输出。
"""

from __future__ import annotations

WIDTH = 52


def section(title: str) -> None:
    print()
    print(f"── {title} " + "─" * max(0, WIDTH - len(title)))


def blank() -> None:
    print()


def line(text: str = "") -> None:
    print(text)


def bullet(text: str) -> None:
    print(f"  - {text}")


def numbered(index: int, text: str) -> None:
    print(f"  {index}. {text}")


def checkbox(text: str) -> None:
    print(f"  [ ] {text}")


def caption(text: str) -> None:
    """以 ※ 开头的强制提示，用于不可忽略的边界声明。"""
    print(f"※ {text}")


def ok_marker(flag: bool | None) -> str:
    if flag is True:
        return "[通过]"
    if flag is False:
        return "[阻断]"
    return "[未知]"
