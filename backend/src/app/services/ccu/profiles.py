"""Heating profile read/write and the direct device commands.

All of this is XML-RPC on the wall thermostat (``<wth>:1``):

* profiles live in the MASTER paramset as ``P{1..6}_{ENDTIME|TEMPERATURE}_{DAY}_{i}``
* ``ACTIVE_PROFILE`` / ``SET_POINT_TEMPERATURE`` / ``SET_POINT_MODE`` are single
  writable VALUES (note: ``CONTROL_MODE`` is read-only – never write it)
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from . import schedule
from .errors import CcuError, CcuValidationError

# The CCU applies a MASTER write asynchronously over RF and 505-lies on
# success, so we poll the read-back rather than checking once. A full-profile
# write (7 days) can take quite a while to settle on the device.
_WRITE_SETTLE_SECONDS = 1.5
_CONFIRM_POLL_SECONDS = 2.0
_CONFIRM_TIMEOUT_SECONDS = 25.0

SETPOINT_MIN = 4.5
SETPOINT_MAX = 30.5
MODE_MIN = 0
MODE_MAX = 3


@dataclass(frozen=True)
class TimeBlock:
    start: str  # "HH:MM"
    end: str
    setpoint: float


@dataclass
class WeekProfile:
    profile: int
    days: dict[str, list[TimeBlock]]  # lowercase weekday -> ordered blocks


def _blocks_to_dto(blocks: list[schedule.Block]) -> list[TimeBlock]:
    return [
        TimeBlock(
            start=schedule.min_to_hhmm(b.start),
            end=schedule.min_to_hhmm(b.end),
            setpoint=b.temp,
        )
        for b in blocks
    ]


def _week_from_master(master: dict, profile: int) -> WeekProfile:
    days = {
        day.lower(): _blocks_to_dto(schedule.blocks_from_master(master, profile, day))
        for day in schedule.DAYS
    }
    return WeekProfile(profile=profile, days=days)


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------
def read_all_profiles(xmlrpc, wth_address: str) -> dict[int, WeekProfile]:
    """One MASTER fetch -> all of P1..P6."""
    master = xmlrpc.get_paramset(f"{wth_address}:1", "MASTER")
    return {p: _week_from_master(master, p) for p in schedule.PROFILE_RANGE}


def read_profile(xmlrpc, wth_address: str, profile: int) -> WeekProfile:
    if profile not in schedule.PROFILE_RANGE:
        raise CcuValidationError(f"profile {profile} out of range 1..6")
    master = xmlrpc.get_paramset(f"{wth_address}:1", "MASTER")
    return _week_from_master(master, profile)


# ---------------------------------------------------------------------------
# profile edits (read-modify-write on MASTER, one day at a time)
# ---------------------------------------------------------------------------
def _day_blocks(master: dict, profile: int, day: str) -> list[schedule.Block]:
    blocks = schedule.blocks_from_master(master, profile, day)
    if blocks:
        return blocks
    # profile/day never programmed – seed one all-day block at the base temp
    try:
        base = float(master.get("TEMPERATURE_LOWERING", 17.0))
    except (TypeError, ValueError):
        base = 17.0
    return [schedule.Block(0, schedule.DAY_MINUTES, base)]


def _typed_set(payload: dict) -> list[dict]:
    """MASTER {key: number} -> Interface.putParamset set=[{name,type,value}].

    ENDTIME is an XML-RPC int, TEMPERATURE an XML-RPC double; value must be a
    string. Any other type name makes the CCU store the literal "<type> <value>".
    """
    out: list[dict] = []
    for key, value in payload.items():
        if "ENDTIME" in key:
            out.append({"name": key, "type": "int",
                        "value": str(round(float(value)))})
        else:
            out.append({"name": key, "type": "double", "value": str(float(value))})
    return out


def _mismatches(fresh: dict, want: dict) -> list[str]:
    bad = []
    for name, target in want.items():
        try:
            got = float(fresh[name])
        except (KeyError, TypeError, ValueError):
            bad.append(name)
            continue
        tolerance = 0.5 if "ENDTIME" in name else 0.05
        if abs(got - float(target)) > tolerance:
            bad.append(name)
    return bad


def day_differs(master: dict, blocks: list[schedule.Block],
                profile: int, day: str) -> bool:
    """True if the device MASTER does not already hold *blocks* for that
    profile/day. Empty/invalid block lists are reported as "no difference" so
    callers skip them."""
    try:
        want = schedule.master_from_blocks(blocks, profile, day.upper())
    except ValueError:
        return False
    return bool(_mismatches(master, want))


def write_days(
    xmlrpc, jsonrpc, wth_address: str, profile: int,
    day_blocks: dict[str, list[schedule.Block]],
) -> WeekProfile:
    """Write one or more days of a profile via JSON-RPC Interface.putParamset
    (the only path that works for HmIP MASTER), one putParamset per day (large
    `set` arrays are unreliable), then poll the read-back to confirm – the CCU
    returns a spurious error even on success."""
    channel = f"{wth_address}:1"
    try:
        per_day = {
            day.upper(): schedule.master_from_blocks(blocks, profile, day.upper())
            for day, blocks in day_blocks.items()
        }
    except ValueError as exc:
        raise CcuValidationError(str(exc)) from exc

    for sub in per_day.values():
        jsonrpc.put_paramset(channel, "MASTER", _typed_set(sub))

    want = {name: value for sub in per_day.values() for name, value in sub.items()}
    deadline = time.monotonic() + _CONFIRM_TIMEOUT_SECONDS
    time.sleep(_WRITE_SETTLE_SECONDS)
    while True:
        fresh = xmlrpc.get_paramset(channel, "MASTER")
        bad = _mismatches(fresh, want)
        if not bad:
            return _week_from_master(fresh, profile)
        if time.monotonic() >= deadline:
            raise CcuError(
                f"profile write not confirmed for P{profile}: "
                f"{len(bad)} value(s) still off, e.g. {bad[0]} "
                f"(wanted {want[bad[0]]}, device {fresh.get(bad[0])!r})"
            )
        time.sleep(_CONFIRM_POLL_SECONDS)


def _apply_day(
    xmlrpc, jsonrpc, wth_address: str, profile: int, day: str, transform,
) -> WeekProfile:
    channel = f"{wth_address}:1"
    day = day.upper()
    master = xmlrpc.get_paramset(channel, "MASTER")
    try:
        updated = transform(_day_blocks(master, profile, day))
    except ValueError as exc:
        raise CcuValidationError(str(exc)) from exc
    return write_days(xmlrpc, jsonrpc, wth_address, profile, {day: updated})


def copy_profile(
    xmlrpc, jsonrpc, src_wth: str, src_profile: int,
    dst_wth: str, dst_profile: int,
    *, from_day: str | None = None,
    to_day: str | None = None, to_days: list[str] | None = None,
) -> WeekProfile:
    """Copy onto another profile / room:

    - no ``from_day``            -> all 7 days into ``dst_profile``
    - ``from_day`` + ``to_day``  -> that one target day
    - ``from_day`` + ``to_days`` -> several target days (one write)

    Returns the resulting target ``WeekProfile``.
    """
    targets = to_days if to_days is not None else ([to_day] if to_day else None)

    if from_day is None:
        if targets:
            raise CcuValidationError("to_day / to_days require from_day")
        src_master = xmlrpc.get_paramset(f"{src_wth}:1", "MASTER")
        day_blocks = {
            day: _day_blocks(src_master, src_profile, day) for day in schedule.DAYS
        }
        return write_days(xmlrpc, jsonrpc, dst_wth, dst_profile, day_blocks)

    if not targets:
        raise CcuValidationError("from_day needs a to_day or to_days")

    src_master = xmlrpc.get_paramset(f"{src_wth}:1", "MASTER")
    blocks = _day_blocks(src_master, src_profile, from_day.upper())
    day_blocks = {d.upper(): blocks for d in targets}
    return write_days(xmlrpc, jsonrpc, dst_wth, dst_profile, day_blocks)


def edit_range(xmlrpc, jsonrpc, wth_address: str, profile: int, day: str,
               start: str, end: str, setpoint: float) -> WeekProfile:
    _check_setpoint(setpoint)
    return _apply_day(
        xmlrpc, jsonrpc, wth_address, profile, day,
        lambda blocks: schedule.overlay(
            blocks, schedule.hhmm_to_min(start), schedule.hhmm_to_min(end), setpoint
        ),
    )


def clear_range(xmlrpc, jsonrpc, wth_address: str, profile: int, day: str,
                start: str, end: str) -> WeekProfile:
    """Delete the block covering ``[start, end)`` – the gap inherits the
    previous block's setpoint."""
    return _apply_day(
        xmlrpc, jsonrpc, wth_address, profile, day,
        lambda blocks: schedule.remove_range(
            blocks, schedule.hhmm_to_min(start), schedule.hhmm_to_min(end)
        ),
    )


