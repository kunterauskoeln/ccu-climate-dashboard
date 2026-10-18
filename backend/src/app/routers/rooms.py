"""Room status + partial updates."""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.deps import get_device_map, get_jsonrpc, get_xmlrpc
from app.schemas import RoomPatch
from app.services import profile_sets, profile_transfer
from app.services.ccu import climate
from app.services.ccu import profiles as prof
from app.services.ccu.errors import CcuError, CcuValidationError
from app.services.ccu.state import RoomState, read_state

log = logging.getLogger(__name__)

router = APIRouter(prefix="/rooms", tags=["rooms"])

# ACTIVE_PROFILE has no confirmation at the XML-RPC level, unlike every other
# write here -- an unconfirmed switch that silently doesn't land would get
# "corrected" back into the store as the new baseline on the next real mode
# switch (save_active_profiles captures whatever the device actually has).
_ACTIVE_PROFILE_TIMEOUT = 8.0
_ACTIVE_PROFILE_POLL = 1.0


@router.get("", response_model=list[RoomState])
def list_rooms():
    device_map = get_device_map().get()
    xmlrpc, jsonrpc = get_xmlrpc(), get_jsonrpc()
    out: list[RoomState] = []
    for name in device_map.room_names:
        try:
            out.append(read_state(
                xmlrpc, jsonrpc, device_map.rooms[name], full=False, valve=True,
            ))
        except CcuError:
            continue  # skip a momentarily failing room
    return out


def _start_profile_sync(xmlrpc, room: str, room_devices, profile: int) -> bool:
    """True when a background job took over (schedule differs from the device).
    Raises CcuBusy if another transfer is running."""
    try:
        device_map = get_device_map().get()
        cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
        plan = profile_transfer.plan_profile_switch(xmlrpc, room, room_devices, profile, cooling)
    except Exception:
        log.warning("%s: could not compare P%s with the stored schedule; switching directly",
                    room, profile, exc_info=True)
        return False
    if not plan:
        return False
    profile_transfer.start_profile_switch(room, room_devices.wth_address, profile, cooling, plan)
    return True


def _switch_profile_now(xmlrpc, room: str, wth: str, profile: int) -> None:
    confirmed = prof.set_active_profile_confirmed(
        xmlrpc, wth, profile,
        timeout=_ACTIVE_PROFILE_TIMEOUT, poll=_ACTIVE_PROFILE_POLL,
    )
    if not confirmed:
        raise CcuError(f"profile P{profile} was not confirmed active")
    try:
        device_map = get_device_map().get()
        cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
        profile_sets.put_active_profile(room, cooling, profile)
    except Exception:
        # The device switch is confirmed; only remembering it failed. Don't fail
        # the request, but say so: the store's baseline for this mode is now stale.
        log.warning("%s: could not remember active profile P%s in the store",
                    room, profile, exc_info=True)


@router.get("/{room}", response_model=RoomState)
def get_room(room: str):
    room_devices = get_device_map().get().room(room)
    return read_state(get_xmlrpc(), get_jsonrpc(), room_devices, full=True)


@router.patch("/{room}", response_model=RoomState)
def patch_room(room: str, patch: RoomPatch):
    if patch.is_empty():
        raise CcuValidationError("patch body has no fields")

    room_devices = get_device_map().get().room(room)
    xmlrpc = get_xmlrpc()
    wth = room_devices.wth_address

    # mode before setpoint: writing a setpoint implicitly forces MANU, so a
    # combined {mode: AUTO, setpoint: ...} would otherwise contradict itself.
    if patch.mode is not None:
        prof.set_mode(xmlrpc, wth, patch.mode)
    if patch.active_profile is not None:
        # If the stored schedule of that profile differs from what's on the
        # thermostat, a background job writes it first and switches afterwards.
        if not _start_profile_sync(xmlrpc, room, room_devices, patch.active_profile):
            _switch_profile_now(xmlrpc, room, wth, patch.active_profile)
    if patch.boost is not None:
        prof.set_boost(xmlrpc, wth, patch.boost)
    if patch.setpoint is not None:
        prof.set_setpoint(xmlrpc, wth, patch.setpoint)

    return read_state(xmlrpc, get_jsonrpc(), room_devices, full=True)
