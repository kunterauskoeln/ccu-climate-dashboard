"""app.services.valve_history - valve positions for the 48 h chart."""
import json

from app.services import valve_history as vh

H = 3600.0


def test_record_and_series_in_percent():
    vh.record({"Bad": 0.4, "Flur": 0.0, "WC": None}, now=1000.0)
    vh.record({"Bad": 1.0, "Flur": 0.25}, now=1300.0)
    s = vh.series(48, now=1400.0)
    assert s.times == [1000.0, 1300.0]
    assert s.rooms == {"Bad": [40, 100], "Flur": [0, 25]}       # WC never had a reading


def test_old_samples_are_dropped_after_72_hours():
    vh.record({"Bad": 0.1}, now=0.0)
    vh.record({"Bad": 0.2}, now=73 * H)
    assert vh.series(72, now=73 * H).times == [73 * H]


def test_only_the_requested_window():
    for i in range(10):                                  # one sample every 5 minutes
        vh.record({"Bad": i / 10}, now=i * 300.0)
    s = vh.series(0.25, now=9 * 300.0)                   # last 15 minutes
    assert s.times == [1800.0, 2100.0, 2400.0, 2700.0] and s.rooms["Bad"] == [60, 70, 80, 90]


def test_a_pause_breaks_the_lines():
    vh.record({"Bad": 0.5}, now=0.0)
    vh.record({"Bad": 0.5}, now=300.0)
    vh.record({"Bad": 0.7}, now=5 * H)                    # server was off
    s = vh.series(48, now=5 * H)
    assert s.times == [0.0, 300.0, 600.0, 5 * H]
    assert s.rooms["Bad"] == [50, 50, None, 70]


def test_survives_a_restart():
    vh.record({"Bad": 0.3}, now=10.0)
    vh.reset()                                           # new process
    assert vh.series(48, now=20.0).rooms == {"Bad": [30]}
    with open(vh._PATH, encoding="utf-8") as fh:
        assert json.load(fh)["samples"] == [[10.0, {"Bad": 0.3}]]


def test_broken_file_starts_empty():
    with open(vh._PATH, "w", encoding="utf-8") as fh:
        fh.write("kaputt")
    vh.reset()
    assert vh.series(48, now=1.0).times == []
