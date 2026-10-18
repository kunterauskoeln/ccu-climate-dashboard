"""API request bodies and response wrappers (Pydantic).

The domain DTOs (``RoomState``, ``WeekProfile``, ``TimeBlock`` from
``app.services.ccu``) are used directly as response models – FastAPI builds
the OpenAPI schema from those dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.services.ccu.profiles import WeekProfile

SETPOINT_MIN = 4.5
SETPOINT_MAX = 30.5


class RoomPatch(BaseModel):
    """Partial room update – every field optional, at least one required."""

    setpoint: float | None = Field(None, ge=SETPOINT_MIN, le=SETPOINT_MAX)
    mode: int | None = Field(None, ge=0, le=3, description="0=AUTO 1=MANU 2=PARTY 3=BOOST")
    active_profile: int | None = Field(None, ge=1, le=6)
    boost: bool | None = None

    def is_empty(self) -> bool:
        return (
            self.setpoint is None
            and self.mode is None
            and self.active_profile is None
            and self.boost is None
        )


class BlockEdit(BaseModel):
    start: str = Field(examples=["06:00"], pattern=r"^\d{1,2}:\d{2}$")
    end: str = Field(examples=["09:00"], pattern=r"^\d{1,2}:\d{2}$")
    setpoint: float = Field(ge=SETPOINT_MIN, le=SETPOINT_MAX)


class BlockClear(BaseModel):
    start: str = Field(pattern=r"^\d{1,2}:\d{2}$")
    end: str = Field(pattern=r"^\d{1,2}:\d{2}$")


class ProfileNameBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ProfileCopy(BaseModel):
    """Copy the schedule of the source (room/profile from the URL) somewhere.

    - no days          -> copy all 7 days into ``to_profile``
    - from_day + to_day -> copy just that one day
    ``to_room`` defaults to the source room.
    """

    to_room: str | None = None
    to_profile: int = Field(ge=1, le=6)
    from_day: str | None = None
    to_day: str | None = None
    to_days: list[str] | None = None


@dataclass
class DeviceInfo:
    id: str | None
    name: str | None
    address: str | None
    type: str | None
    interface: str | None


@dataclass
class ProfilesResponse:
    active: int | None
    profiles: dict[int, WeekProfile]


@dataclass
class HistoryEntry:
    id: str
    at: str                 # ISO 8601, UTC
    kind: str               # "profile" | "name"
    mode: str | None        # profile entries: "heating" / "cooling"
    room: str | None        # profile entries only
    profile: int
    summary: str


@dataclass
class RestoreResult:
    names: int              # profile names put back (done immediately)
    profiles: int           # room profiles being put back
    days: int               # thermostat days written in this run
    deferred: int           # days left for another "reset" (over the per-run cap)
    background: bool        # True: days are being written, see /system/climate/transfer


class ApartmentProfile(BaseModel):
    """Switch every room to the same profile slot."""

    profile: int = Field(ge=1, le=6)


@dataclass
class ApartmentSwitchResult:
    rooms: int          # rooms being switched in this run
    skipped: int        # rooms already on that profile
    deferred: int       # rooms over the per-run write budget (tap again)
    background: bool    # True: switching, see /system/climate/transfer


class ClimatePatch(BaseModel):
    cooling: bool


@dataclass
class ClimateState:
    cooling: bool
    actuator: str | None


class ClimateSchedulePoint(BaseModel):
    """A yearly point in time (local time, see SCHEDULE_TZ)."""

    day: int = Field(ge=1, le=31)
    month: int = Field(ge=1, le=12)
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    enabled: bool  # switch automatically at this point


class ClimateSchedulePut(BaseModel):
    heating: ClimateSchedulePoint  # switch to heating at this point every year
    cooling: ClimateSchedulePoint  # switch to cooling at this point every year


@dataclass
class ClimateScheduleNext:
    at: str        # ISO with offset
    cooling: bool


@dataclass
class ClimateScheduleState:
    heating: dict | None       # {"day", "month", "time", "enabled"}
    cooling: dict | None
    next: ClimateScheduleNext | None
    last_run: dict | None      # {"at", "due", "cooling", "result", "message"}
    timezone: str


class AbsencePut(BaseModel):
    """Plan an absence (or change the running one). Times as ISO 8601; without
    an offset they are local time (SCHEDULE_TZ). ``start`` null/empty: now."""

    profile: int = Field(ge=1, le=6)
    start: str | None = None
    end: str
