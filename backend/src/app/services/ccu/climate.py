"""System-wide heating vs cooling, on the HmIP-FALMOT-C12 actuator (channel :0).

``HEATING_COOLING`` ENUM: 0 = HEATING, 1 = COOLING.
"""
from __future__ import annotations

import time

from .errors import CcuError

# The FALMOT applies a config change over RF – the read-back can lag several
# seconds, so we poll rather than check once.
_POLL_SECONDS = 1.0
_CONFIRM_TIMEOUT = 15.0


def _current(xmlrpc, channel: str) -> int | None:
    try:
        return int(xmlrpc.get_value(channel, "HEATING_COOLING"))
    except (CcuError, TypeError, ValueError):
        return None


def _confirm(xmlrpc, channel: str, target: int) -> bool:
    deadline = time.monotonic() + _CONFIRM_TIMEOUT
    while True:
        time.sleep(_POLL_SECONDS)
        if _current(xmlrpc, channel) == target:
            return True
        if time.monotonic() >= deadline:
            return False


def get_cooling(xmlrpc, actuator_channel: str | None) -> bool:
    if not actuator_channel:
        return False
    try:
        value = xmlrpc.get_value(actuator_channel, "HEATING_COOLING")
    except CcuError:
        return False
    try:
        return bool(int(value))
    except (TypeError, ValueError):
        return str(value).upper() == "COOLING"


def set_cooling(xmlrpc, actuator_channel: str, cooling: bool) -> bool:
    """Switch the whole system to cooling / heating.

    Sends the write both ways (some HmIP datapoints ignore ``setValue``), then
    polls the actuator for up to ~15 s before giving up. Raises ``CcuError``
    only if the switch is still not reflected after that.
    """
    target = 1 if cooling else 0
    if _current(xmlrpc, actuator_channel) == target:
        return cooling

    for write in (
        lambda: xmlrpc.set_value(actuator_channel, "HEATING_COOLING", target),
        lambda: xmlrpc.put_paramset(
            actuator_channel, "VALUES", {"HEATING_COOLING": target}
        ),
    ):
        try:
            write()
        except CcuError:
            pass

    if _confirm(xmlrpc, actuator_channel, target):
        return cooling
    raise CcuError(
        f"switch to {'cooling' if cooling else 'heating'} was not confirmed by the actuator"
    )
