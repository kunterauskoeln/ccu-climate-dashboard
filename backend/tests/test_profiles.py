"""Tests for app.services.ccu.profiles using a fake XML-RPC client."""
import pytest
from conftest import FakeJsonRpc, FakeXmlRpc

from app.services.ccu import profiles
from app.services.ccu.errors import CcuError

WTH = "000AAAA0000001"
CH1 = f"{WTH}:1"


def _p1_monday_master() -> dict:
    ends = [360, 540, 1020, 1320, 1440, 1440, 1440, 1440, 1440, 1440, 1440, 1440, 1440]
    temps = [17.0, 21.0, 17.0, 21.0, 17.0, 17.0, 17.0, 17.0, 17.0, 17.0, 17.0, 17.0, 17.0]
    out = {}
    for i in range(1, 14):
        out[f"P1_ENDTIME_MONDAY_{i}"] = ends[i - 1]
        out[f"P1_TEMPERATURE_MONDAY_{i}"] = temps[i - 1]
    return out


@pytest.fixture
def xmlrpc() -> FakeXmlRpc:
    return FakeXmlRpc({(CH1, "MASTER"): _p1_monday_master()})


@pytest.fixture
def jsonrpc(xmlrpc) -> FakeJsonRpc:
    # putParamset writes land back in the fake XML-RPC MASTER so the
    # read-back verification in _apply_day sees them
    return FakeJsonRpc(xmlrpc=xmlrpc)


# --- reads --------------------------------------------------------------
def test_read_profile_returns_blocks_for_programmed_day(xmlrpc):
    wp = profiles.read_profile(xmlrpc, WTH, 1)
    assert wp.profile == 1
    assert wp.days["monday"] == [
        profiles.TimeBlock("00:00", "06:00", 17.0),
        profiles.TimeBlock("06:00", "09:00", 21.0),
        profiles.TimeBlock("09:00", "17:00", 17.0),
        profiles.TimeBlock("17:00", "22:00", 21.0),
        profiles.TimeBlock("22:00", "24:00", 17.0),
    ]
    assert wp.days["tuesday"] == []  # not in the fake master


def test_read_all_profiles_reads_master_once(xmlrpc):
    result = profiles.read_all_profiles(xmlrpc, WTH)
    assert set(result) == {1, 2, 3, 4, 5, 6}
    assert xmlrpc.get_calls == [(CH1, "MASTER")]


@pytest.mark.parametrize("bad", [0, 7])
def test_read_profile_rejects_out_of_range(xmlrpc, bad):
    with pytest.raises(CcuError):
        profiles.read_profile(xmlrpc, WTH, bad)


# --- edits (read-modify-write) --------------------------------------
def _written(jsonrpc) -> dict:
    """Flatten the last Interface.putParamset set=[{name,type,value}] back to
    {name: number} for assertions, checking the XML-RPC type names on the way."""
    address, key, typed_set = jsonrpc.put_calls[-1]
    assert (address, key) == (CH1, "MASTER")
    out = {}
    for item in typed_set:
        if "ENDTIME" in item["name"]:
            assert item["type"] == "int"
            out[item["name"]] = int(item["value"])
        else:
            assert item["type"] == "double"
            out[item["name"]] = float(item["value"])
    assert all(isinstance(v, str) for i in typed_set for v in [i["value"]])
    return out


def test_edit_range_writes_overlaid_master(xmlrpc, jsonrpc):
    profiles.edit_range(xmlrpc, jsonrpc, WTH, 1, "MONDAY", "12:00", "14:00", 23.0)

    assert len(jsonrpc.put_calls) == 1
    payload = _written(jsonrpc)
    # 09:00-17:00@17 is split; 12:00-14:00 becomes 23.0
    assert payload["P1_ENDTIME_MONDAY_3"] == 720   # 12:00
    assert payload["P1_TEMPERATURE_MONDAY_3"] == 17.0
    assert payload["P1_ENDTIME_MONDAY_4"] == 840   # 14:00
    assert payload["P1_TEMPERATURE_MONDAY_4"] == 23.0
    assert payload["P1_ENDTIME_MONDAY_5"] == 1020  # 17:00
    assert sum(k.startswith("P1_ENDTIME_MONDAY_") for k in payload) == 13


def test_edit_range_verifies_with_readback(xmlrpc, jsonrpc):
    # one MASTER read up front, JSON-RPC write, one MASTER read back to confirm
    profiles.edit_range(xmlrpc, jsonrpc, WTH, 1, "MONDAY", "12:00", "14:00", 23.0)
    assert xmlrpc.get_calls == [(CH1, "MASTER"), (CH1, "MASTER")]
    assert len(jsonrpc.put_calls) == 1


