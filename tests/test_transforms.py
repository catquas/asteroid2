"""Example unit tests for the polars weighting transform.

Two styles are shown:

1. Example-based pytest tests: build a tiny input frame by hand, state the
   exact expected output, and compare with polars.testing.assert_frame_equal.
2. Property-based hypothesis tests: polars.testing.parametric generates
   random input frames, and we assert invariants that must hold for ANY
   input (e.g. non-A/T rows never contribute weighted employment).

Run with:  pytest tests/ -v
"""

import hypothesis.strategies as st
import polars as pl
from hypothesis import given
from polars.testing import assert_frame_equal, assert_series_equal
from polars.testing.parametric import column, dataframes

from transforms import add_sample_weights


def make_input(rows: list[dict]) -> pl.LazyFrame:
    """Small helper so each test only spells out the columns it cares about."""
    defaults = {
        "sample_weight": 1.0,
        "diff_resp_rate": 1.0,
        "cont_tot_dwnwght": 1.0,
        "a_typ_flag": "T",
        "pm_value": 0.0,
        "cm_value": 0.0,
    }
    return pl.LazyFrame(
        [{**defaults, **row} for row in rows],
        schema={
            "sample_weight": pl.Float64,
            "diff_resp_rate": pl.Float64,
            "cont_tot_dwnwght": pl.Float64,
            "a_typ_flag": pl.String,
            "pm_value": pl.Float64,
            "cm_value": pl.Float64,
        },
    )


# ── Example-based tests ──────────────────────────────────────────────


def test_t_flag_rows_are_weighted():
    lf = make_input(
        [
            {
                "a_typ_flag": "T",
                "sample_weight": 2.0,
                "diff_resp_rate": 1.5,
                "cont_tot_dwnwght": 1.0,
                "pm_value": 100.0,
                "cm_value": 110.0,
            }
        ]
    )

    result = add_sample_weights(lf).select("wgt", "wpm", "wcm", "wotm").collect()

    expected = pl.DataFrame(
        {"wgt": [3.0], "wpm": [300.0], "wcm": [330.0], "wotm": [30.0]}
    )
    assert_frame_equal(result, expected)


def test_a_flag_rows_pass_through_unweighted():
    lf = make_input(
        [
            {
                "a_typ_flag": "A",
                "sample_weight": 5.0,  # must be ignored for "A" rows
                "pm_value": 40.0,
                "cm_value": 45.0,
            }
        ]
    )

    result = add_sample_weights(lf).select("wpm", "wcm", "wotm").collect()

    expected = pl.DataFrame({"wpm": [40.0], "wcm": [45.0], "wotm": [5.0]})
    assert_frame_equal(result, expected)


def test_other_flags_contribute_zero():
    lf = make_input(
        [
            {"a_typ_flag": "U", "pm_value": 40.0, "cm_value": 45.0},
            {"a_typ_flag": "X", "pm_value": 10.0, "cm_value": 90.0},
        ]
    )

    result = add_sample_weights(lf).select("wpm", "wcm", "wotm").collect()

    expected = pl.DataFrame(
        {"wpm": [0.0, 0.0], "wcm": [0.0, 0.0], "wotm": [0.0, 0.0]}
    )
    assert_frame_equal(result, expected)


def test_zero_downweight_is_treated_as_one():
    lf = make_input(
        [
            {
                "a_typ_flag": "T",
                "sample_weight": 2.0,
                "diff_resp_rate": 1.0,
                "cont_tot_dwnwght": 0.0,  # would zero everything out if kept
                "pm_value": 100.0,
                "cm_value": 100.0,
            }
        ]
    )

    result = add_sample_weights(lf).collect()

    assert result.item(0, "cont_tot_dwnwght") == 1.0
    assert result.item(0, "wgt") == 2.0
    assert result.item(0, "wpm") == 200.0


# ── Property-based tests (hypothesis) ────────────────────────────────

finite_floats = st.floats(
    min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False
)

sample_frames = dataframes(
    cols=[
        column("sample_weight", dtype=pl.Float64, strategy=finite_floats),
        column("diff_resp_rate", dtype=pl.Float64, strategy=finite_floats),
        column("cont_tot_dwnwght", dtype=pl.Float64, strategy=finite_floats),
        column("a_typ_flag", dtype=pl.String, strategy=st.sampled_from(["T", "A", "U", "X"])),
        column("pm_value", dtype=pl.Float64, strategy=finite_floats),
        column("cm_value", dtype=pl.Float64, strategy=finite_floats),
    ],
    min_size=1,
    allow_null=False,
)


@given(df=sample_frames)
def test_only_a_and_t_rows_contribute(df: pl.DataFrame):
    out = add_sample_weights(df.lazy()).collect()

    others = out.filter(~pl.col("a_typ_flag").is_in(["A", "T"]))
    assert (others["wpm"] == 0).all()
    assert (others["wcm"] == 0).all()
    assert (others["wotm"] == 0).all()


@given(df=sample_frames)
def test_a_rows_keep_reported_values(df: pl.DataFrame):
    out = add_sample_weights(df.lazy()).collect().filter(pl.col("a_typ_flag") == "A")

    assert_series_equal(out["wpm"], out["pm_value"], check_names=False)
    assert_series_equal(out["wcm"], out["cm_value"], check_names=False)


@given(df=sample_frames)
def test_wotm_is_rounded_weighted_change(df: pl.DataFrame):
    out = add_sample_weights(df.lazy()).collect()

    assert_series_equal(
        out["wotm"], (out["wcm"] - out["wpm"]).round(), check_names=False
    )


@given(df=sample_frames)
def test_row_count_and_input_columns_preserved(df: pl.DataFrame):
    out = add_sample_weights(df.lazy()).collect()

    assert out.height == df.height
    assert_frame_equal(out.select(df.columns).drop("cont_tot_dwnwght"),
                       df.drop("cont_tot_dwnwght"))
