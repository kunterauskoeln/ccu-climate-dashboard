"""app.services.absence - all rooms on one profile for a while, then back."""
from datetime import datetime, timedelta

import pytest
from test_api_routes import client  # noqa: F401  (fixture with fake CCU + transfer)

from app.services import absence, apartment, climate_schedule, profile_transfer

TZ = climate_schedule.tz()


def now():
    return datetime.now(TZ).replace(second=0, microsecond=0)


def clients_of(c):
    return lambda: (c.xmlrpc, c.device_map.get())


def active(c, wth):
    return c.xmlrpc.paramsets[(f"{wth}:1", "VALUES")]["ACTIVE_PROFILE"]


def run(c, at):
    """One tick plus the background transfer it may have started."""
    absence.tick(clients_of(c), now=at)
    profile_transfer.join(timeout=3)


def test_whole_absence_from_start_to_return(client):  # noqa: F811
    t0 = now()
    r = client.put("/system/absence", json={"profile": 2, "end": (t0 + timedelta(hours=2)).isoformat()})
    assert r.status_code == 200 and r.json()["phase"] == "geplant"

    run(client, t0 + timedelta(minutes=1))              # start: remember, switch
    st = absence.state()
    assert st.phase == "aktiv" and st.previous == {"Arbeitszimmer": 4, "Wohnzimmer": 4}
    assert active(client, "WTH_WZ") == 2 and active(client, "WTH_AZ") == 2
    run(client, t0 + timedelta(minutes=2))              # verify
    assert absence.state().applied is True
    assert "alle Räume umgeschaltet" in absence.state().message

    # a room changed by hand during the absence keeps its profile
    client.xmlrpc.paramsets[("WTH_WZ:1", "VALUES")]["ACTIVE_PROFILE"] = 3
    run(client, t0 + timedelta(minutes=30))
    assert active(client, "WTH_WZ") == 3

    run(client, t0 + timedelta(hours=2, minutes=1))     # end: back to the previous profiles
    assert active(client, "WTH_WZ") == 4 and active(client, "WTH_AZ") == 4
    run(client, t0 + timedelta(hours=2, minutes=2))
    assert absence.state().phase == "beendet"


def test_planned_start_waits(client):  # noqa: F811
    t0 = now()
    absence.configure(2, (t0 + timedelta(days=1)).isoformat(), (t0 + timedelta(days=3)).isoformat(), now=t0)
    run(client, t0 + timedelta(hours=1))
    assert absence.state().phase == "geplant" and active(client, "WTH_WZ") == 4
    run(client, t0 + timedelta(days=1, minutes=1))
    assert absence.state().phase == "aktiv" and active(client, "WTH_WZ") == 2


def test_missed_start_and_end_are_caught_up(client):  # noqa: F811
    t0 = now()
    absence.configure(2, (t0 + timedelta(hours=1)).isoformat(), (t0 + timedelta(hours=5)).isoformat(), now=t0)
    run(client, t0 + timedelta(hours=8))    # server was off the whole time
    # start and end both passed: the rooms are already on their old profiles,
    # so it ends at once without switching anything back and forth
    st = absence.state()
    assert st.phase == "beendet" and st.previous["Wohnzimmer"] == 4
    assert active(client, "WTH_WZ") == 4
    assert client.xmlrpc.set_calls == []


def test_cancel(client):  # noqa: F811
    t0 = now()
    absence.configure(2, (t0 + timedelta(days=1)).isoformat(), (t0 + timedelta(days=2)).isoformat(), now=t0)
    assert client.delete("/system/absence").json()["phase"] == "abgebrochen"

    client.put("/system/absence", json={"profile": 2, "end": (t0 + timedelta(days=2)).isoformat()})
    run(client, t0 + timedelta(minutes=1))
    assert active(client, "WTH_WZ") == 2
    client.delete("/system/absence")                     # end now
    run(client, now() + timedelta(minutes=1))
    assert active(client, "WTH_WZ") == 4 and absence.state().phase == "rueckkehr"
    run(client, now() + timedelta(minutes=2))
    assert absence.state().phase == "beendet"
    assert client.delete("/system/absence").status_code == 422


def test_change_profile_while_active_switches_again(client):  # noqa: F811
    t0 = now()
    absence.configure(2, None, (t0 + timedelta(days=2)).isoformat(), now=t0)
    run(client, t0 + timedelta(minutes=1))
    run(client, t0 + timedelta(minutes=2))
    absence.configure(5, None, (t0 + timedelta(days=3)).isoformat(), now=t0 + timedelta(minutes=3))
    st = absence.state()
    assert st.applied is False and st.previous == {"Arbeitszimmer": 4, "Wohnzimmer": 4}
    run(client, t0 + timedelta(minutes=4))
    assert active(client, "WTH_WZ") == 5


def test_waits_while_another_transfer_runs(client, monkeypatch):  # noqa: F811
    t0 = now()
    absence.configure(2, None, (t0 + timedelta(days=1)).isoformat(), now=t0)
    monkeypatch.setattr(profile_transfer, "is_running", lambda: True)
    absence.tick(clients_of(client), now=t0 + timedelta(minutes=1))
    assert absence.state().phase == "geplant"


def test_gives_up_after_three_attempts(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(apartment, "start", lambda *a, **k: True)   # switching never happens
    t0 = now()
    absence.configure(2, None, (t0 + timedelta(days=1)).isoformat(), now=t0)
    for minute in range(1, 6):
        run(client, t0 + timedelta(minutes=minute))
    st = absence.state()
    assert st.applied is True and "nicht umgeschaltet nach 3 Versuchen" in st.message
    assert "Wohnzimmer" in st.message


@pytest.mark.parametrize("body, message", [
    ({"profile": 2, "end": "2020-01-01T10:00"}, "Zukunft"),
    ({"profile": 2, "start": "2099-01-02T10:00", "end": "2099-01-01T10:00"}, "nach dem Beginn"),
    ({"profile": 2, "end": "morgen"}, "nicht lesbar"),
])
def test_validation(client, body, message):  # noqa: F811
    r = client.put("/system/absence", json=body)
    assert r.status_code == 422 and message in r.json()["error"]["message"]


def test_profile_out_of_range_is_rejected(client):  # noqa: F811
    assert client.put("/system/absence", json={"profile": 7, "end": "2099-01-01T10:00"}).status_code == 422


def test_default_state(client):  # noqa: F811
    assert client.get("/system/absence").json()["phase"] == "aus"
