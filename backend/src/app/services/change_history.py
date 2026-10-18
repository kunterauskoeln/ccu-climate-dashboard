"""Change history for profile edits (active mode) and profile renames.

Each entry records what a change looked like *before* it happened, so that
"reset to here" can put things back: pick an entry, and it and every newer
entry are undone. For a profile touched by several of those entries, the
oldest entry's before-state wins -- that is exactly the state before the
first undone change.

Deliberately not a full history:

* only edits of the mode that is currently running (the device path) are
  recorded; edits of the inactive mode (store only) are not
* a heating/cooling switch drops all profile entries -- their before-states
  belong to the other mode's schedules. Profile names are shared by both
  modes, so their entries survive a switch.

On disk (``data/change_history.json``), oldest first::

    {"entries": [
      {"id": "...", "at": "2026-09-28T10:15:02+00:00", "kind": "profile",
       "mode": "heating", "room": "Bad", "profile": 1,
       "summary": "Montag: 08:00–08:30 auf 23,5 °C", "before": {<Days>}},
      {"id": "...", "at": "...", "kind": "name", "profile": 2,
       "summary": "Name P2: „Urlaub“ → „Winterurlaub“", "before": "Urlaub"}
    ]}

Not CCU-related: pure JSON persistence, same locking/in-place-write approach
as ``profile_sets``.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import UTC, datetime

from . import profile_sets

_PATH = os.getenv("CHANGE_HISTORY_FILE", "/app/app/data/change_history.json")
_lock = threading.Lock()

# Oldest entries fall off beyond this; a week of Days is small, so even the
# full cap stays well under a megabyte.
MAX_ENTRIES = 200

PROFILE = "profile"
NAME = "name"


def _load() -> list[dict]:
    try:
        with open(_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return entries if isinstance(entries, list) else []


def _save(entries: list[dict]) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as handle:
        json.dump({"entries": entries}, handle, indent=2, ensure_ascii=False)


def _append(entry: dict) -> None:
    with _lock:
        entries = _load()
        entries.append(entry)
        _save(entries[-MAX_ENTRIES:])


def _new_entry(kind: str, profile: int, summary: str) -> dict:
    return {
        "id": f"{time.time_ns():x}",
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "kind": kind,
        "profile": int(profile),
        "summary": summary,
    }


def record_profile(
    room: str, cooling: bool, profile: int, before: profile_sets.Days, summary: str,
) -> None:
    entry = _new_entry(PROFILE, profile, summary)
    entry.update(mode=profile_sets.mode_key(cooling), room=room, before=before)
    _append(entry)


def record_name(profile: int, before: str | None, summary: str) -> None:
    entry = _new_entry(NAME, profile, summary)
    entry["before"] = before
    _append(entry)


def entries() -> list[dict]:
    """All entries, oldest first (including their before-states)."""
    with _lock:
        return _load()


def entries_from(entry_id: str) -> list[dict]:
    """The entry *entry_id* and every newer one, oldest first; [] if unknown."""
    all_entries = entries()
    for index, entry in enumerate(all_entries):
        if entry.get("id") == entry_id:
            return all_entries[index:]
    return []


def remove_ids(ids: set[str]) -> None:
    with _lock:
        _save([e for e in _load() if e.get("id") not in ids])


def clear_profile_entries() -> None:
    """Drop every profile entry (after a heating/cooling switch); keep names."""
    with _lock:
        _save([e for e in _load() if e.get("kind") != PROFILE])


def profile_targets(undone: list[dict]) -> dict[tuple[str, str, int], profile_sets.Days]:
    """(room, mode, profile) -> state to go back to, for the given entries
    (oldest first): the oldest entry touching a profile carries its state
    before all of them."""
    targets: dict[tuple[str, str, int], profile_sets.Days] = {}
    for entry in undone:
        if entry.get("kind") != PROFILE:
            continue
        key = (entry["room"], entry["mode"], int(entry["profile"]))
        targets.setdefault(key, entry["before"])
    return targets


def name_targets(undone: list[dict]) -> dict[int, str | None]:
    """profile slot -> name before the oldest of the given entries (None: had none)."""
    targets: dict[int, str | None] = {}
    for entry in undone:
        if entry.get("kind") == NAME:
            targets.setdefault(int(entry["profile"]), entry.get("before"))
    return targets


def clear() -> None:
    """Drop every entry (after an import: its before-states would no longer fit)."""
    with _lock:
        _save([])
