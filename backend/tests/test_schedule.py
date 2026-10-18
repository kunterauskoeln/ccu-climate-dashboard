"""Unit tests for app.services.ccu.schedule – pure, no CCU."""
import pytest

from app.services.ccu.schedule import (
    DAY_MINUTES,
    Block,
    blocks_from_master,
    hhmm_to_min,
    master_from_blocks,
    min_to_hhmm,
    overlay,
    remove_range,
    validate_blocks,
)


# --- real P1 / Monday dump from the CCU (Wohnzimmer, 2026-09-02) --------------
def _p1_monday_master() -> dict:
    ends = {1: 360, 2: 540, 3: 1020, 4: 1320, 5: 1440,
            6: 1440, 7: 1440, 8: 1440, 9: 1440, 10: 1440,
            11: 1440, 12: 1440, 13: 1440}
    temps = {1: 17.0, 2: 21.0, 3: 17.0, 4: 21.0, 5: 17.0,
             6: 17.0, 7: 17.0, 8: 17.0, 9: 17.0, 10: 17.0,
             11: 17.0, 12: 17.0, 13: 17.0}
    out = {}
    for i in range(1, 14):
        out[f"P1_ENDTIME_MONDAY_{i}"] = ends[i]
        out[f"P1_TEMPERATURE_MONDAY_{i}"] = temps[i]
    return out


# --- time helpers -----------------------------------------------------------
@pytest.mark.parametrize("text,minutes", [
    ("00:00", 0), ("06:00", 360), ("09:00", 540), ("24:00", 1440), ("22:30", 1350),
])
def test_hhmm_roundtrip(text, minutes):
    assert hhmm_to_min(text) == minutes
    assert min_to_hhmm(minutes) == text


@pytest.mark.parametrize("bad", ["", "7", "7:60", "25:00", "-1:00", None])
def test_hhmm_rejects_garbage(bad):
    with pytest.raises(ValueError):
        hhmm_to_min(bad)


# --- blocks_from_master ---------------------------------------------------
def test_blocks_from_real_master():
    blocks = blocks_from_master(_p1_monday_master(), 1, "MONDAY")
    assert blocks == [
        Block(0, 360, 17.0),
        Block(360, 540, 21.0),
        Block(540, 1020, 17.0),
        Block(1020, 1320, 21.0),
        Block(1320, 1440, 17.0),
    ]


def test_blocks_from_master_accepts_lowercase_day():
    assert blocks_from_master(_p1_monday_master(), 1, "monday")


def test_blocks_from_master_missing_profile_returns_empty():
    assert blocks_from_master(_p1_monday_master(), 5, "MONDAY") == []


def test_blocks_from_master_extends_when_last_slot_short():
    master = {
        "P2_ENDTIME_TUESDAY_1": 480, "P2_TEMPERATURE_TUESDAY_1": 20.0,
        "P2_ENDTIME_TUESDAY_2": 600, "P2_TEMPERATURE_TUESDAY_2": 22.0,
    }
    blocks = blocks_from_master(master, 2, "TUESDAY")
    # the short final slot is held to midnight and coalesced with slot 2
    assert blocks == [Block(0, 480, 20.0), Block(480, DAY_MINUTES, 22.0)]


def test_blocks_from_master_coalesces_equal_neighbours():
    master = {
        "P1_ENDTIME_FRIDAY_1": 400, "P1_TEMPERATURE_FRIDAY_1": 18.0,
        "P1_ENDTIME_FRIDAY_2": 800, "P1_TEMPERATURE_FRIDAY_2": 18.0,
        "P1_ENDTIME_FRIDAY_3": 1440, "P1_TEMPERATURE_FRIDAY_3": 18.0,
    }
    assert blocks_from_master(master, 1, "FRIDAY") == [Block(0, 1440, 18.0)]


# --- master_from_blocks (roundtrip + padding) -------------------------------
def test_master_roundtrip_is_stable():
    original = _p1_monday_master()
    blocks = blocks_from_master(original, 1, "MONDAY")
    assert master_from_blocks(blocks, 1, "MONDAY") == original


def test_master_from_blocks_pads_with_hold_temp():
    blocks = [Block(0, 360, 17.0), Block(360, 1440, 21.0)]
    out = master_from_blocks(blocks, 3, "SUNDAY")
    assert out["P3_ENDTIME_SUNDAY_1"] == 360
    assert out["P3_ENDTIME_SUNDAY_2"] == 1440
    for i in range(3, 14):
        assert out[f"P3_ENDTIME_SUNDAY_{i}"] == 1440
        assert out[f"P3_TEMPERATURE_SUNDAY_{i}"] == 21.0


