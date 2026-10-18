"""Heating profiles: read P1..P6, edit one day at a time.

Every endpoint takes an optional ``?mode=heating|cooling`` query parameter
(omitted: the mode the system is running).

Only the profile that is **active on the thermostat in the running mode** is
read and written on the device ("live"). Every other profile -- the inactive
mode's, but also the other five slots of the running mode -- is read and
written in the JSON store: that is the plan that gets written onto the
thermostat when a room switches to it (plan first, then the switch). The
thermostat's own table for those slots may hold anything (the WTH-1 shares
one table between heating and cooling), so showing it would mislead, and
editing on top of it would put that stale content into the store.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.deps import get_device_map, get_jsonrpc, get_xmlrpc
from app.schemas import BlockClear, BlockEdit, ProfileCopy, ProfilesResponse
from app.services import change_history, climate_profiles, profile_sets
from app.services.ccu import climate, schedule
from app.services.ccu import profiles as prof
from app.services.ccu.errors import CcuValidationError
from app.services.ccu.profiles import WeekProfile

log = logging.getLogger(__name__)

router = APIRouter(prefix="/rooms/{room}/profiles", tags=["profiles"])


def _is_live(xmlrpc, room_devices, is_active: bool, profile: int) -> bool:
    """True if *profile* is what the thermostat runs right now (active mode and
    ACTIVE_PROFILE). An unreadable ACTIVE_PROFILE counts as live, the old
    behaviour, rather than guessing at the store."""
    if not is_active:
        return False
    active = prof.get_active_profile(xmlrpc, room_devices.wth_address)
    return active is None or active == profile


def _ensure_seeded(xmlrpc, room: str, room_devices) -> None:
    """A room whose store is still empty gets it filled from the device first."""
    if profile_sets.get_mode(room, False) or profile_sets.get_mode(room, True):
        return
    climate_profiles.seed_room_if_empty(xmlrpc, room, room_devices.wth_address)


def _mode_context(room: str, mode: str | None):
    """Resolve a request's ``?mode=`` against the room and the system's
    current mode. Returns ``(cooling, is_active, room_devices, xmlrpc)`` --
    ``is_active`` tells the endpoint whether to hit the device (the requested
    mode matches what's currently running) or the store (it doesn't)."""
    device_map = get_device_map().get()
    room_devices = device_map.room(room)
    xmlrpc = get_xmlrpc()
    system_cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
    if mode is None:
        cooling = system_cooling
    elif mode in ("heating", "cooling"):
        cooling = mode == "cooling"
    else:
        raise CcuValidationError(f"mode must be 'heating' or 'cooling', got {mode!r}")
    return cooling, cooling == system_cooling, room_devices, xmlrpc


_DE_DAYS = {
    "MONDAY": "Montag", "TUESDAY": "Dienstag", "WEDNESDAY": "Mittwoch",
    "THURSDAY": "Donnerstag", "FRIDAY": "Freitag", "SATURDAY": "Samstag",
    "SUNDAY": "Sonntag",
}


def _de_day(day: str) -> str:
    return _DE_DAYS.get(day.upper(), day)


def _with_mirror(room: str, profile: int, summary: str, run):
    """Phase 2b glue around a *device* profile edit:

    1. seed both heating/cooling sets from the *pristine* device (first time only)
    2. remember the profile's state before the edit, for the change history
    3. run the edit (device write + read-back) -- errors propagate
    4. mirror its result into the currently active mode's set, and record the
       edit in the change history (unless it changed nothing)

    Everything but step 3 is best-effort: it must never turn a successful
    device write into a failed request.
    """
    cooling: bool | None = None
    before = None
    try:
        device_map = get_device_map().get()
        xmlrpc = get_xmlrpc()
        cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
        room_devices = device_map.room(room)
        climate_profiles.seed_room_if_empty(xmlrpc, room, room_devices.wth_address)
        before = climate_profiles.week_to_days(
            prof.read_profile(xmlrpc, room_devices.wth_address, profile)
        )
    except Exception:
        log.warning("%s: could not seed the profile store / read P%s before an edit",
                    room, profile, exc_info=True)

    week = run()

    if cooling is not None:
        try:
            climate_profiles.remember_edit(room, cooling, week)
        except Exception:
            # Device write succeeded but the store missed it: the next mode switch
            # would restore stale data for this profile.
            log.warning("%s: device edit not mirrored into the profile store", room,
                        exc_info=True)
        if before is not None and before != climate_profiles.week_to_days(week):
            try:
                change_history.record_profile(room, cooling, profile, before, summary)
            except Exception:
                log.warning("%s: edit of P%s not recorded in the change history", room,
                            profile, exc_info=True)
    return week


@router.get("", response_model=ProfilesResponse)
def list_profiles(room: str, mode: str | None = None):
    cooling, is_active, room_devices, xmlrpc = _mode_context(room, mode)
    if is_active:
        active = prof.get_active_profile(xmlrpc, room_devices.wth_address)
        if active is None:
            return ProfilesResponse(
                active=None, profiles=prof.read_all_profiles(xmlrpc, room_devices.wth_address))
        _ensure_seeded(xmlrpc, room, room_devices)
        profiles = climate_profiles.read_all_profiles_from_store(room, cooling)
        profiles[active] = prof.read_profile(xmlrpc, room_devices.wth_address, active)
        return ProfilesResponse(active=active, profiles=profiles)
    return ProfilesResponse(
        active=profile_sets.get_active_profile(room, cooling),
        profiles=climate_profiles.read_all_profiles_from_store(room, cooling),
    )


@router.get("/{profile}", response_model=WeekProfile)
def get_profile(room: str, profile: int, mode: str | None = None):
    cooling, is_active, room_devices, xmlrpc = _mode_context(room, mode)
    if _is_live(xmlrpc, room_devices, is_active, profile):
        return prof.read_profile(xmlrpc, room_devices.wth_address, profile)
    if is_active:
        _ensure_seeded(xmlrpc, room, room_devices)
    if profile not in schedule.PROFILE_RANGE:
        raise CcuValidationError(f"profile {profile} out of range 1..6")
    stored = profile_sets.get_profile(room, cooling, profile) or {}
    return climate_profiles.week_from_store(profile, stored)


@router.post("/{profile}/days/{day}/blocks", response_model=WeekProfile)
def add_or_change_block(room: str, profile: int, day: str, edit: BlockEdit, mode: str | None = None):
    cooling, is_active, room_devices, xmlrpc = _mode_context(room, mode)
    if _is_live(xmlrpc, room_devices, is_active, profile):
        setpoint = f"{edit.setpoint:.1f}".replace(".", ",")
        summary = f"{_de_day(day)}: {edit.start}–{edit.end} auf {setpoint} °C"
        return _with_mirror(room, profile, summary, lambda: prof.edit_range(
            xmlrpc, get_jsonrpc(), room_devices.wth_address, profile, day,
            edit.start, edit.end, edit.setpoint,
        ))
    if is_active:
        _ensure_seeded(xmlrpc, room, room_devices)
    return climate_profiles.edit_range_in_store(
        room, cooling, profile, day, edit.start, edit.end, edit.setpoint,
    )


@router.post("/{profile}/copy", response_model=WeekProfile)
def copy_profile(room: str, profile: int, body: ProfileCopy, mode: str | None = None):
    """Copy this room's profile (all days, or one day) onto another
    profile / room, within the requested mode's data."""
    cooling, is_active, room_devices, xmlrpc = _mode_context(room, mode)
    device_map = get_device_map().get()
    dst_room = body.to_room or room
    dst = device_map.room(dst_room)  # validate it exists either way

    src_live = _is_live(xmlrpc, room_devices, is_active, profile)
    dst_live = _is_live(xmlrpc, dst, is_active, body.to_profile)
    if is_active:
        _ensure_seeded(xmlrpc, room, room_devices)
        _ensure_seeded(xmlrpc, dst_room, dst)

    if dst_live:
        source = f"{room} P{profile}"
        if body.from_day is None:
            summary = f"Ganzes Profil übernommen von {source}"
        else:
            targets = body.to_days if body.to_days is not None else [body.to_day or ""]
            summary = (f"{_de_day(body.from_day)} von {source} kopiert nach "
                       f"{', '.join(_de_day(d) for d in targets)}")
        if src_live:
            return _with_mirror(dst_room, body.to_profile, summary, lambda: prof.copy_profile(
                xmlrpc, get_jsonrpc(),
                room_devices.wth_address, profile, dst.wth_address, body.to_profile,
                from_day=body.from_day, to_day=body.to_day, to_days=body.to_days,
            ))
        # the source lives only in the store: write the stored plan, not the
        # thermostat's (possibly stale) table for that slot
        stored = climate_profiles.days_to_blocklists(
            profile_sets.get_profile(room, cooling, profile) or {})
        if body.from_day is None:
            day_blocks = stored
        else:
            day_targets = body.to_days if body.to_days is not None else (
                [body.to_day] if body.to_day else [])
            if not day_targets:
                raise CcuValidationError("from_day needs a to_day or to_days")
            day_blocks = {d.upper(): stored.get(body.from_day.upper(), []) for d in day_targets}
        if not day_blocks or any(not blocks for blocks in day_blocks.values()):
            raise CcuValidationError(f"P{profile} ist für {room} nicht vollständig gespeichert")
        return _with_mirror(dst_room, body.to_profile, summary, lambda: prof.write_days(
            xmlrpc, get_jsonrpc(), dst.wth_address, body.to_profile, day_blocks,
        ))

    if src_live:
        # the store copy of the running profile follows the device
        climate_profiles.remember_edit(
            room, cooling, prof.read_profile(xmlrpc, room_devices.wth_address, profile))
    return climate_profiles.copy_profile_in_store(
        room, cooling, profile, dst_room, body.to_profile,
        from_day=body.from_day, to_day=body.to_day, to_days=body.to_days,
    )


@router.delete("/{profile}/days/{day}/blocks", response_model=WeekProfile)
def clear_block(room: str, profile: int, day: str, body: BlockClear, mode: str | None = None):
    cooling, is_active, room_devices, xmlrpc = _mode_context(room, mode)
    if _is_live(xmlrpc, room_devices, is_active, profile):
        summary = f"{_de_day(day)}: {body.start}–{body.end} gelöscht"
        return _with_mirror(room, profile, summary, lambda: prof.clear_range(
            xmlrpc, get_jsonrpc(), room_devices.wth_address, profile, day,
            body.start, body.end,
        ))
    if is_active:
        _ensure_seeded(xmlrpc, room, room_devices)
    return climate_profiles.clear_range_in_store(room, cooling, profile, day, body.start, body.end)
