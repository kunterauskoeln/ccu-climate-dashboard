"""Shared fakes for the CCU service tests (no network)."""
import pytest

from app.services import (
    absence,
    change_history,
    climate_schedule,
    profile_names,
    profile_sets,
    valve_history,
)
from app.services.ccu import profiles as _profiles

_profiles._WRITE_SETTLE_SECONDS = 0  # no real sleep in tests
_profiles._CONFIRM_POLL_SECONDS = 0
_profiles._CONFIRM_TIMEOUT_SECONDS = 0.05


@pytest.fixture(autouse=True)
def _data_files_in_tmp(tmp_path, monkeypatch):
    """Every test gets its own data directory. The modules default to the
    container path /app/app/data, which on a dev machine is a real directory
    on the current drive -- tests that didn't redirect a file (the profile-set
    backup, say) used to leave copies there."""
    monkeypatch.setattr(profile_sets, "_PATH", str(tmp_path / "profile_sets.json"))
    monkeypatch.setattr(profile_sets, "_BACKUP_PATH", str(tmp_path / "profile_sets.backup.json"))
    monkeypatch.setattr(profile_names, "_PATH", str(tmp_path / "profile_names.json"))
    monkeypatch.setattr(change_history, "_PATH", str(tmp_path / "change_history.json"))
    monkeypatch.setenv("VALVE_CHANNELS_FILE", str(tmp_path / "valve_channels.json"))
    monkeypatch.setattr(climate_schedule, "_PATH", str(tmp_path / "climate_schedule.json"))
    monkeypatch.setattr(absence, "_PATH", str(tmp_path / "absence.json"))
    monkeypatch.setattr(valve_history, "_PATH", str(tmp_path / "valve_history.json"))
    monkeypatch.setattr(valve_history, "_samples", None)


class FakeXmlRpc:
    def __init__(self, paramsets: dict | None = None):
        # keyed by (address, paramsetKey) -> dict
        self.paramsets = paramsets or {}
        self.get_calls: list[tuple[str, str]] = []
        self.set_calls: list[tuple[str, str, object]] = []
        self.put_calls: list[tuple[str, str, dict]] = []

    def get_paramset(self, address: str, key: str = "VALUES") -> dict:
        self.get_calls.append((address, key))
        return dict(self.paramsets.get((address, key), {}))

    def put_paramset(self, address: str, key: str, values: dict) -> None:
        self.put_calls.append((address, key, dict(values)))
        self.paramsets[(address, key)] = {**self.paramsets.get((address, key), {}), **values}

    def get_value(self, address: str, key: str) -> object:
        return self.paramsets.get((address, "VALUES"), {}).get(key)

    def set_value(self, address: str, key: str, value: object) -> None:
        self.set_calls.append((address, key, value))


class FakeJsonRpc:
    def __init__(self, devices=None, group_values=None, xmlrpc=None):
        self._devices = devices or []
        self._group_values = group_values or {}
        self._xmlrpc = xmlrpc  # optional: putParamset writes land here
        self.put_calls: list[tuple[str, str, list]] = []
        self.duty_cycle: int | None = None  # CCU radio load; None: not reported

    def call(self, method: str, params: dict | None = None, **_kwargs):
        if method == "Interface.listBidcosInterfaces":
            if self.duty_cycle is None:
                return []
            return [{"address": "RF", "dutyCycle": str(self.duty_cycle), "isDefault": True}]
        raise NotImplementedError(method)

    def list_devices(self):
        return list(self._devices)

    def get_paramset(self, interface: str, address: str, key: str) -> dict:
        return dict(self._group_values.get(address, {}))

    def put_paramset(self, address: str, paramset_key: str, typed_set: list,
                     *, interface: str = "HmIP-RF") -> None:
        self.put_calls.append((address, paramset_key, list(typed_set)))
        if self._xmlrpc is not None:
            store = self._xmlrpc.paramsets.setdefault((address, paramset_key), {})
            for item in typed_set:
                raw = item["value"]
                store[item["name"]] = int(raw) if item["type"] == "int" else float(raw)


@pytest.fixture
def fake_xmlrpc():
    return FakeXmlRpc()


@pytest.fixture
def fake_jsonrpc():
    return FakeJsonRpc()
