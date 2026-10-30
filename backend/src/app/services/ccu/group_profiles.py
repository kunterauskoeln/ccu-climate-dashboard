"""Compare a room's heating group (``VirtualDevices`` ``INTxxxxxxx:1``) with its
wall thermostat.

The app writes profiles to the thermostat only, so the group's own copy can go
stale. The group still hands its setpoint to its members, so a stale group plan
shows up as a thermostat that ignores its own schedule. Everything here only
reads; the comparison itself is pure.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import schedule

GROUP_INTERFACE = "VirtualDevices"


@dataclass(frozen=True)
class DayDiff:
    profile: int
    day: str  # "MONDAY".."SUNDAY"
    device: list[schedule.Block]
    group: list[schedule.Block]


def has_profiles(master: dict) -> bool:
    return any(key.startswith("P1_ENDTIME_") for key in master)


def read_group_master(jsonrpc, group_address: str) -> tuple[str, dict]:
    """MASTER of the group, from the channel or – failing that – the device
    root. Returns ``(address_used, paramset)``; the paramset is the last one
    tried when neither holds profile keys, so callers can show what is there."""
    master: dict = {}
    address = f"{group_address}:1"
    for address in (f"{group_address}:1", group_address):
        master = jsonrpc.get_paramset(GROUP_INTERFACE, address, "MASTER")
        if has_profiles(master):
            break
    return address, master


def _same(a: list[schedule.Block], b: list[schedule.Block]) -> bool:
    if len(a) != len(b):
        return False
    return all(
        x.start == y.start and x.end == y.end and abs(x.temp - y.temp) < 0.05
        for x, y in zip(a, b, strict=True)
    )


def diff_profiles(device_master: dict, group_master: dict) -> list[DayDiff]:
    """Every profile/day whose block list differs between device and group."""
    out: list[DayDiff] = []
    for profile in schedule.PROFILE_RANGE:
        for day in schedule.DAYS:
            dev = schedule.blocks_from_master(device_master, profile, day)
            grp = schedule.blocks_from_master(group_master, profile, day)
            if not _same(dev, grp):
                out.append(DayDiff(profile, day, dev, grp))
    return out


def setpoint_at(blocks: list[schedule.Block], minute: int) -> float | None:
    for block in blocks:
        if block.start <= minute < block.end:
            return block.temp
    return None


def describe(blocks: list[schedule.Block]) -> str:
    if not blocks:
        return "(nicht programmiert)"
    return ", ".join(
        f"{schedule.min_to_hhmm(b.start)}–{schedule.min_to_hhmm(b.end)} {b.temp:g}"
        for b in blocks
    )
