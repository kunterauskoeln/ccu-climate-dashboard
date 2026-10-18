"""HmIPServer XML-RPC client (port 2010).

The only interface that reads and writes HmIP profiles / MASTER paramsets and
executes real device commands. Values come back natively typed (unlike the
JSON-RPC path, which stringifies everything).
"""
from __future__ import annotations

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
        self._proxy = xmlrpc.client.ServerProxy(
            f"http://{host}:{port}",
            transport=_TimeoutTransport(timeout),
            allow_none=True,
        )

    def _call(self, method: str, *args: object) -> object:
        try:
            return getattr(self._proxy, method)(*args)
        except xmlrpc.client.Fault as exc:
            raise CcuError(f"{method}{args!r}: {exc.faultString}") from exc
        except (xmlrpc.client.ProtocolError, OSError) as exc:
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
