"""Export and import of everything the app stores itself.

The export is one JSON document (see :func:`build_export`). Importing one is
strict: :func:`check` validates the whole document with the same rules the app
uses when editing (blocks tile 00:00..24:00, at most 13 per day, setpoints
4.5..30.5, profiles 1..6, ...) and collects *every* problem with its location;
nothing is written unless the document is completely valid. :func:`apply`
then replaces profile sets, profile names, the valve mapping and the
schedule of the automatic heating/cooling switch, and clears the
change history -- its before-states describe the thermostats before the import
and would no longer fit.

The CCU credentials are never part of an export, and an import never touches
them.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

from . import change_history, climate_schedule, profile_names, profile_sets
from .ccu import schedule
from .ccu.profiles import SETPOINT_MAX, SETPOINT_MIN

EXPORT_FORMAT = "ccu-dashboard-export"
EXPORT_VERSION = 1

_MODES = {"heating": "Heizen", "cooling": "Kühlen"}
_DAYS = {
    "monday": "Montag", "tuesday": "Dienstag", "wednesday": "Mittwoch",
    "thursday": "Donnerstag", "friday": "Freitag", "saturday": "Samstag",
    "sunday": "Sonntag",
}
_PROFILES = {str(p) for p in schedule.PROFILE_RANGE}
_NAME_MAX = 64
_VALVE_CHANNELS = range(1, 13)


def build_export(valve_channels: dict[str, list[int]]) -> dict:
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "profile_sets": profile_sets.load(),
        "profile_names": profile_names.load(),
        "valve_channels": valve_channels,
        "climate_schedule": climate_schedule.export(),
        "change_history": change_history.entries(),
    }


@dataclass
class ImportCheck:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rooms: int = 0          # rooms with stored profiles in the file
    profiles: int = 0       # room/mode/profile combinations
    names: int = 0
    valve_rooms: int = 0
    # "replace": file has a schedule, "clear": file has none set,
    # "keep": file predates the schedule (the current one stays)
    schedule: str = "keep"

    @property
    def valid(self) -> bool:
        return not self.errors


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_day(where: str, blocks: object, errors: list[str]) -> None:
    if not isinstance(blocks, list) or not blocks:
        errors.append(f"{where}: keine Zeitabschnitte")
        return
    parsed: list[schedule.Block] = []
    for index, block in enumerate(blocks, start=1):
        try:
            if not isinstance(block, dict):
                raise TypeError
            start = schedule.hhmm_to_min(block["start"])
            end = schedule.hhmm_to_min(block["end"])
            setpoint = block["setpoint"]
            if isinstance(setpoint, bool) or not isinstance(setpoint, int | float):
                raise TypeError
            parsed.append(schedule.Block(start, end, float(setpoint)))
        except (KeyError, TypeError, ValueError):
            errors.append(f"{where}, Abschnitt {index}: ungültig (erwartet start/end als "
                          f"HH:MM und setpoint als Zahl)")
            return
        if not SETPOINT_MIN <= float(setpoint) <= SETPOINT_MAX:
            errors.append(f"{where}, Abschnitt {index}: {setpoint} °C liegt außerhalb "
                          f"von {SETPOINT_MIN}–{SETPOINT_MAX} °C")
    if len(parsed) > schedule.MAX_SLOTS:
        errors.append(f"{where}: {len(parsed)} Zeitabschnitte, höchstens "
                      f"{schedule.MAX_SLOTS} möglich")
    try:
        schedule.validate_blocks(parsed)
    except ValueError:
        errors.append(f"{where}: Zeitabschnitte decken 00:00–24:00 nicht lückenlos "
                      f"und ohne Überschneidung ab")


def _check_profile_sets(data: object, result: ImportCheck) -> None:
    errors = result.errors
    if not isinstance(data, dict):
        errors.append("profile_sets: fehlt oder ist kein Objekt")
        return
    for room, entry in data.items():
        where = f"Raum „{room}“"
        if not isinstance(entry, dict):
            errors.append(f"{where}: kein Objekt")
            continue
        result.rooms += 1
        for key, value in entry.items():
            if key == "active_profile":
                if not isinstance(value, dict):
                    errors.append(f"{where}, aktives Profil: kein Objekt")
                    continue
                for mode, profile in value.items():
                    if mode not in _MODES:
                        errors.append(f"{where}, aktives Profil: unbekannter Modus „{mode}“")
                    elif not _is_int(profile) or profile not in schedule.PROFILE_RANGE:
                        errors.append(f"{where}, aktives Profil {_MODES[mode]}: "
                                      f"„{profile}“ ist kein Profil 1–6")
            elif key in _MODES:
                if not isinstance(value, dict):
                    errors.append(f"{where}, {_MODES[key]}: kein Objekt")
                    continue
                for profile, days in value.items():
                    at = f"{where}, {_MODES[key]}, P{profile}"
                    if profile not in _PROFILES:
                        errors.append(f"{where}, {_MODES[key]}: „{profile}“ ist kein Profil 1–6")
                        continue
                    if not isinstance(days, dict):
                        errors.append(f"{at}: kein Objekt")
                        continue
                    result.profiles += 1
                    for day, blocks in days.items():
                        if day not in _DAYS:
                            errors.append(f"{at}: unbekannter Tag „{day}“")
                            continue
                        _check_day(f"{at}, {_DAYS[day]}", blocks, errors)
            else:
                errors.append(f"{where}: unbekannter Eintrag „{key}“")


def _check_names(data: object, result: ImportCheck) -> None:
    if not isinstance(data, dict):
        result.errors.append("profile_names: fehlt oder ist kein Objekt")
        return
    for slot, name in data.items():
        if slot not in _PROFILES:
            result.errors.append(f"Profilname „{slot}“: kein Profil 1–6")
        elif not isinstance(name, str) or not name.strip() or len(name) > _NAME_MAX:
            result.errors.append(f"Profilname P{slot}: muss 1–{_NAME_MAX} Zeichen lang sein")
        else:
            result.names += 1


def _check_valves(data: object, result: ImportCheck) -> None:
    if not isinstance(data, dict):
        result.errors.append("valve_channels: fehlt oder ist kein Objekt")
        return
    for room, channels in data.items():
        if (not isinstance(channels, list)
                or not all(_is_int(c) and c in _VALVE_CHANNELS for c in channels)):
            result.errors.append(f"Ventil-Zuordnung „{room}“: erwartet eine Liste von "
                                 f"Kanalnummern 1–12")
        else:
            result.valve_rooms += 1


def _schedule_point(where: str, raw: object, errors: list[str]) -> None:
    if not isinstance(raw, dict) or set(raw) != {"day", "month", "time", "enabled"}:
        errors.append(f"{where}: erwartet day, month, time und enabled")
        return
    day, month, time, enabled = raw["day"], raw["month"], raw["time"], raw["enabled"]
    if not (_is_int(day) and _is_int(month) and isinstance(time, str)
            and isinstance(enabled, bool)):
        errors.append(f"{where}: day/month als Zahl, time als HH:MM, enabled als true/false")
        return
    try:
        climate_schedule.Point(day, month, time, enabled).validate(where)
    except ValueError as exc:
        errors.append(str(exc))


def _check_schedule(doc: dict, result: ImportCheck) -> None:
    if "climate_schedule" not in doc:
        result.warnings.append("Die Datei enthält keinen Zeitplan für das automatische "
                               "Umschalten (älterer Export) – der bestehende bleibt.")
        return
    data = doc["climate_schedule"]
    if not isinstance(data, dict) or set(data) != {"heating", "cooling"}:
        result.errors.append("climate_schedule: erwartet heating und cooling")
        return
    heating, cooling = data["heating"], data["cooling"]
    if heating is None and cooling is None:
        result.schedule = "clear"
        return
    if heating is None or cooling is None:
        result.errors.append("Zeitplan: heating und cooling müssen beide gesetzt oder beide "
                             "null sein")
        return
    before = len(result.errors)
    _schedule_point("Zeitplan „Auf Heizen“", heating, result.errors)
    _schedule_point("Zeitplan „Auf Kühlen“", cooling, result.errors)
    if len(result.errors) == before:
        if ((heating["day"], heating["month"], heating["time"])
                == (cooling["day"], cooling["month"], cooling["time"])):
            result.errors.append("Zeitplan: Heizen und Kühlen brauchen verschiedene Zeitpunkte")
        else:
            result.schedule = "replace"


def check(doc: object, known_rooms: list[str] | None) -> ImportCheck:
    """Validate an export document completely. *known_rooms* are the rooms the
    CCU has right now (None: unknown -- then no room warnings)."""
    result = ImportCheck()
    if not isinstance(doc, dict):
        result.errors.append("Die Datei enthält kein JSON-Objekt.")
        return result
    if doc.get("format") != EXPORT_FORMAT:
        result.errors.append("Die Datei ist kein Export dieser App (Feld „format“ fehlt "
                             "oder ist falsch).")
        return result
    if doc.get("version") != EXPORT_VERSION:
        result.errors.append(f"Export-Version {doc.get('version')!r} wird nicht unterstützt "
                             f"(erwartet {EXPORT_VERSION}).")
        return result

    _check_profile_sets(doc.get("profile_sets"), result)
    _check_names(doc.get("profile_names"), result)
    _check_valves(doc.get("valve_channels"), result)
    _check_schedule(doc, result)

    if known_rooms is None:
        result.warnings.append("Die Räume konnten nicht mit der CCU abgeglichen werden.")
    elif result.valid:
        known = set(known_rooms)
        in_file = set(doc["profile_sets"])
        for room in sorted(in_file - known):
            result.warnings.append(f"„{room}“ hat keinen Thermostat in der CCU – die Profile "
                                   f"werden trotzdem gespeichert.")
        for room in sorted(known - in_file):
            result.warnings.append(f"Für „{room}“ enthält die Datei keine Profile – die bisher "
                                   f"gespeicherten Profile dieses Raums werden entfernt.")
        for room in sorted(set(doc["valve_channels"]) - known):
            result.warnings.append(f"Ventil-Zuordnung für „{room}“: kein Thermostat in der CCU.")
    return result


def save_pre_import_backup(valve_channels: dict[str, list[int]]) -> str:
    """Write the current state, in export format, next to the data files.
    Returns the file name."""
    now = datetime.now(UTC)
    name = f"vor-import-{now:%Y-%m-%d-%H%M%S}.json"
    directory = os.path.dirname(profile_sets._PATH) or "."
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
        json.dump(build_export(valve_channels), handle, indent=2, ensure_ascii=False)
    return name


def apply(doc: dict, checked: ImportCheck) -> None:
    """Replace the stored data with a document :func:`check` found valid.
    The valve mapping is written by the caller (it knows the file's path).
    The schedule starts fresh: points up to now count as handled, so an import
    never switches the mode by itself."""
    profile_sets.replace_all(doc["profile_sets"])
    profile_names.replace_all(doc["profile_names"])
    change_history.clear()
    if checked.schedule == "replace":
        points = {
            key: climate_schedule.Point(raw["day"], raw["month"], raw["time"], raw["enabled"])
            for key, raw in doc["climate_schedule"].items()
        }
        climate_schedule.configure(points["heating"], points["cooling"])
    elif checked.schedule == "clear":
        climate_schedule.clear()
