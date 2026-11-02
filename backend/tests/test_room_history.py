"""app.services.room_history - temperature, plan and valve of one room."""
import json
from dataclasses import dataclass
from datetime import datetime

from app.services import climate_schedule
from app.services import room_history as rh
from app.services.ccu.errors import CcuUnreachable
from app.services.ccu.mapping import RoomDevices

H = 3600.0


def test_record_and_series_for_one_room():
    rh.record({"Bad": (22.14, 21.0, 0.4), "Flur": (20.0, 18.0, 0.0)}, now=1000.0)
    rh.record({"Bad": (22.5, None, None)}, now=1300.0)
    s = rh.series("Bad", 48, now=1400.0)
    assert s.times == [1000.0, 1300.0]
    assert s.temperature == [22.1, 22.5]
    assert s.plan == [21.0, None]
    assert s.valve == [40, None]


def test_unknown_room_is_empty():
    rh.record({"Bad": (22.0, 21.0, 0.4)}, now=1000.0)
    s = rh.series("Keller", 48, now=1400.0)
    assert s.times == [] and s.temperature == [] and s.plan == [] and s.valve == []


def test_old_samples_are_dropped_after_72_hours():
    rh.record({"Bad": (20.0, 21.0, 0.1)}, now=0.0)
    rh.record({"Bad": (21.0, 21.0, 0.2)}, now=73 * H)
    assert rh.series("Bad", 72, now=73 * H).times == [73 * H]


def test_only_the_requested_window():
    for i in range(10):
        rh.record({"Bad": (20.0 + i, 21.0, 0.0)}, now=i * 300.0)
    s = rh.series("Bad", 0.25, now=9 * 300.0)            # last 15 minutes
    assert s.times == [1800.0, 2100.0, 2400.0, 2700.0]
    assert s.temperature == [26.0, 27.0, 28.0, 29.0]


def test_a_pause_breaks_the_lines():
    rh.record({"Bad": (20.0, 21.0, 0.5)}, now=0.0)
    rh.record({"Bad": (21.0, 21.0, 0.6)}, now=2 * H)
    s = rh.series("Bad", 48, now=2 * H)
    assert s.times == [0.0, 300.0, 2 * H]
    assert s.temperature == [20.0, None, 21.0]
    assert s.plan == [21.0, None, 21.0]
    assert s.valve == [50, None, 60]


def test_samples_survive_a_restart(tmp_path):
    rh.record({"Bad": (20.0, None, 0.5)}, now=1000.0)
    rh.reset()
    assert rh.series("Bad", 48, now=1100.0).plan == [None]
    assert rh.series("Bad", 48, now=1100.0).temperature == [20.0]


def test_a_damaged_file_starts_empty():
    with open(rh._PATH, "w", encoding="utf-8") as handle:
        json.dump({"samples": [[1.0, {"Bad": [20.0]}]]}, handle)
    rh.reset()
    assert rh.series("Bad", 48, now=2.0).times == []


class FakeXml:
    def __init__(self, master=None, active=2, fail=False):
        self.master = master if master is not None else {}
        self.active = active
        self.fail = fail

    def get_paramset(self, address, key="VALUES"):
        if self.fail:
            raise CcuUnreachable("down")
        return self.master if key == "MASTER" else {"ACTIVE_PROFILE": self.active}

    def get_value(self, address, key):
        if self.fail:
            raise CcuUnreachable("down")
        return self.active


ROOM = RoomDevices(room="Bad", wth_address="A", group_address=None)
# Monday 08:30 in the schedule's time zone
MONDAY = datetime(2026, 11, 2, 8, 30, tzinfo=climate_schedule.tz()).timestamp()
PLAN = {"P2_ENDTIME_MONDAY_1": 480, "P2_TEMPERATURE_MONDAY_1": 17.0,
        "P2_ENDTIME_MONDAY_2": 540, "P2_TEMPERATURE_MONDAY_2": 24.5,
        "P2_ENDTIME_MONDAY_3": 1440, "P2_TEMPERATURE_MONDAY_3": 18.0}


def test_plan_setpoint_uses_the_active_profile_and_local_time():
    assert rh.plan_setpoint(FakeXml(PLAN), ROOM, MONDAY) == 24.5
    assert rh.plan_setpoint(FakeXml(PLAN), ROOM, MONDAY + 3600) == 18.0


def test_plan_setpoint_is_none_when_unreadable():
    assert rh.plan_setpoint(FakeXml(fail=True), ROOM, MONDAY) is None
    assert rh.plan_setpoint(FakeXml({}), ROOM, MONDAY) is None


@dataclass
class SnapRoom:
    room: str
    temperature: float | None
    valve: float | None


@dataclass
class Map:
    rooms: dict


def test_collect_stores_temperature_plan_and_valve():
    rh.collect(FakeXml(PLAN), Map({"Bad": ROOM}),
               [SnapRoom("Bad", 22.0, 0.5), SnapRoom("Neu", 19.0, None)], now=MONDAY)
    s = rh.series("Bad", 1, now=MONDAY)
    assert s.temperature == [22.0] and s.plan == [24.5] and s.valve == [50]
    neu = rh.series("Neu", 1, now=MONDAY)                # not in the device map (yet)
    assert neu.temperature == [19.0] and neu.plan == [None] and neu.valve == [None]
