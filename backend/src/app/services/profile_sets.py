"""Persistent per-room heating and cooling profile sets.

The HmIP-WTH-1 stores only ONE set of six weekly profiles, shared between the
heating and cooling system modes. To give the two modes independent schedules
we keep a full copy of both here and swap the matching set onto the thermostats
whenever the system mode changes (see ``app.services.climate_profiles`` and
``routers/system.py``).

On disk::

    {
      "<room>": {
        "heating": {"1": {"monday": [<block>, ...], ..., "sunday": [...]}, ...},
        "cooling": {"1": {...}, ...},
        "active_profile": {"heating": 2, "cooling": 1}
      }
    }

with ``<block> = {"start": "HH:MM", "end": "HH:MM", "setpoint": <float>}`` and
lowercase weekday keys. A profile missing from a mode means "never captured for
that mode" -- the swap then leaves that profile untouched on the device.

``active_profile`` remembers which profile SLOT (1..6) was selected the last
time the room was in that mode -- the device has only one ``ACTIVE_PROFILE``
pointer, shared across modes just like the schedules themselves, so switching
modes must restore it too (see ``climate_profiles.save_active_profiles`` /
``restore_active_profiles``), or the profile transfer ends up writing the
schedule onto whatever slot happens to be selected instead of the right one.

Not CCU-related: pure JSON persistence, same shape/locking as
``app.services.profile_names``.
"""
from __future__ import annotations

import json
import os
import shutil
import threading

_PATH = os.getenv("PROFILE_SETS_FILE", "/app/app/data/profile_sets.json")
# One-generation rolling backup: whatever was on disk right before the most
# recent write. Also a real (bind-mounted) file, not just in the container, so
# a bad write, a bug, or an --apply with the wrong data never destroys the
# only copy of a real profile set.
_BACKUP_PATH = os.getenv("PROFILE_SETS_BACKUP_FILE", "/app/app/data/profile_sets.backup.json")
_lock = threading.Lock()

HEATING = "heating"
COOLING = "cooling"

Days = dict[str, list[dict]]  # weekday -> ordered block dicts


def mode_key(cooling: bool) -> str:
    return COOLING if cooling else HEATING


def load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        # missing file, unreadable, or a bind mount Docker created as a
        # directory -- treat all of it as "no data yet", never crash a request
        return {}
    return data if isinstance(data, dict) else {}


def _backup_before_write() -> None:
    """Copy whatever is currently on disk to the backup path, before it gets
    overwritten. Best-effort -- must never block or fail the actual save."""
    try:
        if os.path.isfile(_PATH):
            os.makedirs(os.path.dirname(_BACKUP_PATH) or ".", exist_ok=True)
            shutil.copyfile(_PATH, _BACKUP_PATH)
    except OSError:
        pass


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    _backup_before_write()
    # write in place -- _PATH is usually a single-file bind mount, and renaming
    # over a bind mount fails with EBUSY. The lock serialises writers.
    with open(_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def is_empty() -> bool:
    return not load()


def has_mode(room: str, cooling: bool) -> bool:
    return bool(load().get(room, {}).get(mode_key(cooling)))


def get_mode(room: str, cooling: bool) -> dict[int, Days]:
    raw = load().get(room, {}).get(mode_key(cooling), {})
    return {int(profile): days for profile, days in raw.items()}


def get_profile(room: str, cooling: bool, profile: int) -> Days | None:
    return get_mode(room, cooling).get(int(profile))


def put_profile(room: str, cooling: bool, profile: int, days: Days) -> None:
    """Upsert one profile of one mode for one room."""
    with _lock:
        data = load()
        mode_entry = data.setdefault(room, {}).setdefault(mode_key(cooling), {})
        mode_entry[str(int(profile))] = days
        _save(data)


def put_mode(room: str, cooling: bool, profiles: dict[int, Days]) -> None:
    """Replace a room's whole set for one mode (used by the device snapshot)."""
    with _lock:
        data = load()
        data.setdefault(room, {})[mode_key(cooling)] = {
            str(int(profile)): days for profile, days in profiles.items()
        }
        _save(data)


def get_active_profile(room: str, cooling: bool) -> int | None:
    """The profile slot (1..6) last selected while the room was in this mode,
    or None if we've never seen this room in this mode."""
    raw = load().get(room, {}).get("active_profile", {}).get(mode_key(cooling))
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def put_active_profile(room: str, cooling: bool, profile: int) -> None:
    with _lock:
        data = load()
        data.setdefault(room, {}).setdefault("active_profile", {})[mode_key(cooling)] = int(profile)
        _save(data)


def replace_all(data: dict) -> None:
    """Replace the whole store (import). The previous content still goes to the
    rolling backup first, like every other write."""
    with _lock:
        _save(data)
