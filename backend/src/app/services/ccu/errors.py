"""Domain exceptions for the CCU service layer."""
from __future__ import annotations


class CcuError(RuntimeError):
    """Any failure while talking to the CCU (RPC fault, bad response, ...)."""


class CcuUnreachable(CcuError):
    """Network-level failure: timeout, connection refused, DNS, protocol error."""


class CcuBusy(CcuError):
    """Another background transfer is running; try again when it has finished."""


class CcuMethodError(CcuError):
    """The CCU rejected one call on a *valid* session (e.g. a TCL error for a
    method/address it can't serve). Retrying or re-logging-in can't help."""


class CcuValidationError(CcuError):
    """Caller passed an out-of-range value (setpoint, profile, mode, ...)."""


class RoomNotFound(CcuError):
    """No wall thermostat is known for the requested room."""

    def __init__(self, room: str) -> None:
        super().__init__(f"no thermostat for room {room!r}")
        self.room = room
