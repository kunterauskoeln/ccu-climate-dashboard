"""app.services.auto_backup - nightly backup in export format."""
import json
import os
from datetime import datetime

from app.services import auto_backup as ab
from app.services import climate_schedule, profile_names

BERLIN = climate_schedule.tz()


def at(d, h=0, mi=0):
    return datetime(2026, 10, d, h, mi, tzinfo=BERLIN)


def test_nothing_before_the_hour_then_once_per_day():
    assert ab.tick(at(2, 2, 59)) is None
    assert ab.tick(at(2, 3, 0)) == "ccu-auto-2026-10-02.json"
    assert ab.tick(at(2, 3, 5)) is None          # already there
    assert ab.tick(at(2, 23, 0)) is None
    assert [f.name for f in ab.list_files()] == ["ccu-auto-2026-10-02.json"]


def test_a_night_with_the_server_off_is_caught_up_later_that_day():
    assert ab.tick(at(5, 14, 30)) == "ccu-auto-2026-10-05.json"


def test_the_file_is_a_complete_export():
    profile_names.set_name(1, "Standard")
    ab.tick(at(2, 4))
    with open(os.path.join(ab.backup_dir(), "ccu-auto-2026-10-02.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["format"] == "ccu-dashboard-export" and doc["profile_names"] == {"1": "Standard"}
    assert "climate_schedule" in doc


def test_only_the_newest_are_kept(monkeypatch):
    monkeypatch.setenv("AUTO_BACKUP_KEEP", "3")
    for day in range(1, 7):
        ab.tick(at(day, 3))
    names = sorted(f.name for f in ab.list_files())
    assert names == ["ccu-auto-2026-10-04.json", "ccu-auto-2026-10-05.json", "ccu-auto-2026-10-06.json"]


def test_hour_is_configurable(monkeypatch):
    monkeypatch.setenv("AUTO_BACKUP_HOUR", "22")
    assert ab.tick(at(2, 21, 59)) is None
    assert ab.tick(at(2, 22)) is not None


def test_pre_import_copies_are_listed_but_never_pruned(monkeypatch):
    monkeypatch.setenv("AUTO_BACKUP_KEEP", "1")
    with open(os.path.join(ab.data_dir(), "vor-import-2026-09-30-091502.json"), "w") as fh:
        fh.write("{}")
    ab.tick(at(1, 3))
    ab.tick(at(2, 3))
    kinds = sorted((f.kind, f.name) for f in ab.list_files())
    assert kinds == [("auto", "ccu-auto-2026-10-02.json"),
                     ("vor-import", "vor-import-2026-09-30-091502.json")]


def test_path_of_only_resolves_listed_names():
    ab.tick(at(2, 3))
    assert ab.path_of("ccu-auto-2026-10-02.json") is not None
    for bad in ("../profile_names.json", "profile_sets.json", "ccu-auto-2026-10-03.json",
                "ccu-auto-2026-10-02.json/../x", "..%2fprofile_sets.json"):
        assert ab.path_of(bad) is None, bad


def test_a_write_error_is_reported_and_retried(monkeypatch):
    def broken(*_args, **_kwargs):
        raise OSError("Datenträger voll")

    working = ab.write_now
    monkeypatch.setattr(ab, "write_now", broken)
    assert ab.tick(at(2, 3)) is None
    assert "Datenträger voll" in ab.last_error()
    # not monkeypatch.undo(): that would also undo conftest's redirect of the data dir
    monkeypatch.setattr(ab, "write_now", working)
    assert ab.tick(at(2, 3, 5)) == "ccu-auto-2026-10-02.json"
    assert ab.last_error() is None
