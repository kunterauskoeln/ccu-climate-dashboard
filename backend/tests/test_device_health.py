"""app.services.device_health and the duty cycle brake of the profile transfer."""
import pytest
from conftest import FakeJsonRpc, FakeXmlRpc

from app.services import device_health as dh
from app.services.ccu.errors import CcuError
from app.services.ccu.mapping import DeviceMap, RoomDevices

WTH = {"CONFIG_PENDING": False, "DUTY_CYCLE": False, "LOW_BAT": False, "UNREACH": False,
       "OPERATING_VOLTAGE": 2.9, "RSSI_DEVICE": -55}
ACTOR = {"CONFIG_PENDING": False, "DUTY_CYCLE": False, "UNREACH": False, "RSSI_DEVICE": -43}


def device_map():
    return DeviceMap(rooms={
        "Bad": RoomDevices(room="Bad", wth_address="WTH_BAD", group_address=None),
        "Flur": RoomDevices(room="Flur", wth_address="WTH_FLUR", group_address=None),
    }, actuator_address="FALMOT1")


def test_all_fine():
    xmlrpc = FakeXmlRpc({("WTH_BAD:0", "VALUES"): WTH, ("WTH_FLUR:0", "VALUES"): WTH,
                         ("FALMOT1:0", "VALUES"): ACTOR})
    jsonrpc = FakeJsonRpc()
    jsonrpc.duty_cycle = 3
    snap = dh.tick(xmlrpc, jsonrpc, device_map(), now=1.0)
    assert snap.level == "ok" and snap.message == "Alle Geräte in Ordnung."
    assert snap.ccu_duty_cycle == 3
    actor = snap.devices[-1]
    assert actor.name == "Aktor" and actor.low_battery is None and actor.voltage is None
    assert dh.snapshot() is snap


def test_problems_are_listed():
    xmlrpc = FakeXmlRpc({
        ("WTH_BAD:0", "VALUES"): {**WTH, "LOW_BAT": True, "OPERATING_VOLTAGE": 2.2},
        ("WTH_FLUR:0", "VALUES"): {**WTH, "UNREACH": True, "DUTY_CYCLE": True},
        ("FALMOT1:0", "VALUES"): ACTOR,
    })
    jsonrpc = FakeJsonRpc()
    jsonrpc.duty_cycle = 65
    snap = dh.tick(xmlrpc, jsonrpc, device_map(), now=1.0)
    assert snap.level == "warnung"
    assert snap.problems == ["Bad: Batterie schwach (2,2 V)", "Flur: nicht erreichbar",
                             "Flur: Funk-Limit erreicht", "CCU-Funkauslastung 65 %"]
    assert snap.message.startswith("Geräte: Bad: Batterie schwach (2,2 V) · ")


def test_unreadable_device_and_unknown_duty_cycle():
    class Broken(FakeXmlRpc):
        def get_paramset(self, address, key="VALUES"):
            if address == "WTH_FLUR:0":
                raise CcuError("timeout")
            return super().get_paramset(address, key)

    xmlrpc = Broken({("WTH_BAD:0", "VALUES"): WTH, ("FALMOT1:0", "VALUES"): ACTOR})
    snap = dh.tick(xmlrpc, FakeJsonRpc(), device_map(), now=1.0)
    assert snap.ccu_duty_cycle is None
    assert snap.problems == ["Flur: Zustand nicht lesbar"]


@pytest.fixture
def fresh_health():
    dh.reset()
    yield
    dh.reset()


def _pending_map(bad_pending=True, flur_unreadable=False):
    class X(FakeXmlRpc):
        def get_paramset(self, address, key="VALUES"):
            if flur_unreadable and address == "WTH_FLUR:0":
                raise CcuError("timeout")
            return super().get_paramset(address, key)

    return X({("WTH_BAD:0", "VALUES"): {**WTH, "CONFIG_PENDING": bad_pending},
              ("WTH_FLUR:0", "VALUES"): {**WTH, "CONFIG_PENDING": True},
              ("FALMOT1:0", "VALUES"): ACTOR})


def test_short_config_pending_is_normal(fresh_health):
    snap = dh.tick(_pending_map(), FakeJsonRpc(), device_map(), now=1000.0)
    snap = dh.tick(_pending_map(), FakeJsonRpc(), device_map(), now=1000.0 + 29 * 60)
    assert snap.level == "ok"
    bad = snap.devices[0]
    assert bad.config_pending and bad.config_pending_since == 1000.0 and not bad.config_stuck


def test_long_config_pending_is_a_problem(fresh_health):
    dh.tick(_pending_map(), FakeJsonRpc(), device_map(), now=1000.0)
    snap = dh.tick(_pending_map(), FakeJsonRpc(), device_map(), now=1000.0 + 3 * 3600)
    assert snap.level == "warnung"
    assert "Bad: Einstellungen seit 3 h nicht übertragen" in snap.problems
    assert all(d.config_stuck for d in snap.devices[:2])


def test_config_pending_clock_restarts_once_gone(fresh_health):
    dh.tick(_pending_map(), FakeJsonRpc(), device_map(), now=1000.0)
    dh.tick(_pending_map(bad_pending=False), FakeJsonRpc(), device_map(), now=2000.0)
    snap = dh.tick(_pending_map(), FakeJsonRpc(), device_map(), now=1000.0 + 3 * 3600)
    assert snap.devices[0].config_pending_since == 1000.0 + 3 * 3600
    assert not snap.devices[0].config_stuck


def test_unreadable_device_keeps_pending_clock(fresh_health):
    dh.tick(_pending_map(), FakeJsonRpc(), device_map(), now=1000.0)
    snap = dh.tick(_pending_map(flur_unreadable=True), FakeJsonRpc(), device_map(),
                   now=1000.0 + 3 * 86400)
    flur = snap.devices[1]
    assert flur.reachable is None and flur.config_pending_since == 1000.0 and flur.config_stuck
    assert "Flur: Einstellungen seit 3 Tagen nicht übertragen" in snap.problems


@pytest.mark.parametrize("seconds, text", [(45 * 60, "45 min"), (5 * 3600, "5 h"),
                                           (49 * 3600, "2 Tagen")])
def test_duration(seconds, text):
    assert dh._duration(seconds) == text


@pytest.mark.parametrize("interfaces, expected", [
    ([{"dutyCycle": "7", "isDefault": True}], 7),
    ([{"dutyCycle": "50", "isDefault": False}, {"dutyCycle": "2", "isDefault": True}], 2),
    ([{"dutyCycle": "9"}], 9),
    ([], None), ("kaputt", None), ([{"dutyCycle": "?"}], None),
])
def test_read_ccu_duty_cycle(interfaces, expected):
    class J:
        def call(self, method, params=None):
            return interfaces
    assert dh.read_ccu_duty_cycle(J()) == expected


def test_duty_cycle_error_does_not_raise():
    class J:
        def call(self, method, params=None):
            raise CcuError("too many sessions")
    assert dh.read_ccu_duty_cycle(J()) is None
