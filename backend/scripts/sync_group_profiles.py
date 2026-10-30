"""Copy weekly profiles from each wall thermostat into its heating group.

The app has only ever written profiles to the thermostats, so the CCU heating
groups hold stale plans -- and a group hands its setpoint to the thermostat
(2026-10-30: Arbeitszimmer at 23/17 °C instead of 24.5 °C). This script makes
the group match the thermostat, one profile day at a time, paced like the
profile transfer (4 s gap, stop at high CCU duty cycle, stop after 3 errors in
a row), each day confirmed by reading the group back.

Source is always the thermostat. By default only each room's ACTIVE profile is
synced (the one that actually runs); the other profiles are written to the
thermostat by the app when you switch to them.

Dry run unless --apply. Run in the backend container:

    docker compose exec backend python scripts/sync_group_profiles.py
    docker compose exec backend python scripts/sync_group_profiles.py --room Arbeitszimmer --day Fr --apply
    docker compose exec backend python scripts/sync_group_profiles.py --apply

Afterwards check with scripts/compare_group_profiles.py.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.deps import get_device_map, get_jsonrpc, get_xmlrpc
from app.services.ccu import group_profiles as gp
from app.services.ccu import schedule
from app.services.device_health import duty_limit, read_ccu_duty_cycle

PACE_SECONDS = 4.0
MAX_CONSECUTIVE_ERRORS = 3
DUTY_CHECK_EVERY = 4
DAY_DE = {"MONDAY": "Mo", "TUESDAY": "Di", "WEDNESDAY": "Mi", "THURSDAY": "Do",
          "FRIDAY": "Fr", "SATURDAY": "Sa", "SUNDAY": "So"}
DAY_ARG = {v.lower(): k for k, v in DAY_DE.items()} | {k.lower(): k for k in DAY_DE}


@dataclass
class Item:
    room: str
    group_address: str  # where the group keeps its profiles
    profile: int
    day: str
    blocks: list


def _transfer_running() -> bool:
    """The app's own background transfer writes to the same devices."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/system/climate/transfer",
                                    timeout=5) as resp:
            return bool(json.load(resp).get("running"))
    except Exception:
        return False


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_plan(xmlrpc, jsonrpc, rooms, profile_arg, all_profiles, day_arg) -> list[Item]:
    plan: list[Item] = []
    for room in rooms:
        if not room.group_address:
            print(f"  {room.room}: keine Heizgruppe -- übersprungen")
            continue
        dev_master = xmlrpc.get_paramset(room.thermostat_channel, "MASTER")
        address, grp_master = gp.read_group_master(jsonrpc, room.group_address)
        if not gp.has_profiles(grp_master):
            print(f"  {room.room}: Gruppe ohne Profilschlüssel -- übersprungen")
            continue
        if all_profiles:
            wanted = set(schedule.PROFILE_RANGE)
        elif profile_arg:
            wanted = {profile_arg}
        else:
            active = _num(xmlrpc.get_paramset(room.thermostat_channel, "VALUES")
                          .get("ACTIVE_PROFILE"))
            if active is None:
                print(f"  {room.room}: aktives Profil nicht lesbar -- übersprungen")
                continue
            wanted = {int(active)}
        for d in gp.diff_profiles(dev_master, grp_master):
            if d.profile not in wanted or (day_arg and d.day != day_arg):
                continue
            if not d.device:
                continue  # never copy an unprogrammed thermostat day
            plan.append(Item(room.room, address, d.profile, d.day, d.device))
    return plan


def apply(xmlrpc, jsonrpc, device_map, plan: list[Item]) -> None:
    errors_in_a_row = 0
    written = 0
    for index, item in enumerate(plan):
        if index:
            time.sleep(PACE_SECONDS)
        if index % DUTY_CHECK_EVERY == 0:
            duty = read_ccu_duty_cycle(jsonrpc)
            if duty is not None and duty >= duty_limit():
                print(f"\nFunkauslastung der CCU bei {duty} % -- angehalten. "
                      f"{len(plan) - index} Tag(e) offen; später erneut starten.")
                break
        label = f"{item.room} P{item.profile} {DAY_DE[item.day]}"
        try:
            gp.write_group_days(jsonrpc, item.group_address, item.profile,
                                {item.day: item.blocks})
            written += 1
            errors_in_a_row = 0
            print(f"  ok     {label}")
        except Exception as exc:
            errors_in_a_row += 1
            print(f"  FEHLER {label}: {exc}")
            if errors_in_a_row >= MAX_CONSECUTIVE_ERRORS:
                print(f"\n{MAX_CONSECUTIVE_ERRORS} Fehler hintereinander -- abgebrochen.")
                break

    print(f"\n{written} von {len(plan)} Tag(en) in die Gruppen geschrieben.")
    duty = read_ccu_duty_cycle(jsonrpc)
    print(f"Funkauslastung der CCU jetzt: {'–' if duty is None else f'{duty} %'}")
    print("\nSoll jetzt (Gerät / Gruppe):")
    for name in sorted({i.room for i in plan}):
        room = device_map.rooms[name]
        dev = _num(xmlrpc.get_paramset(room.thermostat_channel, "VALUES")
                   .get("SET_POINT_TEMPERATURE"))
        grp = _num(jsonrpc.get_paramset(gp.GROUP_INTERFACE, room.group_channel, "VALUES")
                   .get("SET_POINT_TEMPERATURE"))
        print(f"  {name:14} {dev} / {grp}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="schreiben (sonst nur Probelauf)")
    ap.add_argument("--room", help="nur dieser Raum")
    ap.add_argument("--day", help="nur dieser Wochentag (Mo..So)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--profile", type=int, choices=list(schedule.PROFILE_RANGE),
                       help="dieses Profil statt des aktiven")
    group.add_argument("--all-profiles", action="store_true", help="alle 6 Profile")
    args = ap.parse_args()

    day = None
    if args.day:
        day = DAY_ARG.get(args.day.lower())
        if not day:
            sys.exit(f"unbekannter Wochentag {args.day!r} (Mo..So)")

    device_map = get_device_map().get()
    rooms = [r for name, r in sorted(device_map.rooms.items())
             if not args.room or name.lower() == args.room.lower()]
    if not rooms:
        sys.exit(f"Raum {args.room!r} nicht gefunden")

    xmlrpc, jsonrpc = get_xmlrpc(), get_jsonrpc()
    print("Plan (Quelle: Thermostat -> Ziel: Heizgruppe):")
    plan = build_plan(xmlrpc, jsonrpc, rooms, args.profile, args.all_profiles, day)
    if not plan:
        print("  nichts zu tun -- die Gruppen stimmen mit den Thermostaten überein.")
        return
    for item in plan:
        print(f"  {item.room} P{item.profile} {DAY_DE[item.day]}: {gp.describe(item.blocks)}")

    if not args.apply:
        print(f"\nProbelauf -- nichts geschrieben. {len(plan)} Tag(e), "
              f"ca. {len(plan) * (PACE_SECONDS + 3):.0f} s mit --apply.")
        return
    if _transfer_running():
        sys.exit("\nDie App überträgt gerade Profile -- bitte warten, bis das fertig ist.")
    print()
    apply(xmlrpc, jsonrpc, device_map, plan)


if __name__ == "__main__":
    try:
        main()
    finally:
        # a short-lived script must not leave its CCU session dangling
        try:
            get_jsonrpc().logout()
        except Exception:
            pass
