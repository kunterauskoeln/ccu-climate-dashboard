"""app.services.climate_profiles - store <-> device bridge for Phase 2b."""
import pytest
from conftest import FakeJsonRpc, FakeXmlRpc

from app.services import climate_profiles, profile_sets
from app.services.ccu import profiles
from app.services.ccu.errors import CcuValidationError
from app.services.ccu.mapping import DeviceMap, RoomDevices

WZ = RoomDevices(room="Wohnzimmer", wth_address="WTH_WZ", group_address=None)
BAD = RoomDevices(room="Bad", wth_address="WTH_BAD", group_address=None)
DEVICE_MAP = DeviceMap(rooms={"Wohnzimmer": WZ, "Bad": BAD}, actuator_address="FAL1")


def _p1_monday() -> dict:
    ends = [360, 540, 1020, 1320, 1440] + [1440] * 8
    temps = [17.0, 21.0, 17.0, 21.0, 17.0] + [17.0] * 8
    out = {}
    for i in range(1, 14):
        out[f"P1_ENDTIME_MONDAY_{i}"] = ends[i - 1]
        out[f"P1_TEMPERATURE_MONDAY_{i}"] = temps[i - 1]
    return out


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(profile_sets, "_PATH", str(tmp_path / "profile_sets.json"))


@pytest.fixture
def xmlrpc():
    return FakeXmlRpc({
        ("WTH_WZ:1", "MASTER"): _p1_monday(),
        ("WTH_BAD:1", "MASTER"): {},
    })


@pytest.fixture
def jsonrpc(xmlrpc):
    return FakeJsonRpc(xmlrpc=xmlrpc)


def _seed_all(xmlrpc):
    for rd in DEVICE_MAP.rooms.values():
        climate_profiles.seed_room_if_empty(xmlrpc, rd.room, rd.wth_address)


# --- seeding --------------------------------------------------------------
def test_seed_room_if_empty_fills_both_modes_from_device(xmlrpc):
    climate_profiles.seed_room_if_empty(xmlrpc, "Wohnzimmer", "WTH_WZ")

    heat = profile_sets.get_profile("Wohnzimmer", False, 1)
    cool = profile_sets.get_profile("Wohnzimmer", True, 1)
    assert heat == cool
    assert heat["monday"][1] == {"start": "06:00", "end": "09:00", "setpoint": 21.0}
    assert heat["tuesday"] == []  # unprogrammed day stored as empty
    # only the one room was touched
    assert profile_sets.get_profile("Bad", False, 1) is None


def test_seed_room_if_empty_is_noop_once_a_mode_exists(xmlrpc):
    profile_sets.put_profile("Wohnzimmer", True, 1, {"monday": []})
    climate_profiles.seed_room_if_empty(xmlrpc, "Wohnzimmer", "WTH_WZ")
    # heating side not backfilled -> the existing (cooling-only) data is kept
    assert profile_sets.get_profile("Wohnzimmer", False, 1) is None


def test_seed_room_if_empty_swallows_read_errors_but_logs_them(caplog):
    class Boom(FakeXmlRpc):
        def get_paramset(self, *a, **k):
            raise RuntimeError("no CCU")

    climate_profiles.seed_room_if_empty(Boom(), "Wohnzimmer", "WTH_WZ")
    assert profile_sets.is_empty()
    assert "Wohnzimmer: seeding the profile store" in caplog.text


# --- swap (function exists but is not wired into the mode switch yet) -----
def test_swap_writes_only_differing_days(xmlrpc, jsonrpc):
    _seed_all(xmlrpc)
    cool = profile_sets.get_mode("Wohnzimmer", True)
    cool[1]["monday"][3]["setpoint"] = 23.0  # evening 21 -> 23
    profile_sets.put_mode("Wohnzimmer", True, cool)

    report = climate_profiles.swap_to(
        xmlrpc, jsonrpc, DEVICE_MAP, cooling=True, pace_seconds=0
    )

    assert report["written"] == {"Wohnzimmer": [1]}
    assert report["days"] == 1
    assert report["errors"] == []
    assert len(jsonrpc.put_calls) == 1
    _, key, typed = jsonrpc.put_calls[0]
    assert key == "MASTER"
    assert {i["name"].split("_")[2] for i in typed} == {"MONDAY"}
    assert xmlrpc.paramsets[("WTH_WZ:1", "MASTER")]["P1_TEMPERATURE_MONDAY_4"] == 23.0


