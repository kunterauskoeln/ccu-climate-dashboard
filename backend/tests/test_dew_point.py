"""app.services.dew_point / flow_sensor - Taupunktüberwachung."""
from types import SimpleNamespace

import pytest
from conftest import FakeXmlRpc

from app.services import dew_point as dp
from app.services import flow_sensor
from app.services.ccu.mapping import DeviceMap, RoomDevices

MIN = 60.0


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    dp.reset()
    monkeypatch.setattr(flow_sensor, "_latest", None)
    monkeypatch.setenv("MQTT_HOST", "broker")
    monkeypatch.setenv("MQTT_FLOW_TOPIC", "t/vorlauf")
    yield
    dp.reset()


def room(name, temp=26.0, hum=60, valve=0.5):
    return SimpleNamespace(room=name, actual_temperature=temp, humidity=hum, valve=valve)


# --- formula and classification ----------------------------------------------------
@pytest.mark.parametrize("t, rh, expected", [(26.0, 60, 17.6), (20.0, 50, 9.3), (30.0, 80, 26.2)])
def test_dew_point_magnus(t, rh, expected):
    assert dp.dew_point(t, rh) == pytest.approx(expected, abs=0.1)


def test_dew_point_rejects_impossible_humidity():
    assert dp.dew_point(20.0, 0) is None and dp.dew_point(20.0, 101) is None


@pytest.mark.parametrize("margin, status", [
    (None, "unbekannt"), (0.4, "gefahr"), (-2.0, "gefahr"), (1.0, "knapp"), (2.9, "knapp"), (3.0, "ok"),
])
def test_classify(margin, status):
    assert dp.classify(margin) == status


def test_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("DEW_WARN_MARGIN", "4")
    monkeypatch.setenv("DEW_ALARM_MARGIN", "2")
    assert dp.classify(1.5) == "gefahr" and dp.classify(3.0) == "knapp"


# --- payloads ------------------------------------------------------------------------
@pytest.mark.parametrize("payload, value", [
    (b"18.4", 18.4), (b" 17 \n", 17.0), (b'{"state": "18.25"}', 18.25),
    (b'{"temperature": 19.5, "unit": "C"}', 19.5), (b"19.1", 19.1),
    (b"unavailable", None), (b'{"foo": 1}', None), (b"true", None),
])
def test_parse_payload(payload, value):
    assert flow_sensor.parse_payload(payload) == value


def test_real_sensor_payload_and_its_timestamp():
    payload = b'{"temperature": 23.5, "timestamp": "2026-10-01T21:06:57.485295+02:00"}'
    assert flow_sensor.parse_payload(payload) == 23.5
    stamp = flow_sensor.payload_time(payload)
    assert stamp == pytest.approx(1790881617.485295)
    # a retained (older) message keeps its measuring time ...
    assert flow_sensor._measured_at(payload, stamp + 3600) == stamp
    # ... a clock running ahead or a missing/odd stamp falls back to the arrival time
    assert flow_sensor._measured_at(payload, stamp - 3600) == stamp - 3600
    assert flow_sensor._measured_at(b"18.4", 5.0) == 5.0
    assert flow_sensor._measured_at(b'{"temperature": 1, "timestamp": "gestern"}', 5.0) == 5.0


# --- flow validity: the sensor is only right while water flows ----------------------
def test_flow_reading_only_counts_after_valves_were_open_for_the_settle_time():
    t0 = 1_000_000.0
    flow_sensor.record(24.0, t0)                         # pipe warmed up, all valves closed
    snap = dp.evaluate(t0, True, [room("Bad", valve=0.0)])
    assert snap.flow.effective is None and snap.level == "ok"
    assert snap.rooms[0].status == "ventil_zu"
    assert snap.message.startswith("Alle Ventile zu")

    snap = dp.evaluate(t0 + MIN, True, [room("Bad", valve=0.8)])   # valve opens
    assert snap.flow.effective is None and snap.rooms[0].status == "unbekannt"
    flow_sensor.record(19.0, t0 + 5 * MIN)               # still settling: not trusted
    snap = dp.evaluate(t0 + 6 * MIN, True, [room("Bad", valve=0.8)])
    assert snap.flow.effective is None

    flow_sensor.record(17.0, t0 + 12 * MIN)              # after 10 min of flow
    snap = dp.evaluate(t0 + 12 * MIN, True, [room("Bad", valve=0.8)])
    assert snap.flow.source == "live" and snap.flow.effective == 17.0
    assert snap.rooms[0].dew_point == pytest.approx(17.6, abs=0.1)
    assert snap.rooms[0].status == "gefahr" and snap.level == "gefahr"
    assert snap.message.startswith("Kondensgefahr: Bad (-0,6 K)")


