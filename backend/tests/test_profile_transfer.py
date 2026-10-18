"""app.services.profile_transfer - background, paced profile-set apply."""
import pytest
from conftest import FakeJsonRpc, FakeXmlRpc

from app.services import climate_profiles, profile_sets, profile_transfer
from app.services.ccu.errors import CcuError
from app.services.ccu.mapping import DeviceMap, RoomDevices

WZ = RoomDevices(room="Wohnzimmer", wth_address="WTH_WZ", group_address=None)
AZ = RoomDevices(room="Arbeitszimmer", wth_address="WTH_AZ", group_address=None)
DEVICE_MAP = DeviceMap(rooms={"Wohnzimmer": WZ, "Arbeitszimmer": AZ}, actuator_address="FAL1")


def _p1_monday() -> dict:
    ends = [360, 540, 1020, 1320, 1440] + [1440] * 8
    temps = [17.0, 21.0, 17.0, 21.0, 17.0] + [17.0] * 8
    out = {}
    for i in range(1, 14):
        out[f"P1_ENDTIME_MONDAY_{i}"] = ends[i - 1]
        out[f"P1_TEMPERATURE_MONDAY_{i}"] = temps[i - 1]
    return out


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(profile_sets, "_PATH", str(tmp_path / "profile_sets.json"))
    monkeypatch.setattr(profile_transfer, "_PACE_SECONDS", 0)
    monkeypatch.setattr(profile_transfer, "_state", profile_transfer.TransferState())
    monkeypatch.setattr(profile_transfer, "_thread", None)
    monkeypatch.setattr(profile_transfer, "_reusable_clients", None)
    profile_transfer._cancel.clear()
    yield
    profile_transfer.cancel()


@pytest.fixture
def xmlrpc():
    return FakeXmlRpc({
        ("WTH_WZ:1", "VALUES"): {"ACTIVE_PROFILE": 1},
        ("WTH_WZ:1", "MASTER"): _p1_monday(),
        ("WTH_AZ:1", "VALUES"): {"ACTIVE_PROFILE": 1},
        ("WTH_AZ:1", "MASTER"): {},
    })


@pytest.fixture
def jsonrpc(xmlrpc):
    return FakeJsonRpc(xmlrpc=xmlrpc)


@pytest.fixture
def clients(xmlrpc, jsonrpc, monkeypatch):
    monkeypatch.setattr(profile_transfer, "_make_clients", lambda: (xmlrpc, jsonrpc))
    return xmlrpc, jsonrpc


def _seed_and_diverge_cooling(xmlrpc, *, temps_evening=23.0):
    """Seed both modes from the device, then change cooling P1 monday."""
    climate_profiles.seed_room_if_empty(xmlrpc, "Wohnzimmer", "WTH_WZ")
    cool = profile_sets.get_mode("Wohnzimmer", True)
    cool[1]["monday"][3]["setpoint"] = temps_evening
    profile_sets.put_mode("Wohnzimmer", True, cool)


# --- status -------------------------------------------------------------
def test_status_starts_idle():
    st = profile_transfer.status()
    assert st.running is False and st.total == 0 and st.written == []


# --- plan -------------------------------------------------------------
def test_plan_only_covers_active_profile_and_changed_days(xmlrpc):
    _seed_and_diverge_cooling(xmlrpc)
    plan, deferred = profile_transfer._build_plan(
        xmlrpc, DEVICE_MAP, cooling=True, max_days=8
    )
    assert deferred == []
    assert [(p.room, p.profile, p.day) for p in plan] == [("Wohnzimmer", 1, "MONDAY")]


def test_plan_skips_when_active_profile_has_no_divergence(xmlrpc):
    climate_profiles.seed_room_if_empty(xmlrpc, "Wohnzimmer", "WTH_WZ")  # identical
    plan, deferred = profile_transfer._build_plan(
        xmlrpc, DEVICE_MAP, cooling=True, max_days=8
    )
    assert plan == [] and deferred == []


def test_plan_ignores_inactive_profile_divergence(xmlrpc):
    climate_profiles.seed_room_if_empty(xmlrpc, "Wohnzimmer", "WTH_WZ")
    cool = profile_sets.get_mode("Wohnzimmer", True)
    cool[2] = {"monday": [{"start": "00:00", "end": "24:00", "setpoint": 9.9}]}
    profile_sets.put_mode("Wohnzimmer", True, cool)  # P2 diverges, but active is P1
    plan, _ = profile_transfer._build_plan(xmlrpc, DEVICE_MAP, cooling=True, max_days=8)
    assert plan == []


