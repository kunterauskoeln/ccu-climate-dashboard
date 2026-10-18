"""Switching the whole system between heating and cooling.

Shared by ``PATCH /system/climate`` and the scheduled switch
(:mod:`climate_schedule`); the lock keeps the two from running at once.
"""
from __future__ import annotations

import logging
import threading

from . import change_history, climate_profiles, profile_transfer
from .ccu import climate
from .ccu.errors import CcuError
from .ccu.mapping import DeviceMap

log = logging.getLogger(__name__)

_lock = threading.Lock()


def switch(xmlrpc, device_map: DeviceMap, cooling: bool) -> bool:
    """Flip the FALMOT to *cooling* (confirmed). If the mode actually changed:
    remember each room's active profile under the outgoing mode first, then
    start the background transfer of the incoming mode's plans and clear the
    profile change history. Returns True if the mode changed."""
    channel = device_map.actuator_channel
    if not channel:
        raise CcuError("no heating actuator (HmIP-FALMOT) found")

    with _lock:
        was_cooling = climate.get_cooling(xmlrpc, channel)
        changing = cooling != was_cooling

        if changing:
            climate_profiles.save_active_profiles(xmlrpc, device_map, was_cooling)

        climate.set_cooling(xmlrpc, channel, cooling)

        if changing:
            profile_transfer.start(device_map, cooling)
            # Profile entries describe the outgoing mode's schedules; undoing them
            # after the switch would write them into the wrong mode. Names are
            # shared by both modes and keep their entries.
            try:
                change_history.clear_profile_entries()
            except Exception:
                log.warning("could not clear the profile change history after a mode switch",
                            exc_info=True)
    return changing
