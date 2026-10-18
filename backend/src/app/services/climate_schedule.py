"""Scheduled switching between heating and cooling ("Automatisch umschalten").

One point in time for "to heating" and one for "to cooling", each as day,
month and time of day and each switched on or off on its own -- they recur
every year and stay in force until they are changed or switched off. Stored in
``data/climate_schedule.json``::

    {"heating": {"day": 15, "month": 9, "time": "08:00", "enabled": true},
     "cooling": {"day": 15, "month": 5, "time": "08:00", "enabled": false},
     "last_handled": "2026-05-15T08:00:00+02:00",
     "last_run": {"at": "...", "cooling": true, "result": "switched", "message": null}}

A background thread (:func:`start`) calls :func:`tick` every 30 s. The point
that is due is the most recent one in the past, switched on or not; it is
acted on once (``last_handled``) and only if it is switched on. A point missed
while the server was off is therefore caught up after the next start -- but
not once the other point has passed too (only cooling on, server off from May
to October: the heating point in September ended the cooling season, so
nothing happens). Saving the schedule counts everything up to that moment as
handled, so switching a point on never switches right away, and a manual
switch after a point is not undone.

Times are local time of ``SCHEDULE_TZ`` (default Europe/Berlin), independent
of the container's own time zone.
"""
from __future__ import annotations

import calendar
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from . import climate_switch
from .ccu import climate
from .ccu.errors import CcuError

log = logging.getLogger(__name__)

_PATH = os.getenv("CLIMATE_SCHEDULE_FILE", "/app/app/data/climate_schedule.json")
_TICK_SECONDS = 30.0
_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()

# replaced in tests: returns (xmlrpc, device_map)
_make_clients = None


def tz() -> ZoneInfo:
    return ZoneInfo(os.getenv("SCHEDULE_TZ", "Europe/Berlin"))


@dataclass(frozen=True)
class Point:
    day: int
    month: int
    time: str  # "HH:MM"
    enabled: bool = True

    def validate(self, label: str) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"{label}: Monat {self.month} gibt es nicht")
        # 29.02. is allowed (leap years); in other years it becomes 28.02.
        if not 1 <= self.day <= calendar.monthrange(2024, self.month)[1]:
            raise ValueError(f"{label}: den {self.day}.{self.month}. gibt es nicht")
        try:
            hours, minutes = (int(x) for x in self.time.split(":"))
        except ValueError:
            raise ValueError(f"{label}: Uhrzeit „{self.time}“ ist nicht HH:MM") from None
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError(f"{label}: Uhrzeit „{self.time}“ gibt es nicht")

    def at(self, year: int, zone: ZoneInfo) -> datetime:
        day = min(self.day, calendar.monthrange(year, self.month)[1])
        hours, minutes = (int(x) for x in self.time.split(":"))
        return datetime(year, self.month, day, hours, minutes, tzinfo=zone)

    def as_dict(self) -> dict:
        return {"day": self.day, "month": self.month, "time": self.time, "enabled": self.enabled}

    def same_time(self, other: Point) -> bool:
        return (self.day, self.month, self.time) == (other.day, other.month, other.time)


@dataclass(frozen=True)
class Due:
    at: datetime
    cooling: bool
    enabled: bool = True


def _point(raw: object, default_enabled: bool) -> Point | None:
    if not isinstance(raw, dict):
        return None
    try:
        return Point(int(raw["day"]), int(raw["month"]), str(raw["time"]),
                     bool(raw.get("enabled", default_enabled)))
    except (KeyError, TypeError, ValueError):
        return None


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


def _points(data: dict) -> list[tuple[Point, bool]]:
    out = []
    # files written before the per-point switch had one "enabled" for both
    legacy = bool(data.get("enabled", False))
    for key, cooling in (("heating", False), ("cooling", True)):
        point = _point(data.get(key), legacy)
        if point is not None:
            out.append((point, cooling))
    return out


def points(data: dict) -> dict[str, Point | None]:
    """The stored points as {"heating": Point|None, "cooling": Point|None}."""
    found = {("cooling" if cooling else "heating"): p for p, cooling in _points(data)}
    return {"heating": found.get("heating"), "cooling": found.get("cooling")}


