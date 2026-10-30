"""Device health: reachability, batteries, duty cycle.

Read from each device's maintenance channel ``:0`` (XML-RPC, local, no radio
traffic) -- the room thermostats (``UNREACH``, ``LOW_BAT``,
``OPERATING_VOLTAGE``, ``DUTY_CYCLE``, ``RSSI_DEVICE``) and the actuator (no
battery). The CCU's own radio load comes from JSON-RPC
``Interface.listBidcosInterfaces`` (``dutyCycle`` in percent of the legal
1 % airtime; at 100 % the CCU sends nothing more for a while).

The dew point monitor thread calls :func:`tick` every 5 minutes; the API and
Home Assistant read :func:`snapshot`. The profile transfer uses
:func:`read_ccu_duty_cycle` directly to hold back when the radio is busy.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field

from .ccu.errors import CcuError
from .ccu.mapping import DeviceMap
from .ccu.state import _as_bool, _as_float, _as_int

log = logging.getLogger(__name__)

_lock = threading.Lock()
_snapshot: Snapshot | None = None
# address -> first tick that saw CONFIG_PENDING (cleared once it is gone)
_pending_since: dict[str, float] = {}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


def duty_warn() -> int:
    """CCU duty cycle (%) from which the app warns."""
    return _env_int("DUTY_CYCLE_WARN", 60)


def duty_limit() -> int:
    """CCU duty cycle (%) from which profile transfers hold back."""
    return _env_int("DUTY_CYCLE_LIMIT", 70)


def pending_warn_minutes() -> int:
    """Minutes CONFIG_PENDING may last before it counts as a problem. Right
    after any settings or profile write it is set briefly – that is normal."""
    return _env_int("CONFIG_PENDING_WARN_MINUTES", 30)


@dataclass
class DeviceState:
    name: str
    address: str
    kind: str                     # "thermostat" | "aktor"
    reachable: bool | None        # None: could not be read
    low_battery: bool | None      # None: no battery
    voltage: float | None
    rssi: int | None
    duty_cycle: bool              # the device itself hit its airtime limit
    config_pending: bool
    # first seen pending (epoch s, since this app start) and whether that is
    # longer than pending_warn_minutes(): settings the CCU cannot hand over
    config_pending_since: float | None = None
    config_stuck: bool = False


@dataclass
class Snapshot:
    at: float
    ccu_duty_cycle: int | None
    level: str                    # "ok" | "warnung"
    message: str
    problems: list[str] = field(default_factory=list)
    devices: list[DeviceState] = field(default_factory=list)


def read_ccu_duty_cycle(jsonrpc) -> int | None:
    """Duty cycle of the CCU's default radio interface in percent, None if unknown."""
    try:
        interfaces = jsonrpc.call("Interface.listBidcosInterfaces", {"interface": "BidCos-RF"})
    except CcuError:
        log.debug("duty cycle not readable", exc_info=True)
        return None
    if not isinstance(interfaces, list) or not interfaces:
        return None
    chosen = next((i for i in interfaces if isinstance(i, dict) and _as_bool(i.get("isDefault"))),
                  interfaces[0])
    return _as_int(chosen.get("dutyCycle")) if isinstance(chosen, dict) else None


def _read_device(xmlrpc, name: str, address: str, kind: str) -> DeviceState:
    try:
        values = xmlrpc.get_paramset(f"{address}:0", "VALUES")
    except CcuError:
        return DeviceState(name, address, kind, None, None, None, None, False, False)
    has_battery = "LOW_BAT" in values
    return DeviceState(
        name=name, address=address, kind=kind,
        reachable=not _as_bool(values.get("UNREACH")),
        low_battery=_as_bool(values.get("LOW_BAT")) if has_battery else None,
        voltage=_as_float(values.get("OPERATING_VOLTAGE")) if has_battery else None,
        rssi=_as_int(values.get("RSSI_DEVICE")),
        duty_cycle=_as_bool(values.get("DUTY_CYCLE")),
        config_pending=_as_bool(values.get("CONFIG_PENDING")),
    )


def _de(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 120:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} Tagen"


def evaluate(now: float, devices: list[DeviceState], ccu_duty: int | None) -> Snapshot:
    problems: list[str] = []
    for d in devices:
        d.config_stuck = (
            d.config_pending and d.config_pending_since is not None
            and now - d.config_pending_since >= pending_warn_minutes() * 60
        )
        if d.reachable is None:
            problems.append(f"{d.name}: Zustand nicht lesbar")
        elif not d.reachable:
            problems.append(f"{d.name}: nicht erreichbar")
        if d.low_battery:
            volts = f" ({_de(d.voltage)} V)" if d.voltage is not None else ""
            problems.append(f"{d.name}: Batterie schwach{volts}")
        if d.duty_cycle:
            problems.append(f"{d.name}: Funk-Limit erreicht")
        if d.config_stuck and d.config_pending_since is not None:
            problems.append(f"{d.name}: Einstellungen seit "
                            f"{_duration(now - d.config_pending_since)} nicht übertragen")
    if ccu_duty is not None and ccu_duty >= duty_warn():
        problems.append(f"CCU-Funkauslastung {ccu_duty} %")
    if problems:
        message = "Geräte: " + " · ".join(problems)
    else:
        message = "Alle Geräte in Ordnung."
    return Snapshot(at=now, ccu_duty_cycle=ccu_duty, level="warnung" if problems else "ok",
                    message=message, problems=problems, devices=devices)


def tick(xmlrpc, jsonrpc, device_map: DeviceMap, now: float | None = None) -> Snapshot:
    global _snapshot
    devices = [_read_device(xmlrpc, name, device_map.room(name).wth_address, "thermostat")
               for name in device_map.room_names]
    if device_map.actuator_address:
        devices.append(_read_device(xmlrpc, "Aktor", device_map.actuator_address, "aktor"))
    now = now if now is not None else time.time()
    with _lock:
        for d in devices:
            if d.config_pending:
                d.config_pending_since = _pending_since.setdefault(d.address, now)
            elif d.reachable is not None:  # unreadable: keep the clock running
                _pending_since.pop(d.address, None)
            else:
                d.config_pending_since = _pending_since.get(d.address)
                d.config_pending = d.config_pending_since is not None
    snap = evaluate(now, devices, read_ccu_duty_cycle(jsonrpc))
    with _lock:
        _snapshot = snap
    return snap


def snapshot() -> Snapshot | None:
    with _lock:
        return _snapshot


def reset() -> None:
    global _snapshot
    with _lock:
        _snapshot = None
        _pending_since.clear()
