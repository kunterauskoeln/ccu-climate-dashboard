"""One-off catch-up: push ALL remaining differing profile-days for the
currently active system mode, not just the per-switch 8-day budget.

Uses the exact same mechanism as a normal mode switch
(app.services.profile_transfer): one MASTER day per write, the same 4 s
pacing, only each room's active profile. Only the per-run write budget is
raised for this single run, so everything still pending gets pushed in one go
instead of trickling in over several real mode switches.

It only ever writes what a normal switch to the CURRENT mode would eventually
write anyway -- nothing new is invented here. Still: run it with any room
you're unsure about set to Manual/a safe setpoint, since the schedule values
it writes take over as soon as they land.

Do not trigger a mode switch in the app while this script is running --
both would write to the same devices independently.

Run in the backend container:

    docker compose exec backend python scripts/drain_profile_transfer.py          # dry run
    docker compose exec backend python scripts/drain_profile_transfer.py --apply
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.deps import get_device_map, get_jsonrpc, get_xmlrpc
from app.services import profile_transfer
from app.services.ccu import climate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run / plan only)")
    ap.add_argument("--max-days", type=int, default=500,
                    help="per-run write budget for this run (default: effectively unlimited)")
    args = ap.parse_args()

    device_map = get_device_map().get()
    xmlrpc = get_xmlrpc()
    cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
    mode = "cooling" if cooling else "heating"
    print(f"system mode: {mode.upper()} -- will push the stored {mode} set\n")

    plan, deferred = profile_transfer._build_plan(
        xmlrpc, device_map, cooling, max_days=args.max_days
    )
    if not plan:
        print("nothing to do -- device already matches the stored set for every "
             "room's active profile.")
        return

    print(f"{len(plan)} profile-day(s) to write "
         f"({len(deferred)} would still be deferred beyond --max-days={args.max_days}):")
    for item in plan:
        print(f"  {item.room} P{item.profile} {item.day.title()}")

    if not args.apply:
        eta = len(plan) * profile_transfer._PACE_SECONDS
        print(f"\ndry run -- nothing written. Re-run with --apply "
             f"(paced {profile_transfer._PACE_SECONDS:.0f}s/day, ~{eta:.0f}s total).")
        return

    profile_transfer._MAX_DAYS = args.max_days
    profile_transfer.start(device_map, cooling)
    while True:
        st = profile_transfer.status()
        print(f"\r  {st.done}/{st.total} done "
             f"({len(st.written)} ok, {len(st.errors)} error)   ", end="", flush=True)
        if not st.running:
            break
        time.sleep(1)
    print()

    st = profile_transfer.status()
    for w in st.written:
        print(f"  ok    {w}")
    for e in st.errors:
        print(f"  ERROR {e}")
    if st.deferred:
        print(f"\nstill deferred ({len(st.deferred)}) -- run the script again to continue")
    else:
        print("\nall done -- device now matches the stored set for every room's active profile.")


if __name__ == "__main__":
    try:
        main()
    finally:
        # this script and profile_transfer's own reused client each hold a CCU
        # session -- a short-lived script must not leave either dangling.
        try:
            get_jsonrpc().logout()
        except Exception:
            pass
        profile_transfer.close()
