import pytest

from app.services.ccu import group_profiles as gp
from app.services.ccu import schedule
from app.services.ccu.errors import CcuError
from app.services.ccu.schedule import Block

WORKDAY = [Block(0, 480, 17.0), Block(480, 1020, 24.5), Block(1020, 1440, 17.0)]
STALE = [Block(0, 480, 17.0), Block(480, 1020, 23.0), Block(1020, 1440, 17.0)]


def _master(day_blocks: dict[str, list[Block]], profile: int = 1) -> dict:
    master: dict = {}
    for day in schedule.DAYS:
        master.update(schedule.master_from_blocks(day_blocks.get(day, WORKDAY), profile, day))
    return master


def _as_strings(master: dict) -> dict:
    # JSON-RPC delivers every value as a string
    return {k: str(v) for k, v in master.items()}


def test_identical_profiles_have_no_diff():
    master = _master({})
    assert gp.diff_profiles(master, _as_strings(master)) == []


def test_stale_group_day_is_reported():
    device = _master({})
    group = _as_strings(_master({"FRIDAY": STALE}))
    diffs = gp.diff_profiles(device, group)
    assert [(d.profile, d.day) for d in diffs] == [(1, "FRIDAY")]
    assert gp.setpoint_at(diffs[0].device, 531) == 24.5
    assert gp.setpoint_at(diffs[0].group, 531) == 23.0


def test_profile_missing_in_group_counts_as_diff():
    diffs = gp.diff_profiles(_master({}), {})
    assert len(diffs) == 7 and all(d.group == [] for d in diffs)


class _FakeJsonRpc:
    def __init__(self, paramsets):
        self.paramsets = paramsets
        self.calls = []

    def get_paramset(self, interface, address, key):
        self.calls.append((interface, address, key))
        return self.paramsets.get(address, {})


def test_group_master_falls_back_to_device_root():
    group = _as_strings(_master({}))
    rpc = _FakeJsonRpc({"INT0000002:1": {"SOMETHING": "1"}, "INT0000002": group})
    address, master = gp.read_group_master(rpc, "INT0000002")
    assert address == "INT0000002" and master is group
    assert all(c[0] == "VirtualDevices" and c[2] == "MASTER" for c in rpc.calls)


def test_group_master_prefers_channel():
    group = _as_strings(_master({}))
    rpc = _FakeJsonRpc({"INT0000002:1": group})
    assert gp.read_group_master(rpc, "INT0000002") == ("INT0000002:1", group)
    assert len(rpc.calls) == 1


class _GroupRpc(_FakeJsonRpc):
    """putParamset lands in the stored MASTER (as strings, like the CCU),
    unless *stuck*; records every put."""

    def __init__(self, paramsets, stuck=False):
        super().__init__(paramsets)
        self.stuck = stuck
        self.puts = []

    def put_paramset(self, address, key, typed_set, *, interface="HmIP-RF"):
        self.puts.append((interface, address, key, typed_set))
        if not self.stuck:
            self.paramsets[address].update({s["name"]: s["value"] for s in typed_set})


def test_write_group_days_writes_and_confirms(monkeypatch):
    monkeypatch.setattr(gp.time, "sleep", lambda s: None)
    rpc = _GroupRpc({"INT0000002:1": _as_strings(_master({"FRIDAY": STALE}))})
    gp.write_group_days(rpc, "INT0000002:1", 1, {"FRIDAY": WORKDAY})

    assert len(rpc.puts) == 1
    interface, address, key, typed = rpc.puts[0]
    assert (interface, address, key) == ("VirtualDevices", "INT0000002:1", "MASTER")
    assert all(s["name"].startswith("P1_") and s["name"].endswith(
        tuple(f"FRIDAY_{i}" for i in range(1, 14))) for s in typed)
    group_now = schedule.blocks_from_master(rpc.paramsets["INT0000002:1"], 1, "FRIDAY")
    assert group_now == WORKDAY


def test_write_group_days_raises_when_group_does_not_take(monkeypatch):
    monkeypatch.setattr(gp.time, "sleep", lambda s: None)
    rpc = _GroupRpc({"INT0000002:1": _as_strings(_master({"FRIDAY": STALE}))}, stuck=True)
    with pytest.raises(CcuError):
        gp.write_group_days(rpc, "INT0000002:1", 1, {"FRIDAY": WORKDAY}, timeout=0)


def test_describe():
    assert gp.describe(WORKDAY) == "00:00–08:00 17, 08:00–17:00 24.5, 17:00–24:00 17"
    assert gp.describe([]) == "(nicht programmiert)"
