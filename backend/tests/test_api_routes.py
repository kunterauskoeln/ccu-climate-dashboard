"""Route-level tests for the Phase 2 resource API (CCU clients faked)."""
import json

import pytest
from conftest import FakeJsonRpc, FakeXmlRpc
from fastapi.testclient import TestClient

import app.main
import app.routers.backup as backup_router
import app.routers.devices as devices_router
import app.routers.history as history_router
import app.routers.profiles as profiles_router
import app.routers.rooms as rooms_router
import app.routers.system as system_router
from app.services import (
    change_history,
    climate_profiles,
    climate_schedule,
    profile_names,
    profile_sets,
    profile_transfer,
)
from app.services.ccu import profiles as ccu_profiles
from app.services.ccu.errors import CcuError
from app.services.ccu.mapping import DeviceMap, RoomDevices

WZ = RoomDevices(
    room="Wohnzimmer", wth_address="WTH_WZ", group_address="INT0000003",
    valve_channels=("FALMOT1:2", "FALMOT1:3"),
)
AZ = RoomDevices(room="Arbeitszimmer", wth_address="WTH_AZ", group_address="INT0000002")
CH1 = "WTH_WZ:1"


def _p1_monday(prefix="WTH_WZ") -> dict:
    ends = [360, 540, 1020, 1320, 1440] + [1440] * 8
    temps = [17.0, 21.0, 17.0, 21.0, 17.0] + [17.0] * 8
    out = {}
    for i in range(1, 14):
        out[f"P1_ENDTIME_MONDAY_{i}"] = ends[i - 1]
        out[f"P1_TEMPERATURE_MONDAY_{i}"] = temps[i - 1]
    return out


VALUES_WZ = {
    "ACTUAL_TEMPERATURE": 25.3, "SET_POINT_TEMPERATURE": 27.0, "HUMIDITY": 48,
    "SET_POINT_MODE": 1, "ACTIVE_PROFILE": 4, "WINDOW_STATE": 0,
    "BOOST_MODE": False, "HEATING_COOLING": 1,
}


def _run_p1(client):
    """Make P1 the profile the Wohnzimmer thermostat runs (live on the device)."""
    client.xmlrpc.paramsets[("WTH_WZ:1", "VALUES")]["ACTIVE_PROFILE"] = 1


class _FakeMap:
    def __init__(self, dm):
        self._dm = dm

    def get(self, *, force=False):
        return self._dm

    def set_valve_channels(self, channels):
        self.valve_channels = channels


class _LiveXmlRpc(FakeXmlRpc):
    """set_value actually updates VALUES, so confirmed writes (ACTIVE_PROFILE,
    HEATING_COOLING) can see their own change on the read-back poll."""

    def set_value(self, address, key, value):
        self.set_calls.append((address, key, value))
        self.paramsets.setdefault((address, "VALUES"), {})[key] = value


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(profile_sets, "_PATH", str(tmp_path / "profile_sets.json"))
    xmlrpc = _LiveXmlRpc({
        ("WTH_WZ:1", "VALUES"): dict(VALUES_WZ),
        ("WTH_WZ:1", "MASTER"): _p1_monday(),
        ("WTH_AZ:1", "VALUES"): {**VALUES_WZ, "SET_POINT_MODE": 0},
        ("WTH_AZ:1", "MASTER"): {},
        ("FALMOT1:0", "VALUES"): {"HEATING_COOLING": 0},
        ("FALMOT1:2", "VALUES"): {"LEVEL": 0.6},
        ("FALMOT1:3", "VALUES"): {"LEVEL": 0.4},
    })
    jsonrpc = FakeJsonRpc(
        devices=[
            {"address": "WTH_WZ", "type": "HmIP-WTH-1", "interface": "HmIP-RF", "name": "Wohnzimmer"},
            {"address": "INT0000003", "type": "HmIP-HEATING", "interface": "VirtualDevices", "name": "Wohnzimmer INT0000003"},
        ],
        group_values={"INT0000003:1": {"LEVEL": "0.5"}},
        xmlrpc=xmlrpc,  # profile writes land back in the fake MASTER
    )
    device_map = DeviceMap(
        rooms={"Wohnzimmer": WZ, "Arbeitszimmer": AZ}, actuator_address="FALMOT1"
    )
    fake_map = _FakeMap(device_map)
    for mod in (rooms_router, profiles_router, devices_router, system_router, history_router,
                backup_router):
        monkeypatch.setattr(mod, "get_xmlrpc", lambda: xmlrpc, raising=False)
        monkeypatch.setattr(mod, "get_jsonrpc", lambda: jsonrpc, raising=False)
        monkeypatch.setattr(mod, "get_device_map", lambda: fake_map, raising=False)

    from app.services.ccu import climate as _climate
    monkeypatch.setattr(_climate, "_POLL_SECONDS", 0, raising=False)
    monkeypatch.setattr(_climate, "_CONFIRM_TIMEOUT", 0.05, raising=False)

    monkeypatch.setattr(rooms_router, "_ACTIVE_PROFILE_TIMEOUT", 0.05, raising=False)
    monkeypatch.setattr(rooms_router, "_ACTIVE_PROFILE_POLL", 0, raising=False)

    monkeypatch.setattr(profile_transfer, "_PACE_SECONDS", 0)
    monkeypatch.setattr(profile_transfer, "_RESTORE_TIMEOUT", 0.05)
    monkeypatch.setattr(profile_transfer, "_RESTORE_POLL", 0)
    monkeypatch.setattr(profile_transfer, "_state", profile_transfer.TransferState())
    monkeypatch.setattr(profile_transfer, "_thread", None)
    monkeypatch.setattr(profile_transfer, "_make_clients", lambda: (xmlrpc, jsonrpc))
    profile_transfer._cancel.clear()

    c = TestClient(app.main.app, raise_server_exceptions=False)
    c.xmlrpc = xmlrpc
    c.jsonrpc = jsonrpc
    c.device_map = fake_map
    yield c
    profile_transfer.cancel()


def test_list_rooms(client):
    rows = client.get("/rooms").json()
    names = {r["room"] for r in rows}
    assert names == {"Wohnzimmer", "Arbeitszimmer"}
    wz = next(r for r in rows if r["room"] == "Wohnzimmer")
    assert wz["actual_temperature"] == 25.3
    assert wz["set_temperature"] == 27.0
    assert wz["mode"] == "MANU" and wz["mode_code"] == 1
    assert wz["active_profile"] == 4
    assert wz["valve"] == 0.5  # mean of the two actuator circuits, carried in the list too
    assert wz["rssi"] is None  # ...but still not the maintenance extras


def test_get_single_room_is_full(client):
    wz = client.get("/rooms/Wohnzimmer").json()
    assert wz["valve"] == 0.5  # group LEVEL