def test_swap_noop_when_store_matches_device(xmlrpc, jsonrpc):
    _seed_all(xmlrpc)
    report = climate_profiles.swap_to(
        xmlrpc, jsonrpc, DEVICE_MAP, cooling=True, pace_seconds=0
    )
    assert jsonrpc.put_calls == []
    assert report["days"] == 0


def test_swap_defers_profiles_that_exceed_the_day_budget(xmlrpc, jsonrpc):
    _seed_all(xmlrpc)
    # rewrite P1 for every weekday so all 7 days differ from the device
    cool = profile_sets.get_mode("Wohnzimmer", True)
    for day in ("monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday"):
        cool[1][day] = [{"start": "00:00", "end": "24:00", "setpoint": 19.5}]
    profile_sets.put_mode("Wohnzimmer", True, cool)

    report = climate_profiles.swap_to(
        xmlrpc, jsonrpc, DEVICE_MAP, cooling=True, max_days=3, pace_seconds=0
    )
    assert jsonrpc.put_calls == []
    assert report["days"] == 0
    assert report["deferred"] == ["Wohnzimmer P1 (7d)"]


def test_swap_skips_room_without_stored_mode(xmlrpc, jsonrpc):
    profile_sets.put_profile(
        "Wohnzimmer", True, 1,
        {"monday": [{"start": "00:00", "end": "24:00", "setpoint": 19.0}]},
    )
    report = climate_profiles.swap_to(
        xmlrpc, jsonrpc, DEVICE_MAP, cooling=True, pace_seconds=0
    )
    assert list(report["written"]) == ["Wohnzimmer"]
    assert all(addr == "WTH_WZ:1" for addr, _, _ in jsonrpc.put_calls)


# --- active profile save/restore ------------------------------------------
def _xmlrpc_with_active_profile(wz_profile: int, bad_profile: int | None = None) -> FakeXmlRpc:
    paramsets = {
        ("WTH_WZ:1", "MASTER"): _p1_monday(),
        ("WTH_BAD:1", "MASTER"): {},
        ("WTH_WZ:1", "VALUES"): {"ACTIVE_PROFILE": wz_profile},
    }
    if bad_profile is not None:
        paramsets[("WTH_BAD:1", "VALUES")] = {"ACTIVE_PROFILE": bad_profile}
    return FakeXmlRpc(paramsets)


def test_save_active_profiles_reads_each_room_and_stores_under_the_mode():
    xmlrpc = _xmlrpc_with_active_profile(wz_profile=3, bad_profile=5)
    climate_profiles.save_active_profiles(xmlrpc, DEVICE_MAP, cooling=False)
    assert profile_sets.get_active_profile("Wohnzimmer", False) == 3
    assert profile_sets.get_active_profile("Bad", False) == 5
    assert profile_sets.get_active_profile("Wohnzimmer", True) is None  # other mode untouched


def test_save_active_profiles_logs_and_continues_when_a_room_raises(caplog):
    class Boom(FakeXmlRpc):
        def get_value(self, address, key):
            if address.startswith("WTH_BAD"):
                raise RuntimeError("radio timeout")
            return super().get_value(address, key)

    xmlrpc = Boom({("WTH_WZ:1", "VALUES"): {"ACTIVE_PROFILE": 3}})
    climate_profiles.save_active_profiles(xmlrpc, DEVICE_MAP, cooling=False)
    assert profile_sets.get_active_profile("Wohnzimmer", False) == 3
    assert profile_sets.get_active_profile("Bad", False) is None
    assert "Bad: could not save the active profile" in caplog.text


