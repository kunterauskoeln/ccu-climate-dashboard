"""Publish the app's state to Home Assistant via MQTT discovery.

Uses the MQTT connection of :mod:`flow_sensor`. After every dew point round
(:mod:`dew_point`, once a minute) the whole state goes as one retained JSON
document to ``<base>/state`` (default ``ccu-dashboard/state``); the entities
read their value from it with a template. The discovery configs go retained to
``<prefix>/<component>/ccu_dashboard/<object>/config`` (prefix default
``homeassistant``) -- after each (re)connect and whenever the set of rooms
changes. Availability is ``<base>/status`` (online, offline via last will).

The broker must allow the app's user to write ``<base>/#`` and
``<prefix>/+/ccu_dashboard/#``; without that the broker drops the messages
silently and Home Assistant simply sees nothing.

Off with ``HA_DISCOVERY=0``.
"""
from __future__ import annotations

import json
import logging
import os
import re

from . import flow_sensor
from .device_health import Snapshot as HealthSnapshot
from .dew_point import Snapshot

log = logging.getLogger(__name__)

NODE_ID = "ccu_dashboard"
LEVELS = ["aus", "ok", "unbekannt", "knapp", "gefahr"]
ROOM_STATUSES = [*LEVELS, "ventil_zu"]

_announced: frozenset | None = None   # what was announced since the last connect


def enabled() -> bool:
    return flow_sensor.configured() and os.getenv("HA_DISCOVERY", "1") != "0"


def prefix() -> str:
    return os.getenv("HA_DISCOVERY_PREFIX", "homeassistant").strip("/") or "homeassistant"


def state_topic() -> str:
    return f"{flow_sensor.base_topic()}/state"


def slug(name: str) -> str:
    """"Wohnzimmer" -> "wohnzimmer", "Kinderzimmer Süd" -> "kinderzimmer_sued"."""
    text = name.lower()
    for umlaut, plain in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(umlaut, plain)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "raum"


def _health_payload(health: HealthSnapshot | None) -> dict | None:
    if health is None:
        return None
    return {
        "level": health.level,
        "message": health.message,
        "ccu_duty_cycle": health.ccu_duty_cycle,
        "devices": {
            slug(d.name): {
                "reachable": d.reachable,
                "low_battery": d.low_battery,
                "voltage": d.voltage,
                "rssi": d.rssi,
            }
            for d in health.devices
        },
    }


def _absence_payload() -> dict:
    from . import absence

    current = absence.state()
    running = current.phase in ("aktiv", "rueckkehr")
    return {"phase": current.phase, "active": running,
            "end": current.end if running else None, "profile": current.profile_name}


def state_payload(snap: Snapshot, health: HealthSnapshot | None = None) -> dict:
    return {
        "absence": _absence_payload(),
        "health": _health_payload(health),
        "level": snap.level,
        "message": snap.message,
        "cooling": snap.cooling,
        "flow": snap.flow.effective,
        "flow_sensor": snap.flow.value,
        "flow_source": snap.flow.source,
        "rooms": {
            slug(r.room): {
                "dew_point": r.dew_point,
                "margin": r.margin,
                "status": r.status,
                "valve": round(r.valve * 100) if r.valve is not None else None,
                "temperature": r.temperature,
                "humidity": r.humidity,
            }
            for r in snap.rooms
        },
    }


def _device() -> dict:
    return {
        "identifiers": [NODE_ID],
        "name": "CCU Dashboard",
        "manufacturer": "CCU Dashboard",
        "model": "Fußbodenheizung/-kühlung (HomematicIP)",
    }


def _entity(object_id: str, name: str, template: str, **extra) -> dict:
    return {
        "name": name,
        "unique_id": f"{NODE_ID}_{object_id}",
        "state_topic": state_topic(),
        "value_template": template,
        "availability_topic": flow_sensor.status_topic(),
        "device": _device(),
        **extra,
    }


