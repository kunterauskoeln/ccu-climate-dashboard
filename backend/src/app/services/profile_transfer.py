"""Background transfer of a stored profile set onto the thermostats.

The HmIP-WTH-1 keeps only ONE physical profile table, shared by heating and
cooling, so after a mode switch the app has to rewrite it. Hard constraints
(learned from an incident where the naive synchronous version hung the app and
flooded the HmIP RF duty cycle):

* never on the request thread -- a single daemon thread does the work
* one MASTER day per write, paced, with a hard cap on days per run
* a mode switch transfers only each room's *active* profile (``ACTIVE_PROFILE``);
  the other five stay in the store until the user selects one -- and selecting
  one (``start_profile_switch``) writes its stored schedule FIRST and only then
  moves the pointer, so the thermostat never runs another mode's stale plan
* cooperative cancel -- a new mode switch aborts the run in progress

State is a module-level singleton (one worker at a time) exposed via
:func:`status` for a small progress indicator in the UI.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from . import climate_profiles, profile_names, profile_sets
from .ccu import profiles as prof
from .ccu import schedule
from .ccu.errors import CcuBusy, CcuError
from .ccu.mapping import DeviceMap

_PACE_SECONDS = 4.0          # gap between MASTER day-writes (RF duty cycle)
_MAX_DAYS = 8                # per-run write budget; the rest is reported as deferred
_JOIN_TIMEOUT = 2.0          # how long start()/cancel() wait for the old run to notice
_MAX_CONSECUTIVE_ERRORS = 3  # abort a run early rather than hammer a struggling CCU
_DUTY_CHECK_EVERY = 4        # look at the CCU's radio load before every 4th write
_RESTORE_TIMEOUT = 8.0       # per-room ACTIVE_PROFILE confirm poll, see restore_active_profiles
_RESTORE_POLL = 1.0
# Undoing changes from the history can touch many profiles at once (e.g. a
# profile copied into every room); cap one run like a mode switch, a second
# "reset" writes the rest.
MAX_HISTORY_RESTORE_DAYS = 14
# Switching the whole apartment to one profile: rooms whose stored plan must be
# written first share this per-run budget; rooms beyond it wait for another tap.
MAX_APARTMENT_DAYS = 14

_DE_DAYS = {
    "MONDAY": "Montag", "TUESDAY": "Dienstag", "WEDNESDAY": "Mittwoch",
    "THURSDAY": "Donnerstag", "FRIDAY": "Freitag", "SATURDAY": "Samstag",
    "SUNDAY": "Sonntag",
}

# Injectable so tests can supply fakes; default lazily builds ONE (xmlrpc, jsonrpc)
# pair and reuses it for every run in this process. The CCU's ReGaHss backend
# caps concurrent JSON-RPC sessions -- a fresh client (and login) per run leaks
# a session every time nothing ever logs it out, and enough of those exhaust
# the cap ("invalid credentials or too many sessions"). One reused client logs
# in once and lets JsonRpcClient's own TTL/retry keep the session alive.
_make_clients = None
_reusable_clients = None


@dataclass
class TransferState:
    running: bool = False
    mode: str | None = None          # "heating" / "cooling" being applied
    kind: str | None = None          # "mode_switch" | "profile_switch" | "restore" | "apartment_switch"
    label: str | None = None         # profile_switch: "Arbeitszimmer P3"
    started_at: float | None = None  # epoch seconds; identifies the run (UI dismissals)
    total: int = 0                   # profile-days planned for this run
    done: int = 0
    written: list[str] = field(default_factory=list)   # "Wohnzimmer P3 Montag"
    deferred: list[str] = field(default_factory=list)  # over the per-run cap
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _PlanItem:
    room: str
    wth_address: str
    profile: int
    day: str
    blocks: tuple[schedule.Block, ...]


log = logging.getLogger(__name__)

_lock = threading.Lock()
_state = TransferState()
_thread: threading.Thread | None = None
_cancel = threading.Event()


def _label(item: _PlanItem) -> str:
    return f"{item.room} P{item.profile} {_DE_DAYS.get(item.day.upper(), item.day.title())}"


def status() -> TransferState:
    with _lock:
        return TransferState(
            running=_state.running, mode=_state.mode,
            kind=_state.kind, label=_state.label, started_at=_state.started_at,
            total=_state.total, done=_state.done,
            written=list(_state.written),
            deferred=list(_state.deferred),
            errors=list(_state.errors),
        )


def _clients():
    if _make_clients is not None:
        return _make_clients()
    global _reusable_clients
    if _reusable_clients is None:
        from ..deps import new_jsonrpc, new_xmlrpc
        _reusable_clients = (new_xmlrpc(), new_jsonrpc())
    return _reusable_clients


def close() -> None:
    """Log out and drop the reusable client pair. The live app doesn't need to
    call this (the session lives for the process lifetime, same as the
    request-handler singletons in app.deps) -- it's for short-lived scripts
    that use profile_transfer directly and should clean up their session
    before exiting."""
    global _reusable_clients
    if _reusable_clients is not None:
        _, jsonrpc = _reusable_clients
        try:
            jsonrpc.logout()
        except Exception:
            # A failed logout leaves a CCU session open (the CCU caps them).
            log.warning("CCU JSON-RPC logout failed; session may stay open", exc_info=True)
        _reusable_clients = None


def _diff_items(
    xmlrpc, room: str, wth_address: str, thermostat_channel: str,
    profile: int, days: dict,
) -> list[_PlanItem]:
    """Days of *profile* whose stored blocks differ from the device MASTER."""
    master = xmlrpc.get_paramset(thermostat_channel, "MASTER")
    return [
        _PlanItem(room, wth_address, profile, day, tuple(blocks))
        for day, blocks in climate_profiles.days_to_blocklists(days).items()
        if prof.day_differs(master, blocks, profile, day)
    ]


def _build_plan(
    xmlrpc, device_map: DeviceMap, cooling: bool, *, max_days: int,
) -> tuple[list[_PlanItem], list[str]]:
    plan: list[_PlanItem] = []
    for room, room_devices in device_map.rooms.items():
        stored = profile_sets.get_mode(room, cooling)
        if not stored:
            continue
        active = prof.get_active_profile(xmlrpc, room_devices.wth_address)
        if active is None:
            continue
        days = stored.get(active)
        if not days:
            continue
        try:
            plan.extend(_diff_items(
                xmlrpc, room, room_devices.wth_address,
                room_devices.thermostat_channel, active, days,
            ))
        except CcuError:
            continue
    deferred = [_label(item) for item in plan[max_days:]]
    return plan[:max_days], deferred


def plan_days(
    xmlrpc, room: str, room_devices, profile: int, days: dict,
) -> list[_PlanItem]:
    """Writes needed to bring *profile* on *room*'s thermostat to *days*."""
    return _diff_items(
        xmlrpc, room, room_devices.wth_address,
        room_devices.thermostat_channel, profile, days,
    )


