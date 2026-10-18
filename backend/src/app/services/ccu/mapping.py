"""Room -> device address resolution.

One HmIP-WTH-1 wall thermostat per room (channel ``:1`` carries status +
MASTER profiles, ``:0`` carries battery / RSSI). One HmIP-HEATING virtual
group per room (``INTxxxx``) exists too, but its ``LEVEL`` stays 0 on this
installation. One HmIP-FALMOT-C12 actuator switches heating/cooling for the whole
system and its channels ``:1``..``:9`` are the real floor-heating valves; which
channel belongs to which room is not exposed by the JSON-RPC device list, so it
comes from ``valve_channels.json`` (see :func:`load_valve_channels`).

``map_from_devices`` is pure; :class:`CachedDeviceMap` adds a TTL around a
live ``Device.listAllDetail``.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import RoomNotFound

log = logging.getLogger(__name__)

_DEFAULT_VALVE_CHANNELS_FILE = Path(__file__).resolve().parents[2] / "valve_channels.json"

_WTH_TYPE_PREFIX = "HmIP-WTH"
_ACTUATOR_HINTS = ("FALMOT", "FAL230", "FAL24", "HEATING_ACTUATOR")


@dataclass(frozen=True)
class RoomDevices:
    room: str
    wth_address: str
    group_address: str | None
    # Actuator channel addresses ("<FALMOT>:<n>") whose LEVEL is this room's valve;
    # a room can have several floor-heating circuits.
    valve_channels: tuple[str, ...] = ()

    @property
    def thermostat_channel(self) -> str:
        return f"{self.wth_address}:1"

    @property
    def maintenance_channel(self) -> str:
        return f"{self.wth_address}:0"

    @property
    def group_channel(self) -> str | None:
        return f"{self.group_address}:1" if self.group_address else None


@dataclass(frozen=True)
class DeviceMap:
    rooms: dict[str, RoomDevices]
    actuator_address: str | None

    def room(self, name: str) -> RoomDevices:
        try:
            return self.rooms[name]
        except KeyError:
            raise RoomNotFound(name) from None

    @property
    def room_names(self) -> list[str]:
        return sorted(self.rooms)

    @property
    def actuator_channel(self) -> str | None:
        return f"{self.actuator_address}:0" if self.actuator_address else None


def load_valve_channels(path: Path | str | None = None) -> dict[str, list[int]]:
    """Room name -> FALMOT channel numbers, from ``valve_channels.json``.

    Missing or malformed file -> ``{}`` (rooms then simply show no valve)."""
    target = Path(path) if path else _DEFAULT_VALVE_CHANNELS_FILE
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return {str(room): [int(ch) for ch in channels] for room, channels in raw.items()}
    except (OSError, ValueError, TypeError, AttributeError):
        log.warning("valve channel map %s unreadable; valve levels will be empty", target,
                    exc_info=True)
        return {}


def save_valve_channels(channels: dict[str, list[int]], path: Path | str) -> None:
    """Write the room -> channel map (import). In place, like the other data files."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(channels, indent=2, ensure_ascii=False), encoding="utf-8")


def map_from_devices(
    devices: list[dict], valve_channels: dict[str, list[int]] | None = None
) -> DeviceMap:
    thermostats: dict[str, str] = {}
    groups: dict[str, str] = {}
    actuator: str | None = None

    for device in devices:
        device_type = device.get("type") or ""
        name = (device.get("name") or "").strip()
        address = device.get("address") or ""

        if device_type.startswith(_WTH_TYPE_PREFIX) and name and address:
            thermostats[name] = address
        elif (
            device.get("interface") == "VirtualDevices"
            and device_type == "HmIP-HEATING"
        ):
            room = name.split(" INT")[0].strip() or name
            if room and address:
                groups[room] = address
        elif any(hint in device_type.upper() for hint in _ACTUATOR_HINTS):
            actuator = address or actuator

    channel_map = valve_channels or {}
    rooms = {
        room: RoomDevices(
            room=room,
            wth_address=address,
            group_address=groups.get(room),
            valve_channels=tuple(
                f"{actuator}:{ch}" for ch in channel_map.get(room, [])
            ) if actuator else (),
        )
        for room, address in thermostats.items()
    }
    return DeviceMap(rooms=rooms, actuator_address=actuator)


class CachedDeviceMap:
    """Builds a :class:`DeviceMap` lazily and refreshes it after *ttl* seconds."""

    def __init__(
        self, jsonrpc, *, ttl: float = 300.0,
        valve_channels: dict[str, list[int]] | None = None,
    ) -> None:
        self._jsonrpc = jsonrpc
        self._ttl = ttl
        self._valve_channels = valve_channels
        self._value: DeviceMap | None = None
        self._deadline = 0.0

    def get(self, *, force: bool = False) -> DeviceMap:
        if force or self._value is None or time.monotonic() >= self._deadline:
            self._value = map_from_devices(self._jsonrpc.list_devices(), self._valve_channels)
            self._deadline = time.monotonic() + self._ttl
        return self._value

    def invalidate(self) -> None:
        self._value = None

    def set_valve_channels(self, channels: dict[str, list[int]]) -> None:
        """Use a new room -> channel map from the next lookup on (import)."""
        self._valve_channels = channels
        self.invalidate()
