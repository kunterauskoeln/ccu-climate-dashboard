"""Automatic daily backup of the app's data (export format).

Every night at ``AUTO_BACKUP_HOUR`` (default 3, local time of SCHEDULE_TZ) a
file ``ccu-auto-YYYY-MM-DD.json`` is written to ``data/backups/`` -- the same
document as a manual export, so it can be imported again. The newest
``AUTO_BACKUP_KEEP`` (default 14) are kept, older ones deleted.

A background thread checks every 5 minutes: once the hour has passed and
today's file is missing, it is written. A night with the server off is thus
caught up on the next start.

:func:`list_files` also lists the ``vor-import-…json`` copies an import leaves
in the data directory; :func:`path_of` resolves a listed name to its file and
refuses anything else (no path tricks via the API).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime

from . import backup_data, climate_schedule, profile_sets

log = logging.getLogger(__name__)

_TICK_SECONDS = 300.0
_AUTO = re.compile(r"^ccu-auto-(\d{4}-\d{2}-\d{2})\.json$")
_PRE_IMPORT = re.compile(r"^vor-import-\d{4}-\d{2}-\d{2}-\d{6}\.json$")

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()
_last_error: str | None = None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


def hour() -> int:
    return min(max(_env_int("AUTO_BACKUP_HOUR", 3), 0), 23)


def keep() -> int:
    return max(_env_int("AUTO_BACKUP_KEEP", 14), 1)


def data_dir() -> str:
    return os.path.dirname(profile_sets._PATH) or "."


def backup_dir() -> str:
    return os.path.join(data_dir(), "backups")


def last_error() -> str | None:
    return _last_error


@dataclass
class BackupFile:
    name: str
    kind: str        # "auto" | "vor-import"
    size: int        # bytes
    modified: float  # epoch seconds


def list_files() -> list[BackupFile]:
    """Automatic backups and pre-import copies, newest first."""
    found: list[BackupFile] = []
    for directory, pattern, kind in ((backup_dir(), _AUTO, "auto"),
                                     (data_dir(), _PRE_IMPORT, "vor-import")):
        try:
            names = os.listdir(directory)
        except FileNotFoundError:
            continue
        for name in names:
            if pattern.match(name):
                stat = os.stat(os.path.join(directory, name))
                found.append(BackupFile(name, kind, stat.st_size, stat.st_mtime))
    return sorted(found, key=lambda f: f.modified, reverse=True)


def path_of(name: str) -> str | None:
    """The file behind a listed name, or None for anything else."""
    if _AUTO.match(name):
        path = os.path.join(backup_dir(), name)
    elif _PRE_IMPORT.match(name):
        path = os.path.join(data_dir(), name)
    else:
        return None
    return path if os.path.isfile(path) else None


def write_now(valve_channels: dict[str, list[int]], today: str) -> str:
    """Write (or overwrite) today's automatic backup and prune old ones."""
    os.makedirs(backup_dir(), exist_ok=True)
    name = f"ccu-auto-{today}.json"
    target = os.path.join(backup_dir(), name)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(backup_data.build_export(valve_channels), handle, indent=2, ensure_ascii=False)
    os.replace(tmp, target)  # a half-written file never looks like a backup
    _prune()
    return name


def _prune() -> None:
    autos = sorted((n for n in os.listdir(backup_dir()) if _AUTO.match(n)), reverse=True)
    for name in autos[keep():]:
        try:
            os.remove(os.path.join(backup_dir(), name))
        except OSError:
            log.warning("could not delete old backup %s", name, exc_info=True)


def tick(now: datetime | None = None) -> str | None:
    """Write today's backup if its hour has passed and it is missing.
    Returns the file name written, else None."""
    global _last_error
    now = now or datetime.now(climate_schedule.tz())
    if now.hour < hour():
        return None
    today = now.strftime("%Y-%m-%d")
    with _lock:
        if os.path.exists(os.path.join(backup_dir(), f"ccu-auto-{today}.json")):
            return None
        from ..deps import valve_channels_path
        from .ccu.mapping import load_valve_channels
        try:
            name = write_now(load_valve_channels(valve_channels_path()), today)
        except OSError as exc:
            _last_error = f"{now:%d.%m.%Y %H:%M}: {exc}"
            log.warning("automatic backup failed", exc_info=True)
            return None
        _last_error = None
        log.info("automatic backup written: %s", name)
        return name


def _loop() -> None:
    while True:
        try:
            tick()
        except Exception:
            log.warning("automatic backup round failed", exc_info=True)
        if _stop.wait(_TICK_SECONDS):
            break


def start() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="auto-backup", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
