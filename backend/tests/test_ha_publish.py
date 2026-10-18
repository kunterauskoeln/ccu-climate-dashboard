"""app.services.ha_publish - Home Assistant MQTT discovery and state."""
import json
from types import SimpleNamespace

import pytest

from app.services import dew_point as dp
from app.services import flow_sensor, ha_publish


@pytest.fixture
def sent(monkeypatch):
    """Capture publishes instead of talking to a broker."""
    messages: list[tuple[str, dict | str, bool]] = []

    def fake_publish(topic, payload, *, retain=False):
        try:
            body = json.loads(payload)
        except ValueError:
            body = payload
        messages.append((topic, body, retain))
        return True

    monkeypatch.setenv("MQTT_HOST", "broker")
    monkeypatch.setenv("MQTT_FLOW_TOPIC", "t/vorlauf")
    monkeypatch.setattr(flow_sensor, "publish", fake_publish)
    monkeypatch.setattr(ha_publish, "_announced", None)
    dp.reset()
    return messages


def snapshot(*rooms, cooling=True):
    return dp.evaluate(0.0, cooling, [
        SimpleNamespace(room=name, actual_temperature=26.0, humidity=60, valve=valve)
        for name, valve in rooms])


@pytest.mark.parametrize("name, expected", [
    ("Wohnzimmer", "wohnzimmer"), ("Kinderzimmer Süd", "kinderzimmer_sued"),
    ("Bad/WC", "bad_wc"), ("Größe", "groesse"), ("!!!", "raum"),
])
def test_slug(name, expected):
    assert ha_publish.slug(name) == expected


def test_first_round_announces_every_entity_then_sends_the_state(sent):
    ha_publish.publish(snapshot(("Bad", 0.5), ("Wohnzimmer", 0.0)))

    configs = {t: b for t, b, _ in sent if t.endswith("/config")}
    assert all(t.startswith("homeassistant/") and "/ccu_dashboard/" in t for t in configs)
    assert len(configs) == 12 + 2 * 4
    assert all(retain for _, _, retain in sent)
    dew = configs["homeassistant/sensor/ccu_dashboard/bad_taupunkt/config"]
    assert dew["name"] == "Bad Taupunkt" and dew["unique_id"] == "ccu_dashboard_bad_taupunkt"
    assert dew["state_topic"] == "ccu-dashboard/state"
    assert dew["availability_topic"] == "ccu-dashboard/status"
    assert dew["value_template"] == "{{ value_json.rooms.bad.dew_point }}"
    assert dew["device"]["identifiers"] == ["ccu_dashboard"]
    alarm = configs["homeassistant/binary_sensor/ccu_dashboard/kondensgefahr/config"]
    assert alarm["device_class"] == "moisture"

    topic, state, _ = sent[-1]
    assert topic == "ccu-dashboard/state"
    assert state["rooms"]["bad"]["valve"] == 50
    assert state["rooms"]["bad"]["dew_point"] == pytest.approx(17.6, abs=0.1)
    assert state["rooms"]["wohnzimmer"]["status"] == "ventil_zu"


def test_later_rounds_send_only_the_state(sent):
    ha_publish.publish(snapshot(("Bad", 0.5)))
    sent.clear()
    ha_publish.publish(snapshot(("Bad", 0.5)))
    assert [t for t, _, _ in sent] == ["ccu-dashboard/state"]


def test_a_new_room_or_a_reconnect_announces_again(sent):
    ha_publish.publish(snapshot(("Bad", 0.5)))
    sent.clear()
    ha_publish.publish(snapshot(("Bad", 0.5), ("Flur", 0.2)))
    assert any(t.endswith("flur_taupunkt/config") for t, _, _ in sent)

    sent.clear()
    ha_publish._mark_reconnected()           # what the connect hook does
    ha_publish.publish(snapshot(("Bad", 0.5), ("Flur", 0.2)))
    assert sum(t.endswith("/config") for t, _, _ in sent) == 12 + 2 * 4


def test_not_connected_means_announce_later(sent, monkeypatch):
    monkeypatch.setattr(flow_sensor, "publish", lambda *a, **k: False)
    ha_publish.publish(snapshot(("Bad", 0.5)))
    assert ha_publish._announced is None


def test_switched_off(sent, monkeypatch):
    monkeypatch.setenv("HA_DISCOVERY", "0")
    ha_publish.publish(snapshot(("Bad", 0.5)))
    assert sent == []


def test_templates_render_with_jinja_like_home_assistant(sent):
    """The value templates must work on the state document as HA renders them."""
    jinja2 = pytest.importorskip("jinja2")
    ha_publish.publish(snapshot(("Bad", 1.0), ("WC", 0.0)))
    state = sent[-1][1]
    configs = {t: b for t, b, _ in sent if t.endswith("/config")}
    rendered = {t.split("/")[-2]: jinja2.Template(c["value_template"]).render(value_json=state)
                for t, c in configs.items()}
    assert rendered["kuehlbetrieb"] == "ON"
    assert rendered["kondensgefahr"] in ("ON", "OFF")
    assert rendered["wc_bewertung"] == "ventil_zu"
    assert rendered["bad_ventil"] == "100"
    assert rendered["vorlauf"] == "None"     # HA shows "unknown" for "None"


def test_device_health_entities_and_state(sent):
    from app.services import device_health as dh
    health = dh.evaluate(0.0, [
        dh.DeviceState("Bad", "WTH_BAD", "thermostat", True, True, 2.2, -60, False, False),
        dh.DeviceState("Aktor", "FALMOT1", "aktor", False, None, None, -45, False, False),
    ], ccu_duty=12)
    ha_publish.publish(snapshot(("Bad", 0.5)), health)

    configs = {t.split("/")[-2]: b for t, b, _ in sent if t.endswith("/config")}
    assert configs["bad_batterie_schwach"]["device_class"] == "battery"
    assert configs["bad_batteriespannung"]["unit_of_measurement"] == "V"
    assert "aktor_batterie_schwach" not in configs          # no battery on the actuator
    assert configs["aktor_erreichbar"]["device_class"] == "connectivity"
    state = sent[-1][1]["health"]
    assert state["level"] == "warnung" and state["ccu_duty_cycle"] == 12
    assert state["devices"]["bad"]["voltage"] == 2.2
    assert "Aktor: nicht erreichbar" in state["message"]
