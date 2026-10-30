"""Read-only check: does each room's heating group hold the same weekly
profiles as its wall thermostat?

The app writes profiles to the thermostat only, so the group copies go stale
(saving a group in the CCU WebUI would push its stale plan onto the devices).

Nothing is written to the CCU. Run in the backend container:

    docker compose exec backend python scripts/compare_group_profiles.py
    docker compose exec backend python scripts/compare_group_profiles.py --details
    docker compose exec backend python scripts/compare_group_profiles.py --room Arbeitszimmer
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.deps import get_device_map, get_jsonrpc, get_xmlrpc
from app.services.ccu import group_profiles as gp
from app.services.ccu import schedule
from app.services.climate_schedule import tz

DAY_DE = {"MONDAY": "Mo", "TUESDAY": "Di", "WEDNESDAY": "Mi", "THURSDAY": "Do",
          "FRIDAY": "Fr", "SATURDAY": "Sa", "SUNDAY": "So"}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value) -> str:
    return "–" if value is None else f"{value:g}"


def check_room(xmlrpc, jsonrpc, room, now: datetime, details: bool) -> int:
    print(f"== {room.room}  (Gerät {room.wth_address}, Gruppe {room.group_address or '–'})")
    if not room.group_address:
        print("   keine Heizgruppe gefunden -- nichts zu vergleichen\n")
        return 0

    dev_master = xmlrpc.get_paramset(room.thermostat_channel, "MASTER")
    dev_values = xmlrpc.get_paramset(room.thermostat_channel, "VALUES")
    grp_values = jsonrpc.get_paramset(gp.GROUP_INTERFACE, room.group_channel, "VALUES")
    grp_address, grp_master = gp.read_group_master(jsonrpc, room.group_address)

    dev_active = _num(dev_values.get("ACTIVE_PROFILE"))
    grp_active = _num(grp_values.get("ACTIVE_PROFILE"))
    print(f"   aktives Profil: Gerät {_fmt(dev_active)}, Gruppe {_fmt(grp_active)}"
          f"   | Soll jetzt: Gerät {_fmt(_num(dev_values.get('SET_POINT_TEMPERATURE')))}, "
          f"Gruppe {_fmt(_num(grp_values.get('SET_POINT_TEMPERATURE')))}")

    if not gp.has_profiles(grp_master):
        keys = sorted(grp_master)
        print(f"   Gruppe {grp_address} MASTER enthält keine P1_…-Profilschlüssel "
              f"({len(keys)} Schlüssel), z. B.: {', '.join(keys[:15]) or '(leer)'}\n")
        return 0

    day = schedule.DAYS[now.weekday()]
    minute = now.hour * 60 + now.minute
    for label, active, master in (("Gerät", dev_active, dev_master),
                                  ("Gruppe", grp_active, grp_master)):
        if active is not None:
            p = int(active)
            blocks = schedule.blocks_from_master(master, p, day)
            print(f"   Plan jetzt ({DAY_DE[day]} {now:%H:%M}) laut {label} P{p}: "
                  f"{_fmt(gp.setpoint_at(blocks, minute))}")

    diffs = gp.diff_profiles(dev_master, grp_master)
    if not diffs:
        print("   alle 6 Profile identisch\n")
        return 0

    by_profile: dict[int, list[str]] = {}
    for d in diffs:
        by_profile.setdefault(d.profile, []).append(DAY_DE[d.day])
    for p, days in by_profile.items():
        print(f"   P{p} weicht ab: {' '.join(days)}")
    for d in diffs:
        if details or (dev_active is not None and d.profile == int(dev_active)):
            print(f"     P{d.profile} {DAY_DE[d.day]}  Gerät : {gp.describe(d.device)}")
            print(f"     P{d.profile} {DAY_DE[d.day]}  Gruppe: {gp.describe(d.group)}")
    print()
    return len(diffs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", help="nur diesen Raum prüfen")
    ap.add_argument("--details", action="store_true",
                    help="Zeitabschnitte aller abweichenden Tage zeigen "
                         "(sonst nur für das aktive Profil)")
    args = ap.parse_args()

    device_map = get_device_map().get()
    xmlrpc, jsonrpc = get_xmlrpc(), get_jsonrpc()
    now = datetime.now(tz())
    rooms = [r for name, r in sorted(device_map.rooms.items())
             if not args.room or name.lower() == args.room.lower()]
    if not rooms:
        sys.exit(f"Raum {args.room!r} nicht gefunden")

    total = 0
    for room in rooms:
        try:
            total += check_room(xmlrpc, jsonrpc, room, now, args.details)
        except Exception as exc:
            print(f"   FEHLER beim Lesen: {exc}\n")
    print(f"Zusammen {total} abweichende Profiltage. Es wurde nichts geschrieben.")


if __name__ == "__main__":
    try:
        main()
    finally:
        # a short-lived script must not leave its CCU session dangling
        try:
            get_jsonrpc().logout()
        except Exception:
            pass
