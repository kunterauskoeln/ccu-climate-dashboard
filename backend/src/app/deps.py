"""Process-wide singletons for the CCU clients and the device map.

Kept deliberately simple (module-level, ``lru_cache``) to match the current
sync request handlers. FastAPI ``Depends`` wiring comes with the Phase 2 API.
"""
from __future__ import annotations

import os
from functools import lru_cache

from app.services.ccu.jsonrpc import JsonRpcClient
from app.services.ccu.mapping import CachedDeviceMap, load_valve_channels
from app.services.ccu.xmlrpc import XmlRpcClient


def _env(name: str) -> str:
    return os.getenv(name, "")


def new_jsonrpc() -> JsonRpcClient:
    """A fresh, uncached client. Use for work that runs off the request thread
    (the background profile transfer) -- the cached singletons are not safe to
    share across threads."""
    return JsonRpcClient(_env("CCU_HOST"), _env("CCU_USERNAME"), _env("CCU_PASSWORD"))


def new_xmlrpc() -> XmlRpcClient:
    return XmlRpcClient(_env("CCU_HOST"))


@lru_cache(maxsize=1)
def get_jsonrpc() -> JsonRpcClient:
    return new_jsonrpc()


@lru_cache(maxsize=1)
def get_xmlrpc() -> XmlRpcClient:
    return new_xmlrpc()


def valve_channels_path() -> str | None:
    """VALVE_CHANNELS_FILE points at the mounted data directory in the compose
    setup; unset (local/dev), load_valve_channels falls back to the shipped
    template next to the source."""
    return _env("VALVE_CHANNELS_FILE") or None


@lru_cache(maxsize=1)
def get_device_map() -> CachedDeviceMap:
    return CachedDeviceMap(
        get_jsonrpc(), valve_channels=load_valve_channels(valve_channels_path())
    )