def test_master_from_blocks_rejects_too_many_blocks():
    blocks = []
    t = 0
    for i in range(14):  # 14 distinct segments -> exceeds 13
        blocks.append(Block(t, t + 100, float(15 + i)))
        t += 100
    blocks.append(Block(t, DAY_MINUTES, 99.0))
    with pytest.raises(ValueError):
        master_from_blocks(blocks, 1, "MONDAY")


@pytest.mark.parametrize("profile,day", [(0, "MONDAY"), (7, "MONDAY"), (1, "FUNDAY")])
def test_require_rejects_bad_profile_or_day(profile, day):
    with pytest.raises(ValueError):
        master_from_blocks([Block(0, DAY_MINUTES, 20.0)], profile, day)


# --- validate_blocks ------------------------------------------------------
@pytest.mark.parametrize("blocks", [
    [],
    [Block(60, DAY_MINUTES, 20.0)],                       # doesn't start at 0
    [Block(0, 720, 20.0)],                                # doesn't end at 24:00
    [Block(0, 700, 20.0), Block(720, DAY_MINUTES, 21.0)],  # gap
    [Block(0, 740, 20.0), Block(720, DAY_MINUTES, 21.0)],  # overlap
])
def test_validate_blocks_rejects_broken_schedules(blocks):
    with pytest.raises(ValueError):
        validate_blocks(blocks)


# --- overlay ------------------------------------------------------------
@pytest.fixture
def base_day():
    return [Block(0, DAY_MINUTES, 17.0)]


def test_overlay_inside_single_block_splits_into_three(base_day):
    out = overlay(base_day, 540, 660, 22.0)
    assert out == [
        Block(0, 540, 17.0),
        Block(540, 660, 22.0),
        Block(660, DAY_MINUTES, 17.0),
    ]


def test_overlay_spanning_multiple_blocks():
    blocks = [
        Block(0, 360, 17.0), Block(360, 540, 21.0),
        Block(540, 1020, 17.0), Block(1020, DAY_MINUTES, 21.0),
    ]
    out = overlay(blocks, 400, 1100, 19.0)
    assert out == [
        Block(0, 360, 17.0),
        Block(360, 400, 21.0),
        Block(400, 1100, 19.0),
        Block(1100, DAY_MINUTES, 21.0),
    ]


def test_overlay_whole_day(base_day):
    assert overlay(base_day, 0, DAY_MINUTES, 20.0) == [Block(0, DAY_MINUTES, 20.0)]


def test_overlay_coalesces_with_equal_neighbour():
    blocks = [Block(0, 600, 20.0), Block(600, DAY_MINUTES, 17.0)]
    out = overlay(blocks, 600, 800, 20.0)
    assert out == [Block(0, 800, 20.0), Block(800, DAY_MINUTES, 17.0)]


def test_overlay_exact_block_replacement():
    blocks = [Block(0, 600, 20.0), Block(600, 900, 22.0), Block(900, DAY_MINUTES, 20.0)]
    out = overlay(blocks, 600, 900, 20.0)
    assert out == [Block(0, DAY_MINUTES, 20.0)]


@pytest.mark.parametrize("start,end", [(-10, 100), (100, 100), (100, 50), (0, 1500)])
def test_overlay_rejects_bad_range(base_day, start, end):
    with pytest.raises(ValueError):
        overlay(base_day, start, end, 20.0)


def test_remove_range_inherits_previous_block():
    blocks = [Block(0, 600, 20.0), Block(600, 900, 22.0), Block(900, DAY_MINUTES, 19.0)]
    # delete 10:00-15:00 -> gap takes the previous block's 20.0, then coalesces
    assert remove_range(blocks, 600, 900) == [
        Block(0, 900, 20.0),
        Block(900, DAY_MINUTES, 19.0),
    ]


def test_remove_range_at_day_start_inherits_next_block():
    blocks = [Block(0, 600, 22.0), Block(600, DAY_MINUTES, 18.0)]
    assert remove_range(blocks, 0, 600) == [Block(0, DAY_MINUTES, 18.0)]


def test_remove_range_rejects_bad_range():
    with pytest.raises(ValueError):
        remove_range([Block(0, DAY_MINUTES, 20.0)], 100, 50)


def test_overlay_result_still_roundtrips_through_master(base_day):
    edited = overlay(base_day, 540, 1320, 21.5)
    master = master_from_blocks(edited, 2, "WEDNESDAY")
    assert blocks_from_master(master, 2, "WEDNESDAY") == edited
