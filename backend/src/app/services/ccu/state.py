"""Room status assembled from the verified datapoint sources.

    device ``:1`` VALUES (XML-RPC, typed)  -> temp / setpoint / humidity / mode /
                                              active profile / window / boost /
                                              heating-cooling
    device ``:0`` VALUES (XML-RPC)         -> battery / voltage / RSSI / reachable
    heating group ``:1`` VALUES (JSON-RPC) -> valve LEVEL (only place it exists)

``full=False`` reads just ``:1`` – enough for the room overview and much cheaper.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .errors import CcuError
from .mapping import RoomDevices

_MODE_NAMES = {0: "AUTO", 1: "MANU", 2: "PARTY", 3: "BOOST"}


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    number = _as_float(value)
    return round(number) if number is not None else None


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in ("", "0", "false")


@dataclass
class RoomState:
    room: str
    actual_temperature: float | None
    set_temperature: float | None
    humidity: int | None
    mode_code: int
    mode: str
    active_profile: int | None
    window_open: bool
    boost: bool
    cooling: bool
    valve: float | None = None
    battery_low: bool = False
    voltage: float | None = None
    rssi: int | None = None
    reachable: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def read_state(
    xmlrpc,
    jsonrpc,
    room: RoomDevices,
    *,
    full: bool = True,
    valve: bool | None = None,
) -> RoomState:
    """``full`` adds the maintenance channel (battery/RSSI/reachable) and the
    valve level. ``valve`` overrides just the valve part: the room list wants
    the level (a local HmIPServer read per circuit) but not the maintenance extras.
    ``jsonrpc`` is kept for the callers' signature; the valve no longer needs it."""
    values = xmlrpc.get_paramset(room.thermostat_channel, "VALUES")

    mode_code = _as_int(values.get("SET_POINT_MODE")) or 0
    state = RoomState(
        room=room.room,
        actual_temperature=_as_float(values.get("ACTUAL_TEMPERATURE")),
        set_temperature=_as_float(values.get("SET_POINT_TEMPERATURE")),
        humidity=_as_int(values.get("HUMIDITY")),
        mode_code=mode_code,
        mode=_MODE_NAMES.get(mode_code, f"UNKNOWN_{mode_code}"),
        active_profile=_as_int(values.get("ACTIVE_PROFILE")),
        window_open=_as_bool(values.get("WINDOW_STATE")),
        boost=_as_bool(values.get("BOOST_MODE")),
        cooling=_as_bool(values.get("HEATING_COOLING")),
    )

    want_valve = full if valve is None else valve

    if full:
        _read_maintenance(xmlrpc, room, state)
    if want_valve:
        _read_valve(xmlrpc, room, state)
    return state


def _read_maintenance(xmlrpc, room: RoomDevices, state: RoomState) -> None:
    try:
        maint = xmlrpc.get_paramset(room.maintenance_channel, "VALUES")
        state.battery_low = _as_bool(maint.get("LOW_BAT"))
        state.voltage = _as_float(maint.get("OPERATING_VOLTAGE"))
        state.rssi = _as_int(maint.get("RSSI_DEVICE"))
        state.reachable = not _as_bool(maint.get("UNREACH"))
    except CcuError:
        pass  # maintenance channel optional – status is still useful without it


def _read_valve(xmlrpc, room: RoomDevices, state: RoomState) -> None:
    """Mean LEVEL over the room's floor-heating circuits (actuator channels).

    The heating group's own ``LEVEL`` stays 0 on this installation, so the real
    valve position is read from the FALMOT channels the room is linked to."""
    levels: list[float] = []
    for address in room.valve_channels:
        try:
            level = _as_float(xmlrpc.get_paramset(address, "VALUES").get("LEVEL"))
        except CcuError:
            continue  # valve level is a nice-to-have
        if level is not None:
            levels.append(level)
    if levels:
        state.valve = sum(levels) / len(levels)