def test_save_active_profiles_skips_a_room_it_cant_read():
    xmlrpc = _xmlrpc_with_active_profile(wz_profile=3)  # Bad has no VALUES -> get_value -> None
    climate_profiles.save_active_profiles(xmlrpc, DEVICE_MAP, cooling=False)
    assert profile_sets.get_active_profile("Wohnzimmer", False) == 3
    assert profile_sets.get_active_profile("Bad", False) is None


class _LiveXmlRpc(FakeXmlRpc):
    """set_value actually updates VALUES, so the confirm poll can succeed --
    unlike the plain FakeXmlRpc, which only records the call."""

    def set_value(self, address, key, value):
        self.set_calls.append((address, key, value))
        self.paramsets.setdefault((address, "VALUES"), {})[key] = value


def test_restore_active_profiles_writes_and_confirms_the_stored_slot():
    profile_sets.put_active_profile("Wohnzimmer", True, 4)
    xmlrpc = _LiveXmlRpc({("WTH_WZ:1", "VALUES"): {"ACTIVE_PROFILE": 2}})  # drifted

    failures = climate_profiles.restore_active_profiles(
        xmlrpc, DEVICE_MAP, cooling=True, timeout=0.05, poll=0
    )

    assert failures == []
    assert ("WTH_WZ:1", "ACTIVE_PROFILE", 4) in xmlrpc.set_calls
    # Bad has no stored slot for cooling -> left alone
    assert not any(addr == "WTH_BAD:1" for addr, _, _ in xmlrpc.set_calls)


def test_restore_active_profiles_noop_when_nothing_stored():
    xmlrpc = _xmlrpc_with_active_profile(wz_profile=2)
    failures = climate_profiles.restore_active_profiles(
        xmlrpc, DEVICE_MAP, cooling=True, timeout=0.05, poll=0
    )
    assert xmlrpc.set_calls == []
    assert failures == []


def test_restore_active_profiles_reports_when_write_never_confirms():
    profile_sets.put_active_profile("Wohnzimmer", True, 4)
    # plain FakeXmlRpc: set_value is recorded but never actually updates VALUES
    xmlrpc = _xmlrpc_with_active_profile(wz_profile=2)

    failures = climate_profiles.restore_active_profiles(
        xmlrpc, DEVICE_MAP, cooling=True, timeout=0.05, poll=0
    )

    assert failures == ["Wohnzimmer: profile P4 not confirmed active"]


# --- store-only editing (Phase 2b.2, inactive-mode profile editor) --------
def test_week_from_store_fills_missing_days_empty():
    week = climate_profiles.week_from_store(3, {"monday": [
        {"start": "00:00", "end": "24:00", "setpoint": 19.0},
    ]})
    assert week.profile == 3
    assert week.days["monday"] == [profiles.TimeBlock("00:00", "24:00", 19.0)]
    assert week.days["tuesday"] == []


def test_edit_range_in_store_seeds_unprogrammed_day_and_persists():
    week = climate_profiles.edit_range_in_store(
        "Bad", True, 2, "MONDAY", "12:00", "14:00", 23.0
    )
    assert week.profile == 2
    assert week.days["monday"] == [
        profiles.TimeBlock("00:00", "12:00", 17.0),
        profiles.TimeBlock("12:00", "14:00", 23.0),
        profiles.TimeBlock("14:00", "24:00", 17.0),
    ]
    # persisted -- a second read sees the same thing without re-editing
    assert profile_sets.get_profile("Bad", True, 2)["monday"] == [
        {"start": "00:00", "end": "12:00", "setpoint": 17.0},
        {"start": "12:00", "end": "14:00", "setpoint": 23.0},
        {"start": "14:00", "end": "24:00", "setpoint": 17.0},
    ]


def test_edit_range_in_store_rejects_out_of_range_setpoint():
    with pytest.raises(CcuValidationError):
        climate_profiles.edit_range_in_store("Bad", True, 1, "MONDAY", "12:00", "14:00", 40.0)


