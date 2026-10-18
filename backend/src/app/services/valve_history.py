"""Valve position history for the chart (Ventilverlauf).

The dew point monitor reads every room's valve once a minute anyway; every
5th round it hands the values to :func:`record`. Samples are kept for
``KEEP_HOURS`` (72 h) in ``data/valve_history.json`` so a restart does not
lose the curve:

    {"samples": [[epoch_seconds, {"Bad": 0.4, "Flur": 0.0, ...}], ...]}

:func:`series` turns them into one column per room (percent) for the chart,
with ``None`` inserted where the recording paused (server off) so the lines
break instead of bridging the gap.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_PATH = os.getenv("VALVE_HISTORY_FILE", "/app/app/data/valve_history.json")
STEP_SECONDS = 300
KEEP_HOURS = 72
_lock = threading.Lock()
_samples: list[tuple[float, dict[str, float]]] | None = None   # loaded lazily


def _load() -> list[tuple[float, dict[str, float]]]:
    global _samples
    if _samples is None:
        try:
            with open(_PATH, encoding="utf-8") as handle:
                raw = json.load(handle).get("samples", [])
            _samples = [(float(t), {str(k): float(v) for k, v in values.items()})
                        for t, values in raw if isinstance(values, dict)]
        except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
            _samples = []
    return _samples


def _save(samples: list[tuple[float, dict[str, float]]]) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"samples": [[t, v] for t, v in samples]}, handle, ensure_ascii=False,
                  separators=(",", ":"))
    os.replace(tmp, _PATH)


def record(valves: dict[str, float | None], now: float | None = None) -> None:
    """Store one sample (rooms without a reading are left out)."""
    now = now if now is not None else time.time()
    values = {room: round(v, 3) for room, v in valves.items() if v is not None}
    with _lock:
        samples = _load()
        samples.append((now, values))
        cutoff = now - KEEP_HOURS * 3600
        while samples and samples[0][0] < cutoff:
            samples.pop(0)
        try:
            _save(samples)
        except OSError:
            log.warning("valve history not saved", exc_info=True)


@dataclass
class Series:
    times: list[float] = field(default_factory=list)          # epoch seconds
    rooms: dict[str, list[float | None]] = field(default_factory=dict)  # percent


def series(hours: float, now: float | None = None) -> Series:
    now = now if now is not None else time.time()
    with _lock:
        samples = [s for s in _load() if s[0] >= now - hours * 3600]
    names = sorted({room for _, values in samples for room in values})
    out = Series(rooms={name: [] for name in names})
    previous: float | None = None
    for t, values in samples:
        if previous is not None and t - previous > 3 * STEP_SECONDS:
            # recording paused: a break in every line
            out.times.append(previous + STEP_SECONDS)
            for name in names:
                out.rooms[name].append(None)
        out.times.append(t)
        for name in names:
            v = values.get(name)
            out.rooms[name].append(round(v * 100) if v is not None else None)
        previous = t
    return out


def reset() -> None:
    """Forget the in-memory copy (tests)."""
    global _samples
    with _lock:
        _samples = None
