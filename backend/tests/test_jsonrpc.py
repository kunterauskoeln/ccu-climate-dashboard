"""JsonRpcClient session handling: no leaked CCU sessions on failing calls."""
import pytest
import requests

from app.services.ccu import jsonrpc
from app.services.ccu.errors import CcuError, CcuMethodError, CcuUnreachable


class FakeCcu:
    """Stands in for requests.post; records the methods and open sessions."""

    def __init__(self, on_call):
        self.on_call = on_call  # method -> payload dict, or raises
        self.methods: list[str] = []
        self.open_sessions: set[str] = set()
        self._n = 0

    def __call__(self, url, json=None, timeout=None):
        method = json["method"]
        self.methods.append(method)
        if method == "Session.login":
            self._n += 1
            sid = f"S{self._n}"
            self.open_sessions.add(sid)
            return self._resp({"result": sid})
        if method == "Session.logout":
            self.open_sessions.discard(json["params"]["_session_id_"])
            return self._resp({"result": True})
        return self._resp(self.on_call(method))

    @staticmethod
    def _resp(payload):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        return R()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(jsonrpc.time, "sleep", lambda s: None)
    return jsonrpc.JsonRpcClient("ccu", "user", "pw")


def _install(monkeypatch, on_call):
    fake = FakeCcu(on_call)
    monkeypatch.setattr(jsonrpc.requests, "post", fake)
    return fake


def test_tcl_error_is_not_retried_and_keeps_its_single_session(client, monkeypatch):
    fake = _install(monkeypatch, lambda m: {"error": {"code": 601, "message": "TCL error"}})
    with pytest.raises(CcuMethodError):
        client.call("Interface.getLinkPeers", {})
    assert fake.methods == ["Session.login", "Interface.getLinkPeers"]
    assert len(fake.open_sessions) == 1


def test_failing_call_logs_out_each_session_it_abandons(client, monkeypatch):
    fake = _install(monkeypatch, lambda m: {"error": {"code": 400, "message": "denied"}})
    with pytest.raises(CcuError):
        client.call("Device.listAllDetail")
    assert fake.methods.count("Session.login") == 3      # 1 try + 2 retries
    assert fake.methods.count("Session.logout") == 3     # every one released
    assert fake.open_sessions == set()                   # nothing left dangling


def test_unreachable_ccu_does_not_try_to_log_out(client, monkeypatch):
    def boom(url, json=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(jsonrpc.requests, "post", boom)
    with pytest.raises(CcuUnreachable):
        client.call("Device.listAllDetail")


def test_parallel_first_calls_open_only_one_session(client, monkeypatch):
    """A page fires several requests at once; they must share one login."""
    import threading

    gate = threading.Barrier(8)
    slow_login = FakeCcu(lambda m: {"result": "ok"})
    original = slow_login.__call__

    def post(url, json=None, timeout=None):
        if json["method"] == "Session.login":
            import time as real_time
            real_time.sleep(0.05)  # widen the race window
        return original(url, json=json, timeout=timeout)

    monkeypatch.setattr(jsonrpc.requests, "post", post)

    def worker():
        gate.wait()
        client.call("Interface.listDevices", {})

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert slow_login.methods.count("Session.login") == 1
    assert len(slow_login.open_sessions) == 1


def test_failed_call_does_not_log_out_a_newer_session(client, monkeypatch):
    fake = _install(monkeypatch, lambda m: {"result": "ok"})
    client.call("Interface.listDevices", {})          # session S1
    client._session_id = "S2"                         # another thread renewed it
    client._drop_session("S1", release=True)
    assert client._session_id == "S2" and "Session.logout" not in fake.methods
