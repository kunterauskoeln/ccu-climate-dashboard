"""Pure schedule math for HmIP-WTH-1 weekly heating profiles.

The CCU stores one ``(profile, weekday)`` schedule as up to 13 slots in the
device MASTER paramset (channel ``:1``)::

    P{p}_ENDTIME_{DAY}_{i}      int   – cumulative minutes from midnight (0..1440)
    P{p}_TEMPERATURE_{DAY}_{i}  float – setpoint in degrees Celsius

Slots are filled from ``i = 1``. The first slot whose ``ENDTIME`` is 1440
closes the day; any further slots are padding (``ENDTIME = 1440``,
``TEMPERATURE`` = the last active setpoint).

This module converts between that wire format and a clean, contiguous list of
:class:`Block` objects covering 00:00..24:00, and provides the overlay/clear
operations used when the user edits a single time range. No CCU access, no IO.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

DAYS: tuple[str, ...] = (
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY",
)
DAY_MINUTES = 1440
MAX_SLOTS = 13
PROFILE_RANGE = range(1, 7)  # P1..P6 (verified against a real HmIP-WTH-1)


@dataclass(frozen=True)
class Block:
    """A single setpoint segment, ``start``/``end`` in minutes from midnight."""

    start: int
    end: int
    temp: float

    def __post_init__(self) -> None:
        if not (0 <= self.start < self.end <= DAY_MINUTES):
            raise ValueError(f"invalid block bounds: {self.start}..{self.end}")


# ---------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------
def hhmm_to_min(value: str) -> int:
    try:
        hours_str, minutes_str = value.split(":")
        hours, minutes = int(hours_str), int(minutes_str)
    except (ValueError, AttributeError):
        raise ValueError(f"expected HH:MM, got {value!r}") from None
    if hours < 0 or not (0 <= minutes < 60):
        raise ValueError(f"invalid HH:MM value: {value!r}")
    total = hours * 60 + minutes
    if not (0 <= total <= DAY_MINUTES):
        raise ValueError(f"time out of range: {value!r}")
    return total


def min_to_hhmm(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


# ---------------------------------------------------------------------------
# validation / normalisation
# ---------------------------------------------------------------------------
def validate_blocks(blocks: list[Block]) -> None:
    """Raise ``ValueError`` unless *blocks* tile 00:00..24:00 with no gaps."""
    if not blocks:
        raise ValueError("schedule has no blocks")
    if blocks[0].start != 0:
        raise ValueError("schedule must start at 00:00")
    if blocks[-1].end != DAY_MINUTES:
        raise ValueError("schedule must end at 24:00")
    for current, following in pairwise(blocks):
        if current.end != following.start:
            raise ValueError(f"gap or overlap at {min_to_hhmm(current.end)}")


def _coalesce(blocks: list[Block]) -> list[Block]:
    merged: list[Block] = []
    for block in blocks:
        if block.start == block.end:
            continue
        if merged and merged[-1].temp == block.temp and merged[-1].end == block.start:
            merged[-1] = Block(merged[-1].start, block.end, block.temp)
        else:
            merged.append(block)
    return merged


def _require(profile: int, day: str) -> str:
    if profile not in PROFILE_RANGE:
        raise ValueError(f"profile {profile} out of range 1..6")
    day = day.upper()
    if day not in DAYS:
        raise ValueError(f"unknown day {day!r}")
    return day


# ---------------------------------------------------------------------------
# wire format <-> blocks
# ---------------------------------------------------------------------------
def blocks_from_master(master: dict, profile: int, day: str) -> list[Block]:
    """Extract the contiguous block list for one profile/day from a MASTER dump.

    Returns ``[]`` if the profile/day is not present in *master* at all.
    """
    day = _require(profile, day)
    prefix = f"P{profile}_"
    blocks: list[Block] = []
    prev_end = 0

    for index in range(1, MAX_SLOTS + 1):
        end_key = f"{prefix}ENDTIME_{day}_{index}"
        temp_key = f"{prefix}TEMPERATURE_{day}_{index}"
        if end_key not in master or temp_key not in master:
            break

        end = round(float(master[end_key]))
        temp = float(master[temp_key])

        if end <= prev_end:
            break  # padding slot / end of the active chain

        blocks.append(Block(prev_end, min(end, DAY_MINUTES), temp))
        prev_end = end
        if end >= DAY_MINUTES:
            break

    if not blocks:
        return []
    if blocks[-1].end != DAY_MINUTES:
        # last programmed slot stops before midnight – hold its setpoint
        blocks.append(Block(blocks[-1].end, DAY_MINUTES, blocks[-1].temp))
    return _coalesce(blocks)


def master_from_blocks(blocks: list[Block], profile: int, day: str) -> dict:
    """Render a full-day block list back to the 13-slot MASTER key/value dict."""
    day = _require(profile, day)
    blocks = _coalesce(list(blocks))
    validate_blocks(blocks)
    if len(blocks) > MAX_SLOTS:
        raise ValueError(
            f"{len(blocks)} blocks exceed the {MAX_SLOTS}-slot limit for one day"
        )

    prefix = f"P{profile}_"
    out: dict = {}
    hold_temp = blocks[-1].temp
    for index in range(1, MAX_SLOTS + 1):
        if index <= len(blocks):
            block = blocks[index - 1]
            out[f"{prefix}ENDTIME_{day}_{index}"] = int(block.end)
            out[f"{prefix}TEMPERATURE_{day}_{index}"] = float(block.temp)
            hold_temp = block.temp
        else:
            out[f"{prefix}ENDTIME_{day}_{index}"] = DAY_MINUTES
            out[f"{prefix}TEMPERATURE_{day}_{index}"] = float(hold_temp)
    return out


# ---------------------------------------------------------------------------
# edit operations
# ---------------------------------------------------------------------------
def overlay(blocks: list[Block], start: int, end: int, temp: float) -> list[Block]:
    """Return *blocks* with ``[start, end)`` forced to *temp*.

    Overlapping existing blocks are trimmed; adjacent equal-temperature blocks
    are coalesced. *blocks* must already tile the whole day.
    """
    if not (0 <= start < end <= DAY_MINUTES):
        raise ValueError(f"invalid range {start}..{end}")
    validate_blocks(blocks)

    result: list[Block] = []
    for block in blocks:
        if block.end <= start or block.start >= end:
            result.append(block)
            continue
        if block.start < start:
            result.append(Block(block.start, start, block.temp))
        if block.end > end:
            result.append(Block(end, block.end, block.temp))
    result.append(Block(start, end, temp))
    result.sort(key=lambda block: block.start)
    return _coalesce(result)


def remove_range(blocks: list[Block], start: int, end: int) -> list[Block]:
    """Delete the segment ``[start, end)``: fill it with the setpoint of the
    block right before it (or right after, if it starts the day), then coalesce.
    """
    if not (0 <= start < end <= DAY_MINUTES):
        raise ValueError(f"invalid range {start}..{end}")
    validate_blocks(blocks)

    before = [b for b in blocks if b.end <= start]
    after = [b for b in blocks if b.start >= end]
    fill = (
        before[-1].temp if before
        else after[0].temp if after
        else blocks[0].temp
    )
    return overlay(blocks, start, end, fill)