def latest_due(data: dict, now: datetime) -> Due | None:
    """The most recent point at or before *now*, switched on or not (None: none set)."""
    zone = tz()
    best: Due | None = None
    for point, cooling in _points(data):
        for year in (now.year, now.year - 1):
            at = point.at(year, zone)
            if at <= now:
                if best is None or at > best.at:
                    best = Due(at, cooling, point.enabled)
                break
    return best


def next_due(data: dict, now: datetime) -> Due | None:
    """The next switched-on point after *now* (None: both off or none set)."""
    zone = tz()
    best: Due | None = None
    for point, cooling in _points(data):
        if not point.enabled:
            continue
        for year in (now.year, now.year + 1):
            at = point.at(year, zone)
            if at > now:
                if best is None or at < best.at:
                    best = Due(at, cooling)
                break
    return best


def configure(heating: Point, cooling: Point, now: datetime | None = None) -> dict:
    """Validate and store the schedule. Everything up to now counts as handled."""
    heating.validate("Auf Heizen")
    cooling.validate("Auf Kühlen")
    if heating.same_time(cooling):
        raise ValueError("Heizen und Kühlen brauchen verschiedene Zeitpunkte")
    now = now or datetime.now(tz())
    with _lock:
        data = load()
        data.pop("enabled", None)
        data.update({
            "heating": heating.as_dict(),
            "cooling": cooling.as_dict(),
            "last_handled": now.isoformat(timespec="seconds"),
        })
        _save(data)
        return data


def export() -> dict:
    """The two points for the data export (without the run state)."""
    found = points(load())
    return {key: point.as_dict() if point else None for key, point in found.items()}


def clear() -> None:
    """Remove both points (import of a file without a schedule)."""
    with _lock:
        data = load()
        for key in ("enabled", "heating", "cooling"):
            data.pop(key, None)
        _save(data)


def _clients():
    if _make_clients is not None:
        return _make_clients()
    from ..deps import new_jsonrpc, new_xmlrpc, valve_channels_path
    from .ccu.mapping import load_valve_channels, map_from_devices
    jsonrpc = new_jsonrpc()
    try:
        devices = jsonrpc.list_devices()
    finally:
        jsonrpc.logout()
    device_map = map_from_devices(devices, load_valve_channels(valve_channels_path()))
    return new_xmlrpc(), device_map


def tick(now: datetime | None = None) -> None:
    """Switch if a scheduled point has passed that was not acted on yet."""
    now = now or datetime.now(tz())
    with _lock:
        data = load()
        due = latest_due(data, now)
        if due is None:
            return
        try:
            handled = datetime.fromisoformat(str(data.get("last_handled")))
        except ValueError:
            handled = None
        if handled is not None and due.at <= handled:
            return
        if not due.enabled:
            # this point is switched off: it only ends the other point's season
            data["last_handled"] = due.at.isoformat(timespec="seconds")
            _save(data)
            return

        label = "Kühlen" if due.cooling else "Heizen"
        run = {"at": now.isoformat(timespec="seconds"), "due": due.at.isoformat(timespec="minutes"),
               "cooling": due.cooling}
        try:
            xmlrpc, device_map = _clients()
            if climate.get_cooling(xmlrpc, device_map.actuator_channel) == due.cooling:
                run.update(result="already", message=f"Stand schon auf {label}.")
            else:
                climate_switch.switch(xmlrpc, device_map, due.cooling)
                run.update(result="switched", message=f"Auf {label} umgeschaltet.")
            log.info("scheduled climate switch (%s): %s", due.at, run["message"])
            data["last_handled"] = due.at.isoformat(timespec="seconds")
        except CcuError as exc:
            # not marked as handled: tried again on the next tick
            log.warning("scheduled climate switch to %s failed, retrying", label, exc_info=True)
            run.update(result="error", message=f"Umschalten auf {label} fehlgeschlagen: {exc}")
        data["last_run"] = run
        _save(data)


def _loop() -> None:
    while not _stop.wait(_TICK_SECONDS):
        try:
            tick()
        except Exception:
            log.exception("climate schedule tick failed")


def start() -> None:
    """Start the background timer (once, on application startup)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="climate-schedule", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
