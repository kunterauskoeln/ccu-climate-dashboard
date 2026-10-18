"""Bridge between the persisted heating/cooling profile sets and the devices.

* every profile edit is mirrored into the store under the *currently active*
  system mode (:func:`remember_edit`)
* on the first edit of a room both of its modes are seeded from the current
  device schedules, so the two sets start identical and independent
  (:func:`seed_room_if_empty`)
* :func:`swap_to` writes a stored set back onto the thermostats, but ONLY the
  days that differ and with pacing + a hard write budget so it can never flood
  the HmIP RF duty cycle. It is deliberately *not* wired into the mode switch
  yet -- see routers/system.py and the Phase 2b notes.
* the *inactive* mode's profiles can be read and edited directly, without ever
  switching the system mode: :func:`read_all_profiles_from_store`,
  :func:`edit_range_in_store`, :func:`clear_range_in_store`,
  :func:`copy_profile_in_store` mirror the ``ccu.profiles`` read/write API but
  operate purely on the JSON store -- no CCU access at all (Phase 2b.2).

Everything here is best-effort: persistence must never turn a successful device
write into a failed request.
"""
from __future__ import annotations

import logging
import time

from . import profile_sets
from .ccu import profiles as prof
from .ccu import schedule
from .ccu.errors import CcuValidationError
from .ccu.mapping import DeviceMap
from .ccu.profiles import TimeBlock, WeekProfile

log = logging.getLogger(__name__)

# Guard rails for swap_to: never write more than this many profile-days in one
# call, and wait between writes so we stay well under the ~1 % RF duty cycle.
_SWAP_MAX_DAYS = 8
_SWAP_PACE_SECONDS = 4.0


def week_to_days(week: WeekProfile) -> profile_sets.Days:
    return {
        day: [
            {"start": b.start, "end": b.end, "setpoint": b.setpoint} for b in blocks
        ]
        for day, blocks in week.days.items()
    }


def days_to_blocklists(days: profile_sets.Days) -> dict[str, list[schedule.Block]]:
    out: dict[str, list[schedule.Block]] = {}
    for day, blocks in days.items():
        out[day.upper()] = [
            schedule.Block(
                schedule.hhmm_to_min(b["start"]),
                schedule.hhmm_to_min(b["end"]),
                float(b["setpoint"]),
            )
            for b in blocks
        ]
    return out


# Fallback base temperature for a day that was never programmed in either
# mode's store -- matches ccu.profiles._day_blocks's fallback for the device
# path (there it prefers the device's own TEMPERATURE_LOWERING; the store has
# no equivalent, so this is the same hardcoded default).
_DEFAULT_BASE_TEMP = 17.0


def week_from_store(profile: int, days: profile_sets.Days) -> WeekProfile:
    return WeekProfile(profile=profile, days={
        d.lower(): [TimeBlock(**block) for block in days.get(d.lower(), [])]
        for d in schedule.DAYS
    })


def _blocks_to_store(blocks: list[schedule.Block]) -> list[dict]:
    return [
        {"start": schedule.min_to_hhmm(b.start), "end": schedule.min_to_hhmm(b.end),
         "setpoint": b.temp}
        for b in blocks
    ]


def _store_day_blocks(room: str, cooling: bool, profile: int, day: str) -> list[schedule.Block]:
    stored = profile_sets.get_profile(room, cooling, profile) or {}
    blocks = days_to_blocklists(stored).get(day.upper(), [])
    if blocks:
        return blocks
    # profile/day never programmed in this mode's store -- seed one all-day
    # block, same idea as the device path's unprogrammed-day handling.
    return [schedule.Block(0, schedule.DAY_MINUTES, _DEFAULT_BASE_TEMP)]


def _apply_store_day(
    room: str, cooling: bool, profile: int, day: str, blocks: list[schedule.Block],
) -> WeekProfile:
    stored = dict(profile_sets.get_profile(room, cooling, profile) or {})
    stored[day.lower()] = _blocks_to_store(blocks)
    profile_sets.put_profile(room, cooling, profile, stored)
    return week_from_store(profile, stored)


