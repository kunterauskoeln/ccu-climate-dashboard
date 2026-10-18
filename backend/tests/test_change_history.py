"""app.services.change_history -- recording, targets for an undo, clearing."""
import pytest

from app.services import change_history


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(change_history, "_PATH", str(tmp_path / "change_history.json"))


def _day(temp):
    return {"monday": [{"start": "00:00", "end": "24:00", "setpoint": temp}]}


def test_entries_are_kept_oldest_first_with_their_before_state():
    change_history.record_profile("Bad", False, 1, _day(17.0), "erste")
    change_history.record_name(2, "Urlaub", "zweite")
    got = change_history.entries()
    assert [e["summary"] for e in got] == ["erste", "zweite"]
    assert got[0]["mode"] == "heating" and got[0]["before"] == _day(17.0)
    assert got[1]["kind"] == "name" and got[1]["before"] == "Urlaub"


def test_missing_or_broken_file_means_no_history(tmp_path, monkeypatch):
    assert change_history.entries() == []
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    monkeypatch.setattr(change_history, "_PATH", str(broken))
    assert change_history.entries() == []


def test_the_oldest_undone_entry_decides_what_a_profile_goes_back_to():
    change_history.record_profile("Bad", False, 1, _day(17.0), "a")
    change_history.record_profile("Bad", False, 1, _day(19.0), "b")
    change_history.record_profile("Flur", False, 3, _day(16.0), "c")
    change_history.record_name(2, None, "d")
    change_history.record_name(2, "Urlaub", "e")
    first = change_history.entries()[0]["id"]

    undone = change_history.entries_from(first)
    assert change_history.profile_targets(undone) == {
        ("Bad", "heating", 1): _day(17.0),     # state before "a", not before "b"
        ("Flur", "heating", 3): _day(16.0),
    }
    assert change_history.name_targets(undone) == {2: None}  # P2 had no name before "d"


def test_entries_from_an_unknown_id_is_empty():
    change_history.record_name(1, "Standard", "x")
    assert change_history.entries_from("nope") == []


def test_mode_switch_clear_drops_profiles_but_keeps_names():
    change_history.record_profile("Bad", True, 1, _day(26.0), "kuehlen")
    change_history.record_name(1, "Standard", "name")
    change_history.clear_profile_entries()
    assert [e["kind"] for e in change_history.entries()] == ["name"]


def test_only_the_newest_entries_are_kept(monkeypatch):
    monkeypatch.setattr(change_history, "MAX_ENTRIES", 3)
    for n in range(5):
        change_history.record_name(1, str(n), f"#{n}")
    assert [e["summary"] for e in change_history.entries()] == ["#2", "#3", "#4"]


def test_remove_ids_removes_exactly_those():
    for n in range(3):
        change_history.record_name(1, str(n), f"#{n}")
    ids = [e["id"] for e in change_history.entries()]
    change_history.remove_ids({ids[0], ids[2]})
    assert [e["summary"] for e in change_history.entries()] == ["#1"]
