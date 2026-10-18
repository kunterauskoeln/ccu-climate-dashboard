import logging
import os
import time
from datetime import datetime

from fastapi import APIRouter

from app.deps import get_device_map, get_jsonrpc, get_xmlrpc
from app.schemas import (
    AbsencePut,
    ApartmentProfile,
    ApartmentSwitchResult,
    ClimatePatch,
    ClimateScheduleNext,
    ClimateSchedulePut,
    ClimateScheduleState,
    ClimateState,
)
from app.services import (
    absence,
    apartment,
    auto_backup,
    climate_schedule,
    climate_switch,
    device_health,
    dew_point,
    flow_sensor,
    profile_transfer,
    valve_history,
)
from app.services.ccu import climate
from app.services.ccu.errors import CcuBusy, CcuError, CcuValidationError
from app.services.profile_transfer import TransferState

router = APIRouter(tags=["system"])

log = logging.getLogger(__name__)

_start_time = time.time()


def _check_ccu() -> str:
    try:
        get_jsonrpc().check()
        return "ok"
    except Exception:
        # Deliberately broad (any failure = "unreachable"); debug only, the
        # healthcheck runs every few seconds.
        log.debug("CCU health check failed", exc_info=True)
        return "unreachable"


@router.get("/health")
def health():
    """Liveness plus a one-line view of every background job. ``status`` only
    depends on the CCU (it drives the container healthcheck); the rest is
    information for install.sh --check and humans."""
    ccu_status = _check_ccu()
    dew = dew_point.snapshot()
    devices = device_health.snapshot()
    backups = auto_backup.list_files()
    latest_auto = next((f for f in backups if f.kind == "auto"), None)
    return {
        "status": "ok" if ccu_status == "ok" else "degraded",
        "ccu": ccu_status,
        "uptime": int(time.time() - _start_time),
        "ccu_host": os.getenv("CCU_HOST"),
        "mqtt": flow_sensor.status() if flow_sensor.configured() else "nicht eingerichtet",
        "dew_point": dew.level if dew else "noch keine Messung",
        "devices": devices.message if devices else "noch nicht geprüft",
        "backup": latest_auto.name if latest_auto else "noch keine",
        "backup_error": auto_backup.last_error(),
    }


@router.get("/climate", response_model=ClimateState)
def get_climate():
    try:
        device_map = get_device_map().get()
    except CcuError:
        return ClimateState(cooling=False, actuator=None)
    return ClimateState(
        cooling=climate.get_cooling(get_xmlrpc(), device_map.actuator_channel),
        actuator=device_map.actuator_address,
    )


@router.patch("/climate", response_model=ClimateState)
def set_climate(patch: ClimatePatch):
    # Flip the FALMOT synchronously (fast, ~confirm), then -- if the mode
    # actually changed -- save each room's current ACTIVE_PROFILE under the
    # outgoing mode (read-only, fast) and kick off the background transfer.
    # profile_transfer itself restores each room's ACTIVE_PROFILE for the new
    # mode first (confirmed/polled, up to ~8s/room -- too slow for this
    # request) and only then pushes the stored schedule, paced and capped.
    device_map = get_device_map().get()
    xmlrpc = get_xmlrpc()
    climate_switch.switch(xmlrpc, device_map, patch.cooling)
    return ClimateState(
        cooling=climate.get_cooling(xmlrpc, device_map.actuator_channel),
        actuator=device_map.actuator_address,
    )


def _schedule_state() -> ClimateScheduleState:
    data = climate_schedule.load()
    upcoming = climate_schedule.next_due(data, datetime.now(climate_schedule.tz()))
    points = climate_schedule.points(data)
    return ClimateScheduleState(
        heating=points["heating"].as_dict() if points["heating"] else None,
        cooling=points["cooling"].as_dict() if points["cooling"] else None,
        next=ClimateScheduleNext(
            at=upcoming.at.isoformat(timespec="minutes"), cooling=upcoming.cooling,
        ) if upcoming else None,
        last_run=data.get("last_run"),
        timezone=str(climate_schedule.tz()),
    )


@router.get("/climate/schedule", response_model=ClimateScheduleState)
def get_climate_schedule():
    """Scheduled switching between heating and cooling (yearly points)."""
    return _schedule_state()