def test_edit_range_raises_if_write_not_confirmed(xmlrpc):
    # jsonrpc that silently drops the write -> read-back mismatch -> CcuError
    lossy = FakeJsonRpc()  # not linked to xmlrpc
    with pytest.raises(CcuError):
        profiles.edit_range(xmlrpc, lossy, WTH, 1, "MONDAY", "12:00", "14:00", 23.0)


def test_edit_range_returns_updated_week_profile(xmlrpc, jsonrpc):
    wp = profiles.edit_range(xmlrpc, jsonrpc, WTH, 1, "MONDAY", "12:00", "14:00", 23.0)
    assert wp.profile == 1
    assert profiles.TimeBlock("12:00", "14:00", 23.0) in wp.days["monday"]


def test_clear_range_deletes_block_and_inherits_previous(xmlrpc, jsonrpc):
    # delete 06:00-09:00 (the 21.0 block) -> gap takes the previous 17.0, coalesces
    profiles.clear_range(xmlrpc, jsonrpc, WTH, 1, "MONDAY", "06:00", "09:00")
    payload = _written(jsonrpc)
    assert payload["P1_ENDTIME_MONDAY_1"] == 1020   # 00:00-17:00 @ 17
    assert payload["P1_TEMPERATURE_MONDAY_1"] == 17.0
    assert payload["P1_ENDTIME_MONDAY_2"] == 1320   # 17:00-22:00 @ 21
    assert payload["P1_TEMPERATURE_MONDAY_2"] == 21.0


def test_edit_range_on_unprogrammed_day_seeds_base_block(xmlrpc, jsonrpc):
    profiles.edit_range(xmlrpc, jsonrpc, WTH, 1, "SUNDAY", "12:00", "14:00", 23.0)
    payload = _written(jsonrpc)
    assert payload["P1_ENDTIME_SUNDAY_1"] == 720    # 12:00
    assert payload["P1_TEMPERATURE_SUNDAY_1"] == 17.0
    assert payload["P1_ENDTIME_SUNDAY_2"] == 840    # 14:00
    assert payload["P1_TEMPERATURE_SUNDAY_2"] == 23.0
    assert payload["P1_ENDTIME_SUNDAY_3"] == 1440


def test_edit_range_rejects_setpoint_out_of_range(xmlrpc, jsonrpc):
    with pytest.raises(CcuError):
        profiles.edit_range(xmlrpc, jsonrpc, WTH, 1, "MONDAY", "12:00", "14:00", 40.0)


# --- copy --------------------------------------------------------------
def test_copy_single_day_to_another_day(xmlrpc, jsonrpc):
    # P1 MONDAY (360@17, 540@21, 1020@17, 1320@21, 1440@17) -> P1 WEDNESDAY
    wp = profiles.copy_profile(xmlrpc, jsonrpc, WTH, 1, WTH, 1,
                               from_day="MONDAY", to_day="WEDNESDAY")
    payload = _written(jsonrpc)
    assert payload["P1_ENDTIME_WEDNESDAY_1"] == 360
    assert payload["P1_TEMPERATURE_WEDNESDAY_2"] == 21.0
    assert wp.days["wednesday"] == wp.days["monday"]
    # only WEDNESDAY keys written
    assert {n.split("_")[2] for i in jsonrpc.put_calls[-1][2] for n in [i["name"]]} == {"WEDNESDAY"}


def test_copy_whole_profile_to_another_profile(xmlrpc, jsonrpc):
    wp = profiles.copy_profile(xmlrpc, jsonrpc, WTH, 1, WTH, 4)
    # one putParamset per day, 26 keys each, all P4_
    assert len(jsonrpc.put_calls) == 7
    items = [i for _, _, typed in jsonrpc.put_calls for i in typed]
    assert len(items) == 7 * 26
    assert all(i["name"].startswith("P4_") for i in items)
    assert {i["name"].split("_")[2] for i in items} == {
        "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY",
    }
    assert wp.profile == 4
    assert wp.days["monday"] == [
        profiles.TimeBlock("00:00", "06:00", 17.0),
        profiles.TimeBlock("06:00", "09:00", 21.0),
        profiles.TimeBlock("09:00", "17:00", 17.0),
        profiles.TimeBlock("17:00", "22:00", 21.0),
        profiles.TimeBlock("22:00", "24:00", 17.0),
    ]


