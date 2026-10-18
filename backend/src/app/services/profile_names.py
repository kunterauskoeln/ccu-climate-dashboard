"""User-defined profile names, persisted as a small JSON file.

Not CCU-related. One label per profile slot, shared by all rooms:
``{ "1": "Standard", "2": "Urlaub", ... "6": "Individuell" }``.
"""
from __future__ import annotations

import json
import os
import threading

_PATH = os.getenv("PROFILE_NAMES_FILE", "/app/app/data/profile_names.json")
_lock = threading.Lock()


def _flatten(raw: dict) -> dict[str, str]:
    """Accept the current global shape and the old per-room shape
    ``{room: {slot: name}}`` – collapse the latter (all rooms carried the
    same names) into ``{slot: name}``."""
    flat: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, dict):  # old per-room entry
            for slot, name in value.items():
                flat.setdefault(str(slot), name)
        else:
            flat[str(key)] = value
    return flat


def load() -> dict[str, str]:
    try:
        with open(_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return _flatten(data) if isinstance(data, dict) else {}


def _write(data: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    # write in place – _PATH used to be a single-file bind mount, and renaming
    # over a bind mount fails with EBUSY. The lock serialises writers and the
    # file is tiny, so a partial write is not a concern.
    with open(_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def set_name(profile: int, name: str) -> None:
    with _lock:
        data = load()
        data[str(int(profile))] = name
        _write(data)


def restore(names: dict[int, str | None]) -> None:
    """Put slots back to earlier names; None removes a slot's name."""
    with _lock:
        data = load()
        for profile, name in names.items():
            if name is None:
                data.pop(str(int(profile)), None)
            else:
                data[str(int(profile))] = name
        _write(data)


def replace_all(names: dict[str, str]) -> None:
    """Replace every profile name at once (import)."""
    with _lock:
        _write({str(int(slot)): name for slot, name in names.items()})