def read_all_profiles_from_store(room: str, cooling: bool) -> dict[int, WeekProfile]:
    stored = profile_sets.get_mode(room, cooling)
    return {p: week_from_store(p, stored.get(p, {})) for p in schedule.PROFILE_RANGE}


def edit_range_in_store(
    room: str, cooling: bool, profile: int, day: str,
    start: str, end: str, setpoint: float,
) -> WeekProfile:
    """Store-only equivalent of ``ccu.profiles.edit_range`` -- no CCU access,
    used to edit the *inactive* mode's schedule directly."""
    if not (prof.SETPOINT_MIN <= setpoint <= prof.SETPOINT_MAX):
        raise CcuValidationError(
            f"setpoint {setpoint} outside {prof.SETPOINT_MIN}..{prof.SETPOINT_MAX} C"
        )
    blocks = _store_day_blocks(room, cooling, profile, day)
    try:
        updated = schedule.overlay(
            blocks, schedule.hhmm_to_min(start), schedule.hhmm_to_min(end), setpoint
        )
    except ValueError as exc:
        raise CcuValidationError(str(exc)) from exc
    return _apply_store_day(room, cooling, profile, day, updated)


def clear_range_in_store(
    room: str, cooling: bool, profile: int, day: str, start: str, end: str,
) -> WeekProfile:
    """Store-only equivalent of ``ccu.profiles.clear_range``."""
    blocks = _store_day_blocks(room, cooling, profile, day)
    try:
        updated = schedule.remove_range(
            blocks, schedule.hhmm_to_min(start), schedule.hhmm_to_min(end)
        )
    except ValueError as exc:
        raise CcuValidationError(str(exc)) from exc
    return _apply_store_day(room, cooling, profile, day, updated)


def copy_profile_in_store(
    room: str, cooling: bool, src_profile: int,
    dst_room: str, dst_profile: int,
    *, from_day: str | None = None,
    to_day: str | None = None, to_days: list[str] | None = None,
) -> WeekProfile:
    """Store-only equivalent of ``ccu.profiles.copy_profile``."""
    targets = to_days if to_days is not None else ([to_day] if to_day else None)

    if from_day is None:
        if targets:
            raise CcuValidationError("to_day / to_days require from_day")
        dst_days = {
            d.lower(): _blocks_to_store(_store_day_blocks(room, cooling, src_profile, d))
            for d in schedule.DAYS
        }
    else:
        if not targets:
            raise CcuValidationError("from_day needs a to_day or to_days")
        rendered = _blocks_to_store(_store_day_blocks(room, cooling, src_profile, from_day))
        dst_days = dict(profile_sets.get_profile(dst_room, cooling, dst_profile) or {})
        for target_day in targets:
            dst_days[target_day.lower()] = list(rendered)

    profile_sets.put_profile(dst_room, cooling, dst_profile, dst_days)
    return week_from_store(dst_profile, dst_days)


def remember_edit(room: str, cooling: bool, week: WeekProfile) -> None:
    """Persist a just-written profile under the active mode."""
    try:
        profile_sets.put_profile(room, cooling, week.profile, week_to_days(week))
    except OSError:
        pass


def seed_room_if_empty(xmlrpc, room: str, wth_address: str) -> None:
    """First edit of a room ever: copy its current P1..P6 off the device into
    BOTH modes so heating and cooling start from the same baseline. Bounded to
    a single MASTER read; on any error it logs a warning and does nothing."""
    try:
        if profile_sets.has_mode(room, False) or profile_sets.has_mode(room, True):
            return
        weeks = prof.read_all_profiles(xmlrpc, wth_address)
        as_days = {p: week_to_days(w) for p, w in weeks.items()}
        profile_sets.put_mode(room, False, as_days)
        profile_sets.put_mode(room, True, as_days)
    except Exception:
        log.warning("%s: seeding the profile store from the device failed", room,
                    exc_info=True)


def save_active_profiles(xmlrpc, device_map: DeviceMap, cooling: bool) -> None:
    """Remember each room's currently active profile slot under the mode
    that's about to be left. Call this right before switching away from
    *cooling* -- best-effort, read-only on the devices."""
    for room, room_devices in device_map.rooms.items():
        try:
            active = prof.get_active_profile(xmlrpc, room_devices.wth_address)
            if active is not None:
                profile_sets.put_active_profile(room, cooling, active)
        except Exception:
            log.warning("%s: could not save the active profile before the mode switch",
                        room, exc_info=True)


