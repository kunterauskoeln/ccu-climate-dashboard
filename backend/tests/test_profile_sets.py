"""app.services.profile_sets - per-room heating/cooling profile persistence."""
import json
import os

import pytest

from app.services import profile_sets

DAYS_A = {
    "monday": [{"start": "00:00", "end": "24:00", "setpoint": 17.0}],
    "tuesday": [],
}
DAYS_B = {
    "monday": [
        {"start": "00:00", "end": "06:00", "setpoint": 18.0},
        {"start": "06:00", "end": "24:00", "setpoint": 22.0},
    ],
}


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "profile_sets.json"
    monkeypatch.setattr(profile_sets, "_PATH", str(path))
    monkeypatch.setattr(profile_sets, "_BACKUP_PATH", str(tmp_path / "profile_sets.backup.json"))
    return path


def test_load_missing_file_is_empty(store):
    assert profile_sets.load() == {}
    assert profile_sets.is_empty() is True


def test_load_survives_path_being_a_directory(tmp_path, monkeypatch):
    # Docker creates a single-file bind mount as a directory when the host path
    # is missing -- load() must degrade to "no data", not raise IsADirectoryError
    as_dir = tmp_path / "profile_sets.json"
    as_dir.mkdir()
    monkeypatch.setattr(profile_sets, "_PATH", str(as_dir))
    assert profile_sets.load() == {}
    assert profile_sets.is_empty() is True


def test_mode_key():
    assert profile_sets.mode_key(False) == "heating"
    assert profile_sets.mode_key(True) == "cooling"


def test_put_and_get_profile_roundtrip(store):
    profile_sets.put_profile("Bad", False, 1, DAYS_A)
    assert profile_sets.get_profile("Bad", False, 1) == DAYS_A
    assert profile_sets.get_profile("Bad", True, 1) is None
    assert profile_sets.is_empty() is False
    assert profile_sets.has_mode("Bad", False) is True
    assert profile_sets.has_mode("Bad", True) is False


def test_modes_are_independent(store):
    profile_sets.put_profile("Bad", False, 1, DAYS_A)
    profile_sets.put_profile("Bad", True, 1, DAYS_B)
    assert profile_sets.get_profile("Bad", False, 1) == DAYS_A
    assert profile_sets.get_profile("Bad", True, 1) == DAYS_B


def test_put_mode_replaces_whole_set(store):
    profile_sets.put_profile("Bad", False, 5, DAYS_A)
    profile_sets.put_mode("Bad", False, {1: DAYS_B, 2: DAYS_A})
    got = profile_sets.get_mode("Bad", False)
    assert set(got) == {1, 2}  # int keys, old P5 gone
    assert got[1] == DAYS_B


def test_on_disk_shape(store):
    profile_sets.put_profile("Wohnzimmer", True, 3, DAYS_A)
    raw = json.loads(store.read_text(encoding="utf-8"))
    assert raw == {"Wohnzimmer": {"cooling": {"3": DAYS_A}}}


# --- rolling backup ---------------------------------------------------
def test_first_write_ever_creates_no_backup(store):
    profile_sets.put_profile("Bad", False, 1, DAYS_A)
    assert not os.path.exists(profile_sets._BACKUP_PATH)


def test_second_write_backs_up_the_previous_content(store):
    profile_sets.put_profile("Bad", False, 1, DAYS_A)
    profile_sets.put_profile("Bad", False, 1, DAYS_B)  # overwrites P1

    backed_up = json.loads(open(profile_sets._BACKUP_PATH, encoding="utf-8").read())
    assert backed_up == {"Bad": {"heating": {"1": DAYS_A}}}  # state before the 2nd write
    # the live file already has the new value
    assert profile_sets.get_profile("Bad", False, 1) == DAYS_B


def test_backup_survives_even_when_write_touches_different_room(store):
    profile_sets.put_profile("Bad", False, 1, DAYS_A)
    profile_sets.put_profile("Wohnzimmer", True, 2, DAYS_B)
    backed_up = json.loads(open(profile_sets._BACKUP_PATH, encoding="utf-8").read())
    assert backed_up == {"Bad": {"heating": {"1": DAYS_A}}}


# --- active profile per mode --------------------------------------------
def test_active_profile_missing_is_none(store):
    assert profile_sets.get_active_profile("Bad", False) is None


def test_active_profile_roundtrip_and_mode_independence(store):
    profile_sets.put_active_profile("Bad", False, 3)
    profile_sets.put_active_profile("Bad", True, 1)
    assert profile_sets.get_active_profile("Bad", False) == 3
    assert profile_sets.get_active_profile("Bad", True) == 1


def test_active_profile_overwrite(store):
    profile_sets.put_active_profile("Bad", False, 3)
    profile_sets.put_active_profile("Bad", False, 5)
    assert profile_sets.get_active_profile("Bad", False) == 5


def test_active_profile_lives_alongside_schedules_on_disk(store):
    profile_sets.put_profile("Bad", False, 1, DAYS_A)
    profile_sets.put_active_profile("Bad", False, 3)
    raw = json.loads(store.read_text(encoding="utf-8"))
    assert raw == {"Bad": {"heating": {"1": DAYS_A}, "active_profile": {"heating": 3}}}
