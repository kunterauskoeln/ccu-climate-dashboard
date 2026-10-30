from app.services.ccu import group_profiles as gp
from app.services.ccu import schedule
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


def test_describe():
    assert gp.describe(WORKDAY) == "00:00–08:00 17, 08:00–17:00 24.5, 17:00–24:00 17"
    assert gp.describe([]) == "(nicht programmiert)"
