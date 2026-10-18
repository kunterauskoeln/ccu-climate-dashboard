"""Export and import of everything the app itself stores (not the CCU's own data).

One JSON document: heating/cooling profile sets, profile names, the valve
channel mapping, the schedule of the automatic heating/cooling switch and the
change history. The CCU credentials (backend/.env)
are deliberately not part of it -- an export file gets copied around.

Import is a dry run unless ``?apply=true``: the document is checked
completely (see services.backup_data) and the result lists every error and
warning. Applying writes a copy of the current state (``vor-import-….json`` in
the data directory) first, then replaces the data, clears the change history
and transfers the active mode's plans to the thermostats in the background.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.deps import get_device_map, get_xmlrpc, valve_channels_path
from app.services import auto_backup, backup_data, climate_schedule, profile_transfer
from app.services.ccu import climate
from app.services.ccu.errors import CcuBusy, CcuError
from app.services.ccu.mapping import load_valve_channels, save_valve_channels

router = APIRouter(tags=["backup"])

log = logging.getLogger(__name__)


@dataclass
class ImportResult:
    valid: bool
    applied: bool
    errors: list[str]
    warnings: list[str]
    rooms: int
    profiles: int
    names: int
    valve_rooms: int
    schedule: str  # "replace" | "clear" | "keep"
    backup_file: str | None = None
    transfer_started: bool = False


@router.get("/export")
def export_data():
    body = backup_data.build_export(load_valve_channels(valve_channels_path()))
    filename = f"ccu-export-{datetime.now(UTC):%Y-%m-%d}.json"
    return JSONResponse(
        body, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def _known_rooms() -> list[str] | None:
    try:
        return get_device_map().get().room_names
    except CcuError:
        log.warning("import check: CCU rooms not available", exc_info=True)
        return None


@router.post("/import", response_model=ImportResult)
def import_data(doc: dict = Body(...), apply: bool = False):  # noqa: B008
    checked = backup_data.check(doc, _known_rooms())
    result = ImportResult(
        valid=checked.valid, applied=False, errors=checked.errors,
        warnings=checked.warnings, rooms=checked.rooms, profiles=checked.profiles,
        names=checked.names, valve_rooms=checked.valve_rooms, schedule=checked.schedule,
    )
    if not apply or not checked.valid:
        return result
    if profile_transfer.is_running():
        raise CcuBusy("Eine Profilübertragung läuft noch – bitte kurz warten.")

    valve_path = valve_channels_path()
    result.backup_file = backup_data.save_pre_import_backup(load_valve_channels(valve_path))
    backup_data.apply(doc, checked)
    if valve_path:
        save_valve_channels(doc["valve_channels"], valve_path)
        get_device_map().set_valve_channels(doc["valve_channels"])
    else:
        result.warnings.append("Die Ventil-Zuordnung wurde nicht gespeichert "
                               "(VALVE_CHANNELS_FILE ist nicht gesetzt).")
    result.applied = True

    try:
        device_map = get_device_map().get()
        cooling = climate.get_cooling(get_xmlrpc(), device_map.actuator_channel)
        profile_transfer.start(device_map, cooling)
        result.transfer_started = True
    except CcuError:
        log.warning("import: could not start the transfer to the thermostats", exc_info=True)
        result.warnings.append("Die CCU war nicht erreichbar – die Profile werden erst mit "
                               "„Jetzt übertragen“ auf die Thermostate geschrieben.")
    return result


@dataclass
class BackupList:
    files: list[auto_backup.BackupFile]
    hour: int               # automatic backup runs after this hour (local time)
    keep: int               # number of automatic backups kept
    last_error: str | None  # last failure of the automatic backup, if any


@router.get("/backups", response_model=BackupList)
def list_backups():
    """Automatic daily backups and the copies left by imports, newest first."""
    return BackupList(files=auto_backup.list_files(), hour=auto_backup.hour(),
                      keep=auto_backup.keep(), last_error=auto_backup.last_error())


@router.post("/backups", response_model=BackupList)
def backup_now():
    """Write today's automatic backup right away (replaces today's file)."""
    today = datetime.now(climate_schedule.tz()).strftime("%Y-%m-%d")
    auto_backup.write_now(load_valve_channels(valve_channels_path()), today)
    return list_backups()


@router.get("/backups/{name}")
def download_backup(name: str):
    path = auto_backup.path_of(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Sicherung nicht gefunden")
    return FileResponse(path, media_type="application/json", filename=name)
