"""Raw device inventory (settings screen)."""
from __future__ import annotations

from fastapi import APIRouter

from app.deps import get_jsonrpc
from app.schemas import DeviceInfo

router = APIRouter(tags=["devices"])


@router.get("/devices", response_model=list[DeviceInfo])
def list_devices():
    devices = get_jsonrpc().list_devices()
    return [
        DeviceInfo(
            id=dev.get("address"),
            name=dev.get("name"),
            address=dev.get("address"),
            type=dev.get("type"),
            interface=dev.get("interface"),
        )
        for dev in devices
        if dev.get("type") != "HmIP-HEATING"
    ]
