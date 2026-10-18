"""Tests for app.services.ccu.state using canned real paramsets."""
import pytest
from conftest import FakeJsonRpc, FakeXmlRpc

from app.services.ccu.mapping import RoomDevices
from app.services.ccu.state import read_state

WZ = RoomDevices(
    room="Wohnzimmer", wth_address="000AAAA0000001", group_address="INT0000003",
    valve_channels=("FAL:2", "FAL:3", "FAL:4"),  # Wohnzimmer has three floor circuits
)

# real dumps (2026-09-02)
CH1_VALUES = {
    "ACTIVE_PROFILE": 4, "ACTUAL_TEMPERATURE": 25.3, "BOOST_MODE": False,
    "HEATING_COOLING": 1, "HUMIDITY": 48, "SET_POINT_MODE": 1,
    "SET_POINT_TEMPERATURE": 27.0, "WINDOW_STATE": 0,
}
CH0_VALUES = {
    "LOW_BAT": False, "OPERATING_VOLTAGE": 2.9, "RSSI_DEVICE": -48, "UNREACH": False,
}
# the heating group's own LEVEL stays 0 on the real system; the actuator channels are the truth
GROUP_VALUES = {"LEVEL": "0.000000", "VALVE_STATE": "0"}
FAL_LEVELS = {("FAL:2", "VALUES"): {"LEVEL": 0.6}, ("FAL:3", "VALUES"): {"LEVEL": 0.0},
              ("FAL:4", "VALUES"): {"LEVEL": 0.3}}


def _clients(*, with_maint=True, with_valve=True):
    ps = {("000AAAA0000001:1", "VALUES"): CH1_VALUES, **(FAL_LEVELS if with_valve else {})}
    if with_maint:
        ps[("000AAAA0000001:0", "VALUES")] = CH0_VALUES
    x = FakeXmlRpc(ps)
    j = FakeJsonRpc(group_values={"INT0000003:1": GROUP_VALUES})
    return x, j


def test_full_state_from_all_three_sources():
    x, j = _clients()
    s = read_state(x, j, WZ, full=True)
    assert s.actual_temperature == 25.3
    assert s.set_temperature == 27.0
    assert s.humidity == 48
    assert s.mode_code == 1 and s.mode == "MANU"
    assert s.active_profile == 4
    assert s.window_open is False
    assert s.cooling is True          # HEATING_COOLING == 1
    assert s.boost is False
    assert s.valve == pytest.approx(0.3)   # mean of the three actuator circuits (0.6, 0, 0.3)
    assert s.battery_low is False
    assert s.voltage == 2.9
    assert s.rssi == -48
    assert s.reachable is True


def test_valve_only_reads_the_actuator_channels_but_not_the_maintenance_channel():
    x, j = _clients()
    s = read_state(x, j, WZ, full=False, valve=True)
    assert s.valve == pytest.approx(0.3)
    assert s.rssi is None                                    # maintenance not read
    assert ("000AAAA0000001:0", "VALUES") not in x.get_calls


def test_room_without_mapped_valve_channels_has_no_valve_value():
    x, j = _clients()
    unmapped = RoomDevices(room="Wohnzimmer", wth_address="000AAAA0000001", group_address="INT0000003")
    assert read_state(x, j, unmapped, full=True).valve is None


def test_summary_state_skips_maintenance_and_group():
    x, j = _clients()
    s = read_state(x, j, WZ, full=False)
    assert s.actual_temperature == 25.3
    assert s.valve is None            # group not queried
    assert s.rssi is None
    assert x.get_calls == [("000AAAA0000001:1", "VALUES")]  # only :1 was read


def test_state_survives_missing_maintenance_channel():
    x, j = _clients(with_maint=False)
    s = read_state(x, j, WZ, full=True)
    assert s.actual_temperature == 25.3
    assert s.battery_low is False
    assert s.voltage is None


def test_state_survives_missing_actuator_values():
    x, j = _clients(with_valve=False)
    s = read_state(x, j, WZ, full=True)
    assert s.valve is None
    assert s.set_temperature == 27.0


def test_unknown_mode_code_is_labelled():
    x, j = _clients()
    x.paramsets[("000AAAA0000001:1", "VALUES")] = {**CH1_VALUES, "SET_POINT_MODE": 2}
    s = read_state(x, j, WZ, full=False)
    assert s.mode == "PARTY"