# ---------------------------------------------------------------------------
# direct device commands
# ---------------------------------------------------------------------------
def get_active_profile(xmlrpc, wth_address: str) -> int | None:
    try:
        value = xmlrpc.get_value(f"{wth_address}:1", "ACTIVE_PROFILE")
        return int(value) if value is not None else None
    except (CcuError, TypeError, ValueError):
        return None


def set_active_profile(xmlrpc, wth_address: str, profile: int) -> None:
    if profile not in schedule.PROFILE_RANGE:
        raise CcuValidationError(f"profile {profile} out of range 1..6")
    xmlrpc.set_value(f"{wth_address}:1", "ACTIVE_PROFILE", int(profile))


def set_active_profile_confirmed(
    xmlrpc, wth_address: str, profile: int,
    *, timeout: float = 8.0, poll: float = 1.0,
) -> bool:
    """Like :func:`set_active_profile`, but polls the read-back and reports
    whether it actually took effect, instead of trusting a single
    fire-and-forget ``setValue`` -- unlike every other write in this module,
    plain ``set_active_profile`` has no confirmation at all, and a switch that
    silently doesn't land leaves the device on the wrong profile slot."""
    if profile not in schedule.PROFILE_RANGE:
        raise CcuValidationError(f"profile {profile} out of range 1..6")
    if get_active_profile(xmlrpc, wth_address) == profile:
        return True
    xmlrpc.set_value(f"{wth_address}:1", "ACTIVE_PROFILE", int(profile))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(poll)
        if get_active_profile(xmlrpc, wth_address) == profile:
            return True
    return False