def test_clear_range_in_store_deletes_and_inherits_previous():
    climate_profiles.edit_range_in_store("Bad", True, 1, "MONDAY", "06:00", "09:00", 21.0)
    climate_profiles.edit_range_in_store("Bad", True, 1, "MONDAY", "17:00", "22:00", 21.0)
    week = climate_profiles.clear_range_in_store("Bad", True, 1, "MONDAY", "06:00", "09:00")
    assert week.days["monday"] == [
        profiles.TimeBlock("00:00", "17:00", 17.0),
        profiles.TimeBlock("17:00", "22:00", 21.0),
        profiles.TimeBlock("22:00", "24:00", 17.0),
    ]


def test_read_all_profiles_from_store_covers_every_profile_and_day():
    climate_profiles.edit_range_in_store("Bad", False, 4, "FRIDAY", "10:00", "11:00", 25.5)
    weeks = climate_profiles.read_all_profiles_from_store("Bad", False)
    assert set(weeks) == {1, 2, 3, 4, 5, 6}
    assert weeks[4].days["friday"][1] == profiles.TimeBlock("10:00", "11:00", 25.5)
    assert weeks[1].days["monday"] == []  # never touched


def test_copy_profile_in_store_whole_week():
    climate_profiles.edit_range_in_store("Bad", True, 1, "MONDAY", "06:00", "09:00", 21.0)
    week = climate_profiles.copy_profile_in_store("Bad", True, 1, "Bad", 3)
    assert week.profile == 3
    assert week.days["monday"] == [
        profiles.TimeBlock("00:00", "06:00", 17.0),
        profiles.TimeBlock("06:00", "09:00", 21.0),
        profiles.TimeBlock("09:00", "24:00", 17.0),
    ]
    # every day of the week was copied, not just the edited one
    assert week.days["tuesday"] == [profiles.TimeBlock("00:00", "24:00", 17.0)]


def test_copy_profile_in_store_single_day_to_many_days():
    climate_profiles.edit_range_in_store("Bad", True, 1, "MONDAY", "06:00", "09:00", 21.0)
    week = climate_profiles.copy_profile_in_store(
        "Bad", True, 1, "Bad", 1, from_day="MONDAY", to_days=["WEDNESDAY", "FRIDAY"],
    )
    assert week.days["wednesday"] == week.days["monday"] == week.days["friday"]
    assert week.days["tuesday"] == []  # untouched


def test_copy_profile_in_store_to_another_room():
    climate_profiles.edit_range_in_store("Bad", True, 5, "SUNDAY", "08:00", "10:00", 19.5)
    week = climate_profiles.copy_profile_in_store("Bad", True, 5, "Wohnzimmer", 5)
    assert profile_sets.get_profile("Wohnzimmer", True, 5)["sunday"] == [
        {"start": "00:00", "end": "08:00", "setpoint": 17.0},
        {"start": "08:00", "end": "10:00", "setpoint": 19.5},
        {"start": "10:00", "end": "24:00", "setpoint": 17.0},
    ]
    assert week.profile == 5


def test_copy_profile_in_store_rejects_one_sided_day():
    with pytest.raises(CcuValidationError):
        climate_profiles.copy_profile_in_store("Bad", True, 1, "Bad", 1, from_day="MONDAY")


def test_copy_profile_in_store_rejects_day_target_without_from_day():
    with pytest.raises(CcuValidationError):
        climate_profiles.copy_profile_in_store("Bad", True, 1, "Bad", 2, to_day="TUESDAY")


def test_store_only_edit_never_touches_the_device():
    xmlrpc = FakeXmlRpc()
    jsonrpc = FakeJsonRpc(xmlrpc=xmlrpc)
    climate_profiles.edit_range_in_store("Bad", True, 1, "MONDAY", "06:00", "09:00", 21.0)
    assert xmlrpc.get_calls == [] and xmlrpc.put_calls == [] and xmlrpc.set_calls == []
    assert jsonrpc.put_calls == []
