"""Switch several rooms to given profile slots ("Wohnung", Abwesenheit).

:func:`plan` decides per room what has to happen -- nothing (already on its
target), or the stored plan days that differ from the thermostat followed by
the ACTIVE_PROFILE switch -- within a write budget; rooms over the budget are
deferred. :func:`start` hands the result to the background transfer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import profile_transfer
from .ccu import profiles as prof
from .ccu.mapping import DeviceMap


@dataclass
class Plan:
    rooms: list[profile_transfer.RoomSwitch] = field(default_factory=list)
    skipped: int = 0                               # already on their target
    deferred: list[str] = field(default_factory=list)   # over the write budget
    current: dict[str, int | None] = field(default_factory=dict)  # profile before


def plan(xmlrpc, device_map: DeviceMap, targets: dict[str, int], cooling: bool,
         *, budget: int | None = None) -> Plan:
    if budget is None:
        budget = profile_transfer.MAX_APARTMENT_DAYS  # read at call time (tests patch it)
    result = Plan()
    for name in device_map.room_names:
        if name not in targets:
            continue
        room_devices = device_map.room(name)
        current = prof.get_active_profile(xmlrpc, room_devices.wth_address)
        result.current[name] = current
        target = targets[name]
        if current == target:
            result.skipped += 1
            continue
        days = profile_transfer.plan_profile_switch(xmlrpc, name, room_devices, target, cooling)
        if len(days) > budget:
            result.deferred.append(f"{name} ({len(days)} Tage)")
            continue
        budget -= len(days)
        result.rooms.append(profile_transfer.RoomSwitch(
            name, room_devices.wth_address, days, profile=target))
    return result


def start(the_plan: Plan, profile: int, cooling: bool, *, label: str | None = None) -> bool:
    """Run the plan in the background. False if there was nothing to switch."""
    if not the_plan.rooms:
        return False
    profile_transfer.start_apartment_switch(
        profile, cooling, the_plan.rooms, the_plan.deferred, label=label)
    return True