@router.put("/climate/schedule", response_model=ClimateScheduleState)
def put_climate_schedule(body: ClimateSchedulePut):
    """Store the schedule. Only points after this moment are acted on."""
    try:
        climate_schedule.configure(
            climate_schedule.Point(body.heating.day, body.heating.month, body.heating.time,
                                   body.heating.enabled),
            climate_schedule.Point(body.cooling.day, body.cooling.month, body.cooling.time,
                                   body.cooling.enabled),
        )
    except ValueError as exc:
        raise CcuValidationError(str(exc)) from None
    return _schedule_state()


@router.post("/climate/transfer", response_model=TransferState)
def continue_climate_transfer():
    """Re-run the transfer for the current mode: writes the next batch of days
    that still differ from the thermostats (what a mode switch had to defer)."""
    if profile_transfer.status().running:
        raise CcuBusy("Eine Profilübertragung läuft noch – bitte kurz warten.")
    device_map = get_device_map().get()
    xmlrpc = get_xmlrpc()
    cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
    profile_transfer.start(device_map, cooling)
    return profile_transfer.status()


@router.post("/active-profile", response_model=ApartmentSwitchResult)
def set_apartment_profile(body: ApartmentProfile):
    """Switch every room to the same profile slot ("Wohnung"). Rooms already
    on it are skipped; for the others the same rule as a single room's switch
    applies (stored plan written first if it differs). Runs in the background,
    one room after the other."""
    if profile_transfer.is_running():
        raise CcuBusy("Eine Profilübertragung läuft noch – bitte kurz warten.")
    device_map = get_device_map().get()
    xmlrpc = get_xmlrpc()
    cooling = climate.get_cooling(xmlrpc, device_map.actuator_channel)
    the_plan = apartment.plan(
        xmlrpc, device_map, dict.fromkeys(device_map.room_names, body.profile), cooling)
    background = apartment.start(the_plan, body.profile, cooling)
    return ApartmentSwitchResult(
        rooms=len(the_plan.rooms), skipped=the_plan.skipped,
        deferred=len(the_plan.deferred), background=background,
    )


@router.get("/climate/transfer", response_model=TransferState)
def get_climate_transfer():
    """Progress of the background profile transfer started by the last mode
    switch (see PATCH /climate)."""
    return profile_transfer.status()


@router.get("/dew-point", response_model=dew_point.Snapshot)
def get_dew_point():
    """Dew point per room against the flow temperature (cooling only), refreshed
    every 60 s in the background."""
    snap = dew_point.snapshot()
    if snap is not None:
        return snap
    return dew_point.Snapshot(
        at=None, cooling=None, level="unbekannt", message="Erste Messung läuft noch.",
        warn_margin=dew_point.warn_margin(), alarm_margin=dew_point.alarm_margin(),
        flow=dew_point.Flow(
            configured=False, connection="aus", topic="", value=None, received_at=None,
            stale=True, effective=None, source=None, last_valid=None, last_valid_at=None,
            flowing_since=None,
        ),
    )


@router.get("/device-health", response_model=device_health.Snapshot)
def get_device_health():
    """Reachability, batteries and duty cycle, refreshed every 5 minutes."""
    snap = device_health.snapshot()
    if snap is not None:
        return snap
    return device_health.Snapshot(at=0.0, ccu_duty_cycle=None, level="ok",
                                  message="Erste Prüfung läuft noch.")


@router.get("/absence", response_model=absence.AbsenceState)
def get_absence():
    """Planned / running absence (all rooms on one profile, then back)."""
    return absence.state()


@router.put("/absence", response_model=absence.AbsenceState)
def put_absence(body: AbsencePut):
    """Plan an absence, or change end/profile of the running one."""
    try:
        return absence.configure(body.profile, body.start or None, body.end)
    except ValueError as exc:
        raise CcuValidationError(str(exc)) from None


@router.delete("/absence", response_model=absence.AbsenceState)
def cancel_absence():
    """Drop a planned absence, or end the running one now (rooms go back)."""
    try:
        return absence.cancel()
    except ValueError as exc:
        raise CcuValidationError(str(exc)) from None


@router.get("/valve-history", response_model=valve_history.Series)
def get_valve_history(hours: float = 48):
    """Valve position per room (percent) over the last *hours* (max 72), one
    point every 5 minutes; ``null`` where the recording paused."""
    if not 0 < hours <= valve_history.KEEP_HOURS:
        raise CcuValidationError(f"hours muss zwischen 0 und {valve_history.KEEP_HOURS} liegen")
    return valve_history.series(hours)
