"""Dew point monitoring for floor cooling (Taupunktüberwachung).

When cooling, a floor (and the supply pipes) colder than the room air's dew
point collects condensation. Per room the app computes the dew point from the
thermostat's temperature and humidity and compares it with the flow (Vorlauf)
temperature from MQTT (:mod:`flow_sensor`) -- the coldest point, so the
comparison errs on the safe side.

The flow sensor sits in a warm room: with every valve closed the pipe warms up
and the reading is too high. It is trusted only after at least one valve has
been open for ``FLOW_SETTLE_MINUTES`` (default 10); until then the last value
measured under flow is used. A room whose valve is closed gets no cold water
and is not at risk.

A background thread (:func:`start`) refreshes a snapshot every 60 s with local
XML-RPC reads only (no radio traffic); the API returns that snapshot. This is
monitoring, not a safety device: it warns, it does not switch anything.
"""
from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field

from . import flow_sensor
from .ccu import climate
from .ccu.errors import CcuError
from .ccu.state import read_state

log = logging.getLogger(__name__)

_TICK_SECONDS = 60.0
_MAP_REFRESH_SECONDS = 600.0
_HEALTH_EVERY = 5          # device health every 5th round
VALVE_OPEN = 0.1          # LEVEL from which a circuit counts as open
LAST_VALID_MAX_AGE = 48 * 3600.0

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except ValueError:
        return default


def warn_margin() -> float:
    return _env_float("DEW_WARN_MARGIN", 3.0)


def alarm_margin() -> float:
    return _env_float("DEW_ALARM_MARGIN", 1.0)


def settle_seconds() -> float:
    return _env_float("FLOW_SETTLE_MINUTES", 10.0) * 60


def stale_seconds() -> float:
    return _env_float("FLOW_STALE_MINUTES", 120.0) * 60


def dew_point(temperature: float, humidity: float) -> float | None:
    """Magnus formula (Sonntag 1990 constants), good to ~0.1 K for 0-60 °C."""
    if humidity <= 0 or humidity > 100:
        return None
    a, b = 17.62, 243.12
    gamma = math.log(humidity / 100.0) + a * temperature / (b + temperature)
    return b * gamma / (a - gamma)


def classify(margin: float | None) -> str:
    if margin is None:
        return "unbekannt"
    if margin < alarm_margin():
        return "gefahr"
    if margin < warn_margin():
        return "knapp"
    return "ok"


_ORDER = ["aus", "ok", "unbekannt", "knapp", "gefahr"]


@dataclass
class RoomDew:
    room: str
    temperature: float | None
    humidity: int | None
    dew_point: float | None
    valve: float | None
    margin: float | None      # effective flow temperature minus dew point, K
    status: str               # ok | knapp | gefahr | unbekannt | ventil_zu | aus


@dataclass
class Flow:
    configured: bool
    connection: str               # aus | verbinde | verbunden | Fehler: …
    topic: str
    value: float | None           # last value received
    received_at: float | None
    stale: bool                   # no message for FLOW_STALE_MINUTES
    effective: float | None       # value used for the comparison
    source: str | None            # "live" | "last_valid" | None
    last_valid: float | None
    last_valid_at: float | None
    flowing_since: float | None   # some valve open since (epoch)


@dataclass
class Snapshot:
    at: float | None
    cooling: bool | None
    level: str                    # aus | ok | unbekannt | knapp | gefahr
    message: str
    warn_margin: float
    alarm_margin: float
    flow: Flow
    rooms: list[RoomDew] = field(default_factory=list)


# --- tracker state (only touched by the monitor thread / tests) -------------
_flowing_since: float | None = None
_last_valid: flow_sensor.Reading | None = None
_snapshot: Snapshot | None = None


def reset() -> None:
    global _flowing_since, _last_valid, _snapshot
    _flowing_since = None
    _last_valid = None
    _snapshot = None


def _flow(now: float, any_open: bool, cooling: bool | None) -> Flow:
    """Track since when cold water flows and which flow value can be trusted.

    Only while cooling: a value measured with heating water says nothing about
    condensation, and must not serve as the "last valid" value right after a
    switch to cooling (it would make a cold floor look safe)."""
    global _flowing_since, _last_valid
    if not cooling:
        _flowing_since = None
        _last_valid = None
    elif any_open:
        if _flowing_since is None:
            _flowing_since = now
    else:
        _flowing_since = None

    reading = flow_sensor.latest()
    settled_at = _flowing_since + settle_seconds() if _flowing_since is not None else None
    if reading is not None and settled_at is not None and reading.received_at >= settled_at:
        _last_valid = reading

    stale = reading is None or now - reading.received_at > stale_seconds()
    effective: float | None = None
    source: str | None = None
    if (reading is not None and not stale and settled_at is not None
            and now >= settled_at and _last_valid is reading):
        effective, source = reading.value, "live"
    elif _last_valid is not None and now - _last_valid.received_at <= LAST_VALID_MAX_AGE:
        effective, source = _last_valid.value, "last_valid"

    return Flow(
        configured=flow_sensor.configured(), connection=flow_sensor.status(),
        topic=flow_sensor.topic(),
        value=reading.value if reading else None,
        received_at=reading.received_at if reading else None,
        stale=stale, effective=effective, source=source,
        last_valid=_last_valid.value if _last_valid else None,
        last_valid_at=_last_valid.received_at if _last_valid else None,
        flowing_since=_flowing_since,
    )