def test_unknown_room_404_with_error_body(client):
    r = client.get("/rooms/Kueche")
    assert r.status_code == 404
    assert r.json()["error"]["type"] == "room_not_found"


def test_patch_room_setpoint(client):
    r = client.patch("/rooms/Wohnzimmer", json={"setpoint": 21.5})
    assert r.status_code == 200
    assert client.xmlrpc.set_calls == [("WTH_WZ:1", "SET_POINT_TEMPERATURE", 21.5)]


def test_patch_room_mode_uses_control_mode_putparamset(client):
    client.patch("/rooms/Wohnzimmer", json={"mode": 0})
    assert client.xmlrpc.put_calls == [("WTH_WZ:1", "VALUES", {"CONTROL_MODE": 0})]


def test_patch_room_mode_before_setpoint(client):
    client.patch("/rooms/Wohnzimmer", json={"mode": 1, "setpoint": 22.0})
    # mode write (putParamset) happens, then the setpoint (setValue)
    assert client.xmlrpc.put_calls == [("WTH_WZ:1", "VALUES", {"CONTROL_MODE": 1})]
    assert client.xmlrpc.set_calls == [("WTH_WZ:1", "SET_POINT_TEMPERATURE", 22.0)]


def test_patch_room_active_profile_remembers_it_for_the_current_mode(client):
    # client fixture's FALMOT VALUES defaults to HEATING_COOLING=0 -> heating
    r = client.patch("/rooms/Wohnzimmer", json={"active_profile": 3})
    assert r.status_code == 200
    assert client.xmlrpc.set_calls == [("WTH_WZ:1", "ACTIVE_PROFILE", 3)]
    assert profile_sets.get_active_profile("Wohnzimmer", False) == 3
    assert profile_sets.get_active_profile("Wohnzimmer", True) is None


def test_patch_room_active_profile_502s_if_not_confirmed_and_does_not_remember_it(
    client, monkeypatch
):
    monkeypatch.setattr(rooms_router.prof, "set_active_profile_confirmed",
                        lambda *a, **k: False)
    r = client.patch("/rooms/Wohnzimmer", json={"active_profile": 3})
    assert r.status_code == 502
    assert r.json()["error"]["type"] == "ccu_error"
    # never trusted into the store, so a later mode switch can't "correct"
    # the baseline to a value that was never actually confirmed on the device
    assert profile_sets.get_active_profile("Wohnzimmer", False) is None


def test_patch_empty_body_422(client):
    r = client.patch("/rooms/Wohnzimmer", json={})
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "validation_error"


def test_patch_setpoint_out_of_range_422(client):
    r = client.patch("/rooms/Wohnzimmer", json={"setpoint": 40})
    assert r.status_code == 422  # pydantic field validation


def test_get_profile(client):
    wp = client.get("/rooms/Wohnzimmer/profiles/1").json()
    assert wp["profile"] == 1
    assert wp["days"]["monday"] == [
        {"start": "00:00", "end": "06:00", "setpoint": 17.0},
        {"start": "06:00", "end": "09:00", "setpoint": 21.0},
        {"start": "09:00", "end": "17:00", "setpoint": 17.0},
        {"start": "17:00", "end": "22:00", "setpoint": 21.0},
        {"start": "22:00", "end": "24:00", "setpoint": 17.0},
    ]


def test_list_profiles_reports_active(client):
    body = client.get("/rooms/Wohnzimmer/profiles").json()
    assert body["active"] == 4
    assert set(body["profiles"]) == {"1", "2", "3", "4", "5", "6"}


def _master_write(jsonrpc) -> dict:
    addr, key, typed_set = jsonrpc.put_calls[-1]
    assert (addr, key) == ("WTH_WZ:1", "MASTER")
    return {
        i["name"]: (int(i["value"]) if "ENDTIME" in i["name"] else float(i["value"]))
        for i in typed_set
    }


def test_add_block_writes_master_via_jsonrpc_and_returns_profile(client):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    r = client.post(
        "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks",
        json={"start": "12:00", "end": "14:00", "setpoint": 23.0},
    )
    assert r.status_code == 200
    payload = _master_write(client.jsonrpc)
    assert payload["P1_ENDTIME_MONDAY_4"] == 840  # 14:00 boundary
    assert r.json()["days"]["monday"][3] == {"start": "12:00", "end": "14:00", "setpoint": 23.0}


def test_copy_profile_day_route(client):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    r = client.post(
        "/rooms/Wohnzimmer/profiles/1/copy",
        json={"to_profile": 1, "from_day": "MONDAY", "to_day": "FRIDAY"},
    )
    assert r.status_code == 200, r.text
    _, key, typed = client.jsonrpc.put_calls[-1]
    assert key == "MASTER"
    assert {n.split("_")[2] for i in typed for n in [i["name"]]} == {"FRIDAY"}
    assert r.json()["days"]["friday"] == r.json()["days"]["monday"]