def plan_profile_switch(
    xmlrpc, room: str, room_devices, profile: int, cooling: bool,
) -> list[_PlanItem]:
    """Writes needed before *room* may switch to *profile* in the current mode:
    empty when nothing is stored for it or the device already matches."""
    days = profile_sets.get_profile(room, cooling, profile)
    if not days:
        return []
    return _diff_items(
        xmlrpc, room, room_devices.wth_address,
        room_devices.thermostat_channel, profile, days,
    )


def _execute_plan(xmlrpc, jsonrpc, plan: list[_PlanItem]) -> bool:
    """Write *plan* one MASTER day at a time, paced, with the circuit breaker.
    True only if every item was written (no error, not cancelled, no early stop)."""
    consecutive_errors = 0
    failed = 0
    for index, item in enumerate(plan):
        if _cancel.is_set():
            return False
        if index and _cancel.wait(_PACE_SECONDS):
            return False
        if index % _DUTY_CHECK_EVERY == 0 and _radio_busy(jsonrpc, plan[index:]):
            return False
        try:
            prof.write_days(
                xmlrpc, jsonrpc, item.wth_address, item.profile,
                {item.day: list(item.blocks)},
            )
            with _lock:
                _state.written.append(_label(item))
            consecutive_errors = 0
        except CcuError as exc:
            consecutive_errors += 1
            failed += 1
            with _lock:
                _state.errors.append(f"{_label(item)}: {exc}")
        finally:
            with _lock:
                _state.done += 1

        # a CCU that keeps failing (e.g. exhausted its session limit) won't be
        # helped by hammering it with the rest of the plan -- stop and defer.
        if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
            rest = plan[index + 1:]
            with _lock:
                _state.deferred = [_label(p) for p in rest] + _state.deferred
                _state.errors.append(
                    f"stopped after {consecutive_errors} consecutive errors -- "
                    f"{len(rest)} item(s) left for next time"
                )
            return False

    return failed == 0


