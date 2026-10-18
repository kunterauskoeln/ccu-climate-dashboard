"""Absence (Abwesenheit): all rooms on one profile for a while, then back.

One absence at a time, stored in ``data/absence.json``. Phases:

* ``geplant``  -- waiting for its start (start may be "now")
* ``aktiv``    -- at the start every room's current profile is remembered
  (``previous``) and all rooms are switched to ``profile``
* ``rueckkehr`` -- from the end on, every room goes back to its ``previous``
  profile
* ``beendet`` / ``abgebrochen`` -- kept for display until the next absence

Switching uses the same paced background transfer as "Wohnung"
(:mod:`apartment`). A background thread calls :func:`tick` every 30 s; it
waits while another transfer runs, then makes sure every room is where it
should be -- once: after all rooms are confirmed (or ``MAX_ATTEMPTS`` runs
failed) the phase counts as applied and the app no longer interferes, so a
room changed by hand during the absence keeps its manual profile until the
return. A start or end missed while the server was off is caught up.

Times are local time of ``SCHEDULE_TZ`` (like the climate schedule).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from . import apartment, climate_schedule, profile_names, profile_transfer
from .ccu import climate
from .ccu import profiles as prof
from .ccu.errors import CcuError
from .ccu.schedule import PROFILE_RANGE

log = logging.getLogger(__name__)

_PATH = os.getenv("ABSENCE_FILE", "/app/app/data/absence.json")
_TICK_SECONDS = 30.0
MAX_ATTEMPTS = 3

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()


@dataclass
class AbsenceState:
    phase: str                          # aus | geplant | aktiv | rueckkehr | beendet | abgebrochen
    profile: int | None = None
    profile_name: str | None = None
    start: str | None = None            # ISO with offset
    end: str | None = None
    previous: dict[str, int] = field(default_factory=dict)
    applied: bool = False               # current phase's switching is done
    message: str = ""


def load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _parse(value: str) -> datetime:
    stamp = datetime.fromisoformat(value)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=climate_schedule.tz())


def _name(profile: int | None) -> str | None:
    if profile is None:
        return None
    return profile_names.load().get(str(profile)) or f"P{profile}"


def state() -> AbsenceState:
    data = load()
    if not data:
        return AbsenceState(phase="aus", message="Keine Abwesenheit eingerichtet.")
    return AbsenceState(
        phase=data.get("phase", "aus"), profile=data.get("profile"),
        profile_name=_name(data.get("profile")), start=data.get("start"), end=data.get("end"),
        previous=dict(data.get("previous") or {}), applied=bool(data.get("applied")),
        message=data.get("message", ""),
    )


def configure(profile: int, start: str | None, end: str, now: datetime | None = None) -> AbsenceState:
    """Plan an absence, or change the running one (new end and/or profile).
    Raises ValueError with a German message for the user."""
    now = now or datetime.now(climate_schedule.tz())
    if profile not in PROFILE_RANGE:
        raise ValueError("Profil muss 1 bis 6 sein")
    try:
        end_at = _parse(end)
        start_at = _parse(start) if start else now
    except ValueError:
        raise ValueError("Datum/Uhrzeit nicht lesbar") from None
    if end_at <= now:
        raise ValueError("Das Ende muss in der Zukunft liegen")
    if end_at <= start_at:
        raise ValueError("Das Ende muss nach dem Beginn liegen")
    with _lock:
        data = load()
        phase = data.get("phase")
        if phase == "rueckkehr":
            raise ValueError("Die Rückkehr läuft gerade – bitte warten, bis sie fertig ist")
        if phase == "aktiv":
            # running: start stays, previous profiles stay; new profile -> switch again
            changed = profile != data.get("profile")
            data.update(profile=profile, end=end_at.isoformat(timespec="minutes"))
            if changed:
                data.update(applied=False, attempts=0,
                            message=f"Profil geändert: Räume werden auf {_name(profile)} umgeschaltet")
            else:
                data["message"] = f"Ende geändert auf {end_at:%d.%m.%Y %H:%M}"
        else:
            data = {
                "phase": "geplant", "profile": profile,
                "start": start_at.isoformat(timespec="minutes"),
                "end": end_at.isoformat(timespec="minutes"),
                "previous": {}, "applied": False, "attempts": 0,
                "message": "Geplant" if start_at > now else "Beginnt gleich",
            }
        _save(data)
    return state()


def cancel(now: datetime | None = None) -> AbsenceState:
    """Stop: a planned absence is dropped, a running one returns right away."""
    now = now or datetime.now(climate_schedule.tz())
    with _lock:
        data = load()
        phase = data.get("phase")
        if phase == "geplant":
            data.update(phase="abgebrochen", message="Geplante Abwesenheit abgebrochen")
        elif phase == "aktiv":
            data.update(end=now.isoformat(timespec="minutes"),
                        message="Vorzeitig beendet: Räume gehen zurück auf ihr Profil")
        elif phase == "rueckkehr":
            raise ValueError("Die Rückkehr läuft bereits")
        else:
            raise ValueError("Keine laufende oder geplante Abwesenheit")
        _save(data)
    return state()


def _ensure(data: dict, targets: dict[str, int], clients, label: str) -> None:
    """One attempt to bring every room in *targets* to its profile. Marks the
    phase applied when nothing is left (or the attempts are used up)."""
    xmlrpc, device_map = clients()
    cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
    targets = {room: p for room, p in targets.items() if room in device_map.rooms}
    the_plan = apartment.plan(xmlrpc, device_map, targets, cooling)
    wrong = [r.room for r in the_plan.rooms] + [d.split(" (")[0] for d in the_plan.deferred]
    if not wrong:
        data.update(applied=True, message=f"{label}: alle Räume umgeschaltet")
        return
    if data.get("attempts", 0) >= MAX_ATTEMPTS:
        data.update(applied=True,
                    message=f"{label}: nicht umgeschaltet nach {MAX_ATTEMPTS} Versuchen: "
                            + ", ".join(sorted(wrong)))
        log.warning("absence: giving up on %s", wrong)
        return
    data["attempts"] = data.get("attempts", 0) + 1
    first = next(iter(targets.values()))
    apartment.start(the_plan, first, cooling, label=label)
    data["message"] = f"{label}: {len(wrong)} Raum/Räume werden umgeschaltet"


def tick(clients, now: datetime | None = None) -> None:
    now = now or datetime.now(climate_schedule.tz())
    with _lock:
        data = load()
        phase = data.get("phase")
        if phase not in ("geplant", "aktiv", "rueckkehr"):
            return
        if profile_transfer.is_running():
            return  # never interfere with a running transfer; try again next tick
        try:
            if phase == "geplant" and now >= _parse(data["start"]):
                xmlrpc, device_map = clients()
                data["previous"] = {
                    name: p for name in device_map.room_names
                    if (p := prof.get_active_profile(xmlrpc, device_map.room(name).wth_address))
                    is not None
                }
                data.update(phase="aktiv", applied=False, attempts=0)
                phase = "aktiv"
                log.info("absence started: P%s, previous %s", data["profile"], data["previous"])
            if phase == "aktiv" and now >= _parse(data["end"]):
                data.update(phase="rueckkehr", applied=False, attempts=0)
                phase = "rueckkehr"
                log.info("absence ends: back to %s", data["previous"])
            if phase == "aktiv" and not data.get("applied"):
                rooms = list(data["previous"]) or clients()[1].room_names
                _ensure(data, dict.fromkeys(rooms, int(data["profile"])), clients,
                        f"Abwesenheit: {_name(data['profile'])}")
            elif phase == "rueckkehr":
                if not data.get("applied"):
                    _ensure(data, {r: int(p) for r, p in data["previous"].items()}, clients,
                            "Rückkehr aus der Abwesenheit")
                if data.get("applied"):
                    data["phase"] = "beendet"
        except CcuError as exc:
            log.warning("absence round failed, retrying", exc_info=True)
            data["message"] = f"CCU nicht erreichbar, neuer Versuch: {exc}"
        _save(data)


def _loop() -> None:
    from ..deps import new_jsonrpc, new_xmlrpc, valve_channels_path
    from .ccu.mapping import load_valve_channels, map_from_devices

    xmlrpc = new_xmlrpc()
    jsonrpc = new_jsonrpc()
    cache: dict = {"map": None, "at": 0.0}

    def clients():
        if cache["map"] is None or time.monotonic() - cache["at"] > 600:
            cache["map"] = map_from_devices(jsonrpc.list_devices(),
                                            load_valve_channels(valve_channels_path()))
            cache["at"] = time.monotonic()
        return xmlrpc, cache["map"]

    while True:
        try:
            if load().get("phase") in ("geplant", "aktiv", "rueckkehr"):
                tick(clients)
        except Exception:
            log.warning("absence round failed", exc_info=True)
        if _stop.wait(_TICK_SECONDS):
            break
    jsonrpc.logout()


def start() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="absence", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
