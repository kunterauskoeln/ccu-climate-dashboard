"""Prepare a safe cooling -> heating switch test (STORE ONLY, no thermostat writes).

While the system is in COOLING, this
  1. keeps the current device schedules as the stored *cooling* set (for rooms
     that have none yet -- read-only on the CCU), and
  2. replaces the stored *heating* set of the chosen rooms with a flat setpoint
     (default 20.0 C) for all 6 profiles x 7 days.

Nothing is written to the CCU, so cooling is not triggered. On the next switch
to heating the background transfer writes the heating set to the active profile
of each room (paced, max 8 profile-days per switch).

Run in the backend container (needs CCU_* env; store is the bind-mounted file):

    docker compose exec backend python scripts/prepare_heating_sets.py            # dry run, all rooms
    docker compose exec backend python scripts/prepare_heating_sets.py --apply
    docker compose exec backend python scripts/prepare_heating_sets.py --apply --temp 20 Wohnzimmer Bad
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.deps import get_device_map, get_jsonrpc, get_xmlrpc
from app.services import climate_profiles, profile_sets
from app.services.ccu import (
    climate,
    schedule,
)
from app.services.ccu import profiles as prof


def flat_set(temp: float) -> dict[int, dict[str, list[dict]]]:
    day = [{"start": "00:00", "end": "24:00", "setpoint": float(temp)}]
    return {
        p: {d.lower(): [dict(b) for b in day] for d in schedule.DAYS}
        for p in schedule.PROFILE_RANGE
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rooms", nargs="*", help="rooms (default: all)")
    ap.add_argument("--temp", type=float, default=20.0)
    ap.add_argument("--apply", action="store_true", help="write the store (default: dry run)")
    ap.add_argument("--reseed-cooling", action="store_true",
                    help="re-read the cooling set from the devices even if one is stored")
    ap.add_argument("--force", action="store_true", help="run even if not in cooling mode")
    args = ap.parse_args()

    device_map = get_device_map().get()
    xmlrpc = get_xmlrpc()
    rooms = args.rooms or device_map.room_names
    unknown = [r for r in rooms if r not in device_map.rooms]
    if unknown:
        sys.exit(f"unknown room(s): {unknown}; known: {device_map.room_names}")

    cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
    print(f"system mode: {'COOLING' if cooling else 'HEATING'}")
    if not cooling and not args.force:
        sys.exit("not in cooling mode -- the device schedules would be stored as "
                 "'cooling' by mistake. Aborting (use --force to override).")

    plans = []
    for room in rooms:
        seed_cooling = args.reseed_cooling or not profile_sets.has_mode(room, True)
        had_heating = profile_sets.has_mode(room, False)
        plans.append((room, seed_cooling, had_heating))
        if not seed_cooling:
            master = xmlrpc.get_paramset(device_map.room(room).thermostat_channel, "MASTER")
            diff = sum(
                1
                for p, days in profile_sets.get_mode(room, True).items()
                for d, blocks in climate_profiles.days_to_blocklists(days).items()
                if prof.day_differs(master, blocks, p, d)
            )
            print(f"  {room:20} stored cooling vs device: "
                  f"{'identical' if not diff else f'{diff} profile-day(s) DIFFER'}")
        print(f"  {room:20} cooling set: "
              f"{'re-read from device (read-only)' if seed_cooling else 'keep'}; "
              f"heating set: flat {args.temp} C"
              f"{' (replaces existing)' if had_heating else ''}")

    if not args.apply:
        print("\ndry run -- nothing written. Re-run with --apply.")
        return

    path = profile_sets._PATH
    if os.path.isfile(path):
        backup = f"{path}.bak.{time.strftime('%Y%m%d%H%M%S')}"
        shutil.copyfile(path, backup)
        print(f"\nbackup: {backup}")

    for room, seed_cooling, _ in plans:
        if seed_cooling:
            weeks = prof.read_all_profiles(xmlrpc, device_map.room(room).wth_address)
            profile_sets.put_mode(
                room, True, {p: climate_profiles.week_to_days(w) for p, w in weeks.items()}
            )
        profile_sets.put_mode(room, False, flat_set(args.temp))
    print(f"done: heating = flat {args.temp} C for {len(plans)} room(s); devices untouched.")


if __name__ == "__main__":
    try:
        main()
    finally:
        # a short-lived script must not leave a JSON-RPC session dangling on
        # the CCU -- it has a limited number of concurrent sessions, and an
        # unclosed one from every run can eventually exhaust it.
        try:
            get_jsonrpc().logout()
        except Exception:
            pass