def test_last_valid_value_is_used_while_the_pipe_is_warm_again():
    t0 = 2_000_000.0
    dp.evaluate(t0, True, [room("WC", valve=1.0)])
    flow_sensor.record(18.0, t0 + 11 * MIN)
    dp.evaluate(t0 + 11 * MIN, True, [room("WC", valve=1.0)])
    # valves close, pipe warms up, then open again: warm readings are not trusted
    dp.evaluate(t0 + 60 * MIN, True, [room("WC", valve=0.0)])
    flow_sensor.record(25.0, t0 + 90 * MIN)
    snap = dp.evaluate(t0 + 91 * MIN, True, [room("WC", hum=40, valve=1.0)])
    assert snap.flow.source == "last_valid" and snap.flow.effective == 18.0
    assert snap.rooms[0].status == "ok"


def test_heating_water_never_becomes_the_comparison_value():
    t0 = 4_000_000.0
    dp.evaluate(t0, False, [room("Bad", valve=1.0)])              # heating, valve open
    flow_sensor.record(32.0, t0 + 15 * MIN)                        # warm heating water
    snap = dp.evaluate(t0 + 15 * MIN, False, [room("Bad", valve=1.0)])
    assert snap.flow.effective is None and snap.flow.last_valid is None
    assert snap.rooms[0].margin is None

    # switch to cooling: the warm value must not make the floor look safe
    snap = dp.evaluate(t0 + 16 * MIN, True, [room("Bad", valve=1.0)])
    assert snap.flow.effective is None and snap.rooms[0].status == "unbekannt"


def test_cooling_values_are_forgotten_after_a_switch_to_heating():
    t0 = 5_000_000.0
    dp.evaluate(t0, True, [room("Bad", valve=1.0)])
    flow_sensor.record(18.0, t0 + 11 * MIN)
    assert dp.evaluate(t0 + 11 * MIN, True, [room("Bad", valve=1.0)]).flow.effective == 18.0
    dp.evaluate(t0 + 20 * MIN, False, [room("Bad", valve=1.0)])     # heating season
    snap = dp.evaluate(t0 + 21 * MIN, True, [room("Bad", valve=1.0)])  # cooling again
    assert snap.flow.effective is None


def test_heating_mode_shows_dew_points_but_no_risk():
    flow_sensor.record(30.0, 0.0)
    snap = dp.evaluate(10.0, False, [room("Flur", valve=1.0)])
    assert snap.level == "aus" and snap.rooms[0].status == "aus"
    assert snap.rooms[0].dew_point is not None


def test_unknown_when_no_sensor_is_configured(monkeypatch):
    monkeypatch.delenv("MQTT_HOST")
    snap = dp.evaluate(0.0, True, [room("Bad", valve=1.0)])
    assert snap.level == "unbekannt" and "Kein Vorlauf-Sensor" in snap.message


def test_knapp_lists_the_tightest_rooms():
    t0 = 3_000_000.0
    dp.evaluate(t0, True, [room("A"), room("B")])
    flow_sensor.record(19.5, t0 + 10 * MIN)
    snap = dp.evaluate(t0 + 10 * MIN, True, [room("A", hum=60), room("B", hum=55), room("C", valve=0)])
    assert snap.level == "knapp"
    assert snap.message == "Taupunkt knapp: A (+1,9 K)"
    assert [r.status for r in snap.rooms] == ["knapp", "ok", "ventil_zu"]


# --- one monitor round against fake clients ------------------------------------------
def test_tick_reads_rooms_and_valves_from_the_ccu():
    xmlrpc = FakeXmlRpc({
        ("WTH_BAD:1", "VALUES"): {"ACTUAL_TEMPERATURE": 26.0, "HUMIDITY": 60, "SET_POINT_MODE": 0},
        ("FALMOT1:5", "VALUES"): {"LEVEL": 0.7},
        ("FALMOT1:0", "VALUES"): {"HEATING_COOLING": 1},
    })
    device_map = DeviceMap(rooms={"Bad": RoomDevices(
        room="Bad", wth_address="WTH_BAD", group_address=None, valve_channels=("FALMOT1:5",),
    )}, actuator_address="FALMOT1")

    snap = dp.tick(lambda: (xmlrpc, device_map), now=100.0)

    assert snap.cooling is True
    assert snap.rooms[0].valve == 0.7 and snap.rooms[0].dew_point == pytest.approx(17.6, abs=0.1)
    assert dp.snapshot() is snap