def _radio_busy(jsonrpc, rest: list[_PlanItem]) -> bool:
    """Hold back while the CCU's duty cycle is high: defer *rest* and say why.
    An unreadable duty cycle does not block (the circuit breaker still applies)."""
    from .device_health import duty_limit, read_ccu_duty_cycle

    duty = read_ccu_duty_cycle(jsonrpc)
    if duty is None or duty < duty_limit():
        return False
    with _lock:
        _state.deferred = [_label(p) for p in rest] + _state.deferred
        _state.errors.append(
            f"Funkauslastung der CCU bei {duty} % – angehalten, {len(rest)} Tag(e) "
            "aufgeschoben. Später mit „Jetzt übertragen“ fortsetzen.")
    log.warning("profile transfer held back: CCU duty cycle %s %%", duty)
    return True


def _run(device_map: DeviceMap, cooling: bool) -> None:
    try:
        _run_impl(device_map, cooling)
    finally:
        # Only hold the CCU session open for the duration of an actual
        # transfer, not for the process's whole lifetime -- between switches
        # this frees up the session for scripts / other work instead of
        # sitting on it indefinitely (the CCU caps concurrent sessions).
        close()


def _run_impl(device_map: DeviceMap, cooling: bool) -> None:
    try:
        xmlrpc, jsonrpc = _clients()
        # Confirmed (polling) restore of each room's ACTIVE_PROFILE for the
        # new mode -- up to ~8s/room, which is exactly why this runs here and
        # not synchronously in the PATCH /climate handler. Must happen before
        # _build_plan, which reads ACTIVE_PROFILE live off the device.
        restore_errors = climate_profiles.restore_active_profiles(
            xmlrpc, device_map, cooling, timeout=_RESTORE_TIMEOUT, poll=_RESTORE_POLL
        )
        plan, deferred = _build_plan(xmlrpc, device_map, cooling, max_days=_MAX_DAYS)
    except Exception as exc:
        with _lock:
            _state.running = False
            _state.errors.append(f"plan failed: {exc}")
        return

    with _lock:
        _state.errors.extend(restore_errors)
        _state.total = len(plan)
        _state.deferred = deferred

    _execute_plan(xmlrpc, jsonrpc, plan)

    with _lock:
        _state.running = False


def _run_profile_switch(
    room: str, wth_address: str, profile: int, cooling: bool, plan: list[_PlanItem],
) -> None:
    try:
        _run_profile_switch_impl(room, wth_address, profile, cooling, plan)
    except Exception as exc:
        log.warning("profile switch %s P%s failed", room, profile, exc_info=True)
        with _lock:
            _state.errors.append(f"{room} P{profile}: {exc}")
    finally:
        with _lock:
            _state.running = False
        close()