def evaluate(now: float, cooling: bool | None, rooms: list) -> Snapshot:
    """Build a snapshot from room states (RoomState-like: room,
    actual_temperature, humidity, valve)."""
    any_open = any((r.valve or 0) >= VALVE_OPEN for r in rooms)
    flow = _flow(now, any_open, cooling)

    out: list[RoomDew] = []
    for r in rooms:
        dp = (dew_point(r.actual_temperature, r.humidity)
              if r.actual_temperature is not None and r.humidity is not None else None)
        margin = (round(flow.effective - dp, 1)
                  if flow.effective is not None and dp is not None else None)
        if not cooling:
            status = "aus"
        elif (r.valve or 0) < VALVE_OPEN:
            status = "ventil_zu"
        else:
            status = classify(margin)
        out.append(RoomDew(
            room=r.room, temperature=r.actual_temperature, humidity=r.humidity,
            dew_point=round(dp, 1) if dp is not None else None, valve=r.valve,
            margin=margin, status=status,
        ))

    if not cooling:
        level, message = "aus", "Heizbetrieb: keine Kondensgefahr."
    else:
        relevant = [d for d in out if d.status not in ("ventil_zu", "aus")]
        level = max((d.status for d in relevant), key=_ORDER.index, default="ok")
        message = _message(level, relevant, flow)
    return Snapshot(
        at=now, cooling=cooling, level=level, message=message,
        warn_margin=warn_margin(), alarm_margin=alarm_margin(), flow=flow, rooms=out,
    )


def _message(level: str, relevant: list[RoomDew], flow: Flow) -> str:
    if not relevant:
        return "Alle Ventile zu: keine Kondensgefahr."
    if level in ("gefahr", "knapp"):
        worst = sorted((d for d in relevant if d.status == level),
                       key=lambda d: d.margin if d.margin is not None else 0)
        rooms = ", ".join(f"{d.room} ({_de(d.margin)} K)" for d in worst)
        text = "Kondensgefahr" if level == "gefahr" else "Taupunkt knapp"
        return f"{text}: {rooms}"
    if level == "unbekannt":
        if not flow.configured:
            return "Kein Vorlauf-Sensor eingerichtet (MQTT in backend/.env)."
        if flow.effective is None:
            return "Noch kein gültiger Vorlauf-Messwert (gilt erst nach 10 Minuten Durchfluss)."
        return "Für einen Raum fehlen Temperatur oder Luftfeuchte."
    return "Alle Räume mit genügend Abstand zum Taupunkt."


def _de(margin: float | None) -> str:
    return "?" if margin is None else f"{margin:+.1f}".replace(".", ",")


def snapshot() -> Snapshot | None:
    with _lock:
        return _snapshot


def tick(clients, now: float | None = None) -> Snapshot:
    """One monitoring round. *clients* returns (xmlrpc, device_map)."""
    global _snapshot
    now = now if now is not None else time.time()
    xmlrpc, device_map = clients()
    cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
    states = []
    for name in device_map.room_names:
        try:
            states.append(read_state(xmlrpc, None, device_map.room(name), full=False, valve=True))
        except CcuError:
            log.debug("dew point: room %s not readable", name, exc_info=True)
    snap = evaluate(now, cooling, states)
    with _lock:
        _snapshot = snap
    return snap


def _loop() -> None:
    from ..deps import new_jsonrpc, new_xmlrpc, valve_channels_path
    from .ccu.mapping import load_valve_channels, map_from_devices

    xmlrpc = new_xmlrpc()
    jsonrpc = new_jsonrpc()
    cache: dict = {"map": None, "at": 0.0}

    def clients():
        if cache["map"] is None or time.monotonic() - cache["at"] > _MAP_REFRESH_SECONDS:
            cache["map"] = map_from_devices(jsonrpc.list_devices(),
                                            load_valve_channels(valve_channels_path()))
            cache["at"] = time.monotonic()
        return xmlrpc, cache["map"]

    from . import device_health, ha_publish, valve_history

    rounds = 0
    while True:
        try:
            snap = tick(clients)
            # every 5th round (5 min): valve history, device health
            if rounds % _HEALTH_EVERY == 0:
                valve_history.record({r.room: r.valve for r in snap.rooms})
                try:
                    device_health.tick(xmlrpc, jsonrpc, clients()[1])
                except Exception:
                    log.warning("device health round failed", exc_info=True)
            ha_publish.publish(snap, device_health.snapshot())
        except Exception:
            log.warning("dew point monitor round failed", exc_info=True)
        rounds += 1
        if _stop.wait(_TICK_SECONDS):
            break
    jsonrpc.logout()


def start() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="dew-point", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