def test_plan_defers_days_over_the_budget(xmlrpc):
    climate_profiles.seed_room_if_empty(xmlrpc, "Wohnzimmer", "WTH_WZ")
    cool = profile_sets.get_mode("Wohnzimmer", True)
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        cool[1][day] = [{"start": "00:00", "end": "24:00", "setpoint": 19.5}]
    profile_sets.put_mode("Wohnzimmer", True, cool)
    plan, deferred = profile_transfer._build_plan(
        xmlrpc, DEVICE_MAP, cooling=True, max_days=2
    )
    assert len(plan) == 2
    assert len(deferred) == 3


# --- run ------------------------------------------------------------
def test_start_applies_the_plan_and_reports_progress(clients, xmlrpc):
    _seed_and_diverge_cooling(xmlrpc, temps_evening=23.0)

    profile_transfer.start(DEVICE_MAP, cooling=True)
    profile_transfer.join(timeout=3)

    st = profile_transfer.status()
    assert st.running is False
    assert st.mode == "cooling"
    assert st.total == 1 and st.done == 1
    assert st.written == ["Wohnzimmer P1 Montag"]
    assert st.errors == []
    # device MASTER now carries the stored cooling value (evening 21.0 -> 23.0)
    assert xmlrpc.paramsets[("WTH_WZ:1", "MASTER")]["P1_TEMPERATURE_MONDAY_4"] == 23.0


def test_start_with_nothing_to_do_finishes_clean(clients, xmlrpc):
    climate_profiles.seed_room_if_empty(xmlrpc, "Wohnzimmer", "WTH_WZ")
    profile_transfer.start(DEVICE_MAP, cooling=True)
    profile_transfer.join(timeout=3)
    st = profile_transfer.status()
    assert st.running is False and st.total == 0 and st.written == []


def test_start_twice_cancels_the_first_run(clients, xmlrpc, monkeypatch):
    _seed_and_diverge_cooling(xmlrpc)
    profile_transfer.start(DEVICE_MAP, cooling=True)
    profile_transfer.start(DEVICE_MAP, cooling=False)  # must not raise / deadlock
    profile_transfer.join(timeout=3)
    assert profile_transfer.status().running is False


class _FailingJsonRpc(FakeJsonRpc):
    def put_paramset(self, *args, **kwargs):
        raise CcuError("boom")


def test_run_stops_after_consecutive_errors_and_defers_the_rest(clients, xmlrpc, monkeypatch):
    climate_profiles.seed_room_if_empty(xmlrpc, "Wohnzimmer", "WTH_WZ")
    cool = profile_sets.get_mode("Wohnzimmer", True)
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        cool[1][day] = [{"start": "00:00", "end": "24:00", "setpoint": 19.5}]
    profile_sets.put_mode("Wohnzimmer", True, cool)

    monkeypatch.setattr(profile_transfer, "_make_clients",
                        lambda: (xmlrpc, _FailingJsonRpc()))

    profile_transfer.start(DEVICE_MAP, cooling=True)
    profile_transfer.join(timeout=3)

    st = profile_transfer.status()
    assert st.total == 5
    assert st.done == profile_transfer._MAX_CONSECUTIVE_ERRORS  # gave up early
    assert st.written == []
    assert len(st.deferred) == 5 - profile_transfer._MAX_CONSECUTIVE_ERRORS
    assert "stopped after" in st.errors[-1]


# --- session hygiene ---------------------------------------------------
def test_clients_are_built_once_and_reused(monkeypatch):
    from app import deps

    calls = {"xml": 0, "json": 0}
    fake_x, fake_j = FakeXmlRpc(), FakeJsonRpc()

    def fake_new_xmlrpc():
        calls["xml"] += 1
        return fake_x

    def fake_new_jsonrpc():
        calls["json"] += 1
        return fake_j

    monkeypatch.setattr(deps, "new_xmlrpc", fake_new_xmlrpc)
    monkeypatch.setattr(deps, "new_jsonrpc", fake_new_jsonrpc)

    first = profile_transfer._clients()
    second = profile_transfer._clients()
    assert first == second == (fake_x, fake_j)
    assert calls == {"xml": 1, "json": 1}  # not re-created (and re-logged-in) each time


def test_close_logs_out_and_drops_the_cached_clients(monkeypatch):
    fake_j = FakeJsonRpc()
    logged_out = []
    fake_j.logout = lambda: logged_out.append(True)
    monkeypatch.setattr(profile_transfer, "_reusable_clients", (FakeXmlRpc(), fake_j))

    profile_transfer.close()

    assert logged_out == [True]
    assert profile_transfer._reusable_clients is None


def test_close_with_nothing_cached_does_nothing():
    profile_transfer.close()  # must not raise
