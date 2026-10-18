"""app.services.profile_names – global {slot: name}, tolerant loader."""
import json

import pytest

from app.services import profile_names


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "profile_names.json"
    monkeypatch.setattr(profile_names, "_PATH", str(path))
    return path


def test_load_missing_file_returns_empty(store):
    assert profile_names.load() == {}


def test_set_and_get_global(store):
    profile_names.set_name(3, "Nacht")
    profile_names.set_name(1, "Standard")
    assert profile_names.load() == {"3": "Nacht", "1": "Standard"}
    assert json.loads(store.read_text(encoding="utf-8")) == {"3": "Nacht", "1": "Standard"}


def test_load_migrates_old_per_room_shape(store):
    store.write_text(json.dumps({
        "Wohnzimmer": {"1": "Standard", "3": "Nacht"},
        "Bad": {"1": "Standard", "3": "Nacht"},
    }), encoding="utf-8")
    assert profile_names.load() == {"1": "Standard", "3": "Nacht"}


def test_set_name_rewrites_migrated_shape_flat(store):
    store.write_text(json.dumps({"Wohnzimmer": {"2": "Urlaub"}}), encoding="utf-8")
    profile_names.set_name(2, "Ferien")
    assert json.loads(store.read_text(encoding="utf-8")) == {"2": "Ferien"}
