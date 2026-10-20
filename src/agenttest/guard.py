"""replay 期间的网络守卫（docs/DESIGN.md 第 3 节）。

replay 的意义是"模型输出全部来自 cassette"，所以期间任何真实出网都必须
立刻失败，并指出是哪里发起的。做法是替换 `socket` 的几个出口函数。
"""

from __future__ import annotations

import socket
import traceback

_ORIGINALS: dict[str, object] = {}
_INSTALLED = False
_SOCKET = socket.socket


class NetworkBlockedError(RuntimeError):
    """replay 期间尝试真实出网。"""


def _error(target: str) -> NetworkBlockedError:
    frames = "".join(traceback.format_stack()[:-3])
    return NetworkBlockedError(
        f"NETWORK GUARD: replay 期间禁止真实出网，已拦截 {target}。"
        "replay 必须确定：模型输出只能来自 cassette，任何真实网络调用都会让测试失去意义。"
        f"调用栈：\n{frames}"
    )


def _blocked_connect(self, address, *args, **kwargs):
    if self.family == getattr(socket, "AF_UNIX", object()):
        return _ORIGINALS["connect"](self, address, *args, **kwargs)
    host = address[0] if isinstance(address, tuple) else address
    raise _error(f"socket.connect({host!r})")


def _blocked_connect_ex(self, address, *args, **kwargs):
    if self.family == getattr(socket, "AF_UNIX", object()):
        return _ORIGINALS["connect_ex"](self, address, *args, **kwargs)
    host = address[0] if isinstance(address, tuple) else address
    raise _error(f"socket.connect_ex({host!r})")


def _blocked_create_connection(address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else address
    raise _error(f"socket.create_connection({host!r})")


def _blocked_getaddrinfo(host, *args, **kwargs):
    raise _error(f"socket.getaddrinfo({host!r})")


def install() -> None:
    """装上守卫；重复调用无副作用。"""
    global _INSTALLED
    if _INSTALLED:
        return
    _ORIGINALS["connect"] = _SOCKET.connect
    _ORIGINALS["connect_ex"] = _SOCKET.connect_ex
    _ORIGINALS["create_connection"] = socket.create_connection
    _ORIGINALS["getaddrinfo"] = socket.getaddrinfo
    _SOCKET.connect = _blocked_connect
    _SOCKET.connect_ex = _blocked_connect_ex
    socket.create_connection = _blocked_create_connection
    socket.getaddrinfo = _blocked_getaddrinfo
    _INSTALLED = True


def uninstall() -> None:
    global _INSTALLED
    if not _INSTALLED:
        return
    _SOCKET.connect = _ORIGINALS["connect"]
    _SOCKET.connect_ex = _ORIGINALS["connect_ex"]
    socket.create_connection = _ORIGINALS["create_connection"]
    socket.getaddrinfo = _ORIGINALS["getaddrinfo"]
    _INSTALLED = False


def is_installed() -> bool:
    return _INSTALLED
