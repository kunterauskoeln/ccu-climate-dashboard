"""Per-room history for the chart (Raumverlauf): temperature, plan, valve.

The dew point monitor already has every room's temperature and valve; every
5th round it hands them to :func:`collect`, which adds what the room's weekly
plan says for that moment. The plan comes from the thermostat's own table (the
active profile in MASTER, a local XML-RPC read without radio traffic), so a
profile switch or an edit shows up from that moment on and the past stays as it
was. Samples are kept for ``KEEP_HOURS`` (72 h) in ``data/room_history.json``:

    {"samples": [[epoch_seconds, {"Bad": [22.1, 21.0, 0.4], ...}], ...]}

with ``[temperature, plan, valve]`` per room, ``null`` where a value is missing.
:func:`series` turns them into columns for one room, with a break in the lines
where the recording paused (server off).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from . import climate_schedule
from .ccu import group_profiles, schedule
from .ccu import profiles as prof
from .ccu.errors import CcuError

log = logging.getLogger(__name__)

_PATH = os.getenv("ROOM_HISTORY_FILE", "/app/app/data/room_history.json")
STEP_SECONDS = 300
KEEP_HOURS = 72
_lock = threading.Lock()
Reading = tuple[float | None, float | None, float | None]  # temperature, plan, valve 0..1
_samples: list[tuple[float, dict[str, Reading]]] | None = None   # loaded lazily


def _opt(value) -> float | None:
    return None if value is None else float(value)


def _load() -> list[tuple[float, dict[str, Reading]]]:
    global _samples
    if _samples is None:
        try:
            with open(_PATH, encoding="utf-8") as handle:
                raw = json.load(handle).get("samples", [])
            _samples = [
                (float(t), {str(room): (_opt(v[0]), _opt(v[1]), _opt(v[2]))
                            for room, v in values.items()})
                for t, values in raw if isinstance(values, dict)
            ]
        except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError, AttributeError,
                IndexError):
            _samples = []
    return _samples


def _save(samples: list[tuple[float, dict[str, Reading]]]) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"samples": [[t, v] for t, v in samples]}, handle, ensure_ascii=False,
                  separators=(",", ":"))
    os.replace(tmp, _PATH)


def plan_setpoint(xmlrpc, room_devices, now: float) -> float | None:
    """What the room's active profile says at *now* (local time of SCHEDULE_TZ);
    ``None`` if it cannot be read."""
    try:
        active = prof.get_active_profile(xmlrpc, room_devices.wth_address)
        if active is None:
            return None
        master = xmlrpc.get_paramset(room_devices.thermostat_channel, "MASTER")
    except CcuError:
        log.debug("room history: plan of %s not readable", room_devices.room, exc_info=True)
        return None
    local = datetime.fromtimestamp(now, climate_schedule.tz())
    blocks = schedule.blocks_from_master(master, active, schedule.DAYS[local.weekday()])
    return group_profiles.setpoint_at(blocks, local.hour * 60 + local.minute)


def collect(xmlrpc, device_map, snapshot_rooms, now: float | None = None) -> None:
    """Add the plan to the dew point snapshot's rooms and store one sample."""
    now = now if now is not None else time.time()
    readings: dict[str, Reading] = {}
    for room in snapshot_rooms:
        room_devices = device_map.rooms.get(room.room)
        plan = plan_setpoint(xmlrpc, room_devices, now) if room_devices else None
        readings[room.room] = (room.temperature, plan, room.valve)
    record(readings, now)


def record(readings: dict[str, Reading], now: float | None = None) -> None:
    """Store one sample."""
    now = now if now is not None else time.time()
    values: dict[str, Reading] = {
        room: (
            None if temperature is None else round(temperature, 1),
            None if plan is None else round(plan, 1),
            None if valve is None else round(valve, 3),
        )
        for room, (temperature, plan, valve) in readings.items()
    }
    with _lock:
        samples = _load()
        samples.append((now, values))
        cutoff = now - KEEP_HOURS * 3600
        while samples and samples[0][0] < cutoff:
            samples.pop(0)
        try:
            _save(samples)
        except OSError:
            log.warning("room history not saved", exc_info=True)


@dataclass
class Series:
    times: list[float] = field(default_factory=list)                # epoch seconds
    temperature: list[float | None] = field(default_factory=list)   # °C
    plan: list[float | None] = field(default_factory=list)          # °C
    valve: list[float | None] = field(default_factory=list)         # percent


def series(room: str, hours: float, now: float | None = None) -> Series:
    now = now if now is not None else time.time()
    with _lock:
        samples = [s for s in _load() if s[0] >= now - hours * 3600]
    out = Series()
    previous: float | None = None
    for t, values in samples:
        if room not in values:
            continue
        if previous is not None and t - previous > 3 * STEP_SECONDS:
            # recording paused: a break in every line
            out.times.append(previous + STEP_SECONDS)
            out.temperature.append(None)
            out.plan.append(None)
            out.valve.append(None)
        temperature, plan, valve = values[room]
        out.times.append(t)
        out.temperature.append(temperature)
        out.plan.append(plan)
        out.valve.append(round(valve * 100) if valve is not None else None)
        previous = t
    return out


def reset() -> None:
    """Forget the in-memory copy (tests)."""
    global _samples
    with _lock:
        _samples = None