def restore_active_profiles(
    xmlrpc, device_map: DeviceMap, cooling: bool,
    *, timeout: float = 8.0, poll: float = 1.0,
) -> list[str]:
    """Switch each room back to the profile slot it had the last time it was
    in *cooling* mode, if we've seen that mode before. The WTH-1's single
    ``ACTIVE_PROFILE`` pointer is shared across modes just like the schedules
    -- without this, the profile transfer would write the stored schedule onto
    whichever slot happens to be selected, not necessarily the right one.

    Uses the confirmed (polling) write, since a plain ``set_active_profile``
    has no read-back and can silently not land. Takes up to ~8s per room that
    needs a change -- call this off the request thread. Best-effort: keeps
    trying every room even if one fails, and returns the labels of any room
    whose restore didn't confirm (for the caller to surface, e.g. in
    ``TransferState.errors``)."""
    failures: list[str] = []
    for room, room_devices in device_map.rooms.items():
        wanted = profile_sets.get_active_profile(room, cooling)
        if wanted is None:
            continue
        try:
            confirmed = prof.set_active_profile_confirmed(
                xmlrpc, room_devices.wth_address, wanted, timeout=timeout, poll=poll
            )
            if not confirmed:
                failures.append(f"{room}: profile P{wanted} not confirmed active")
        except Exception as exc:
            failures.append(f"{room}: {exc}")
    return failures


def snapshot(xmlrpc, device_map: DeviceMap, cooling: bool) -> None:
    """Copy every room's P1..P6 off the devices into the store for one mode.
    Read-only on the devices (no duty-cycle cost)."""
    for room, room_devices in device_map.rooms.items():
        try:
            weeks = prof.read_all_profiles(xmlrpc, room_devices.wth_address)
            profile_sets.put_mode(
                room, cooling, {p: week_to_days(w) for p, w in weeks.items()}
            )
        except Exception:
            log.warning("%s: snapshot of device profiles failed", room, exc_info=True)


def swap_to(
    xmlrpc, jsonrpc, device_map: DeviceMap, cooling: bool,
    *, max_days: int = _SWAP_MAX_DAYS, pace_seconds: float = _SWAP_PACE_SECONDS,
) -> dict:
    """Write the stored set for *cooling* onto every thermostat, one profile at
    a time and only the days whose MASTER keys differ. Paced, and capped at
    *max_days* profile-days total -- anything beyond that is reported under
    ``"deferred"`` rather than written, so a large divergence can never hang
    the caller or flood the RF duty cycle.

    NOTE: not currently invoked on the mode switch; kept for the deliberate,
    backgrounded "apply set to thermostats" action (Phase 2b, still to come).
    """
    report: dict = {"written": {}, "days": 0, "deferred": [], "errors": []}
    budget = max_days
    for room, room_devices in device_map.rooms.items():
        stored = profile_sets.get_mode(room, cooling)
        if not stored:
            continue
        try:
            master = xmlrpc.get_paramset(room_devices.thermostat_channel, "MASTER")
        except Exception as exc:
            report["errors"].append(f"{room}: {exc}")
            continue
        for profile, days in sorted(stored.items()):
            diff = {
                day: blocks
                for day, blocks in days_to_blocklists(days).items()
                if prof.day_differs(master, blocks, profile, day)
            }
            if not diff:
                continue
            if len(diff) > budget:
                report["deferred"].append(f"{room} P{profile} ({len(diff)}d)")
                continue
            try:
                if report["days"] and pace_seconds:
                    time.sleep(pace_seconds)
                prof.write_days(
                    xmlrpc, jsonrpc, room_devices.wth_address, profile, diff
                )
                budget -= len(diff)
                report["days"] += len(diff)
                report["written"].setdefault(room, []).append(profile)
            except Exception as exc:
                report["errors"].append(f"{room} P{profile}: {exc}")
    return report
