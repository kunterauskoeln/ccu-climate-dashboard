"""Tests for app.services.ccu.mapping – pure, built from the real inventory."""
import pytest

from app.services.ccu.errors import RoomNotFound
from app.services.ccu.mapping import (
    CachedDeviceMap,
    DeviceMap,
    load_valve_channels,
    map_from_devices,
)

# Example Device.listAllDetail shaped like a real CCU (made-up serials, channels omitted).
REAL_DEVICES = [
    {"address": "000AAAA0000002", "type": "HmIP-WTH-1", "interface": "HmIP-RF", "name": "Ankleide"},
    {"address": "INT0000006", "type": "HmIP-HEATING", "interface": "VirtualDevices", "name": "Ankleide INT0000006"},
    {"address": "000AAAA0000003", "type": "HmIP-WTH-1", "interface": "HmIP-RF", "name": "Arbeitszimmer"},
    {"address": "INT0000002", "type": "HmIP-HEATING", "interface": "VirtualDevices", "name": "Arbeitszimmer INT0000002"},
    {"address": "000AAAA0000004", "type": "HmIP-WTH-1", "interface": "HmIP-RF", "name": "Bad"},
    {"address": "INT0000004", "type": "HmIP-HEATING", "interface": "VirtualDevices", "name": "Bad INT0000004"},
    {"address": "000AAAA0000005", "type": "HmIP-WTH-1", "interface": "HmIP-RF", "name": "Flur"},
    {"address": "INT0000007", "type": "HmIP-HEATING", "interface": "VirtualDevices", "name": "Flur INT0000007"},
    {"address": "BidCoS-RF", "type": "HM-RCV-50", "interface": "BidCos-RF", "name": "HM-RCV-50 BidCoS-RF"},
    {"address": "000CCCC0000001", "type": "HmIP-CCU3", "interface": "HmIP-RF", "name": "HmIP-CCU3 000CCCC0000001"},
    {"address": "000BBBB0000001", "type": "HmIP-FALMOT-C12", "interface": "HmIP-RF", "name": "HmIP-FALMOT-C12 000BBBB0000001"},
    {"address": "HmIP-RCV-1", "type": "HmIP-RCV-50", "interface": "HmIP-RF", "name": "HmIP-RCV-50 HmIP-RCV-1"},
    {"address": "000AAAA0000006", "type": "HmIP-WTH-1", "interface": "HmIP-RF", "name": "Schlafzimmer"},
    {"address": "INT0000001", "type": "HmIP-HEATING", "interface": "VirtualDevices", "name": "Schlafzimmer INT0000001"},
    {"address": "000AAAA0000007", "type": "HmIP-WTH-1", "interface": "HmIP-RF", "name": "WC"},
    {"address": "INT0000005", "type": "HmIP-HEATING", "interface": "VirtualDevices", "name": "WC INT0000005"},
    {"address": "000AAAA0000001", "type": "HmIP-WTH-1", "interface": "HmIP-RF", "name": "Wohnzimmer"},
    {"address": "INT0000003", "type": "HmIP-HEATING", "interface": "VirtualDevices", "name": "Wohnzimmer INT0000003"},
]


@pytest.fixture
def device_map() -> DeviceMap:
    return map_from_devices(REAL_DEVICES)


def test_all_seven_rooms_are_found(device_map):
    assert device_map.room_names == [
        "Ankleide", "Arbeitszimmer", "Bad", "Flur", "Schlafzimmer", "WC", "Wohnzimmer",
    ]


def test_room_resolves_to_channels(device_map):
    wz = device_map.room("Wohnzimmer")
    assert wz.wth_address == "000AAAA0000001"
    assert wz.thermostat_channel == "000AAAA0000001:1"
    assert wz.maintenance_channel == "000AAAA0000001:0"
    assert wz.group_address == "INT0000003"
    assert wz.group_channel == "INT0000003:1"


def test_actuator_is_the_falmot(device_map):
    assert device_map.actuator_address == "000BBBB0000001"
    assert device_map.actuator_channel == "000BBBB0000001:0"


def test_ccu_and_receivers_are_ignored(device_map):
    addresses = {r.wth_address for r in device_map.rooms.values()}
    assert "000CCCC0000001" not in addresses  # HmIP-CCU3
    assert "BidCoS-RF" not in addresses
    assert "HmIP-RCV-1" not in addresses


def test_unknown_room_raises(device_map):
    with pytest.raises(RoomNotFound):
        device_map.room("Küche")


def test_group_optional_when_missing():
    devices = [{"address": "ABC", "type": "HmIP-WTH-1", "interface": "HmIP-RF", "name": "Keller"}]
    dm = map_from_devices(devices)
    room = dm.room("Keller")
    assert room.group_address is None
    assert room.group_channel is None
    assert dm.actuator_address is None


def test_cached_map_refreshes_after_ttl():
    calls = []

    class FakeRpc:
        def list_devices(self):
            calls.append(1)
            return REAL_DEVICES

    clock = [1000.0]
    cached = CachedDeviceMap(FakeRpc(), ttl=300.0)

    import app.services.ccu.mapping as mapping_mod
    original = mapping_mod.time.monotonic
    mapping_mod.time.monotonic = lambda: clock[0]
    try:
        cached.get()
        cached.get()
        assert len(calls) == 1          # served from cache
        clock[0] += 301
        cached.get()
        assert len(calls) == 2          # TTL expired -> refetched
        cached.invalidate()
        cached.get()
        assert len(calls) == 3
    finally:
        mapping_mod.time.monotonic = original


def test_valve_channels_are_resolved_to_actuator_addresses():
    dm = map_from_devices(REAL_DEVICES, {"Wohnzimmer": [2, 3, 4], "Flur": [9]})
    assert dm.rooms["Wohnzimmer"].valve_channels == (
        "000BBBB0000001:2", "000BBBB0000001:3", "000BBBB0000001:4")
    assert dm.rooms["Flur"].valve_channels == ("000BBBB0000001:9",)
    assert dm.rooms["Bad"].valve_channels == ()  # not in the map


def test_load_valve_channels_reads_the_shipped_file():
    channels = load_valve_channels()
    assert channels == {"Wohnzimmer": [1, 2], "Schlafzimmer": [3], "Bad": [4]}


def test_load_valve_channels_tolerates_missing_and_broken_files(tmp_path):
    assert load_valve_channels(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2")
    assert load_valve_channels(bad) == {}