def test_copy_profile_one_sided_day_is_422(client):
    r = client.post(
        "/rooms/Wohnzimmer/profiles/1/copy",
        json={"to_profile": 2, "from_day": "MONDAY"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "validation_error"


def test_clear_block(client):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    r = client.request(
        "DELETE", "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks",
        json={"start": "06:00", "end": "09:00"},
    )
    assert r.status_code == 200
    payload = _master_write(client.jsonrpc)
    assert payload["P1_ENDTIME_MONDAY_1"] == 1020  # 00:00-17:00 coalesced @ 17


# --- Phase 2b.2: ?mode= edits the inactive mode's store, never the device --
# client fixture's FALMOT defaults to HEATING_COOLING=0 -> heating is active
def test_get_profile_mode_matching_active_reads_the_device(client):
    r = client.get("/rooms/Wohnzimmer/profiles/1", params={"mode": "heating"})
    assert r.status_code == 200
    assert r.json()["days"]["monday"][1] == {"start": "06:00", "end": "09:00", "setpoint": 21.0}


def test_get_profile_mode_inactive_reads_the_store_not_the_device(client):
    r = client.get("/rooms/Wohnzimmer/profiles/1", params={"mode": "cooling"})
    assert r.status_code == 200
    # nothing stored yet for cooling -> empty, NOT the device's heating data
    assert r.json()["days"]["monday"] == []
    assert client.xmlrpc.get_calls == []  # never touched MASTER


def test_add_block_mode_inactive_writes_store_only(client):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    r = client.post(
        "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks",
        params={"mode": "cooling"},
        json={"start": "12:00", "end": "14:00", "setpoint": 19.5},
    )
    assert r.status_code == 200, r.text
    assert r.json()["days"]["monday"] == [
        {"start": "00:00", "end": "12:00", "setpoint": 17.0},
        {"start": "12:00", "end": "14:00", "setpoint": 19.5},
        {"start": "14:00", "end": "24:00", "setpoint": 17.0},
    ]
    assert client.jsonrpc.put_calls == []  # device never touched
    assert profile_sets.get_profile("Wohnzimmer", True, 1)["monday"] == [
        {"start": "00:00", "end": "12:00", "setpoint": 17.0},
        {"start": "12:00", "end": "14:00", "setpoint": 19.5},
        {"start": "14:00", "end": "24:00", "setpoint": 17.0},
    ]
    # the active (heating) profile is untouched
    assert client.get("/rooms/Wohnzimmer/profiles/1").json()["days"]["monday"][0] == {
        "start": "00:00", "end": "06:00", "setpoint": 17.0,
    }


def test_clear_block_mode_inactive_store_only(client):
    client.post(
        "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks", params={"mode": "cooling"},
        json={"start": "06:00", "end": "09:00", "setpoint": 21.0},
    )
    r = client.request(
        "DELETE", "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks",
        params={"mode": "cooling"}, json={"start": "06:00", "end": "09:00"},
    )
    assert r.status_code == 200
    assert r.json()["days"]["monday"] == [
        {"start": "00:00", "end": "24:00", "setpoint": 17.0},
    ]
    assert client.jsonrpc.put_calls == []


def test_copy_profile_mode_inactive_store_only(client):
    client.post(
        "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks", params={"mode": "cooling"},
        json={"start": "06:00", "end": "09:00", "setpoint": 21.0},
    )
    r = client.post(
        "/rooms/Wohnzimmer/profiles/1/copy", params={"mode": "cooling"},
        json={"to_profile": 2},
    )
    assert r.status_code == 200, r.text
    assert r.json()["days"]["monday"] == profile_sets.get_profile("Wohnzimmer", True, 1)["monday"]
    assert client.jsonrpc.put_calls == []


def test_list_profiles_mode_inactive_reports_stored_active_profile(client):
    profile_sets.put_active_profile("Wohnzimmer", True, 5)
    body = client.get("/rooms/Wohnzimmer/profiles", params={"mode": "cooling"}).json()
    assert body["active"] == 5
    assert set(body["profiles"]) == {"1", "2", "3", "4", "5", "6"}


def test_profiles_invalid_mode_is_422(client):
    r = client.get("/rooms/Wohnzimmer/profiles/1", params={"mode": "sideways"})
    assert r.status_code == 422
    assert r.json()["error"]["type"] == "validation_error"



def test_patch_climate_does_not_write_master_synchronously(client):
    # the mode switch must NOT touch any thermostat MASTER paramset on the
    # request thread -- applying the stored schedule is deferred to the
    # background transfer. Saving/restoring ACTIVE_PROFILE is a separate,
    # lightweight bit of bookkeeping and IS expected to happen synchronously
    # (see test_patch_climate_restores_the_active_profile_of_the_new_mode).
    r = client.patch("/system/climate", json={"cooling": True})
    assert r.status_code == 200, r.text
    assert r.json()["cooling"] is True
    assert client.jsonrpc.put_calls == []
    assert not any(key == "MASTER" for _, key, _ in client.xmlrpc.put_calls)


def test_patch_climate_restores_the_active_profile_of_the_new_mode(client):
    # Wohnzimmer was on P4 the last time it was in cooling; something changed
    # it to P2 in the meantime (e.g. while testing heating).
    profile_sets.put_active_profile("Wohnzimmer", True, 4)
    client.xmlrpc.paramsets[("WTH_WZ:1", "VALUES")]["ACTIVE_PROFILE"] = 2

    r = client.patch("/system/climate", json={"cooling": True})
    assert r.status_code == 200, r.text

    # the restore now happens inside the background transfer, not synchronously
    profile_transfer.join(timeout=3)

    assert ("WTH_WZ:1", "ACTIVE_PROFILE", 4) in client.xmlrpc.set_calls
    # and the room the current mode had never captured a profile for is left alone
    assert not any(addr == "WTH_AZ:1" and key == "ACTIVE_PROFILE"
                   for addr, key, _ in client.xmlrpc.set_calls)


def test_patch_climate_saves_the_outgoing_mode_active_profile(client):
    client.xmlrpc.paramsets[("WTH_WZ:1", "VALUES")]["ACTIVE_PROFILE"] = 3
    client.patch("/system/climate", json={"cooling": True})  # was heating -> save P3 as heating
    assert profile_sets.get_active_profile("Wohnzimmer", False) == 3


def test_patch_climate_same_mode_is_noop(client):
    r = client.patch("/system/climate", json={"cooling": False})
    assert r.status_code == 200
    assert r.json()["cooling"] is False
    assert client.jsonrpc.put_calls == []


def test_climate_switch_starts_background_transfer_of_active_profile(client):
    client.xmlrpc.paramsets[("WTH_WZ:1", "VALUES")]["ACTIVE_PROFILE"] = 1
    # diverge heating P1 from the (still pristine) cooling set via an edit
    client.post(
        "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks",
        json={"start": "12:00", "end": "14:00", "setpoint": 23.0},
    )
    r = client.patch("/system/climate", json={"cooling": True})
    assert r.status_code == 200 and r.json()["cooling"] is True

    profile_transfer.join(timeout=3)
    st = client.get("/system/climate/transfer").json()
    assert st["running"] is False
    assert st["mode"] == "cooling"
    assert st["written"] == ["Wohnzimmer P1 Montag"]
    assert st["errors"] == []
    # device MONDAY is back to the stored cooling schedule (no 12-14 block)
    payload = client.xmlrpc.paramsets[("WTH_WZ:1", "MASTER")]
    assert payload["P1_ENDTIME_MONDAY_1"] == 360


def test_transfer_holds_back_while_the_ccu_radio_is_busy(client):
    client.xmlrpc.paramsets[("WTH_WZ:1", "VALUES")]["ACTIVE_PROFILE"] = 1
    client.post(
        "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks",
        json={"start": "12:00", "end": "14:00", "setpoint": 23.0},
    )
    client.jsonrpc.duty_cycle = 85           # at/above DUTY_CYCLE_LIMIT (70)
    client.patch("/system/climate", json={"cooling": True})
    profile_transfer.join(timeout=3)

    st = client.get("/system/climate/transfer").json()
    assert st["written"] == []
    assert st["deferred"] == ["Wohnzimmer P1 Montag"]
    assert "Funkauslastung der CCU bei 85 %" in st["errors"][0]

    client.jsonrpc.duty_cycle = 20           # radio calm again: "Jetzt übertragen"
    assert client.post("/system/climate/transfer").status_code == 200
    profile_transfer.join(timeout=3)
    assert client.get("/system/climate/transfer").json()["written"] == ["Wohnzimmer P1 Montag"]


def test_climate_transfer_status_idle_by_default(client):
    st = client.get("/system/climate/transfer").json()
    assert st == {
        "running": False, "mode": None, "kind": None, "label": None, "started_at": None,
        "total": 0, "done": 0, "written": [], "deferred": [], "errors": [],
    }


def test_edit_block_seeds_room_and_mirrors_into_active_heating_set(client):
    client.post(
        "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks",
        json={"start": "12:00", "end": "14:00", "setpoint": 23.0},
    )
    heat = profile_sets.get_profile("Wohnzimmer", False, 1)  # heating is active
    cool = profile_sets.get_profile("Wohnzimmer", True, 1)
    block = {"start": "12:00", "end": "14:00", "setpoint": 23.0}
    assert block in heat["monday"]
    # the inactive (cooling) set keeps the seeded original
    assert block not in cool["monday"]
    # only the edited room was seeded
    assert "Arbeitszimmer" not in profile_sets.load()


def test_edit_succeeds_but_logs_when_the_store_mirror_fails(client, monkeypatch, caplog):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(climate_profiles, "remember_edit", boom)
    r = client.post(
        "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks",
        json={"start": "12:00", "end": "14:00", "setpoint": 23.0},
    )
    assert r.status_code == 200  # the device write itself succeeded
    assert "Wohnzimmer: device edit not mirrored" in caplog.text


def test_devices_filters_heating_groups(client):
    rows = client.get("/devices").json()
    assert rows == [{
        "id": "WTH_WZ", "name": "Wohnzimmer", "address": "WTH_WZ",
        "type": "HmIP-WTH-1", "interface": "HmIP-RF",
    }]


# --- profile switch: stored plan first, pointer second ------------------------
_FLAT_19 = {"monday": [{"start": "00:00", "end": "24:00", "setpoint": 19.0}]}


def test_switching_to_a_profile_with_a_different_stored_plan_writes_it_first(client, monkeypatch):
    profile_sets.put_mode("Wohnzimmer", False, {2: _FLAT_19})  # heating set, P2
    seen = {}
    real = ccu_profiles.set_active_profile_confirmed

    def spy(xmlrpc, wth, profile, **kw):
        # what is on the thermostat at the moment the pointer moves?
        seen["endtime_when_switching"] = xmlrpc.paramsets[("WTH_WZ:1", "MASTER")].get(
            "P2_ENDTIME_MONDAY_1")
        return real(xmlrpc, wth, profile, **kw)

    monkeypatch.setattr(profile_transfer.prof, "set_active_profile_confirmed", spy)

    r = client.patch("/rooms/Wohnzimmer", json={"active_profile": 2})
    assert r.status_code == 200
    profile_transfer.join(timeout=3)

    master = client.xmlrpc.paramsets[("WTH_WZ:1", "MASTER")]
    assert master["P2_ENDTIME_MONDAY_1"] == 1440 and master["P2_TEMPERATURE_MONDAY_1"] == 19.0
    assert seen["endtime_when_switching"] == 1440          # written BEFORE the switch
    assert ("WTH_WZ:1", "ACTIVE_PROFILE", 2) in client.xmlrpc.set_calls
    assert profile_sets.get_active_profile("Wohnzimmer", False) == 2
    st = client.get("/system/climate/transfer").json()
    assert st["kind"] == "profile_switch" and st["label"] == "Wohnzimmer P2"
    assert st["errors"] == [] and st["running"] is False


def test_profile_switch_is_immediate_when_the_device_already_matches(client):
    same = ccu_profiles.read_profile(client.xmlrpc, "WTH_WZ", 1)
    profile_sets.put_mode("Wohnzimmer", False, {1: climate_profiles.week_to_days(same)})
    r = client.patch("/rooms/Wohnzimmer", json={"active_profile": 1})
    assert r.status_code == 200
    assert client.xmlrpc.set_calls == [("WTH_WZ:1", "ACTIVE_PROFILE", 1)]
    assert client.get("/system/climate/transfer").json()["kind"] is None  # no job started


def test_profile_switch_does_not_happen_when_the_plan_could_not_be_written(client, monkeypatch):
    profile_sets.put_mode("Wohnzimmer", False, {2: _FLAT_19})

    def boom(*a, **k):
        raise CcuError("radio timeout")

    monkeypatch.setattr(profile_transfer.prof, "write_days", boom)
    assert client.patch("/rooms/Wohnzimmer", json={"active_profile": 2}).status_code == 200
    profile_transfer.join(timeout=3)

    assert client.xmlrpc.paramsets[("WTH_WZ:1", "VALUES")]["ACTIVE_PROFILE"] == 4  # unchanged
    st = client.get("/system/climate/transfer").json()
    assert any("nicht umgeschaltet" in e for e in st["errors"])
    assert profile_sets.get_active_profile("Wohnzimmer", False) is None


def test_profile_switch_is_refused_while_a_transfer_runs(client):
    profile_sets.put_mode("Wohnzimmer", False, {2: _FLAT_19})
    profile_transfer._state.running = True
    r = client.patch("/rooms/Wohnzimmer", json={"active_profile": 2})
    assert r.status_code == 409
    assert r.json()["error"]["type"] == "busy"
    assert client.xmlrpc.paramsets[("WTH_WZ:1", "VALUES")]["ACTIVE_PROFILE"] == 4


def test_continue_transfer_writes_what_still_differs_for_the_active_profile(client):
    profile_sets.put_mode("Wohnzimmer", False, {4: _FLAT_19})  # device P4 is empty -> differs
    r = client.post("/system/climate/transfer")
    assert r.status_code == 200
    profile_transfer.join(timeout=3)
    st = client.get("/system/climate/transfer").json()
    assert st["kind"] == "mode_switch" and "Wohnzimmer P4 Montag" in st["written"]


def test_continue_transfer_is_refused_while_one_runs(client):
    profile_transfer._state.running = True
    assert client.post("/system/climate/transfer").status_code == 409


# --- change history -------------------------------------------------------------
_MONDAY = "/rooms/Wohnzimmer/profiles/1/days/MONDAY/blocks"


def _history(client):
    return client.get("/history").json()


def _p1(client):
    return ccu_profiles.read_profile(client.xmlrpc, "WTH_WZ", 1)


def test_active_edit_is_recorded_with_the_state_before_it(client):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    original = climate_profiles.week_to_days(_p1(client))
    client.post(_MONDAY, json={"start": "12:00", "end": "14:00", "setpoint": 23.0})

    rows = _history(client)
    assert len(rows) == 1
    assert rows[0]["kind"] == "profile" and rows[0]["mode"] == "heating"
    assert rows[0]["room"] == "Wohnzimmer" and rows[0]["profile"] == 1
    assert rows[0]["summary"] == "Montag: 12:00–14:00 auf 23,0 °C"
    assert "before" not in rows[0]  # the list stays small
    assert change_history.entries()[0]["before"] == original


def test_edits_of_the_inactive_mode_are_not_recorded(client):
    client.post(_MONDAY + "?mode=cooling",
                json={"start": "12:00", "end": "14:00", "setpoint": 26.0})
    assert _history(client) == []


def test_an_edit_that_changes_nothing_is_not_recorded(client):
    client.post(_MONDAY, json={"start": "06:00", "end": "09:00", "setpoint": 21.0})
    assert _history(client) == []


def test_rename_is_recorded_and_can_be_undone(client):
    profile_names.set_name(2, "Urlaub")
    client.put("/profile-names/2", json={"name": "Winterurlaub"})

    rows = _history(client)
    assert rows[0]["kind"] == "name"
    assert rows[0]["summary"] == "Name P2: „Urlaub“ → „Winterurlaub“"

    r = client.post(f"/history/{rows[0]['id']}/restore")
    assert r.status_code == 200
    assert r.json() == {"names": 1, "profiles": 0, "days": 0, "deferred": 0,
                        "background": False}
    assert client.get("/profile-names").json()["2"] == "Urlaub"
    assert _history(client) == []


def test_reset_to_the_oldest_change_puts_thermostat_and_store_back(client):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    original = climate_profiles.week_to_days(_p1(client))
    client.post(_MONDAY, json={"start": "12:00", "end": "14:00", "setpoint": 23.0})
    client.post(_MONDAY, json={"start": "15:00", "end": "16:00", "setpoint": 19.0})
    _newest, oldest = _history(client)

    r = client.post(f"/history/{oldest['id']}/restore")
    assert r.status_code == 200 and r.json()["background"] is True
    profile_transfer.join(timeout=3)

    assert climate_profiles.week_to_days(_p1(client)) == original
    assert profile_sets.get_profile("Wohnzimmer", False, 1) == original
    assert _history(client) == []
    st = client.get("/system/climate/transfer").json()
    assert st["kind"] == "restore" and st["errors"] == []


def test_reset_to_the_newest_change_keeps_the_older_ones(client):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    client.post(_MONDAY, json={"start": "12:00", "end": "14:00", "setpoint": 23.0})
    after_first = climate_profiles.week_to_days(_p1(client))
    client.post(_MONDAY, json={"start": "15:00", "end": "16:00", "setpoint": 19.0})
    newest, oldest = _history(client)

    client.post(f"/history/{newest['id']}/restore")
    profile_transfer.join(timeout=3)

    assert climate_profiles.week_to_days(_p1(client)) == after_first
    assert [row["id"] for row in _history(client)] == [oldest["id"]]


def test_a_failed_reset_keeps_its_entries_for_another_try(client, monkeypatch):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    client.post(_MONDAY, json={"start": "12:00", "end": "14:00", "setpoint": 23.0})
    entry = _history(client)[0]

    def boom(*a, **k):
        raise CcuError("radio timeout")

    monkeypatch.setattr(profile_transfer.prof, "write_days", boom)
    client.post(f"/history/{entry['id']}/restore")
    profile_transfer.join(timeout=3)

    assert [row["id"] for row in _history(client)] == [entry["id"]]
    assert client.get("/system/climate/transfer").json()["errors"]


def test_mode_switch_drops_profile_entries_but_keeps_renames(client):
    client.post(_MONDAY, json={"start": "12:00", "end": "14:00", "setpoint": 23.0})
    client.put("/profile-names/3", json={"name": "Nacht"})

    assert client.patch("/system/climate", json={"cooling": True}).status_code == 200
    profile_transfer.join(timeout=3)

    assert [row["kind"] for row in _history(client)] == ["name"]


def test_reset_is_refused_while_a_transfer_runs(client):
    _run_p1(client)  # these edit the profile that runs on the thermostat
    client.post(_MONDAY, json={"start": "12:00", "end": "14:00", "setpoint": 23.0})
    profile_transfer._state.running = True
    r = client.post(f"/history/{_history(client)[0]['id']}/restore")
    assert r.status_code == 409


def test_reset_to_an_unknown_entry_is_a_validation_error(client):
    r = client.post("/history/does-not-exist/restore")
    assert r.status_code == 422


# --- export ------------------------------------------------------------------------
def test_export_contains_all_app_data_but_no_credentials(client, monkeypatch, tmp_path):
    week = {"monday": [{"start": "00:00", "end": "24:00", "setpoint": 19.5}]}
    profile_sets.put_mode("Wohnzimmer", False, {1: week})
    profile_names.set_name(1, "Standard")
    change_history.record_name(1, None, "Name P1: „P1“ → „Standard“")
    valves = tmp_path / "valve_channels.json"
    valves.write_text('{"Wohnzimmer": [2, 3]}', encoding="utf-8")
    monkeypatch.setattr(backup_router, "valve_channels_path", lambda: str(valves))
    monkeypatch.setenv("CCU_PASSWORD", "geheim-123")

    r = client.get("/export")

    assert r.status_code == 200
    assert 'attachment; filename="ccu-export-' in r.headers["content-disposition"]
    body = r.json()
    assert body["format"] == "ccu-dashboard-export" and body["version"] == 1
    assert body["profile_sets"]["Wohnzimmer"]["heating"]["1"] == week
    assert body["profile_names"] == {"1": "Standard"}
    assert body["valve_channels"] == {"Wohnzimmer": [2, 3]}
    assert [e["summary"] for e in body["change_history"]] == ["Name P1: „P1“ → „Standard“"]
    assert "geheim-123" not in r.text


# --- whole apartment to one profile ("Wohnung") -------------------------------------
def _active(client, wth):
    return client.xmlrpc.paramsets[(f"{wth}:1", "VALUES")]["ACTIVE_PROFILE"]


def test_apartment_switch_writes_differing_plans_first_then_switches_every_room(client):
    profile_sets.put_mode("Wohnzimmer", False, {2: _FLAT_19})  # differs from the device
    # Arbeitszimmer has nothing stored for P2 -> pointer switch only

    r = client.post("/system/active-profile", json={"profile": 2})
    assert r.status_code == 200
    assert r.json() == {"rooms": 2, "skipped": 0, "deferred": 0, "background": True}
    profile_transfer.join(timeout=3)

    assert _active(client, "WTH_WZ") == 2 and _active(client, "WTH_AZ") == 2
    master = client.xmlrpc.paramsets[("WTH_WZ:1", "MASTER")]
    assert master["P2_ENDTIME_MONDAY_1"] == 1440 and master["P2_TEMPERATURE_MONDAY_1"] == 19.0
    assert profile_sets.get_active_profile("Wohnzimmer", False) == 2
    assert profile_sets.get_active_profile("Arbeitszimmer", False) == 2
    st = client.get("/system/climate/transfer").json()
    assert st["kind"] == "apartment_switch" and st["label"] == "Wohnung: P2"
    assert st["errors"] == [] and st["done"] == st["total"] == 3  # 1 plan day + 2 switches


def test_apartment_switch_label_uses_the_profile_name(client):
    profile_names.set_name(3, "Nacht")
    client.post("/system/active-profile", json={"profile": 3})
    profile_transfer.join(timeout=3)
    assert client.get("/system/climate/transfer").json()["label"] == "Wohnung: Nacht"


def test_apartment_switch_skips_rooms_already_on_the_profile(client):
    client.xmlrpc.paramsets[("WTH_WZ:1", "VALUES")]["ACTIVE_PROFILE"] = 2
    r = client.post("/system/active-profile", json={"profile": 2})
    assert r.json() == {"rooms": 1, "skipped": 1, "deferred": 0, "background": True}
    profile_transfer.join(timeout=3)
    assert _active(client, "WTH_AZ") == 2
    assert ("WTH_WZ:1", "ACTIVE_PROFILE", 2) not in client.xmlrpc.set_calls


def test_apartment_switch_with_nothing_to_do_starts_no_job(client):
    for wth in ("WTH_WZ", "WTH_AZ"):
        client.xmlrpc.paramsets[(f"{wth}:1", "VALUES")]["ACTIVE_PROFILE"] = 3
    r = client.post("/system/active-profile", json={"profile": 3})
    assert r.json() == {"rooms": 0, "skipped": 2, "deferred": 0, "background": False}
    assert client.get("/system/climate/transfer").json()["kind"] is None


def test_apartment_switch_leaves_a_room_alone_whose_plan_could_not_be_written(
    client, monkeypatch
):
    profile_sets.put_mode("Wohnzimmer", False, {2: _FLAT_19})

    def boom(*a, **k):
        raise CcuError("radio timeout")

    monkeypatch.setattr(profile_transfer.prof, "write_days", boom)
    client.post("/system/active-profile", json={"profile": 2})
    profile_transfer.join(timeout=3)

    assert _active(client, "WTH_WZ") == 4          # not switched onto a stale plan
    assert _active(client, "WTH_AZ") == 2          # the other room still went ahead
    errors = client.get("/system/climate/transfer").json()["errors"]
    assert any(e.startswith("Wohnzimmer: Profil P2 nicht umgeschaltet") for e in errors)


def test_apartment_switch_defers_rooms_over_the_write_budget(client, monkeypatch):
    monkeypatch.setattr(profile_transfer, "MAX_APARTMENT_DAYS", 0)
    profile_sets.put_mode("Wohnzimmer", False, {2: _FLAT_19})  # needs 1 day > budget 0
    r = client.post("/system/active-profile", json={"profile": 2})
    assert r.json() == {"rooms": 1, "skipped": 0, "deferred": 1, "background": True}
    profile_transfer.join(timeout=3)
    assert _active(client, "WTH_WZ") == 4 and _active(client, "WTH_AZ") == 2
    assert client.get("/system/climate/transfer").json()["deferred"] == ["Wohnzimmer (1 Tage)"]


def test_apartment_switch_is_refused_while_a_transfer_runs(client):
    profile_transfer._state.running = True
    assert client.post("/system/active-profile", json={"profile": 2}).status_code == 409


def test_apartment_switch_rejects_an_invalid_profile(client):
    assert client.post("/system/active-profile", json={"profile": 7}).status_code == 422


# --- import -------------------------------------------------------------------------
def _export_doc(**overrides):
    doc = {
        "format": "ccu-dashboard-export", "version": 1, "exported_at": "2026-09-30T10:00:00+00:00",
        "profile_sets": {
            "Wohnzimmer": {"heating": {"1": _FLAT_19}, "cooling": {"1": _FLAT_19},
                           "active_profile": {"heating": 1, "cooling": 1}},
            "Arbeitszimmer": {"heating": {"2": _FLAT_19}},
        },
        "profile_names": {"1": "Standard", "2": "Urlaub"},
        "valve_channels": {"Wohnzimmer": [2, 3], "Arbeitszimmer": [1]},
        "change_history": [],
    }
    doc.update(overrides)
    return doc


def test_import_dry_run_reports_counts_and_changes_nothing(client):
    profile_names.set_name(1, "Alt")

    r = client.post("/import", json=_export_doc())

    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True and body["applied"] is False and body["errors"] == []
    assert (body["rooms"], body["profiles"], body["names"], body["valve_rooms"]) == (2, 3, 2, 2)
    assert profile_names.load() == {"1": "Alt"}
    assert profile_sets.load() == {}


def test_import_apply_replaces_data_backs_up_and_transfers(client, tmp_path):
    profile_names.set_name(1, "Alt")
    change_history.record_name(1, None, "Name P1")

    r = client.post("/import?apply=true", json=_export_doc())

    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is True and body["transfer_started"] is True
    assert body["backup_file"].startswith("vor-import-")
    backup = json.loads((tmp_path / body["backup_file"]).read_text(encoding="utf-8"))
    assert backup["profile_names"] == {"1": "Alt"}
    assert profile_names.load() == {"1": "Standard", "2": "Urlaub"}
    assert profile_sets.load()["Wohnzimmer"]["heating"]["1"] == _FLAT_19
    assert change_history.entries() == []
    saved = json.loads((tmp_path / "valve_channels.json").read_text(encoding="utf-8"))
    assert saved == {"Wohnzimmer": [2, 3], "Arbeitszimmer": [1]}
    assert client.device_map.valve_channels == saved
    profile_transfer.join(timeout=3)
    master = client.xmlrpc.paramsets[("WTH_WZ:1", "MASTER")]
    assert master["P1_ENDTIME_MONDAY_1"] == 1440 and master["P1_TEMPERATURE_MONDAY_1"] == 19.0


def test_import_collects_every_error_and_writes_nothing(client):
    doc = _export_doc(
        profile_sets={
            "Wohnzimmer": {
                "heating": {
                    "7": _FLAT_19,
                    "1": {"monday": [{"start": "00:00", "end": "12:00", "setpoint": 19}],
                          "funday": _FLAT_19["monday"],
                          "tuesday": [{"start": "00:00", "end": "24:00", "setpoint": 40}]},
                },
                "active_profile": {"heating": 9},
                "extra": 1,
            },
        },
        profile_names={"1": "", "8": "X"},
        valve_channels={"Wohnzimmer": [0, 13]},
    )

    r = client.post("/import?apply=true", json=doc)

    body = r.json()
    assert body["valid"] is False and body["applied"] is False
    errors = " | ".join(body["errors"])
    for part in ("„7“ ist kein Profil", "Montag: Zeitabschnitte decken", "unbekannter Tag „funday“",
                 "Dienstag, Abschnitt 1: 40 °C", "aktives Profil Heizen", "unbekannter Eintrag „extra“",
                 "Profilname P1", "Profilname „8“", "Ventil-Zuordnung „Wohnzimmer“"):
        assert part in errors, part
    assert profile_sets.load() == {} and profile_names.load() == {}


def test_import_rejects_foreign_files(client):
    assert client.post("/import", json={"hello": 1}).json()["errors"][0].startswith(
        "Die Datei ist kein Export")
    r = client.post("/import", json=_export_doc(version=2))
    assert "Version 2" in r.json()["errors"][0]


def test_import_warns_about_rooms_that_do_not_match(client):
    doc = _export_doc(profile_sets={"Keller": {"heating": {"1": _FLAT_19}}},
                      valve_channels={"Keller": [4]})

    warnings = client.post("/import", json=doc).json()["warnings"]

    assert any("„Keller“ hat keinen Thermostat" in w for w in warnings)
    assert any("Für „Arbeitszimmer“" in w for w in warnings)
    assert any("Für „Wohnzimmer“" in w for w in warnings)
    assert any("Ventil-Zuordnung für „Keller“" in w for w in warnings)


def test_import_refused_while_a_transfer_runs(client, monkeypatch):
    monkeypatch.setattr(profile_transfer, "is_running", lambda: True)

    r = client.post("/import?apply=true", json=_export_doc())

    assert r.status_code == 409
    assert profile_names.load() == {}


def test_export_import_roundtrip(client):
    profile_sets.put_mode("Wohnzimmer", False, {1: _FLAT_19})
    profile_names.set_name(3, "Party")
    exported = client.get("/export").json()
    profile_names.set_name(3, "Anders")

    r = client.post("/import?apply=true", json=exported)

    assert r.json()["applied"] is True
    assert profile_names.load() == {"3": "Party"}
    profile_transfer.join(timeout=3)


# --- scheduled heating/cooling switch ------------------------------------------------
def test_climate_schedule_is_off_by_default(client):
    body = client.get("/system/climate/schedule").json()
    assert body["heating"] is None and body["cooling"] is None and body["next"] is None
    assert body["timezone"] == "Europe/Berlin"


def test_climate_schedule_put_stores_and_reports_the_next_point(client):
    r = client.put("/system/climate/schedule", json={
        "heating": {"day": 15, "month": 9, "time": "08:00", "enabled": False},
        "cooling": {"day": 15, "month": 5, "time": "07:30", "enabled": True},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["heating"] == {"day": 15, "month": 9, "time": "08:00", "enabled": False}
    assert body["cooling"] == {"day": 15, "month": 5, "time": "07:30", "enabled": True}
    assert body["next"]["cooling"] is True and body["next"]["at"][5:16] == "05-15T07:30"
    assert client.get("/system/climate/schedule").json() == body


def test_climate_schedule_put_rejects_impossible_dates(client):
    r = client.put("/system/climate/schedule", json={
        "heating": {"day": 31, "month": 4, "time": "08:00", "enabled": True},
        "cooling": {"day": 15, "month": 5, "time": "07:30", "enabled": True},
    })
    assert r.status_code == 422
    assert "31.4." in r.json()["error"]["message"]


# --- schedule in the data backup -----------------------------------------------------
_SCHEDULE = {
    "heating": {"day": 15, "month": 9, "time": "08:00", "enabled": False},
    "cooling": {"day": 15, "month": 5, "time": "07:30", "enabled": True},
}


def test_export_contains_the_schedule_without_run_state(client):
    client.put("/system/climate/schedule", json=_SCHEDULE)

    body = client.get("/export").json()

    assert body["climate_schedule"] == _SCHEDULE


def test_export_of_an_unset_schedule_has_both_points_null(client):
    assert client.get("/export").json()["climate_schedule"] == {"heating": None, "cooling": None}


def test_import_replaces_the_schedule_without_switching(client):
    r = client.post("/import?apply=true", json=_export_doc(climate_schedule=_SCHEDULE))

    body = r.json()
    assert body["applied"] is True and body["schedule"] == "replace"
    assert client.get("/system/climate/schedule").json()["cooling"] == _SCHEDULE["cooling"]
    assert "last_handled" in climate_schedule.load()  # points up to now count as handled
    profile_transfer.join(timeout=3)


def test_import_of_an_unset_schedule_clears_it(client):
    client.put("/system/climate/schedule", json=_SCHEDULE)

    r = client.post("/import?apply=true",
                    json=_export_doc(climate_schedule={"heating": None, "cooling": None}))

    assert r.json()["schedule"] == "clear"
    state = client.get("/system/climate/schedule").json()
    assert state["heating"] is None and state["cooling"] is None and state["next"] is None
    profile_transfer.join(timeout=3)


def test_import_of_an_older_export_keeps_the_schedule(client):
    client.put("/system/climate/schedule", json=_SCHEDULE)

    r = client.post("/import?apply=true", json=_export_doc())  # no climate_schedule key

    body = r.json()
    assert body["schedule"] == "keep"
    assert any("keinen Zeitplan" in w for w in body["warnings"])
    assert client.get("/system/climate/schedule").json()["cooling"] == _SCHEDULE["cooling"]
    profile_transfer.join(timeout=3)


def test_import_rejects_a_broken_schedule(client):
    broken = {
        "heating": {"day": 31, "month": 4, "time": "08:00", "enabled": True},
        "cooling": {"day": 15, "month": 5, "time": "7 Uhr", "enabled": "ja"},
    }
    body = client.post("/import", json=_export_doc(climate_schedule=broken)).json()

    errors = " | ".join(body["errors"])
    assert body["valid"] is False
    assert "Zeitplan „Auf Heizen“: den 31.4." in errors
    assert "Zeitplan „Auf Kühlen“: day/month als Zahl" in errors

    half = {"heating": None, "cooling": _SCHEDULE["cooling"]}
    errors = client.post("/import", json=_export_doc(climate_schedule=half)).json()["errors"]
    assert any("beide gesetzt oder beide" in e for e in errors)


# --- dew point ----------------------------------------------------------------------
def test_dew_point_before_the_first_round(client, monkeypatch):
    from app.services import dew_point
    monkeypatch.setattr(dew_point, "_snapshot", None)
    body = client.get("/system/dew-point").json()
    assert body["level"] == "unbekannt" and body["rooms"] == []


def test_dew_point_returns_the_monitor_snapshot(client, monkeypatch):
    from types import SimpleNamespace

    from app.services import dew_point
    monkeypatch.setattr(dew_point, "_snapshot", None)
    dew_point.reset()
    snap = dew_point.evaluate(0.0, False, [SimpleNamespace(
        room="Bad", actual_temperature=22.0, humidity=50, valve=0.0)])
    monkeypatch.setattr(dew_point, "_snapshot", snap)

    body = client.get("/system/dew-point").json()

    assert body["level"] == "aus"
    assert body["rooms"][0]["room"] == "Bad" and body["rooms"][0]["dew_point"] == 11.1
    assert set(body["flow"]) >= {"effective", "source", "connection", "stale"}


# --- automatic backups ---------------------------------------------------------------
def test_backups_list_download_and_backup_now(client):
    assert client.get("/backups").json()["files"] == []

    body = client.post("/backups").json()
    assert body["keep"] == 14 and body["hour"] == 3
    [entry] = body["files"]
    assert entry["kind"] == "auto" and entry["name"].startswith("ccu-auto-")

    r = client.get(f"/backups/{entry['name']}")
    assert r.status_code == 200
    assert r.json()["format"] == "ccu-dashboard-export"
    assert 'filename="ccu-auto-' in r.headers["content-disposition"]


def test_backup_download_refuses_other_files(client):
    profile_names.set_name(1, "x")  # a real data file next to the backups
    for name in ("profile_names.json", "..%2Fprofile_names.json", "ccu-auto-2026-01-01.json"):
        assert client.get(f"/backups/{name}").status_code == 404, name


def test_device_health_endpoint(client, monkeypatch):
    from app.services import device_health
    monkeypatch.setattr(device_health, "_snapshot", None)
    assert client.get("/system/device-health").json()["message"] == "Erste Prüfung läuft noch."
    snap = device_health.evaluate(5.0, [device_health.DeviceState(
        "Bad", "WTH_BAD", "thermostat", True, True, 2.1, -70, False, False)], ccu_duty=4)
    monkeypatch.setattr(device_health, "_snapshot", snap)
    body = client.get("/system/device-health").json()
    assert body["level"] == "warnung" and body["ccu_duty_cycle"] == 4
    assert body["devices"][0]["voltage"] == 2.1


# --- health -------------------------------------------------------------------------
def test_health_reports_every_background_job(client, monkeypatch):
    from app.services import device_health, dew_point
    monkeypatch.setattr(system_router, "_check_ccu", lambda: "ok")
    monkeypatch.setattr(dew_point, "_snapshot", None)
    monkeypatch.setattr(device_health, "_snapshot", None)
    monkeypatch.delenv("MQTT_HOST", raising=False)

    body = client.get("/system/health").json()

    assert body["status"] == "ok" and body["ccu"] == "ok"
    assert body["mqtt"] == "nicht eingerichtet"
    assert body["dew_point"] == "noch keine Messung"
    assert body["devices"] == "noch nicht geprüft"
    assert body["backup"] == "noch keine" and body["backup_error"] is None

    client.post("/backups")
    assert client.get("/system/health").json()["backup"].startswith("ccu-auto-")


# --- only the running profile is live on the device ---------------------------------
def test_other_profiles_of_the_running_mode_come_from_the_store(client):
    """Regression: the thermostat's table for a slot that is not running may hold
    anything (shared heating/cooling table) -- the page must show the stored plan."""
    profile_sets.put_mode("Wohnzimmer", False, {3: _FLAT_19})
    client.xmlrpc.paramsets[("WTH_WZ:1", "MASTER")].update(
        {"P3_ENDTIME_MONDAY_1": 1440, "P3_TEMPERATURE_MONDAY_1": 27.0})   # stale device slot

    one = client.get("/rooms/Wohnzimmer/profiles/3").json()
    assert one["days"]["monday"] == _FLAT_19["monday"]
    listed = client.get("/rooms/Wohnzimmer/profiles").json()
    assert listed["active"] == 4
    assert listed["profiles"]["3"]["days"]["monday"] == _FLAT_19["monday"]


def test_editing_a_profile_that_does_not_run_stays_in_the_store(client):
    profile_sets.put_mode("Wohnzimmer", False, {3: _FLAT_19})
    r = client.post("/rooms/Wohnzimmer/profiles/3/days/MONDAY/blocks",
                    json={"start": "12:00", "end": "14:00", "setpoint": 21.0})
    assert r.status_code == 200, r.text
    assert client.jsonrpc.put_calls == []          # no radio traffic
    assert profile_sets.get_profile("Wohnzimmer", False, 3)["monday"] == [
        {"start": "00:00", "end": "12:00", "setpoint": 19.0},
        {"start": "12:00", "end": "14:00", "setpoint": 21.0},
        {"start": "14:00", "end": "24:00", "setpoint": 19.0},
    ]


def test_copying_a_stored_profile_into_the_running_one_writes_the_stored_plan(client):
    _run_p1(client)
    week = {d: [{"start": "00:00", "end": "24:00", "setpoint": 18.5}]
            for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}
    profile_sets.put_mode("Wohnzimmer", False, {3: week})
    client.xmlrpc.paramsets[("WTH_WZ:1", "MASTER")].update(
        {"P3_ENDTIME_MONDAY_1": 1440, "P3_TEMPERATURE_MONDAY_1": 27.0})   # stale device slot

    r = client.post("/rooms/Wohnzimmer/profiles/3/copy", json={"to_profile": 1})

    assert r.status_code == 200, r.text
    master = client.xmlrpc.paramsets[("WTH_WZ:1", "MASTER")]
    assert master["P1_ENDTIME_MONDAY_1"] == 1440 and master["P1_TEMPERATURE_MONDAY_1"] == 18.5
    assert profile_sets.get_profile("Wohnzimmer", False, 1)["monday"] == week["monday"]


def test_copying_the_running_profile_into_another_slot_uses_the_device_plan(client):
    _run_p1(client)
    r = client.post("/rooms/Wohnzimmer/profiles/1/copy", json={"to_profile": 5})
    assert r.status_code == 200, r.text
    assert client.jsonrpc.put_calls == []          # P5 does not run: store only
    stored = profile_sets.get_profile("Wohnzimmer", False, 5)["monday"]
    assert stored[0] == {"start": "00:00", "end": "06:00", "setpoint": 17.0}


# --- valve history -------------------------------------------------------------------
def test_valve_history_endpoint(client):
    import time

    from app.services import valve_history
    valve_history.record({"Wohnzimmer": 0.5}, now=time.time() - 600)
    body = client.get("/system/valve-history").json()
    assert body["rooms"] == {"Wohnzimmer": [50]} and len(body["times"]) == 1
    assert client.get("/system/valve-history", params={"hours": 100}).status_code == 422
