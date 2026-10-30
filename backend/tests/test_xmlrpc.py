"""XmlRpcClient: one proxy per thread, broken connections become CcuUnreachable."""
import http.client
import threading

import pytest

from app.services.ccu import xmlrpc
from app.services.ccu.errors import CcuUnreachable


def test_each_thread_gets_its_own_proxy():
    client = xmlrpc.XmlRpcClient("ccu")
    seen = []

    def grab():
        seen.append(client._proxy)
        seen.append(client._proxy)  # stable within a thread

    threads = [threading.Thread(target=grab) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({id(p) for p in seen}) == 3
    assert seen[0] is seen[1]


def test_http_state_error_is_unreachable_and_drops_the_proxy():
    client = xmlrpc.XmlRpcClient("ccu")

    class Broken:
        def __getattr__(self, name):
            def call(*args):
                raise http.client.CannotSendRequest("Request-sent")
            return call

    client._local.proxy = Broken()
    with pytest.raises(CcuUnreachable):
        client.get_paramset("WTH:1", "VALUES")
    assert client._local.proxy is None
