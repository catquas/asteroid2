"""Example unit tests for the filter/dropdown bar selection logic.

Same two styles as tests/test_transforms.py:

1. Example-based pytest tests: one small, named scenario per test, so a
   failure message tells you exactly which dropdown behavior broke.
2. Property-based hypothesis tests: invariants that must hold for any
   options list ("the page always ends up with a usable selection").

Run with:  pytest tests/ -v
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given

from dropdown_logic import (
    closest_match,
    first_or_current,
    max_or_current,
    max_value,
    month_target,
    numeric_previous_next,
    previous_next,
)

# ── first_or_current / closest_match ─────────────────────────────────


def test_valid_current_selection_is_kept():
    assert first_or_current(["01", "02", "03"], "02") == "02"


def test_invalid_selection_falls_back_to_first_option():
    assert first_or_current(["01", "02"], "99") == "01"
    assert first_or_current(["01", "02"], None) == "01"


def test_no_options_yields_empty_selection():
    assert first_or_current([], "02") == ""


def test_bestop_prefers_closest_series_prefix():
    # A user on series 20238000 steps to an area that only has 2023xxxx
    # variants: keep them in the closest series instead of jumping to the top.
    options = ["10000000", "20231000", "20239000"]
    assert first_or_current(options, "20238000", bestop=True) == "20231000"


def test_closest_match_tries_shorter_prefixes():
    assert closest_match(["555", "301", "662"], "3019") == "301"
    assert closest_match(["555", "662"], "3019") == ""


def test_closest_match_naics_sector_fallback():
    # Manufacturing/trade sectors span codes (31-33, 41-45): a query starting
    # with "31" may match an option in a sibling sector like "32".
    assert closest_match(["32000000"], "31500000") == "32000000"


# ── max_value / max_or_current ───────────────────────────────────────


def test_max_value_orders_numerically_not_alphabetically():
    assert max_value(["9", "10", "2"]) == "10"  # "9" > "10" as strings


def test_max_or_current_defaults_to_highest_closing():
    assert max_or_current(["1", "2", "3"], None) == "3"
    assert max_or_current(["1", "2", "3"], "2") == "2"
    assert max_or_current([], "2") == ""


# ── previous_next step buttons ───────────────────────────────────────


def test_previous_next_middle_and_edges():
    options = ["a", "b", "c"]
    assert previous_next(options, "b") == {"prev": "a", "next": "c"}
    assert previous_next(options, "a") == {"prev": None, "next": "b"}
    assert previous_next(options, "c") == {"prev": "b", "next": None}


def test_previous_next_with_unknown_current():
    assert previous_next(["a", "b"], "z") == {"prev": None, "next": None}


def test_numeric_previous_next_sorts_numerically():
    # String sort would put "10" between "1" and "2".
    assert numeric_previous_next(["1", "2", "10"], "2") == {"prev": "1", "next": "10"}


# ── month step buttons ───────────────────────────────────────────────

MONTH_BOUNDS = dict(startyear=2017, maxyear="2026", maxmonth="06")


@pytest.mark.parametrize(
    ("year", "month", "direction", "expected"),
    [
        ("2025", "05", "prev", ("2025", "04")),
        ("2025", "01", "prev", ("2024", "12")),  # wraps into prior year
        ("2017", "01", "prev", None),  # at the very start of the data
        ("2025", "05", "next", ("2025", "06")),
        ("2025", "12", "next", ("2026", "01")),  # wraps into next year
        ("2026", "06", "next", None),  # at the latest available month
    ],
)
def test_month_target(year, month, direction, expected):
    assert month_target(year, month, direction, **MONTH_BOUNDS) == expected


# ── Property-based tests (hypothesis) ────────────────────────────────

codes = st.text(alphabet="0123456789", min_size=1, max_size=8)
option_lists = st.lists(codes, min_size=1, max_size=20, unique=True)


@given(options=option_lists, current=st.one_of(st.none(), codes))
def test_page_always_gets_a_usable_selection(options, current):
    # Whatever the query string says, the resolved selection must be one of
    # the real options whenever any options exist.
    assert first_or_current(options, current, bestop=True) in options
    assert max_or_current(options, current) in options


@given(options=option_lists, current=codes)
def test_step_buttons_point_at_adjacent_options(options, current):
    nav = previous_next(options, current)
    if current not in options:
        assert nav == {"prev": None, "next": None}
    else:
        index = options.index(current)
        assert nav["prev"] == (options[index - 1] if index > 0 else None)
        assert nav["next"] == (
            options[index + 1] if index < len(options) - 1 else None
        )


@given(
    year=st.integers(min_value=2017, max_value=2026),
    month=st.integers(min_value=1, max_value=12),
)
def test_month_stepping_round_trips(year, month):
    # Going next then prev (or vice versa) must return to where you started,
    # for every month strictly inside the valid range.
    start = (str(year), str(month).zfill(2))
    forward = month_target(*start, "next", **MONTH_BOUNDS)
    if forward is not None:
        assert month_target(*forward, "prev", **MONTH_BOUNDS) == start
