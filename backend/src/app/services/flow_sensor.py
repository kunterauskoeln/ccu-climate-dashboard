"""Flow (Vorlauf) temperature from an MQTT topic.

A background MQTT client (paho, its own network thread, reconnects by itself)
keeps the last value and when it arrived. Configured in backend/.env:

    MQTT_HOST, MQTT_PORT (1883), MQTT_USERNAME, MQTT_PASSWORD, MQTT_FLOW_TOPIC

Without MQTT_HOST and MQTT_FLOW_TOPIC nothing is started and :func:`latest`
stays None. The password is only handed to the client, never logged.

Payloads accepted: a plain number ("18.4"), or JSON -- a number or an object
with one of the keys state / value / temperature / temp. If the object carries
its own measuring time (timestamp / time, ISO 8601), that time is used instead
of the arrival time: a retained message delivered on (re)connect must not look
fresh.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime

log = logging.getLogger(__name__)

_lock = threading.Lock()
_latest: Reading | None = None
_client = None
_status = "aus"  # "aus" | "verbinde" | "verbunden" | "Fehler: …"
# called (in paho's thread) after every successful (re)connect
_connect_hooks: list = []


@dataclass(frozen=True)
class Reading:
    value: float
    received_at: float  # epoch seconds


def configured() -> bool:
    return bool(os.getenv("MQTT_HOST") and os.getenv("MQTT_FLOW_TOPIC"))


def topic() -> str:
    return os.getenv("MQTT_FLOW_TOPIC", "")


def base_topic() -> str:
    """Topics the app publishes under (state, status)."""
    return os.getenv("MQTT_BASE_TOPIC", "ccu-dashboard").strip("/") or "ccu-dashboard"


def status_topic() -> str:
    return f"{base_topic()}/status"


def add_connect_hook(hook) -> None:
    if hook not in _connect_hooks:
        _connect_hooks.append(hook)


def publish(topic: str, payload: str, *, retain: bool = False) -> bool:
    """Send if connected (QoS 0). Returns False when not connected. A topic the
    broker's ACL does not allow is dropped by the broker without an error."""
    client = _client
    if client is None or _status != "verbunden":
        return False
    return client.publish(topic, payload, qos=0, retain=retain).rc == 0


def parse_payload(payload: bytes | str) -> float | None:
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict):
        for key in ("state", "value", "temperature", "temp"):
            if key in data:
                data = data[key]
                break
    if isinstance(data, bool):
        return None
    try:
        return float(data)
    except (TypeError, ValueError):
        return None


def payload_time(payload: bytes | str) -> float | None:
    """The sensor's own measuring time (epoch seconds), if the payload has one."""
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    for key in ("timestamp", "time"):
        raw = data.get(key)
        if isinstance(raw, str):
            try:
                stamp = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
            # without an offset: local time of the server (the sensor's zone)
            return stamp.timestamp()
    return None


def _measured_at(payload: bytes | str, now: float) -> float:
    """Sensor time if plausible (not ahead of us by more than 5 min), else now."""
    stamp = payload_time(payload)
    if stamp is None or stamp > now + 300:
        return now
    return min(stamp, now)


def record(value: float, at: float | None = None) -> None:
    global _latest
    with _lock:
        _latest = Reading(value, at if at is not None else time.time())


def latest() -> Reading | None:
    with _lock:
        return _latest


def status() -> str:
    return _status


def _on_connect(client, _userdata, _flags, reason_code, _properties=None) -> None:
    global _status
    if reason_code.is_failure:
        if "authori" in str(reason_code).lower() or "password" in str(reason_code).lower():
            _status = "Fehler: Anmeldung abgelehnt (MQTT_USERNAME/MQTT_PASSWORD prüfen)"
        else:
            _status = f"Fehler: {reason_code}"
        log.warning("MQTT connect refused: %s", reason_code)
        return
    _status = "verbunden"
    client.subscribe(topic())
    client.publish(status_topic(), "online", qos=1, retain=True)
    log.info("MQTT connected, subscribed to %s", topic())
    for hook in list(_connect_hooks):
        try:
            hook()
        except Exception:
            log.warning("MQTT connect hook failed", exc_info=True)


def _on_disconnect(_client, _userdata, _flags, reason_code, _properties=None) -> None:
    global _status
    if _status == "verbunden":
        log.warning("MQTT disconnected (%s), reconnecting", reason_code)
    if _status in ("verbunden", "verbinde"):
        _status = "verbinde"  # a refused login keeps its error text


def _on_message(_client, _userdata, message) -> None:
    value = parse_payload(message.payload)
    if value is None:
        log.warning("MQTT %s: payload is not a temperature: %r", message.topic, message.payload[:80])
        return
    record(value, _measured_at(message.payload, time.time()))


def start() -> None:
    """Connect in the background (once, on application startup)."""
    global _client, _status
    if _client is not None or not configured():
        return
    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ccu-dashboard")
    user = os.getenv("MQTT_USERNAME")
    if user:
        client.username_pw_set(user, os.getenv("MQTT_PASSWORD") or None)
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    # the broker announces "offline" itself if the app goes away unexpectedly
    client.will_set(status_topic(), "offline", qos=1, retain=True)
    client.reconnect_delay_set(min_delay=5, max_delay=120)
    _status = "verbinde"
    host, port = os.getenv("MQTT_HOST", ""), int(os.getenv("MQTT_PORT", "1883"))
    try:
        client.connect_async(host, port, keepalive=60)
        client.loop_start()
    except (OSError, ValueError) as exc:
        _status = f"Fehler: {exc}"
        log.warning("MQTT start failed for %s:%s", host, port, exc_info=True)
        return
    _client = client


def stop() -> None:
    global _client, _status
    if _client is not None:
        if _status == "verbunden":
            try:
                _client.publish(status_topic(), "offline", qos=1, retain=True).wait_for_publish(2)
            except (RuntimeError, ValueError):
                log.debug("MQTT offline status not sent", exc_info=True)
        _status = "aus"
        _client.disconnect()
        _client.loop_stop()
        _client = None