def discovery(snap: Snapshot, health: HealthSnapshot | None = None) -> dict[str, dict]:
    """Discovery topic -> config for every entity."""
    base = prefix()
    out: dict[str, dict] = {}

    def add(component: str, object_id: str, config: dict) -> None:
        out[f"{base}/{component}/{NODE_ID}/{object_id}/config"] = config

    add("sensor", "taupunkt_lage", _entity(
        "taupunkt_lage", "Taupunkt-Lage", "{{ value_json.level }}",
        device_class="enum", options=LEVELS, icon="mdi:water-thermometer-outline"))
    add("sensor", "taupunkt_meldung", _entity(
        "taupunkt_meldung", "Taupunkt-Meldung", "{{ value_json.message }}",
        icon="mdi:message-alert-outline"))
    add("binary_sensor", "kondensgefahr", _entity(
        "kondensgefahr", "Kondensgefahr",
        "{{ 'ON' if value_json.level == 'gefahr' else 'OFF' }}", device_class="moisture"))
    add("binary_sensor", "taupunkt_warnung", _entity(
        "taupunkt_warnung", "Taupunkt-Warnung",
        "{{ 'ON' if value_json.level in ['knapp', 'gefahr'] else 'OFF' }}", device_class="problem"))
    add("binary_sensor", "kuehlbetrieb", _entity(
        "kuehlbetrieb", "Kühlbetrieb", "{{ 'ON' if value_json.cooling else 'OFF' }}",
        icon="mdi:snowflake"))
    temperature = {"unit_of_measurement": "°C", "device_class": "temperature",
                   "state_class": "measurement"}
    add("sensor", "vorlauf", _entity(
        "vorlauf", "Vorlauf (Vergleichswert)", "{{ value_json.flow }}", **temperature))
    add("sensor", "vorlauf_sensor", _entity(
        "vorlauf_sensor", "Vorlauf (Sensor)", "{{ value_json.flow_sensor }}", **temperature))

    add("binary_sensor", "abwesenheit", _entity(
        "abwesenheit", "Abwesenheit", "{{ 'ON' if value_json.absence.active else 'OFF' }}",
        icon="mdi:bag-suitcase-outline"))
    add("sensor", "abwesenheit_ende", _entity(
        "abwesenheit_ende", "Abwesenheit bis", "{{ value_json.absence.end }}",
        device_class="timestamp", icon="mdi:calendar-end"))
    add("binary_sensor", "geraete_problem", _entity(
        "geraete_problem", "Geräteproblem",
        "{{ 'ON' if value_json.health and value_json.health.level == 'warnung' else 'OFF' }}",
        device_class="problem"))
    add("sensor", "geraete_meldung", _entity(
        "geraete_meldung", "Geräte-Meldung",
        "{{ value_json.health.message if value_json.health else None }}",
        icon="mdi:message-alert-outline"))
    add("sensor", "ccu_funkauslastung", _entity(
        "ccu_funkauslastung", "CCU-Funkauslastung",
        "{{ value_json.health.ccu_duty_cycle if value_json.health else None }}",
        unit_of_measurement="%", state_class="measurement", icon="mdi:radio-tower"))
    for device in (health.devices if health else []):
        key = slug(device.name)
        path = f"value_json.health.devices.{key}"
        add("binary_sensor", f"{key}_erreichbar", _entity(
            f"{key}_erreichbar", f"{device.name} erreichbar",
            f"{{{{ 'ON' if {path}.reachable else 'OFF' }}}}", device_class="connectivity"))
        if device.low_battery is not None:
            add("binary_sensor", f"{key}_batterie_schwach", _entity(
                f"{key}_batterie_schwach", f"{device.name} Batterie schwach",
                f"{{{{ 'ON' if {path}.low_battery else 'OFF' }}}}", device_class="battery"))
            add("sensor", f"{key}_batteriespannung", _entity(
                f"{key}_batteriespannung", f"{device.name} Batteriespannung",
                f"{{{{ {path}.voltage }}}}", unit_of_measurement="V",
                device_class="voltage", state_class="measurement"))

    for room in snap.rooms:
        key = slug(room.room)
        path = f"value_json.rooms.{key}"
        add("sensor", f"{key}_taupunkt", _entity(
            f"{key}_taupunkt", f"{room.room} Taupunkt", f"{{{{ {path}.dew_point }}}}", **temperature))
        add("sensor", f"{key}_abstand", _entity(
            f"{key}_abstand", f"{room.room} Abstand zum Vorlauf", f"{{{{ {path}.margin }}}}",
            unit_of_measurement="K", state_class="measurement", icon="mdi:thermometer-minus"))
        add("sensor", f"{key}_bewertung", _entity(
            f"{key}_bewertung", f"{room.room} Taupunkt-Bewertung", f"{{{{ {path}.status }}}}",
            device_class="enum", options=ROOM_STATUSES, icon="mdi:water-alert-outline"))
        add("sensor", f"{key}_ventil", _entity(
            f"{key}_ventil", f"{room.room} Ventil", f"{{{{ {path}.valve }}}}",
            unit_of_measurement="%", state_class="measurement", icon="mdi:valve"))
    return out


def _mark_reconnected() -> None:
    global _announced
    _announced = None


flow_sensor.add_connect_hook(_mark_reconnected)


def publish(snap: Snapshot, health: HealthSnapshot | None = None) -> None:
    """Announce (when needed) and send the current state."""
    global _announced
    if not enabled():
        return
    # what the discovery depends on: rooms, and the devices (with/without battery)
    shape = frozenset(
        [("room", r.room) for r in snap.rooms]
        + [("device", d.name, d.low_battery is not None) for d in (health.devices if health else [])]
    )
    if _announced != shape:
        sent = all(flow_sensor.publish(topic, json.dumps(config, ensure_ascii=False), retain=True)
                   for topic, config in discovery(snap, health).items())
        if not sent:
            return  # not connected: try again after the next round
        _announced = shape
        log.info("Home Assistant discovery sent for %d rooms", len(snap.rooms))
    flow_sensor.publish(state_topic(), json.dumps(state_payload(snap, health), ensure_ascii=False),
                        retain=True)