def test_copy_to_another_room():
    dst_wth = "AABBCCDDEE"
    # one client serves both devices' MASTER, like the real get_xmlrpc()
    xr = FakeXmlRpc({
        (CH1, "MASTER"): _p1_monday_master(),
        (f"{dst_wth}:1", "MASTER"): {},
    })
    j = FakeJsonRpc(xmlrpc=xr)
    wp = profiles.copy_profile(xr, j, WTH, 1, dst_wth, 2)
    assert j.put_calls[0][0] == f"{dst_wth}:1"
    assert wp.profile == 2
    assert wp.days["monday"][1] == profiles.TimeBlock("06:00", "09:00", 21.0)


def test_copy_rejects_one_sided_day(xmlrpc, jsonrpc):
    with pytest.raises(CcuError):
        profiles.copy_profile(xmlrpc, jsonrpc, WTH, 1, WTH, 1, from_day="MONDAY")


def test_copy_one_day_to_many_days(xmlrpc, jsonrpc):
    wp = profiles.copy_profile(
        xmlrpc, jsonrpc, WTH, 1, WTH, 1,
        from_day="MONDAY", to_days=["WEDNESDAY", "FRIDAY", "SUNDAY"],
    )
    # one putParamset per target day
    assert len(jsonrpc.put_calls) == 3
    days = {
        i["name"].split("_")[2]
        for _, _, typed in jsonrpc.put_calls for i in typed
    }
    assert days == {"WEDNESDAY", "FRIDAY", "SUNDAY"}
    assert wp.days["wednesday"] == wp.days["friday"] == wp.days["sunday"] == wp.days["monday"]


# --- direct commands ---------------------------------------------------
def test_set_active_profile(xmlrpc):
    profiles.set_active_profile(xmlrpc, WTH, 3)
    assert xmlrpc.set_calls == [(CH1, "ACTIVE_PROFILE", 3)]


def test_set_active_profile_range(xmlrpc):
    with pytest.raises(CcuError):
        profiles.set_active_profile(xmlrpc, WTH, 9)


class _LiveXmlRpc(FakeXmlRpc):
    """set_value actually updates VALUES, so a confirm poll can succeed."""

    def set_value(self, address, key, value):
        self.set_calls.append((address, key, value))
        self.paramsets.setdefault((address, "VALUES"), {})[key] = value


def test_set_active_profile_confirmed_skips_write_if_already_active():
    live = _LiveXmlRpc({(CH1, "VALUES"): {"ACTIVE_PROFILE": 3}})
    assert profiles.set_active_profile_confirmed(live, WTH, 3) is True
    assert live.set_calls == []


def test_set_active_profile_confirmed_writes_and_confirms():
    live = _LiveXmlRpc({(CH1, "VALUES"): {"ACTIVE_PROFILE": 2}})
    ok = profiles.set_active_profile_confirmed(live, WTH, 5, timeout=0.05, poll=0)
    assert ok is True
    assert (CH1, "ACTIVE_PROFILE", 5) in live.set_calls
    assert profiles.get_active_profile(live, WTH) == 5


def test_set_active_profile_confirmed_false_if_it_never_lands(xmlrpc):
    # plain FakeXmlRpc: set_value is recorded but never updates VALUES
    xmlrpc.paramsets[(CH1, "VALUES")] = {"ACTIVE_PROFILE": 1}
    ok = profiles.set_active_profile_confirmed(xmlrpc, WTH, 4, timeout=0.05, poll=0)
    assert ok is False
    assert (CH1, "ACTIVE_PROFILE", 4) in xmlrpc.set_calls


def test_set_active_profile_confirmed_range():
    with pytest.raises(CcuError):
        profiles.set_active_profile_confirmed(FakeXmlRpc(), WTH, 9)


def test_set_setpoint_ok_and_bounds(xmlrpc):
    profiles.set_setpoint(xmlrpc, WTH, 21.5)
    assert xmlrpc.set_calls == [(CH1, "SET_POINT_TEMPERATURE", 21.5)]
    with pytest.raises(CcuError):
        profiles.set_setpoint(xmlrpc, WTH, 35.0)
    with pytest.raises(CcuError):
        profiles.set_setpoint(xmlrpc, WTH, 3.0)


def test_set_mode_puts_control_mode_on_values(xmlrpc):
    # verified on real hardware: write CONTROL_MODE via putParamset, not setValue
    profiles.set_mode(xmlrpc, WTH, 0)
    assert xmlrpc.set_calls == []
    assert xmlrpc.put_calls == [(CH1, "VALUES", {"CONTROL_MODE": 0})]
    with pytest.raises(CcuError):
        profiles.set_mode(xmlrpc, WTH, 5)


def test_set_boost(xmlrpc):
    profiles.set_boost(xmlrpc, WTH, True)
    assert xmlrpc.set_calls == [(CH1, "BOOST_MODE", True)]
