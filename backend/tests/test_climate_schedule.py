"""app.services.climate_schedule - yearly scheduled heating/cooling switch."""
from datetime import datetime

import pytest
from conftest import FakeXmlRpc

from app.services import climate_schedule as cs
from app.services.ccu.errors import CcuUnreachable
from app.services.ccu.mapping import DeviceMap

BERLIN = cs.tz()
HEAT = cs.Point(15, 9, "08:00")   # 15.09. 08:00 -> heating
COOL = cs.Point(15, 5, "08:00")   # 15.05. 08:00 -> cooling
OFF_HEAT = cs.Point(15, 9, "08:00", enabled=False)
OFF_COOL = cs.Point(15, 5, "08:00", enabled=False)


def at(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=BERLIN)


@pytest.fixture
def switches(monkeypatch):
    """Fake CCU on heating; records every real switch."""
    xmlrpc = FakeXmlRpc({("FALMOT1:0", "VALUES"): {"HEATING_COOLING": 0}})
    device_map = DeviceMap(rooms={}, actuator_address="FALMOT1")
    monkeypatch.setattr(cs, "_make_clients", lambda: (xmlrpc, device_map))
    calls = []

    def fake_switch(x, dm, cooling):
        calls.append(cooling)
        x.paramsets[("FALMOT1:0", "VALUES")]["HEATING_COOLING"] = int(cooling)
        return True

    monkeypatch.setattr(cs.climate_switch, "switch", fake_switch)
    return calls


def test_latest_and_next_due_pick_the_right_point_across_the_year_boundary():
    data = {"heating": HEAT.as_dict(), "cooling": COOL.as_dict()}
    # January: last point was heating in September of the previous year
    assert cs.latest_due(data, at(2027, 1, 10)) == cs.Due(at(2026, 9, 15, 8), False)
    assert cs.next_due(data, at(2027, 1, 10)) == cs.Due(at(2027, 5, 15, 8), True)
    # exactly at the cooling point it is due
    assert cs.latest_due(data, at(2027, 5, 15, 8)) == cs.Due(at(2027, 5, 15, 8), True)
    assert cs.next_due(data, at(2027, 10, 1)) == cs.Due(at(2028, 5, 15, 8), True)
    only_heat = {"heating": HEAT.as_dict(), "cooling": OFF_COOL.as_dict()}
    assert cs.next_due(only_heat, at(2027, 1, 10)) == cs.Due(at(2027, 9, 15, 8), False)
    both_off = {"heating": OFF_HEAT.as_dict(), "cooling": OFF_COOL.as_dict()}
    assert cs.next_due(both_off, at(2027, 1, 10)) is None


def test_29_february_becomes_28_february_in_other_years():
    point = cs.Point(29, 2, "06:30")
    point.validate("x")
    assert point.at(2027, BERLIN) == at(2027, 2, 28, 6, 30)
    assert point.at(2028, BERLIN) == at(2028, 2, 29, 6, 30)


@pytest.mark.parametrize("point, message", [
    (cs.Point(31, 4, "08:00"), "31.4."),
    (cs.Point(1, 13, "08:00"), "Monat 13"),
    (cs.Point(1, 5, "24:00"), "24:00"),
    (cs.Point(1, 5, "8 Uhr"), "HH:MM"),
])
def test_configure_rejects_impossible_points(point, message):
    with pytest.raises(ValueError, match=message):
        cs.configure(point, COOL)


def test_configure_rejects_the_same_point_twice():
    with pytest.raises(ValueError, match="verschiedene"):
        cs.configure(COOL, COOL)


def test_enabling_does_not_switch_right_away(switches):
    cs.configure(HEAT, COOL, now=at(2027, 6, 1))   # cooling would be "due" since May
    cs.tick(at(2027, 6, 1, 0, 1))
    assert switches == []


def test_switches_once_when_the_point_passes(switches):
    cs.configure(HEAT, COOL, now=at(2027, 5, 1))
    cs.tick(at(2027, 5, 15, 7, 59))
    assert switches == []
    cs.tick(at(2027, 5, 15, 8, 0))
    assert switches == [True]
    cs.tick(at(2027, 5, 15, 8, 1))
    assert switches == [True]
    run = cs.load()["last_run"]
    assert run["result"] == "switched" and run["cooling"] is True


def test_missed_points_are_caught_up_with_the_latest_one_only(switches):
    cs.configure(HEAT, COOL, now=at(2027, 5, 1))
    # server was off from April until October: cooling (May) and heating (Sept) missed
    cs.tick(at(2027, 10, 3, 12))
    assert switches == []  # heating is due and the system is on heating already
    assert cs.load()["last_run"]["result"] == "already"

    cs.configure(HEAT, COOL, now=at(2027, 5, 1))
    cs.tick(at(2027, 7, 3, 12))  # only the cooling point (May) passed
    assert switches == [True]


def test_a_manual_switch_after_the_point_is_not_undone(switches):
    cs.configure(HEAT, COOL, now=at(2027, 5, 1))
    cs.tick(at(2027, 5, 15, 8))
    assert switches == [True]
    # user switches back to heating by hand; later ticks leave it alone
    cs.tick(at(2027, 6, 1))
    assert switches == [True]


def test_disabled_schedule_does_nothing(switches):
    cs.configure(OFF_HEAT, OFF_COOL, now=at(2027, 5, 1))
    cs.tick(at(2027, 5, 16))
    assert switches == []


def test_ccu_error_is_retried_on_the_next_tick(switches, monkeypatch):
    cs.configure(HEAT, COOL, now=at(2027, 5, 1))
    real = cs._make_clients

    def broken():
        raise CcuUnreachable("CCU nicht erreichbar")

    monkeypatch.setattr(cs, "_make_clients", broken)
    cs.tick(at(2027, 5, 15, 8))
    assert cs.load()["last_run"]["result"] == "error"
    assert switches == []

    monkeypatch.setattr(cs, "_make_clients", real)
    cs.tick(at(2027, 5, 15, 8, 1))
    assert switches == [True]
    assert cs.load()["last_run"]["result"] == "switched"


def test_only_the_switched_on_point_switches(switches):
    cs.configure(OFF_HEAT, COOL, now=at(2027, 5, 1))
    cs.tick(at(2027, 5, 15, 8))
    assert switches == [True]
    cs.tick(at(2027, 9, 15, 8))   # heating point is off: stays on cooling
    assert switches == [True]
    cs.tick(at(2028, 5, 15, 8))   # next year's cooling point: acted on again
    assert cs.load()["last_run"]["due"].startswith("2028-05-15T08:00")
    assert cs.load()["last_run"]["result"] == "already"  # still on cooling


def test_a_missed_point_is_not_caught_up_once_the_switched_off_point_passed(switches):
    cs.configure(OFF_HEAT, COOL, now=at(2027, 5, 1))
    # server off from before May until October: the cooling season is over
    cs.tick(at(2027, 10, 3, 12))
    assert switches == []
    cs.tick(at(2027, 10, 3, 12, 1))
    assert switches == []


def test_old_files_with_one_switch_for_both_points_still_work():
    data = {"enabled": True, "heating": {"day": 15, "month": 9, "time": "08:00"},
            "cooling": {"day": 15, "month": 5, "time": "08:00"}}
    assert cs.points(data) == {"heating": HEAT, "cooling": COOL}
    data["enabled"] = False
    assert cs.points(data) == {"heating": OFF_HEAT, "cooling": OFF_COOL}
