"""Compare a room's heating group (``VirtualDevices`` ``INTxxxxxxx:1``) with its
wall thermostat.

The app writes profiles to the thermostat only, so the group's own copy can go
stale; saving the group in the CCU WebUI would push that stale plan onto the
devices. Everything here only reads except :func:`write_group_days`; the
comparison itself is pure.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from . import schedule
from .errors import CcuError, CcuValidationError
from .profiles import _mismatches, _typed_set

GROUP_INTERFACE = "VirtualDevices"

# Like the thermostat MASTER write: the CCU answers before the value has
# settled, so poll the read-back.
_WRITE_SETTLE_SECONDS = 1.5
_CONFIRM_POLL_SECONDS = 2.0
_CONFIRM_TIMEOUT_SECONDS = 25.0


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


def write_group_days(
    jsonrpc, group_master_address: str, profile: int,
    day_blocks: dict[str, list[schedule.Block]],
    *, timeout: float = _CONFIRM_TIMEOUT_SECONDS,
) -> None:
    """Write whole days of one profile into the group MASTER (one putParamset
    per day, same typed format as the thermostat) and poll the read-back.
    *group_master_address* is the address :func:`read_group_master` found the
    profiles on. Raises :class:`CcuError` if the group does not confirm."""
    try:
        per_day = {
            day.upper(): schedule.master_from_blocks(blocks, profile, day.upper())
            for day, blocks in day_blocks.items()
        }
    except ValueError as exc:
        raise CcuValidationError(str(exc)) from exc

    for sub in per_day.values():
        jsonrpc.put_paramset(group_master_address, "MASTER", _typed_set(sub),
                             interface=GROUP_INTERFACE)

    want = {name: value for sub in per_day.values() for name, value in sub.items()}
    deadline = time.monotonic() + timeout
    time.sleep(_WRITE_SETTLE_SECONDS)
    while True:
        fresh = jsonrpc.get_paramset(GROUP_INTERFACE, group_master_address, "MASTER")
        bad = _mismatches(fresh, want)
        if not bad:
            return
        if time.monotonic() >= deadline:
            raise CcuError(
                f"group write not confirmed for P{profile}: {len(bad)} value(s) "
                f"still off, e.g. {bad[0]} (wanted {want[bad[0]]}, "
                f"group {fresh.get(bad[0])!r})"
            )
        time.sleep(_CONFIRM_POLL_SECONDS)


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
