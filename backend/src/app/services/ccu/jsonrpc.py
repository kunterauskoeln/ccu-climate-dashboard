"""ReGaHss JSON-RPC client (``http://<host>/api/homematic.cgi``).

Used for structure and status reads only: device discovery and the heating
group VALUES. Profiles and every write go through :mod:`app.services.ccu.xmlrpc`.

Synchronous on purpose – it plugs into the current sync FastAPI handlers.
Moving to async httpx is a Phase 2 concern bundled with the API rewrite.
"""
from __future__ import annotations

import time

import requests

from .errors import CcuError, CcuMethodError, CcuUnreachable

# CCU sessions live ~600 s; renew a bit early.
_SESSION_TTL = 550.0

# JSON-RPC error code for a TCL/script error inside the CCU (deterministic for
# a given method+address, unrelated to the session).
_TCL_ERROR = 601


class JsonRpcClient:
    def __init__(
        self, host: str, username: str, password: str, *, timeout: float = 8.0
    ) -> None:
        self._url = f"http://{host}/api/homematic.cgi"
        self._user = username
        self._password = password
        self._timeout = timeout
        self._session_id: str | None = None
        self._session_deadline = 0.0

    # -- session ----------------------------------------------------------
    def _login(self) -> None:
        session_id = self._post(
            "Session.login",
            {"username": self._user, "password": self._password},
            with_session=False,
        )
        if not isinstance(session_id, str) or not session_id:
            raise CcuError("Session.login: no session id returned")
        self._session_id = session_id
        self._session_deadline = time.monotonic() + _SESSION_TTL

    def _ensure_session(self) -> None:
        if not self._session_id or time.monotonic() >= self._session_deadline:
            self._login()

    def logout(self) -> None:
        if not self._session_id:
            return
        try:
            self._post("Session.logout", {}, with_session=True)
        except CcuError:
            pass
        self._session_id = None

    # -- transport ------------------------------------------------------
    def _post(self, method: str, params: dict, *, with_session: bool) -> object:
        body_params = dict(params)
        if with_session:
            body_params["_session_id_"] = self._session_id
        try:
            response = requests.post(
                self._url,
                json={
                    "method": method,
                    "params": body_params,
                    "id": 1,
                    "jsonrpc": "2.0",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise CcuUnreachable(f"{method}: {exc}") from exc
        except ValueError as exc:
            raise CcuError(f"{method}: invalid JSON in response") from exc

        error = payload.get("error")
        if error:
            code = error.get("code") if isinstance(error, dict) else None
            kind = CcuMethodError if with_session and code == _TCL_ERROR else CcuError
            raise kind(f"{method}: {error}")
        return payload.get("result")

    def call(self, method: str, params: dict | None = None, *, retries: int = 2) -> object:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                self._ensure_session()
                return self._post(method, params or {}, with_session=True)
            except CcuMethodError:
                raise  # valid session, deterministic failure: no retry, keep the session
            except CcuUnreachable as exc:
                last_error = exc
                self._session_id = None  # can't reach the CCU to log out either
                if attempt < retries:
                    time.sleep(0.5)
            except CcuError as exc:
                last_error = exc
                # Release the CCU session slot *before* dropping it. Just forgetting
                # the id leaks one CCU session per retry, and the CCU only allows a
                # handful -> "invalid credentials or too many sessions".
                self.logout()
                if attempt < retries:
                    time.sleep(0.5)
        assert last_error is not None
        raise last_error

    # -- convenience --------------------------------------------------
    def check(self) -> None:
        """Raise :class:`CcuError` unless a session can be obtained."""
        self._ensure_session()

    def list_devices(self) -> list[dict]:
        result = self.call("Device.listAllDetail")
        return result if isinstance(result, list) else []

    def get_paramset(self, interface: str, address: str, key: str) -> dict:
        result = self.call(
            "Interface.getParamset",
            {"interface": interface, "address": address, "paramsetKey": key},
        )
        return result if isinstance(result, dict) else {}

    def put_paramset(
        self,
        address: str,
        paramset_key: str,
        typed_set: list[dict],
        *,
        interface: str = "HmIP-RF",
    ) -> None:
        """Write a paramset via ``Interface.putParamset``.

        ``typed_set`` is a list of ``{"name", "type", "value"}`` – ``type`` must
        be an XML-RPC type name (``"int"``, ``"double"``, ...), ``value`` a str.
        The CCU answers this call with a spurious ``505 "unknown argument or
        value"`` even when the write lands, so that specific error is swallowed
        (the caller verifies with a read-back). One attempt only – no retry, to
        avoid writing three times.
        """
        try:
            self.call(
                "Interface.putParamset",
                {
                    "interface": interface,
                    "address": address,
                    "paramsetKey": paramset_key,
                    "set": typed_set,
                },
                retries=0,
            )
        except CcuError as exc:
            text = str(exc)
            if "505" in text or "unknown argument or value" in text:
                return
            raise