def set_setpoint(xmlrpc, wth_address: str, celsius: float) -> None:
    _check_setpoint(celsius)
    xmlrpc.set_value(f"{wth_address}:1", "SET_POINT_TEMPERATURE", float(celsius))


def set_mode(xmlrpc, wth_address: str, mode_code: int) -> None:
    """0=AUTO 1=MANU 2=PARTY 3=BOOST.

    HmIP asymmetry (verified on a real HmIP-WTH-1): the mode is *read* from
    ``SET_POINT_MODE`` but *written* via ``CONTROL_MODE`` – and only through
    ``putParamset`` on VALUES. ``setValue`` and writing ``SET_POINT_MODE`` are
    both silently ignored; ``CONTROL_MODE`` is flagged read-only but accepts
    the putParamset write anyway.
    """
    if not (MODE_MIN <= mode_code <= MODE_MAX):
        raise CcuValidationError(
            f"mode {mode_code} out of range {MODE_MIN}..{MODE_MAX}"
        )
    xmlrpc.put_paramset(f"{wth_address}:1", "VALUES", {"CONTROL_MODE": int(mode_code)})


def set_boost(xmlrpc, wth_address: str, active: bool) -> None:
    xmlrpc.set_value(f"{wth_address}:1", "BOOST_MODE", bool(active))


def _check_setpoint(celsius: float) -> None:
    if not (SETPOINT_MIN <= celsius <= SETPOINT_MAX):
        raise CcuValidationError(
            f"setpoint {celsius} outside {SETPOINT_MIN}..{SETPOINT_MAX} C"
        )