def _run_profile_switch_impl(
    room: str, wth_address: str, profile: int, cooling: bool, plan: list[_PlanItem],
) -> None:
    with _lock:
        _state.total = len(plan)
    xmlrpc, jsonrpc = _clients()
    if not _execute_plan(xmlrpc, jsonrpc, plan):
        with _lock:
            _state.errors.append(
                f"{room}: Profil P{profile} nicht umgeschaltet – Plan unvollständig übertragen"
            )
        return
    # Schedule is on the device; only now let the thermostat use this profile.
    confirmed = prof.set_active_profile_confirmed(
        xmlrpc, wth_address, profile, timeout=_RESTORE_TIMEOUT, poll=_RESTORE_POLL
    )
    if not confirmed:
        with _lock:
            _state.errors.append(f"{room}: Profil P{profile} nicht bestätigt aktiv")
        return
    try:
        profile_sets.put_active_profile(room, cooling, profile)
    except Exception:
        log.warning("%s: could not remember active profile P%s", room, profile, exc_info=True)


def _run_restore(plan: list[_PlanItem], deferred: list[str], on_done) -> None:
    ok = False
    xmlrpc = None
    try:
        with _lock:
            _state.total = len(plan)
            _state.deferred = list(deferred)
        xmlrpc, jsonrpc = _clients()
        ok = _execute_plan(xmlrpc, jsonrpc, plan) and not deferred
    except Exception as exc:
        log.warning("history restore failed", exc_info=True)
        with _lock:
            _state.errors.append(f"Zurücksetzen fehlgeschlagen: {exc}")
    finally:
        if xmlrpc is not None:
            try:
                on_done(xmlrpc, ok)
            except Exception:
                log.warning("history restore: follow-up after the writes failed", exc_info=True)
        with _lock:
            _state.running = False
        close()


def start_restore(
    plan: list[_PlanItem], cooling: bool, on_done,
    *, max_days: int = MAX_HISTORY_RESTORE_DAYS,
) -> int:
    """Write up to *max_days* of *plan* (profile days going back to an earlier
    state), then call ``on_done(xmlrpc, complete)`` from the worker thread --
    ``complete`` only if every day was written and nothing was left over.
    Refuses while another transfer runs. Returns the number of deferred days."""
    with _lock:
        if _state.running:
            raise CcuBusy("Eine Profilübertragung läuft noch – bitte kurz warten.")
    now, rest = plan[:max_days], plan[max_days:]
    _launch(
        _run_restore, (now, [_label(item) for item in rest], on_done),
        mode=profile_sets.mode_key(cooling), kind="restore", label="Änderungen zurücksetzen",
    )
    return len(rest)


@dataclass(frozen=True)
class RoomSwitch:
    """One room of an apartment-wide profile switch: the stored plan days to
    write first (possibly none), then the ACTIVE_PROFILE switch."""
    room: str
    wth_address: str
    plan: list[_PlanItem]
    profile: int | None = None   # own target for this room (else the run's profile)


