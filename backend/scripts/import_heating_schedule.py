"""Import a real heating schedule into ALL 6 profiles of one room's HEATING
set (store only -- app.services.profile_sets -- never the devices).

Input format::

    {
      "profil": "Standardprofil (<Raum>)",
      "einheit": "°C",
      "basistemperatur": 16.5,
      "zeitplan": {
        "montag": [{"von": "00:00", "bis": "07:30", "temperatur": 16.5}, ...],
        "dienstag": [...], "mittwoch": [...], "donnerstag": [...],
        "freitag": [...], "samstag": [...], "sonntag": [...]
      }
    }

Each day's blocks must tile 00:00..24:00 with no gaps/overlaps (validated
with the same rules the app itself uses to write a profile) and fit the
13-slot-per-day limit.

Always store-only, regardless of the current system mode -- this never
touches a thermostat. The heating set only reaches the devices the normal
way: the next real switch to heating (app.services.profile_transfer), for
each room's currently active profile.

Run in the backend container:

    docker compose exec backend python scripts/import_heating_schedule.py Ankleide /tmp/ankleide.json
    docker compose exec backend python scripts/import_heating_schedule.py --apply Ankleide /tmp/ankleide.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.deps import get_device_map, get_jsonrpc
from app.services import profile_sets
from app.services.ccu import schedule

_DE_DAYS = {
    "montag": "monday", "dienstag": "tuesday", "mittwoch": "wednesday",
    "donnerstag": "thursday", "freitag": "friday", "samstag": "saturday",
    "sonntag": "sunday",
}


def convert(raw: dict) -> dict[str, list[dict]]:
    """German zeitplan -> {english weekday: [{"start","end","setpoint"}, ...]}."""
    zeitplan = raw.get("zeitplan") or {}
    missing = [d for d in _DE_DAYS if d not in zeitplan]
    if missing:
        raise ValueError(f"missing day(s) in zeitplan: {missing}")

    out: dict[str, list[dict]] = {}
    for de_day, en_day in _DE_DAYS.items():
        blocks = [
            {"start": b["von"], "end": b["bis"], "setpoint": float(b["temperatur"])}
            for b in zeitplan[de_day]
        ]
        # fail loudly here (bad gap/overlap/slot count), not on the next
        # mode switch -- Block() itself also rejects a malformed HH:MM range.
        native = [
            schedule.Block(schedule.hhmm_to_min(b["start"]), schedule.hhmm_to_min(b["end"]),
                          b["setpoint"])
            for b in blocks
        ]
        schedule.validate_blocks(native)
        if len(native) > schedule.MAX_SLOTS:
            raise ValueError(
                f"{en_day}: {len(native)} blocks exceed the {schedule.MAX_SLOTS}-slot limit"
            )
        out[en_day] = blocks
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("room")
    ap.add_argument("json_file")
    ap.add_argument("--apply", action="store_true", help="write the store (default: dry run)")
    args = ap.parse_args()

    device_map = get_device_map().get()
    if args.room not in device_map.rooms:
        sys.exit(f"unknown room {args.room!r}; known: {device_map.room_names}")

    with open(args.json_file, encoding="utf-8") as handle:
        raw = json.load(handle)

    days = convert(raw)

    print(f"# {raw.get('profil', args.json_file)} -> {args.room} (heating, all "
         f"{len(schedule.PROFILE_RANGE)} profiles)")
    for day in schedule.DAYS:
        blocks = days[day.lower()]
        print(f"  {day.lower():10} " +
             " | ".join(f"{b['start']}-{b['end']}@{b['setpoint']}" for b in blocks))

    if not args.apply:
        print("\ndry run -- nothing written. Re-run with --apply.")
        return

    for profile in schedule.PROFILE_RANGE:
        profile_sets.put_profile(args.room, False, profile, days)  # False = heating
    print(f"\ndone: P1..P{max(schedule.PROFILE_RANGE)} of {args.room!r} (heating) "
         f"all set to this schedule. Store only -- devices untouched.")


if __name__ == "__main__":
    try:
        main()
    finally:
        # short-lived script -- must not leave a JSON-RPC session dangling on
        # the CCU (limited concurrent sessions; see the other scripts' note).
        try:
            get_jsonrpc().logout()
        except Exception:
            pass
