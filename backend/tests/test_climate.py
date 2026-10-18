"""app.services.ccu.climate – heating/cooling switch."""
import pytest
from conftest import FakeXmlRpc

from app.services.ccu import climate
from app.services.ccu.errors import CcuError

climate._POLL_SECONDS = 0
climate._CONFIRM_TIMEOUT = 0.05

CH = "FALMOT1:0"


class _LiveXmlRpc(FakeXmlRpc):
    """set_value updates the VALUES store; put_paramset does too."""

    def set_value(self, address, key, value):
        self.set_calls.append((address, key, value))
        self.paramsets.setdefault((address, "VALUES"), {})[key] = value

    def put_paramset(self, address, key, values):
        self.put_calls.append((address, key, dict(values)))
        self.paramsets.setdefault((address, key), {}).update(values)


class _StuckXmlRpc(FakeXmlRpc):
    """writes are silently dropped."""

    def set_value(self, address, key, value):
        self.set_calls.append((address, key, value))

    def put_paramset(self, address, key, values):
        self.put_calls.append((address, key, dict(values)))


def test_get_cooling_reads_enum():
    assert climate.get_cooling(FakeXmlRpc({(CH, "VALUES"): {"HEATING_COOLING": 1}}), CH) is True
    assert climate.get_cooling(FakeXmlRpc({(CH, "VALUES"): {"HEATING_COOLING": 0}}), CH) is False


def test_get_cooling_no_actuator():
    assert climate.get_cooling(FakeXmlRpc(), None) is False


def test_set_cooling_noop_when_already_there():
    x = _LiveXmlRpc({(CH, "VALUES"): {"HEATING_COOLING": 1}})
    assert climate.set_cooling(x, CH, True) is True
    assert x.set_calls == [] and x.put_calls == []


def test_set_cooling_writes_both_ways_and_confirms():
    x = _LiveXmlRpc({(CH, "VALUES"): {"HEATING_COOLING": 0}})
    assert climate.set_cooling(x, CH, True) is True
    assert (CH, "HEATING_COOLING", 1) in x.set_calls
    assert (CH, "VALUES", {"HEATING_COOLING": 1}) in x.put_calls


def test_set_cooling_raises_when_nothing_takes():
    x = _StuckXmlRpc({(CH, "VALUES"): {"HEATING_COOLING": 0}})
    with pytest.raises(CcuError):
        climate.set_cooling(x, CH, True)