def _run_apartment(profile: int, cooling: bool, rooms: list[RoomSwitch],
                   deferred: list[str]) -> None:
    try:
        with _lock:
            # one step per plan day plus one per room for the switch itself
            _state.total = sum(len(r.plan) for r in rooms) + len(rooms)
            _state.deferred = list(deferred)
        xmlrpc, jsonrpc = _clients()
        failed_in_a_row = 0
        for index, target in enumerate(rooms):
            if _cancel.is_set():
                break
            # the switch itself is an RF command too -- keep the usual gap
            if index and _cancel.wait(_PACE_SECONDS):
                break
            switched = False
            wanted = target.profile or profile
            if not target.plan or _execute_plan(xmlrpc, jsonrpc, target.plan):
                switched = prof.set_active_profile_confirmed(
                    xmlrpc, target.wth_address, wanted,
                    timeout=_RESTORE_TIMEOUT, poll=_RESTORE_POLL,
                )
                if switched:
                    try:
                        profile_sets.put_active_profile(target.room, cooling, wanted)
                    except Exception:
                        log.warning("%s: could not remember active profile P%s",
                                    target.room, wanted, exc_info=True)
                else:
                    with _lock:
                        _state.errors.append(
                            f"{target.room}: Profil P{wanted} nicht bestätigt aktiv")
            else:
                with _lock:
                    _state.errors.append(
                        f"{target.room}: Profil P{wanted} nicht umgeschaltet – "
                        "Plan unvollständig übertragen")
            with _lock:
                _state.done += 1
            failed_in_a_row = 0 if switched else failed_in_a_row + 1
            if failed_in_a_row >= _MAX_CONSECUTIVE_ERRORS:
                rest = rooms[index + 1:]
                with _lock:
                    _state.deferred = [r.room for r in rest] + _state.deferred
                    _state.errors.append(
                        f"nach {failed_in_a_row} Fehlern in Folge abgebrochen -- "
                        f"{len(rest)} Raum/Räume nicht umgeschaltet")
                break
    except Exception as exc:
        log.warning("apartment profile switch to P%s failed", profile, exc_info=True)
        with _lock:
            _state.errors.append(f"Umschalten der Wohnung fehlgeschlagen: {exc}")
    finally:
        with _lock:
            _state.running = False
        close()


def start_apartment_switch(
    profile: int, cooling: bool, rooms: list[RoomSwitch], deferred: list[str],
    *, label: str | None = None,
) -> None:
    """Switch *rooms* one after the other to *profile*: each room's stored plan
    first (if it differs from the thermostat), then its ACTIVE_PROFILE. A room
    whose plan could not be written is NOT switched. Refuses while another
    transfer runs. Returns immediately."""
    with _lock:
        if _state.running:
            raise CcuBusy("Eine Profilübertragung läuft noch – bitte kurz warten.")
    _launch(
        _run_apartment, (profile, cooling, rooms, deferred),
        mode=profile_sets.mode_key(cooling), kind="apartment_switch",
        label=label or f"Wohnung: {profile_names.load().get(str(profile)) or f'P{profile}'}",
    )


def is_running() -> bool:
    with _lock:
        return _state.running


def cancel() -> None:
    global _thread
    thread = _thread
    if thread and thread.is_alive():
        _cancel.set()
        thread.join(timeout=_JOIN_TIMEOUT)
    _thread = None
    with _lock:
        _state.running = False


def _launch(target, args, *, mode: str, kind: str, label: str | None = None) -> None:
    global _thread
    _cancel.clear()
    with _lock:
        _state.running = True
        _state.mode = mode
        _state.kind = kind
        _state.label = label
        _state.started_at = time.time()
        _state.total = 0
        _state.done = 0
        _state.written = []
        _state.deferred = []
        _state.errors = []
    _thread = threading.Thread(target=target, args=args, name="profile-transfer", daemon=True)
    _thread.start()


def start(device_map: DeviceMap, cooling: bool) -> None:
    """Abort any run in progress and kick off a new mode-switch run. Returns immediately."""
    cancel()
    _launch(_run, (device_map, cooling), mode=profile_sets.mode_key(cooling), kind="mode_switch")


def start_profile_switch(
    room: str, wth_address: str, profile: int, cooling: bool, plan: list[_PlanItem],
) -> None:
    """Write *plan* (the stored schedule of *profile*) onto the thermostat, and only
    when that fully succeeded move ``ACTIVE_PROFILE`` over. Refuses while another
    transfer runs instead of cancelling it. Returns immediately."""
    with _lock:
        if _state.running:
            raise CcuBusy("Eine Profilübertragung läuft noch – bitte kurz warten.")
    _launch(
        _run_profile_switch, (room, wth_address, profile, cooling, plan),
        mode=profile_sets.mode_key(cooling), kind="profile_switch", label=f"{room} P{profile}",
    )


def join(timeout: float | None = None) -> None:
    """Test helper: wait for the current run to finish."""
    thread = _thread
    if thread:
        thread.join(timeout)
