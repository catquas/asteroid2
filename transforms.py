"""Pure LazyFrame -> LazyFrame transformations.

These functions do no I/O (no scan_parquet, no collect), which is what makes
them unit-testable: a test can feed in a tiny hand-built frame and assert on
the exact output with polars.testing.assert_frame_equal.
"""

import polars as pl


def add_sample_weights(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Add wgt, wpm, wcm, and wotm columns to a matched-sample frame.

    Expects columns: sample_weight, diff_resp_rate, cont_tot_dwnwght,
    a_typ_flag, pm_value, cm_value.

    - A cont_tot_dwnwght of 0 is treated as 1.0 (no downweighting).
    - "T" rows are weighted by wgt; "A" rows pass through unweighted;
      all other flags contribute 0.
    - wotm is the rounded weighted over-the-month change.
    """
    return (
        lf.with_columns(
            pl.when(pl.col("cont_tot_dwnwght") == 0)
            .then(pl.lit(1.0))
            .otherwise(pl.col("cont_tot_dwnwght"))
            .alias("cont_tot_dwnwght")
        )
        .with_columns(
            wgt=(pl.col("sample_weight") * pl.col("diff_resp_rate") * pl.col("cont_tot_dwnwght"))
        )
        .with_columns(
            pl.when(pl.col("a_typ_flag") == "T")
            .then(pl.struct(wpm=(pl.col("pm_value") * pl.col("wgt")), wcm=(pl.col("cm_value") * pl.col("wgt"))))
            .when(pl.col("a_typ_flag") == "A")
            .then(pl.struct(wpm=pl.col("pm_value"), wcm=pl.col("cm_value")))
            .otherwise(pl.struct(wpm=0, wcm=0))
            .struct.unnest()
        )
        .with_columns(
            wotm=(pl.col("wcm") - pl.col("wpm")).round()
        )
    )
