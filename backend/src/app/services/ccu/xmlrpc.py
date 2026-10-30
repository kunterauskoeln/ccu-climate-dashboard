"""HmIPServer XML-RPC client (port 2010).

The only interface that reads and writes HmIP profiles / MASTER paramsets and
executes real device commands. Values come back natively typed (unlike the
JSON-RPC path, which stringifies everything).

One client is shared by all request threads, but an ``xmlrpc.client.ServerProxy``
keeps a single keep-alive HTTP connection and is not thread-safe: parallel
requests (a page loads several at once) tripped over each other with
``CannotSendRequest`` / ``ResponseNotReady`` and ended as HTTP 500. So every
thread gets its own proxy.
"""
from __future__ import annotations

import http.client
import threading
import xmlrpc.client

from .errors import CcuError, CcuUnreachable


class _TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout: float) -> None:
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self._timeout
        return connection


class XmlRpcClient:
    def __init__(self, host: str, *, port: int = 2010, timeout: float = 8.0) -> None:
        self._url = f"http://{host}:{port}"
        self._timeout = timeout
        self._local = threading.local()

    @property
    def _proxy(self) -> xmlrpc.client.ServerProxy:
        proxy = getattr(self._local, "proxy", None)
        if proxy is None:
            proxy = xmlrpc.client.ServerProxy(
                self._url, transport=_TimeoutTransport(self._timeout), allow_none=True
            )
            self._local.proxy = proxy
        return proxy

    def _call(self, method: str, *args: object) -> object:
        try:
            return getattr(self._proxy, method)(*args)
        except xmlrpc.client.Fault as exc:
            raise CcuError(f"{method}{args!r}: {exc.faultString}") from exc
        except (xmlrpc.client.ProtocolError, OSError, http.client.HTTPException) as exc:
            # a broken keep-alive connection must not stick to this thread
            self._local.proxy = None
            raise CcuUnreachable(f"{method}: {exc}") from exc

    # -- paramsets ----------------------------------------------------
    def get_paramset(self, address: str, key: str = "VALUES") -> dict:
        result = self._call("getParamset", address, key)
        return result if isinstance(result, dict) else {}

    def put_paramset(self, address: str, key: str, values: dict) -> None:
        self._call("putParamset", address, key, values)

    # -- single values ----------------------------------------------
    def get_value(self, address: str, key: str) -> object:
        return self._call("getValue", address, key)

    def set_value(self, address: str, key: str, value: object) -> None:
        self._call("setValue", address, key, value)
