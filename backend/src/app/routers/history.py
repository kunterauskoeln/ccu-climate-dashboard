"""Change history: list recorded changes, undo everything back to one of them.

See ``app.services.change_history`` for what gets recorded. Undoing puts
profile names back immediately; profiles go back through the same paced
background writer as every other thermostat write (``profile_transfer``),
and the store is re-mirrored from the thermostats afterwards. Entries are
removed only once everything they describe is really back -- a failed or
partial run keeps them, and resetting to the same entry again writes what's
still missing.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from app.deps import get_device_map, get_xmlrpc
from app.schemas import HistoryEntry, RestoreResult
from app.services import (
    change_history,
    climate_profiles,
    profile_names,
    profile_sets,
    profile_transfer,
)
from app.services.ccu import climate
from app.services.ccu import profiles as prof
from app.services.ccu.errors import CcuBusy, CcuValidationError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryEntry])
def list_history():
    """Recorded changes, newest first."""
    return [
        HistoryEntry(
            id=e["id"], at=e["at"], kind=e["kind"], mode=e.get("mode"),
            room=e.get("room"), profile=int(e["profile"]), summary=e["summary"],
        )
        for e in reversed(change_history.entries())
    ]


@router.post("/{entry_id}/restore", response_model=RestoreResult)
def restore(entry_id: str):
    """Undo *entry_id* and every newer change."""
    if profile_transfer.is_running():
        raise CcuBusy("Eine Profilübertragung läuft noch – bitte kurz warten.")
    undone = change_history.entries_from(entry_id)
    if not undone:
        raise CcuValidationError("Diesen Eintrag gibt es nicht mehr – bitte die Liste neu laden.")
    ids = {e["id"] for e in undone}
    names = change_history.name_targets(undone)
    targets = change_history.profile_targets(undone)

    if not targets:
        profile_names.restore(names)
        change_history.remove_ids(ids)
        return RestoreResult(names=len(names), profiles=0, days=0, deferred=0, background=False)

    device_map = get_device_map().get()
    xmlrpc = get_xmlrpc()
    cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
    if any(mode != profile_sets.mode_key(cooling) for (_room, mode, _p) in targets):
        # entries are cleared on every switch, so this only happens if that failed
        raise CcuValidationError(
            "Diese Änderungen gehören zum anderen Modus (Heizen/Kühlen) und lassen sich "
            "nicht mehr zurücksetzen."
        )
    keys = [
        (room, device_map.room(room), profile, days)
        for (room, _mode, profile), days in targets.items()
    ]
    plan = []
    for room, room_devices, profile, days in keys:
        plan.extend(profile_transfer.plan_days(xmlrpc, room, room_devices, profile, days))

    def finish(client, complete: bool) -> None:
        # Keep the store in step with whatever is on the thermostats now --
        # also after a partial run, so a later mode switch can't bring back
        # a state the device no longer has.
        for room, room_devices, profile, _days in keys:
            try:
                week = prof.read_profile(client, room_devices.wth_address, profile)
                climate_profiles.remember_edit(room, cooling, week)
            except Exception:
                log.warning("%s: P%s not re-mirrored after reset", room, profile, exc_info=True)
        if complete:
            change_history.remove_ids(ids)

    if not plan:
        # thermostats already hold the earlier state (e.g. a no-op in between)
        profile_names.restore(names)
        finish(xmlrpc, True)
        return RestoreResult(names=len(names), profiles=len(keys), days=0, deferred=0,
                             background=False)

    deferred = profile_transfer.start_restore(plan, cooling, finish)
    profile_names.restore(names)
    return RestoreResult(
        names=len(names), profiles=len(keys), days=len(plan) - deferred,
        deferred=deferred, background=True,
    )
