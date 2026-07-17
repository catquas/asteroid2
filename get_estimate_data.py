import polars as pl
import polars.selectors as cs
import time
from pathlib import Path
from transforms import add_sample_weights
# from pprint import pprint

aceslib_path = Path("/aceslib")
commonlib_path = Path("/commonlib")
aces_estreview = "https://aa123.com"
aces_uirundisplay = "https://aa456.com"
aces_registrydisplay = "https://aa789.com"

# ── Section 1: get closings and bmrkyr ────────────────────────────────────────────

sam3_current = pl.scan_parquet(aceslib_path / "sam3_y1_current.pq")
estimates_current = pl.scan_parquet(aceslib_path / "estimates_current.pq")

print(estimates_current.schema)

area_ser_struct = pl.scan_parquet(commonlib_path / "area_ser_struct.pq")
salist = pl.scan_parquet(commonlib_path / "salist.pq")
series_title = pl.scan_parquet(commonlib_path / "series_title.pq")

def getclosing():
    current_closings = (
        sam3_current
        .filter(
            pl.col.state_fips_code == pl.lit('12'),
            pl.col.area_fips_code == pl.lit('00000'),
            pl.col.series_code == pl.lit('10000000'),
            pl.col.year == pl.col.year.max(),
        )
        .filter(
            pl.col.month == pl.col.month.max(),
        )
        .filter(
            pl.col.estimate_type_code == pl.col.estimate_type_code.max(),
        )
        .select('year', 'month', pl.col('estimate_type_code').alias('closing'))
        .head(1).collect().to_dicts()[0]
    )
    print(current_closings)
    return current_closings

def get_state_statename_df():
    return (
        salist.select("stid", "state")
        .sort("stid", "state")
        .unique()
        .rename({"stid": "state", "state": "statename"})
    )


def get_area_areaname_df():
    return (
        salist.select("msa", "area")
        .sort("msa", "area")
        .unique()
        .rename({"msa": "area", "area": "areaname"})
    )


def get_series_seriesname_df():
    return (
        series_title.select("series_code", "series_name")
        .sort("series_code", "series_name")
        .unique()
        .rename({"series_code": "series", "series_name": "seriesname"})
    )


closings = (
    estimates_current.filter(
        pl.col.state_fips_code == '01',
        pl.col.area_fips_code == "00000",
        pl.col.series_code == '00000000', 
        pl.col.data_type_code == "01",
        pl.col.estimate_type_code.is_in(['1','2','3'])
    )
    .select(["bmrk_year", "year", "month", "estimate_type_code"])
    .unique()
    .sort(["bmrk_year", "year", "month", "estimate_type_code"], descending=True)
)

# bmrkyr = closings.item(0, "bmrk_year")

# maxclosings = (
#     closings.group_by("year", "month")
#     .agg(pl.max("estimate_type_code").alias("maxetc"))
#     .sort(["year", "month", "maxetc"], descending=True)
# )

def get_year_month_closing_df():
    return closings.drop('bmrk_year').rename({'estimate_type_code': 'closing'}).collect()

# ── Section 2: structure table ────────────────────────────────────────────


def get_structure(bmrkyr: str):
    structure = (
        area_ser_struct.filter(
            # (pl.col("state_fips_code").is_in(states)) & (pl.col("year") == bmrkyr)
            pl.col("year") == bmrkyr
        )
        .join(
            salist,
            left_on=["state_fips_code", "area_fips_code"],
            right_on=["stid", "msa"],
            how="inner",
        )
        .filter(
            pl.col("data_type_code").is_in(["01", "85"]),
            pl.col.series_type_code.is_in(["B", "I", "C"]),
        )
        .filter(
            (pl.col("is_published") == "Y")
            | ((pl.col("data_type_code") == "01") & (pl.col("series_type_code") == "B"))
        )
        .join(
            series_title,
            on=["series_code"],
            how="left",
        )
        .select(
            [
                "state_fips_code",
                "area_fips_code",
                "series_code",
                "data_type_code",
                "series_type_code",
                "estimation_type_code",
                "year",
                "is_published",
                pl.col.state.alias("state_name"),
                pl.col.area.alias("area_name"),
                "series_name",
                pl.when(pl.col('ws_flag')=='1').then(pl.lit('Yes'))
                    .when(pl.col('ws_flag')=='0').then(pl.lit('No'))
                    .otherwise(pl.col('ws_flag').cast(pl.String))
                .alias('ws_flag')
            ]
        )
        .unique()
        .sort(["state_fips_code", "area_fips_code", "series_code", "data_type_code"])
    )

    return structure

#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
structure = get_structure(bmrkyr='2025')
#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!


# ── Section 3: get state-area-series info ────────────────────────────────────────────

def get_all_oot_series(year, month, closing):
    estimates_current = pl.scan_parquet(aceslib_path / "estimates_current.pq")
    
    # OOT table
    all_oot_series = (
        estimates_current
        .filter(
            pl.col.year == year,
            pl.col.month == month,
            pl.col.estimate_type_code == closing,
            pl.col("data_type_code")=="01",
            # pl.col.series_type_code.is_in(["B", "I", "C"]),
            # (pl.col("is_published") == "Y")
            # | ((pl.col("data_type_code") == "01") & (pl.col("series_type_code") == "B"))
        )
        .select(
            
# pl.col.estimate_link_relative, pl.col.lower_tolerance, pl.col.upper_tolerance,

            pl.col.state_fips_code, pl.col.area_fips_code, pl.col.series_code, 
            pl.col.data_type_code, 
            pl.col.estimate_link_relative.is_between(pl.col.lower_tolerance, pl.col.upper_tolerance).alias('in_tolerance')
        )
        .filter(~pl.col.in_tolerance)
        .sort(pl.col.state_fips_code, pl.col.area_fips_code, pl.col.series_code, pl.col.data_type_code)
    )

    return all_oot_series

# tol = (estimates_current.filter(pl.col.state_fips_code =='12', pl.col.area_fips_code=='00000', pl.col.series_code=='20237000', pl.col.estimate_type_code.is_in(['1','2']))
#        .select(            pl.col.state_fips_code, pl.col.area_fips_code, pl.col.series_code, 
#             pl.col.data_type_code, pl.col.year, pl.col.month, pl.col.estimate_type_code,
#             pl.col.estimate_link_relative, pl.col.lower_tolerance, pl.col.upper_tolerance,
#             )
#        )
# CHANGE THIS TO USE MAX YEAR MONTH CLOSING, AND LATER TO DEPEND ON SELECTED YEAR
oot_series = get_all_oot_series('2026', '06', '1')
# ################################################################################

# pl.Config.set_tbl_rows(-1)
# pl.Config.set_tbl_cols(-1)
# print(tol.collect())
# print(oot_series.filter(pl.col.state_fips_code=='12').collect())

# def get_state_area_series_df(structure: pl.LazyFrame) -> pl.DataFrame:
def get_state_area_series_lf() -> pl.LazyFrame:
    # Filter-bar source: valid state, area, series, datatype, and TOP choices.

    # Combined condition for the subset of data we want to match against
    match_condition = (pl.col("series_type_code") == "B") & (
        (pl.col("data_type_code") == "85")
        | (pl.col("series_code").cast(pl.String).str.starts_with("90"))
    )

    # Extract the unique matching combinations of state, area, and series
    valid_keys = (
        structure.filter(match_condition)
        .select("state_fips_code", "area_fips_code", "series_code")
        .unique()
        .with_columns(pl.lit("Y").alias("toplev"))
    )

    # 3. Create a single struct column out of the valid combinations DataFrame
    final_state_area_series = ( 
        structure
        .filter(pl.col.estimation_type_code != pl.lit('D'))
        .join(
            valid_keys, on=["state_fips_code", "area_fips_code", "series_code"], how="left"
        )
        .with_columns(pl.col.toplev.fill_null("N"))
        .join(
            oot_series, on=["state_fips_code", "area_fips_code", "series_code"], how="left"
        )
        .select(
            pl.col.state_fips_code.alias("state").cast(pl.String),
            pl.col.area_fips_code.alias("area").cast(pl.String),
            pl.col.series_code.alias("series").cast(pl.String),
            pl.col.series_type_code.alias('seriestype').cast(pl.String),
            pl.col.toplev,
            pl.col.data_type_code.alias('datatype').cast(pl.String),
            pl.when(~pl.col.in_tolerance).then(pl.lit('Y')).otherwise(pl.lit('N')).fill_null(pl.lit('N')).alias('oot')
        )
    )

    return final_state_area_series


# ── Section 3: Output page data ────────────────────────────────────────────

# This creates a dictionary of data to show on the output page
# def get_input_data(selected: dict) -> tuple[dict[str, pl.DataFrame], pl.DataFrame]:
def get_input_data(selected: dict) -> tuple[dict[str, pl.DataFrame], pl.LazyFrame, pl.LazyFrame]:
    # print('selected', selected)
    xstart_counter = time.perf_counter()

    selected['cm'] = selected['month']
    selected['cy'] = selected['year']
    # Get pm_y, pm, pm_closing
    if selected['cm'] == '01':
        selected['pm'] = '12'
        selected['pm_y'] = str(int(selected['cy'])-1)
        selected['pm_closing'] = '3'
    else:
        selected['pm'] = str(int(selected['cm'])-1).zfill(2)
        selected['pm_y'] = selected['cy']
        if selected["closing"] == "3":
            if selected['pm'] in ['11', '12']:
                selected['pm_closing'] = '3'
            else:
                selected['pm_closing'] = '4'
        else:
            selected['pm_closing'] = '2'
    
    # Get p12m_y, p12m, p12m_closing
    selected["p12m_y"] = str(int(selected['cy'])-1)
    selected["p12m"] = selected['cm'] 
    if selected["closing"] == "3" or selected['cm'] < '10':
        selected["p12m_closing"] = '4'
    else:
        selected["p12m_closing"] = '3'

    # get bmrkyr
    if selected['closing'] == '3':
        bmrkyr = selected['cy']
    else:
        bmrkyr = str(int(selected['cy'])-1)

    # get prior_closing, prior_closing_bmrkyr
    if selected["closing"] == "3":
        selected["prior_closing_bmrkyr"] = str(int(bmrkyr) - 1)
        if selected["cm"] == "12":
            selected["prior_closing"] = "1"
        else:
            selected["prior_closing"] = "2"
    elif selected["closing"] == "2":
        selected["prior_closing_bmrkyr"] = bmrkyr
        selected["prior_closing"] = "1"
    else:
        selected["prior_closing_bmrkyr"] = None
        selected["prior_closing"] = None




   # ***********************************************************************************************************************
   # ***********************************************************************************************************************
   #                                        ESTIMATES INFO
   # ***********************************************************************************************************************
   # ***********************************************************************************************************************

    def get_series_estimates(selected, bmrkyr) -> pl.LazyFrame:
        archive_filename = "estimates_archive_" + bmrkyr + '.pq'
        # Combine them into a full path
        pqfile = aceslib_path / archive_filename

        # Verify if the file exists and is not a folder
        if pqfile.is_file():
            estimates_path = pqfile
        else:
            estimates_path = aceslib_path / "estimates_current.pq"
        print('bmrkyr: ', bmrkyr, 'path: ', estimates_path)
        estimates_lf = pl.scan_parquet(estimates_path)
        
        if selected['month'] in ['10','11','12'] and selected['closing'] == '3':
            archive_filename = "estimates_archive_" + str(int(bmrkyr)-1) + '.pq'
            print('archive_filename: ', archive_filename)
            estimates_lf = (
                pl.concat([
                    pl.scan_parquet(aceslib_path / archive_filename),
                    estimates_lf
                ])
            )

        # series estimates
        series_estimates = estimates_lf.filter(
            pl.col.state_fips_code == selected["state"],
            pl.col.area_fips_code == selected["area"],
            pl.col.series_code == selected["series"],
        )
        return series_estimates
    
    series_estimates_lf: pl.LazyFrame = get_series_estimates(selected, bmrkyr)

    #OT, Amt: 912, Type: OTMC  {MS}  removing
    #RW, Amt: 352, adj Y1 weight to unweighted sample coverage of 0.126337 {SR} , This NAICS is causing 50-000000 to be stronger.
    def get_series_history(selected: dict) -> pl.DataFrame:
        
        soismsa_pattern = (
            # r"OT, Amt: (-?\d+), Type: (\w+)\s+\{(SI|MS)\}"  # format for adj cmnts
            r"(?P<adjtype>Manual|OT|EM|RW|R1), Amt: (?P<adjamt>-?\d+)(?:,\s+(Type:|adj Y1 weight to) (?P<adjsubtype>\w+))?.+\{(?P<adjreason>SI|MS|SR|SM|MR)\}"  # format for adj cmnts
        )
        series_hist_df = (
            series_estimates_lf
            .filter(
                pl.col("data_type_code") == "01",
                pl.col.estimate_type_code == pl.col.estimate_type_code.max().over(['year', 'month']),
                pl.col.year.cast(pl.Int64) > int(selected['cy']) - 3
            )

            .with_columns(
                pl.col("analyst_comment").str.extract_groups(soismsa_pattern).alias("extracted")
            )
            .unnest("extracted")
            # .rename({"1": "amount", "2": "otmoty_type", "3": "sims_type"})
            .with_columns(
                pl.when((pl.col('adjreason').is_in(['MS','SI'])) & (pl.col('adjtype')=='OT'))
                .then(pl.concat_str(
                        [
                            pl.col("adjreason"),
                            pl.lit("-"),
                            pl.col("adjsubtype").str.slice(2, 1).str.to_lowercase(),
                            pl.lit(": "),
                            pl.col("adjamt"),
                        ],
                        separator="",
                    )
                )
                .when(pl.col('adjtype') =='RW')
                .then(pl.concat_str(
                        [
                            # (pl.when(pl.col("adjtype")=='Manual').then(pl.lit('RW')).otherwise(pl.col.adjtype)),
                            pl.lit("RW-"),
                            pl.col("adjsubtype").str.slice(0, 1).str.to_lowercase(),
                            pl.lit(": "),
                            pl.col("adjamt"),
                        ],
                        separator="",
                    )
                )
                .when(pl.col('adjtype') =='Manual')
                .then(pl.concat_str(
                        [
                            pl.lit("RW-m: "),
                            pl.col("adjamt"),
                        ],
                        separator="",
                    )
                )
                .otherwise(pl.concat_str(
                        [
                            pl.col("adjtype"),
                            pl.lit(": "),
                            pl.col("adjamt"),
                        ],
                        separator="",
                    )

                )
                .fill_null(pl.col.sample_adjustment.cast(pl.Int64))
                .cast(pl.String)
                .alias("Est Adj")
            )
            .sort(["year", "month", "estimate_type_code"])
            .select(
                'published_estimate_value', 'upper_tolerance', 'lower_tolerance',
                'year', 'month', 'adjtype', 'adjsubtype', 'adjamt', 'adjreason', 'Est Adj',
                pl.col.original_estimate_value.cast(pl.Int64).alias('Orig Est'),
                pl.col("sample_adjustment").round(0).alias("est_adj_value").cast(pl.Int64),
                pl.col("non_sample_adjustment").round(0).alias("NSE").cast(pl.Int64),
                (
                    pl.col("recalc_estimate_value")
                    - pl.col("original_estimate_value")
                    - pl.col("sample_adjustment")
                    - pl.col("non_sample_adjustment")
                )
                    .round(0)
                    .cast(pl.Int64)
                    .alias("Sample Adj"),
                (pl.col("published_estimate_value") - pl.col("recalc_estimate_value"))
                    .round(0)
                    .cast(pl.Int64)
                    .alias("Ratio Adj"),
                est_adj_cmnt = pl.col.analyst_comment,
                closing = pl.col.estimate_type_code,
                rvalue = pl.col.published_estimate_value.cast(pl.Int64),            
                hitol = (pl.col.upper_tolerance * pl.col.published_estimate_value.shift(1)).cast(pl.Int64),
                lotol = (pl.col.lower_tolerance * pl.col.published_estimate_value.shift(1)).cast(pl.Int64),
            )
            .tail(27)
            .collect()
        )
        return series_hist_df

    series_history_df: pl.DataFrame = get_series_history(selected)

    # pl.Config.set_tbl_rows(-1)
    # pl.Config.set_tbl_cols(-1)
    # print(series_hist_df)

    aepy_value = (
        series_history_df
        .filter(pl.col.year == selected['p12m_y'], pl.col.month == selected['cm'])
        .item(0, 'rvalue')
    )
    # print(aepy_value)
    # TODO: ADD THIS IN TO PY SECTION

    print('serieshist', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
    def get_raw_estimate_data() -> pl.LazyFrame:
        oot_raw = (
            series_estimates_lf.join(
                series_estimates_lf.filter(pl.col("data_type_code") == "01").select(
                    [ "state_fips_code", "area_fips_code", "series_code", "year", "month",
                        "estimate_type_code", "upper_tolerance", "lower_tolerance", ]
                ),
                on=[ "state_fips_code", "area_fips_code", "series_code", "year", "month",
                    "estimate_type_code", ],
                how="left",
                suffix="_ae",
            )
            .with_columns(
                [
                    pl.when(pl.col("data_type_code") == "85")
                    .then(pl.col("upper_tolerance_ae"))
                    .otherwise(pl.col("upper_tolerance"))
                    .alias("upper_tolerance"),
                    pl.when(pl.col("data_type_code") == "85")
                    .then(pl.col("lower_tolerance_ae"))
                    .otherwise(pl.col("lower_tolerance"))
                    .alias("lower_tolerance"),
                    pl.col("sample_adjustment").round(0).alias("estimate_adjustment").cast(pl.Int64),
                    pl.col("non_sample_adjustment").round(0).alias("nse").cast(pl.Int64),
                    (
                        pl.col("recalc_estimate_value")
                        - pl.col("original_estimate_value")
                        - pl.col("sample_adjustment")
                        - pl.col("non_sample_adjustment")
                    )
                    .round(0)
                    .alias("sample_treatment").cast(pl.Int64),
                    (pl.col("published_estimate_value") - pl.col("recalc_estimate_value"))
                    .round(0)
                    .alias("ratio_adjustment").cast(pl.Int64),
                ]
            )
            .drop(["upper_tolerance_ae", "lower_tolerance_ae"])
        )
        return oot_raw

    raw_est_data: pl.LazyFrame = get_raw_estimate_data()

    # aarr: pl.DataFrame = raw_est_data.collect()
    # aarr.write_csv('worklib/aarr.csv')
    # print(aarr)

    # ── Get Estimate Info ────────────────────────────────────────────

    def get_estimate_info(thisclosing: str, raw_estimate_data: pl.LazyFrame) -> pl.DataFrame:
        oot = (
            raw_estimate_data.join(
                # NOTE: we cannot join on bmrk year because structure only has the current one
                # so if we want prior data for reest, that will filter out prior bmrk years
                structure
                .drop('year', 'estimation_type_code')
                # .rename({"year": "bmrk_year"})
                ,
                # on=[ "state_fips_code", "area_fips_code", "series_code", "bmrk_year", "data_type_code", ],
                on=[ "state_fips_code", "area_fips_code", "series_code", "data_type_code", ],
                how="inner",
                suffix="_struct",
            )
            .filter(
                (
                    (pl.col("year") == selected["cy"])
                    & (pl.col("month") == selected["cm"])
                    & (pl.col("estimate_type_code") == thisclosing)
                )
                | (
                    (pl.col("year") == selected["pm_y"])
                    & (pl.col("month") == selected["pm"])
                    & (pl.col("estimate_type_code") == selected["pm_closing"])
                )
                | (
                    (pl.col("year") == selected["p12m_y"])
                    & (pl.col("month") == selected["cm"])
                    & (pl.col("estimate_type_code") == selected["p12m_closing"])
                )
            )
            .sort(
                [ "state_fips_code", "area_fips_code", "series_code", "data_type_code", "year", "month", ]
            )
        )

        # oot_dist, otm_oty
        oot_dist = (
            pl.concat(
                [
                    oot.filter(
                        (pl.col("data_type_code") == "01")
                        & ~(
                            (pl.col("month") == selected["cm"])
                            & (pl.col("year") == selected["cy"])
                        )
                    ).with_columns(
                        [
                            pl.lit("85").alias("data_type_code"),
                            pl.lit(None)
                            .cast(pl.Float64)
                            .alias("original_estimate_value"),
                            pl.lit(None)
                            .cast(pl.Float64)
                            .alias("recalc_estimate_value"),
                        ]
                    ),
                    oot.with_columns(
                        [
                            pl.when(
                                (pl.col("month") == selected["cm"])
                                & (pl.col("year") == selected["cy"])
                            )
                            .then(pl.col("original_estimate_value"))
                            .otherwise(None)
                            .alias("original_estimate_value"),
                            pl.when(
                                (pl.col("month") == selected["cm"])
                                & (pl.col("year") == selected["cy"])
                            )
                            .then(pl.col("recalc_estimate_value"))
                            .otherwise(None)
                            .alias("recalc_estimate_value"),
                        ]
                    ),
                ],
                how="diagonal_relaxed",
            )
            .select(
                [ "state_fips_code", "area_fips_code", "series_code", "data_type_code", "year",
                    "month", "published_estimate_value", "original_estimate_value",
                    "recalc_estimate_value", 'series_type_code', 'estimation_type_code', 'birth_death_factor',
                    'sample_treatment', 'estimate_adjustment', 'nse', 'ratio_adjustment', 'ws_flag',]
            )
            .unique()
            .sort(
                [ "state_fips_code", "area_fips_code", "series_code", "data_type_code",
                    "year", "month", ]
            )
        )

        otm_oty = (
            oot_dist.with_columns(
                [
                    # pl.col("published_estimate_value")
                    # .shift(2)
                    # .over(
                    #     [ "state_fips_code", "area_fips_code", "series_code", "data_type_code", ]
                    # )
                    pl.lit(aepy_value).alias("py_pub"),
                    pl.col("published_estimate_value")
                    .shift(1)
                    .over(
                        [ "state_fips_code", "area_fips_code", "series_code", "data_type_code",
                        ]
                    )
                    .alias("pm_pub"),
                    pl.col("published_estimate_value").alias("cm_pub"),
                ]
            )
            .with_columns(
                [
                    (pl.col("cm_pub") - pl.col("py_pub")).alias("oty_change"),
                    (pl.col("cm_pub") - pl.col("pm_pub")).alias("otm_change"),
                    (pl.col("original_estimate_value") - pl.col("py_pub")).alias(
                        "orig_oty_change"
                    ),
                    (pl.col("original_estimate_value") - pl.col("pm_pub")).alias(
                        "orig_otm_change"
                    ),
                    (pl.col("recalc_estimate_value") - pl.col("py_pub")).alias(
                        "recalc_oty_change"
                    ),
                    (pl.col("recalc_estimate_value") - pl.col("pm_pub")).alias(
                        "recalc_otm_change"
                    ),
                ]
            )
            .filter(
                (pl.col("month") == selected["cm"]) & (pl.col("year") == selected["cy"])
            )
            .rename({"py_pub": "py", "pm_pub": "pm", "cm_pub": "cm"})
        )

        # aaotmoty = otm_oty.collect()
        # print(aaotmoty)

        # oot_otm
        estimate_info = (
            oot.sort(
                [ "state_fips_code", "area_fips_code", "series_code", "data_type_code", "year", "month", ]
            )
            .with_columns(
                pl.col("analyst_comment")
                .shift(1)
                .over(
                    [ "state_fips_code", "area_fips_code", "series_code", "data_type_code", ]
                )
                .alias("pm_comment")
            )
            .join(
                otm_oty.select(
                    [ "state_fips_code", "area_fips_code", "series_code", "data_type_code", "year",
                        "month", "py", "pm", "cm", "oty_change", "otm_change", "orig_otm_change",
                        "recalc_otm_change", "orig_oty_change", "recalc_oty_change", ]
                ),
                on=[ "state_fips_code", "area_fips_code", "series_code", "data_type_code", "year", "month",
                ],
                how="left",
            )
            .filter(
                (pl.col("month") == selected["cm"]) & (pl.col("year") == selected["cy"])
            )
            .with_columns(
                (pl.col("original_estimate_value") - pl.col("pm")).alias("orig_otmc")
            )
            .with_columns(
                [
                    pl.when(pl.col("data_type_code").is_in(["01", "85", "06"]))
                    .then(
                        ((pl.col("upper_tolerance") * pl.col("pm")) / 100).round(0)
                        * 100
                    )
                    .otherwise(pl.col("upper_tolerance") * pl.col("pm"))
                    .alias("hi_tolerance"),
                    pl.when(pl.col("data_type_code").is_in(["01", "85", "06"]))
                    .then(
                        ((pl.col("lower_tolerance") * pl.col("pm")) / 100).round(0)
                        * 100
                    )
                    .otherwise(pl.col("lower_tolerance") * pl.col("pm"))
                    .alias("lo_tolerance"),
                    pl.col("cm").alias("cm_tol"),
                ]
            )
            .with_columns(
                pl.when(pl.col("cm_tol") > pl.col("hi_tolerance"))
                .then(pl.lit("H"))
                .when(pl.col("cm_tol") < pl.col("lo_tolerance"))
                .then(pl.lit("L"))
                .otherwise(pl.lit(""))
                .alias("oot")
            )
            .collect()
        )

        print('estimate_info', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
        return estimate_info

    def create_est_comparison(
        my_closing_arg: str, estrow: pl.DataFrame
    ) -> pl.DataFrame:
        # print('--estrow-- ', estrow)
        thisestrow = estrow.filter(
            pl.col.state_fips_code == selected["state"],
            pl.col.area_fips_code == selected["area"],
            pl.col.series_code == selected["series"],
            pl.col.data_type_code == selected['datatype'],
            pl.col.year == selected["cy"],
            pl.col.month == selected["cm"],
            pl.col.estimate_type_code == my_closing_arg,
        )
        # print('thisestrow-- ', thisestrow)
        estimate_comparison = (
            thisestrow.select(
                [
                    # Add 'pm' to the selection so we can use it for calculations
                    pl.col("pm"),
                    # Map to: pub_[metric]
                    pl.col("published_estimate_value").alias("pub_est"),
                    pl.col("otm_change").alias("pub_otm"),
                    pl.col("oty_change").alias("pub_oty"),
                    # Map to: recalc_[metric]
                    pl.col("recalc_estimate_value").alias("recalc_est"),
                    pl.col("recalc_otm_change").alias("recalc_otm"),
                    pl.col("recalc_oty_change").alias("recalc_oty"),
                    # Map to: orig_[metric]
                    pl.col("original_estimate_value").alias("orig_est"),
                    pl.col("orig_otm_change").alias("orig_otm"),
                    pl.col("orig_oty_change").alias("orig_oty"),
                ]
            )
            .with_columns(cs.float().cast(pl.Int64))
            # Turn all metrics into rows, keeping 'pm' attached to each row
            .unpivot(index="pm", variable_name="raw", value_name="value")
            # Split the "prefix_metric" into distinct tracking columns
            .with_columns(
                [
                    pl.col("raw").str.split("_").list.get(0).alias("version"),
                    pl.col("raw")
                    .str.replace(r"^(pub|recalc|orig)_", "")
                    .alias("metric"),
                ]
            )
            # Pivot metrics into headings, keeping version and pm as indexes
            .pivot(
                on="metric",
                index=["version", "pm"],
                values="value",
                aggregate_function="first",
            )
            # Calculate the percentage changes using the formula: change / pm
            .with_columns(
                [
                    # ((pl.col("otm") / pl.col("pm")) * 100).round(1).alias("otm_pct"),
                    # ((pl.col("oty") / pl.col("pm")) * 100).round(1).alias("oty_pct"),
                    (pl.col("otm") / pl.col("pm")).alias("otm_pct"),
                    (pl.col("oty") / pl.col("pm")).alias("oty_pct"),
                ]
            )
            # Finalize table structure and drop 'pm' from the final output view
            .select(
                [
                    'version',
                    "est",
                    pl.when(pl.col.version == "pub")
                    .then(pl.col.pm)
                    .otherwise(pl.lit(""))
                    .alias("pm"),
                    "otm",
                    "oty",
                    "otm_pct",
                    "oty_pct",
                ]
            )
            # Order rows exactly: pub, recalc, orig
            # .with_columns(pl.col("version").cast(pl.Enum(["pub", "recalc", "orig"])))
            # .sort("version")
        )

        # print('estrowSDFSAKFJHSKJHDF', estrow)

        tolerances = (
            thisestrow
            .select(
                pl.col.hi_tolerance.cast(pl.Int64).alias("hi-tol"),
                pl.col.lo_tolerance.cast(pl.Int64).alias("lo-tol"),
            )
            .unpivot(variable_name="version", value_name="est")
            .unique() # TODO: figure out why in need unique here
        )

        # print('tolerancessfkuhsafjhkserthklukjzth,j', tolerances)

        if selected['closing'] != my_closing_arg:
            estimate_comparison = (
                estimate_comparison
                .with_columns(
                    pl.concat_str(pl.lit('p-'), pl.col.version).alias('version'),
                )
            )
        else:
            estimate_comparison = (
                pl.concat([estimate_comparison, tolerances], how="diagonal")
            )
        finalec = (
            estimate_comparison
            .with_columns(
                pl.col("version").cast(
                    pl.Enum(["pub", "hi-tol", "lo-tol", "recalc", "orig", 'p-pub', 'p-recalc', 'p-orig'])
                )
            )
            .sort("version")
             .fill_null(pl.lit(""))
        )
        return finalec

    # if we are in prelims, closing = 1 and prior_closing = None
    # in finals, closing = 2 and prior_closing = 1
    # in reest, closing = 3 and prior_closing = 3
    this_closing_series_info_row: pl.DataFrame = get_estimate_info(
        selected["closing"], raw_est_data
    )  # keep this expanded so it matches the others after formatting
    this_closing_est_compare: pl.DataFrame = create_est_comparison(
        selected["closing"], this_closing_series_info_row
    )
    if selected["prior_closing"]:
        prior_closing_series_info_row: pl.DataFrame = get_estimate_info(
            selected["prior_closing"], raw_est_data
        )
        prior_closing_est_compare: pl.DataFrame = create_est_comparison(
            selected["prior_closing"], prior_closing_series_info_row
        )
        series_info_df = pl.concat([this_closing_series_info_row, prior_closing_series_info_row])
        est_compare_df = pl.concat([this_closing_est_compare, prior_closing_est_compare])
    else:
        series_info_df = this_closing_series_info_row.clone()
        est_compare_df = this_closing_est_compare.clone()




   # ***********************************************************************************************************************
   # ***********************************************************************************************************************
   #                                        MATCHED SAMPLE DATA
   # ***********************************************************************************************************************
   # ***********************************************************************************************************************


    def get_weighted_sample_data(selected, bmrkyr) -> pl.LazyFrame:
        archive_filename = "matched_sample_archive_" + bmrkyr + '.pq'
        # Combine them into a full path
        pqfile = aceslib_path / archive_filename

        # Verify if the file exists and is not a folder
        if pqfile.is_file():
            ms_path = pqfile
        else:
            ms_path = aceslib_path / "matched_sample_current.pq"

        matched_sample_lf = pl.scan_parquet(ms_path)

        if selected['month'] in ['10','11','12'] and selected['closing'] == '3':
            archive_filename = "matched_sample_archive_" + str(int(bmrkyr)-1) + '.pq'
            matched_sample_lf = (
                pl.concat([
                    pl.scan_parquet(aceslib_path / archive_filename),
                    matched_sample_lf
                ])
            )

        weighted = add_sample_weights(
            matched_sample_lf
            .filter(
                pl.col("state_fips_code") == selected["state"],
                pl.col("area_fips_code") == selected["area"],
                pl.col("series_code") == selected["series"],
                pl.col('data_type_code') == selected['datatype'],
                # pl.col("year") == selected["cy"],
                # pl.col("month") == selected["cm"],
                # pl.col("estimate_type_code") == selected["closing"],
            )
        )
        return weighted
    
    weighted_sample_state_area_series_dt: pl.LazyFrame = get_weighted_sample_data(selected, bmrkyr)

    weighted_cm = (
        weighted_sample_state_area_series_dt
        .filter(
            (pl.col("year") == selected["cy"])
            & (pl.col("month") == selected["cm"])
            & (pl.col("estimate_type_code") == selected['closing'])
        )
    )

    def get_sample_summary(selected, weighted_cm: pl.LazyFrame) -> pl.DataFrame:
        flagsum = (
            weighted_cm
            .group_by(["a_typ_flag"])
            .agg(
                [
                    pl.col("report_id").n_unique().alias("rep_count").cast(pl.Int64),
                    pl.col("selected_ui_number").n_unique().alias("ui_count").cast(pl.Int64),
                    pl.col("pm_value").sum().alias("pm_emp").cast(pl.Float64),
                    pl.col("cm_value").sum().alias("cm_emp").cast(pl.Float64),
                    pl.col("wpm").sum().round(0).cast(pl.Float64).alias("pm_weighted_emp"),
                    pl.col("wcm").sum().round(0).cast(pl.Float64).alias("cm_weighted_emp"),
                ]
            )
            .with_columns(unwotm=pl.col.cm_emp.cast(pl.Int64) - pl.col.pm_emp.cast(pl.Int64))
            .with_columns(
                pl.when(pl.col("a_typ_flag").is_in(['U','X']))
                .then(pl.lit(0))
                .otherwise(pl.col("unwotm"))
                .alias("unwotm")
            )
            .collect()
        )
        print('flagsum', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
        signsum = (
            weighted_cm
            .filter(pl.col("a_typ_flag").is_in(["A", "T"]))
            .with_columns(
                (pl.col.cm_value.cast(pl.Int64) - pl.col.pm_value.cast(pl.Int64))
                .cast(pl.Int64)
                .alias("unwotm")
            )
            .with_columns(
                pl.when(pl.col.unwotm > 0)
                .then(pl.lit("Inc"))
                .when(pl.col.unwotm < 0)
                .then(pl.lit("Dec"))
                .otherwise(pl.lit("Const"))
                .alias("a_typ_flag")
            )
            .group_by(["a_typ_flag"])
            .agg(
                [
                    pl.col("report_id").n_unique().alias("rep_count").cast(pl.Int64),
                    pl.col("selected_ui_number")
                    .n_unique()
                    .alias("ui_count")
                    .cast(pl.Int64),
                    pl.col("pm_value").sum().alias("pm_emp").cast(pl.Float64),
                    pl.col("cm_value").sum().alias("cm_emp").cast(pl.Float64),
                    pl.col("wpm").sum().round(0).cast(pl.Float64).alias("pm_weighted_emp"),
                    pl.col("wcm").sum().round(0).cast(pl.Float64).alias("cm_weighted_emp"),
                ]
            )
            .with_columns(
                unwotm=pl.col.cm_emp.cast(pl.Int64)
                - pl.col.pm_emp.cast(pl.Int64).cast(pl.Int64)
            )
            # .with_columns(pl.lit(0).alias("unwotm").cast(pl.Int64))
            .collect()
        )
        print('signsum', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
        # print('signsum', signsum)

        flagsumtotal = (
            flagsum.filter(pl.col("a_typ_flag").is_in(["A", "T"]))
            # Perform the sum directly inside the select using selectors
            .select(pl.lit("Sum").alias("a_typ_flag"), cs.numeric().sum())
        )

        pmest = int(this_closing_est_compare.item(0, 'pm'))
        pubest = int(this_closing_est_compare.item(0, 'est'))

        # print(type(pmest))
        samplecoverage = (
            flagsumtotal
            # .with_columns(
            #     pl.lit(None)
            # )
            .with_columns(
                pl.lit('Coverage').alias('a_typ_flag'),
                pl.lit(0).alias("rep_count").cast(pl.Int64),
                pl.lit(0).alias("ui_count").cast(pl.Int64),
                (pl.col.pm_emp / pl.lit(pmest)).alias('pm_emp'),
                (pl.col.cm_emp / pl.lit(pubest)).alias('cm_emp'),
                (pl.col.pm_weighted_emp / pl.lit(pmest)).alias('pm_weighted_emp'),
                (pl.col.cm_weighted_emp / pl.lit(pubest)).alias('cm_weighted_emp'),
                pl.lit(0).alias('unwotm').cast(pl.Int64),
            )
        )
        
        pmcoverage = (
            weighted_sample_state_area_series_dt
            .filter(
                (pl.col("year") == selected["pm_y"])
                & (pl.col("month") == selected["pm"])
                & (pl.col("estimate_type_code") == selected["pm_closing"])
            )
            .select(
                pl.col("pm_value").sum().alias("pm_emp").cast(pl.Float64),
                pl.col("cm_value").sum().alias("cm_emp").cast(pl.Float64),
                pl.col("wpm").sum().round(0).cast(pl.Float64).alias("pm_weighted_emp"),
                pl.col("wcm").sum().round(0).cast(pl.Float64).alias("cm_weighted_emp"),
            )
            .select(
                pl.lit('Pm-Covg').alias('a_typ_flag'),
                pl.lit(0).alias("rep_count").cast(pl.Int64),
                pl.lit(0).alias("ui_count").cast(pl.Int64),
                (pl.col.pm_emp / pl.lit(pmest)).alias('pm_emp'), # TODO: UPDATE TO CHANGE PMEST TO PPMEST, but we do not have it yet
                (pl.col.cm_emp / pl.lit(pmest)).alias('cm_emp'),
                (pl.col.pm_weighted_emp / pl.lit(pmest)).alias('pm_weighted_emp'),
                (pl.col.cm_weighted_emp / pl.lit(pubest)).alias('cm_weighted_emp'),
                pl.lit(0).alias('unwotm').cast(pl.Int64),
            )
            .collect()
        )
        print('pmcovg', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")

        corder = ["T", "A", "Sum", 'Coverage', 'Pm-Covg', "Inc", "Dec", "Const", "U", "X"]

        sample_summary_final = (
            pl.concat([flagsum, flagsumtotal, samplecoverage, pmcoverage, signsum])
            .with_columns(pl.col("a_typ_flag").cast(pl.Enum(corder)))
            .sort("a_typ_flag")
            .select(
                [
                    pl.col("a_typ_flag").alias("Sample"),
                    pl.col("rep_count").alias("report"),
                    pl.col("ui_count").alias("ui"),
                    pl.col("pm_emp").alias("pm"),
                    pl.col("cm_emp").alias("cm"),
                    pl.col("unwotm").alias("otm"),
                    pl.col("pm_weighted_emp").alias("wpm"),
                    pl.col("cm_weighted_emp").alias("wcm"),
                ]
            )
        )
        return sample_summary_final
    
    sample_summary_df: pl.DataFrame = get_sample_summary(selected, weighted_cm)

    print('samplesummary', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")

    matched_sample_rename = {
        "state_fips_code": "state", "area_fips_code": "area", "series_code": "series", "year": "year",
        "month": "month", "data_type_code": "dtc", "estimate_type_code": "closing", "report_id": "rept",
        "rept_sfc": "reptstate", "sample_weight": "weight", "report_with": "reptw",
        "naics_code": "naics", "ownership_code": "own", "county_fips_code": "county", "pm_value": "pm",
        "cm_value": "cm", "a_typ_flag": "flag", "diff_resp_rate": "drr", "cont_tot_dwnwght": "dwght",
        "pm_comment_1": "pmcc1", "pm_comment_2": "pmcc2", "cm_comment_1": "cmcc1",
        "cm_comment_2": "cmcc2", "ui_number": "uinum", "selection_size": "selsize",
        "selected_ui_number": "ui", "series_type_code": "stc", "bmrk_year": "bmrkyr",
        "original_a_typ_flag": "origflag", "original_cont_tot_dwnwght": "origdwght",
        "treated_by": "treatedby", "reason_code": "reasoncode", "start_period": "startperiod",
        "deeps_flag": "deepsflag", "state_flag": "stateflag",
    }


    sample_detail_vars = [
        'reptstate', 'ui', 'reptw', 'report', 'naics', 
        'selsize', 'pm_size', 'cm_size',
        'szgap',
        'weight', 'pm_dwght', 
        'origdwght', 'dwght', 'drr', 'pm', 'cm', 'pm_flag', 'prior_flag', 
        'origflag', 'flag', 'pmcc', 'cmcc', 'otm', 'wotm', 'wpm', 'wcm',
    ]
    prior_flag = ['prior_flag'] # used as part of a smaller list separate from sample_detail_vars

    if selected['closing'] == '1':
        prior_flag = []
        if 'prior_flag' in sample_detail_vars:
            sample_detail_vars.remove('prior_flag')



    size_class = pl.LazyFrame({
        "size": [1, 2, 3, 4, 5, 6, 7, 8],
        "min":  [0, 10, 20, 50, 100, 250, 500, 1000],
        "max":  [9, 19, 49, 99, 249, 499, 999, 999999999999],
    })
    # TODO: REPORT 01-0355076 HAD ITS WEIGHT UPDATED BUT NOT ITS SELECTED_SIZE CLASS, SO THAT VARIABLE IS NOT THAT RELIABLE

    sample_detail_by_report_lf = (
        weighted_cm
        .rename(matched_sample_rename)
        .select(
            pl.col.reptstate,
            pl.col.ui,
            pl.col.reptw,
            pl.concat_str(pl.col.reptstate, pl.col.rept).alias("report"),
            pl.col.naics,
            pl.col.selsize,
            pl.col.weight,
            pl.col.origdwght.cast(pl.Float64).round(2).alias("origdwght"),
            pl.col.dwght.cast(pl.Float64).round(2),
            pl.col.drr,
            pl.col.pm,
            pl.col.cm,
            pl.col.origflag,
            pl.col.flag,
            # Optimized pmcc without list engine overhead
            # pl.when(pl.col("pmcc1") == pl.col("pmcc2")).then(pl.col("pmcc1").fill_null(""))
            # .when(pl.col("pmcc1").is_null()).then(pl.col("pmcc2").fill_null(""))
            # .when(pl.col("pmcc2").is_null()).then(pl.col("pmcc1").fill_null(""))
            # .otherwise(pl.concat_str("pmcc1", pl.col("pmcc2"), separator=","))
            # .alias("pmcc"),
            # # Optimized cmcc without list engine overhead
            # pl.when(pl.col("cmcc1") == pl.col("cmcc2")).then(pl.col("cmcc1").fill_null(""))
            # .when(pl.col("cmcc1").is_null()).then(pl.col("cmcc2").fill_null(""))
            # .when(pl.col("cmcc2").is_null()).then(pl.col("cmcc1").fill_null(""))
            # .otherwise(pl.concat_str("cmcc1", pl.col("cmcc2"), separator=","))
            # .alias("cmcc"),
            pl.concat_list("pmcc1", "pmcc2")
            .list.unique()
            .list.drop_nulls()
            .list.join(",")
            .alias("pmcc"),
            pl.concat_list("cmcc1", "cmcc2")
            .list.unique()
            .list.drop_nulls()
            .list.join(",")
            .alias("cmcc"),
            (pl.col.cm.cast(pl.Int64) - pl.col.pm.cast(pl.Int64)).alias('otm').cast(pl.Int64),
            pl.col.wotm,
            (pl.col.wgt * pl.col.pm).round().alias("wpm"),
            (pl.col.wgt * pl.col.cm).round().alias("wcm"),
            (pl.col("cmcc1") == "93").alias("_is_knr").fill_null(False),
        )
        .join(
            weighted_sample_state_area_series_dt
            .filter(
                (pl.col("year") == selected["pm_y"]),
                (pl.col("month") == selected["pm"]),
                (pl.col("estimate_type_code") == selected["pm_closing"])
            )
            .rename(matched_sample_rename)
            .select(
                pl.col.reptstate,
                pl.col.ui,
                pl.col.reptw,
                pl.concat_str(pl.col.reptstate, pl.col.rept).alias("report"),
                pl.col.dwght.cast(pl.Float64).round(2).alias('pm_dwght'),
                pl.col.flag.alias('pm_flag'),
            ),
            on=['reptstate', 'ui', 'reptw', 'report'],
            how='left'
        )
        .join(
            weighted_sample_state_area_series_dt
            .filter(
                (pl.col("year") == selected["cy"]),
                (pl.col("month") == selected["cm"]),
                (pl.col("estimate_type_code") == selected["prior_closing"])
            )
            .rename(matched_sample_rename)
            .select(
                pl.col.reptstate,
                pl.col.ui,
                pl.col.reptw,
                pl.concat_str(pl.col.reptstate, pl.col.rept).alias("report"),
                # pl.col.dwght.cast(pl.Float64).round(2).alias('prior_dwght'),
                pl.col.flag.alias('prior_flag'),
            ),
            on=['reptstate', 'ui', 'reptw', 'report'],
            how='left'
        )
        .join_where(
            size_class.rename({'size':'pm_size'}),
            pl.col.pm >= pl.col.min,
            pl.col.pm <= pl.col.max,
        )
        .drop(['min', 'max'])
        .join_where(
            size_class.rename({'size':'cm_size'}),
            pl.col.cm >= pl.col.min,
            pl.col.cm <= pl.col.max,
        )
        .drop(['min', 'max'])
        .with_columns(
            szgap = (pl.max_horizontal('cm_size', 'pm_size') - pl.col.selsize.cast(pl.Int64)).cast(pl.Int64).clip(lower_bound=0)
        )
        .select(sample_detail_vars + ['_is_knr'])
        .with_columns(
            # szgap = pl.when(pl.col.szgap > 0).then(pl.col.szgap).otherwise(pl.lit(0)),
            _row_type = pl.lit('detail'),
            _history_url = pl.format(
                "/sample-history?reptstate={}&ui={}&report={}&flag={}&knr={}&row_type=detail",
                pl.col.reptstate.fill_null(""),
                pl.col("ui").fill_null(""),
                pl.col("report").fill_null(""),
                pl.col("flag").fill_null(""),
                pl.when(pl.col("_is_knr")).then(pl.lit("Y")).otherwise(pl.lit("")),
            ),
            _ui_url = pl.format(
                aces_uirundisplay + "?q={};{};00000;9999;",
                pl.col.reptstate.fill_null(''),
                pl.col.ui.fill_null(''),
            ),
            _report_url = pl.format(
                aces_registrydisplay + '?q={};{}',
                pl.col.reptstate.fill_null(''),
                pl.col.report.str.slice(2).fill_null(''),
            ),
            _abs_wotm = pl.col.wotm.abs(),
        )
        .sort(
            ['flag', "_abs_wotm", "reptstate", "ui", 'report'], descending=[False, True, False, False, False]
        )
    )

    # print('copythese', list(sample_detail_by_report_lf.columns))



    def firstornothing(listcols, nothingvalue=None):
        return [
            (
                pl.when(pl.col(col).n_unique() == 1)
                .then(pl.col(col).first())
                .otherwise(pl.lit(nothingvalue))
            ).alias(col)
            for col in listcols
        ]

    def sharednaics(naicsstruct):
        minnaics, maxnaics = naicsstruct["naics_min"], naicsstruct["naics_max"]
        if not minnaics or not maxnaics:
            return ""
        common = []
        for dig1, dig2 in zip(minnaics, maxnaics):
            if dig1 == dig2:
                common.append(dig1)
            else:
                break
        return "".join(common)
    
    sample_detail_by_ui_lf = (
        sample_detail_by_report_lf
        # .with_columns(
        #     pl.col("cmcc").str.contains("93", literal=True).alias("knr")
        # ) # already defined above
        .group_by(pl.col("reptstate"), pl.col("ui"), pl.col("flag"), pl.col("_is_knr"))
        .agg(
            pl.len().alias("_detail_count"),
            # [pl.col(col).sum().alias(col)
            #     for col in ['pm', 'cm', 'wpm', 'wcm', 'wotm']],
            pl.col("pm", "cm", "wpm", "wcm", 'otm', "wotm").sum(),
            pl.col("pmcc")
                .filter(pl.col("pmcc").is_not_null() & (pl.col("pmcc") != ""))
                .unique()
                .implode()
                .list.join(",")
                .str.split(",")
                .list.unique()
                .list.join(",")
                .alias("pmcc"),
            pl.col("cmcc")
                .filter(pl.col("cmcc").is_not_null() & (pl.col("cmcc") != ""))
                .unique()
                .implode()
                .list.join(",")
                .str.split(",")
                .list.unique()
                .list.join(",")
                .alias("cmcc"),
            # pl.col("pmcc").implode().list.join(",").alias("pmcc"),
            # pl.col("cmcc").implode().list.join(",").alias("cmcc"),
            # for col in ['pmcc', 'cmcc']],
            *firstornothing(
                ["report", "reptw", "pm_flag", "origflag"] + prior_flag,
                nothingvalue="",
            ),
            *firstornothing(
                ['selsize', "weight", "pm_dwght", "origdwght", "dwght", "drr"], nothingvalue=None
            ),
            # pl.struct(
            pl.col("naics").min().alias("naics_min"),
            pl.col("naics").max().alias("naics_max"),
            # ).map_elements(sharednaics, return_dtype=pl.String).alias('naics')
        )
        .join_where(
            size_class.rename({'size':'pm_size'}),
            pl.col.pm >= pl.col.min,
            pl.col.pm <= pl.col.max,
        )
        .drop(['min', 'max'])
        .join_where(
            size_class.rename({'size':'cm_size'}),
            pl.col.cm >= pl.col.min,
            pl.col.cm <= pl.col.max,
        )
        .drop(['min', 'max'])
        .with_columns(
            szgap = (pl.max_horizontal('cm_size', 'pm_size') - pl.col.selsize.cast(pl.Int64)).cast(pl.Int64).clip(lower_bound=0)
            # szgap = pl.max_horizontal('cm_size', 'pm_size') - pl.col.selsize.cast(pl.Int64),
        )
        .with_columns(
            pl.struct("naics_min","naics_max",)
                .map_elements(sharednaics, return_dtype=pl.String)
                .alias("naics"),
            pl.when(pl.col("_detail_count") == pl.lit(1))
                .then(pl.col("report"))
                .otherwise(pl.col("reptw"))
                .alias("report"),
            (pl.col._detail_count > 1).alias("_is_summed"),
            pl.when(pl.col._detail_count > 1)
                .then(pl.lit("summary"))
                .otherwise(pl.lit("single"))
                .alias("_row_type"),
        )
        .with_columns(
            _history_url = pl.format(
                "/sample-history?reptstate={}&ui={}&report={}&flag={}&knr={}&row_type={}",
                pl.col.reptstate.fill_null(""),
                pl.col("ui").fill_null(""),
                pl.col("report").fill_null(""),
                pl.col("flag").fill_null(""),
                pl.when(pl.col("_is_knr")).then(pl.lit("Y")).otherwise(pl.lit("")),
                pl.col._row_type
            ),
            _ui_url = pl.format(
                "https://aa135.com?q={};{};00000;9999;",
                pl.col.reptstate,
                pl.col.ui,
            ),
            _report_url = pl.format(
                'https://aa468.com?q={};{}',
                pl.col.reptstate,
                pl.col.report.str.slice(2)
            ),
            _abs_wotm = pl.col.wotm.abs(),
            _total_rows = pl.len()
        )
        .sort(
            ['flag', "_abs_wotm", "reptstate", "ui", 'report'], 
              descending=[False, True, False, False, False]
        )
        .select(sample_detail_vars + 
                ['_detail_count', '_is_knr', '_is_summed', '_row_type', '_history_url',
                 '_ui_url', '_report_url', '_total_rows'])
        .with_row_index()  # row index will be called 'index'
        .filter((pl.col.flag == 'X') | (pl.col.flag != pl.col.origflag) | (pl.col.index <= 30))
        # .head(30)
        .drop('index')
    )
    '''
    a1vars = [
        'reptstate', 'ui', 'reptw', 'report', 'naics', 
        'weight', 'pm_dwght',
        'origdwght', 'dwght', 'drr', 'pm', 'cm', 
        'origflag', 'flag', 'pmcc', 'cmcc', 'otm', 'wotm', 'wpm', 'wcm',
    ]
    sample_detail_by_ui_lf = (
        sample_detail_by_report_lf
        .group_by(pl.col("reptstate"), pl.col("ui"), pl.col("flag"), pl.col("_is_knr"))
        .agg(
            pl.len().alias("_detail_count"),
            # [pl.col(col).sum().alias(col)
            #     for col in ['pm', 'cm', 'wpm', 'wcm', 'wotm']],
            pl.col("pm", "cm", "wpm", "wcm", 'otm', "wotm").sum(),
            pl.col("pmcc", "cmcc", "report", "reptw", "pm_flag", "origflag",
                'selsize', "weight", "pm_dwght", "origdwght", "dwght", "drr", "naics").first()
        )
        .select(a1vars)
        .head(30)
    )
    sample_detail_by_ui_df: pl.DataFrame = sample_detail_by_ui_lf.collect()
    '''
    sample_detail_by_ui_df: pl.DataFrame = sample_detail_by_ui_lf.drop('selsize', 'pm_size', 'cm_size',).collect()

    print('ui', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
    # with pl.Config(tbl_cols=-1):
    #     print('BY UI THIS IS THE ONE::  ' , sample_detail_by_ui_lf)


    sample_history_vars = [
        'year', 'month',
        'reptstate', 'ui', 'reptw', 'report', 'naics', 'version', 
        'selsize', 
        'weight', 
        'origdwght', 'dwght', 'drr', 'pm', 'cm',
        'origflag', 'flag', 'cmcc', 'otm', 'wotm', 'wpm', 'wcm',
        '_is_knr'
    ]

    sample_history_lf = (
        weighted_sample_state_area_series_dt
        .filter(
            pl.col.estimate_type_code.is_in(['1','2','3']),
            pl.col.estimate_type_code == pl.col.estimate_type_code.max().over(['year', 'month']),
        )
        .rename(matched_sample_rename)
        .with_columns(
            pl.concat_str(pl.col.reptstate, pl.col.rept).alias("report"),
            pl.concat_list("cmcc1", "cmcc2")
            .list.drop_nulls()
            .list.join(",")
            .alias("cmcc"),
            (pl.col.cm.cast(pl.Int64) - pl.col.pm.cast(pl.Int64)).alias('otm').cast(pl.Int64),
            pl.col.wotm,
            (pl.col.wgt * pl.col.pm).round().alias("wpm"),
            (pl.col.wgt * pl.col.cm).round().alias("wcm"),
            (pl.col("cmcc1") == "93").alias("_is_knr").fill_null(False),
        )
        .select(sample_history_vars)
        .join(
            (sample_detail_by_report_lf
             .select(
                'report', 
                pl.col._is_knr.alias('_cm_knr'),
                pl.col.flag.alias('_cm_flag')
             )
            ),
            on='report',
            how='inner'
        )
    )

    # ***********************************************************************************************************************
    # ***********************************************************************************************************************
    #                                        MODEL INFO
    # ***********************************************************************************************************************
    # ***********************************************************************************************************************

    # Get basic data about this series
    this_area = str(selected['area'])
    this_series = str(selected['series'])
    this_own = this_series[3] if this_series[0]=='9' else '5'
    this_estimator = this_closing_series_info_row.item(0, 'estimation_type_code')
    this_comment = str(this_closing_series_info_row.item(0, 'analyst_comment'))
    pmval = this_closing_series_info_row.item(0, 'pm')

    def get_model_info(selected) -> pl.DataFrame:
        modelinfo = pl.DataFrame(schema={'x': pl.Int64})

        # print('tcsir', this_closing_series_info_row)
        # print(' *ntc* ', this_closing_series_info_row.item(0, 'estimation_type_code'))
        if this_estimator in ['S','Q']:

            # Get whether the estimate was adjusted to Y1 or Y2 (government)
            if this_estimator == 'S':
                is_on_y1 = 'Adjusted to Y1 link'.lower().replace(" ","") in \
                    this_comment.lower().replace(" ","")
            elif this_estimator == 'Q':
                is_on_y1 = 'y2' not in this_comment.lower()
            else:
                is_on_y1 = False

            # If non-government msa series, then include y4
            if this_own=='5' and this_area != '00000':
                sdmvarlist = ["weight_y1", "weight_y2", 'weight_y4', "link_y1", "link_y2", 'link_y4']
            else:
                sdmvarlist = ["weight_y1", "weight_y2", "link_y1", "link_y2"]
            
            # Use archive file if we are looking at a prior benchmark year
            archive_filename = "estimates_archive_" + bmrkyr + '.pq'
            pqfile = aceslib_path / archive_filename
            if pqfile.is_file():
                sdmfile = 'small_domain_model_archive.pq'
            else:
                sdmfile = 'small_domain_model_current.pq'
            sdm_df = pl.scan_parquet(aceslib_path / sdmfile)

            sdm_model_table0 = (
                sdm_df.filter(
                    pl.col("state_fips_code") == selected["state"],
                    pl.col("area_fips_code") == selected["area"],
                    pl.col("series_code") == selected["series"],
                    pl.col("year") == selected["cy"],
                    pl.col("month") == selected["cm"],
                    pl.col("estimate_type_code") == selected["closing"],
                    # pl.col("data_type_code") == selected["datatype"],
                    pl.col("data_type_code") == '01',
                )
                .collect()
            )
            print('sdm_model_table0', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
            

            # print('pmval', pmval)
            modelinfo = (
                sdm_model_table0
                .with_columns(
                    pl.when(this_own=='5').then('weight_y1')
                    .when(is_on_y1).then(1)
                    .otherwise(0).alias('weight_y1'),
                    pl.when(this_own=='5').then('weight_y2')
                    .when(is_on_y1).then(0)
                    .otherwise(1).alias('weight_y2'),
                )
                .unpivot(
                    on=sdmvarlist, #variables that will be pivoted. all others dropped
                    variable_name="temp_col", # holds the column names from before unpivot
                    value_name="val", # holds all the values
                )
                .with_columns(
                    [
                        pl.col("temp_col").str.head(-3).alias("prefix"),
                        pl.col("temp_col").str.tail(2).alias("estimator"),
                    ]
                )
                .pivot(
                    on="prefix", # this is going to be the column headings
                    index="estimator", # this is going to be the row headings (1st column)
                    values="val" # this is all the values
                )
                .with_columns(
                    estimate = (pl.col.link * pmval).cast(pl.Int64),
                    otm = ((pl.col.link * pmval)-pmval).cast(pl.Int64),
                )           
            )
            print('modelinfo', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")

        # selected small domain model current variables aces.Small_domain_model_current (weight_y1 is always zero) - not used in comet at all:
        """
        state_fips_code area_fips_code series_code year month estimate_type_code bmrk_yr bmrk_qtr weight_y1 weight_y2 link_y2 link_y1 bdf_y1 data_type_code
        """

        # print(' *ntc* ', this_closing_series_info_row.item(0, 'estimation_type_code'))
        if this_estimator in ['G']:
            
            archive_filename = "estimates_archive_" + bmrkyr + '.pq'
            # Combine them into a full path
            pqfile = aceslib_path / archive_filename
            # Verify if the file exists and is not a folder
            if pqfile.is_file():
                g3file = 'sam3_y1_archive.pq'
            else:
                g3file = 'sam3_y1_current.pq'
            g3_df = pl.scan_parquet(aceslib_path / g3file)

            # print('selected', selected)
            g3_model_table0 = (
                g3_df.filter(
                    pl.col("state_fips_code") == selected["state"],
                    pl.col("area_fips_code") == selected["area"],
                    pl.col("series_code") == selected["series"],
                    pl.col("year") == selected["cy"],
                    pl.col("month") == selected["cm"],
                    pl.col("estimate_type_code") == selected["closing"],
                    pl.col("data_type_code") == selected["datatype"],
                )
                .select(
                    pl.col.beta,
                    pl.col.y2_m,
                    pl.col.pm_est,
                    pl.col.y1.alias('y1_link'),
                    pl.col.y1_st_adj.alias('y1_st_adj_link'),
                    pl.col.syn.alias('syn_link'),
                    pl.col.y_hat.alias('gen3_link'),
                    (pl.col.y1 * pl.col.pm_est).round().alias('y1_est'),
                    (pl.col.y1_st_adj * pl.col.pm_est).round().alias('y1_st_adj_est'),
                    (pl.col.syn * pl.col.pm_est).round().alias('syn_est'),
                    (pl.col.y_hat * pl.col.pm_est).round().alias('gen3_est'),
                    pl.col.orig_w1.alias('y1_weight'),
                    pl.col.orig_w2.alias('y1_st_adj_weight'),
                    pl.col.orig_w3.alias('syn_weight'),
                    pl.lit(1).alias('gen3_weight'),
                )
                .with_columns(
                    (pl.col.y1_est - pl.col.pm_est).alias('y1_otm'),
                    (pl.col.y1_st_adj_est - pl.col.pm_est).alias('y1_st_adj_otm'),
                    (pl.col.syn_est - pl.col.pm_est).alias('syn_otm'),
                    (pl.col.gen3_est - pl.col.pm_est).alias('gen3_otm'),
                )
                .collect()
            )
            # print(g3_model_table0)
            print('g3model', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
            modelinfo = (
                g3_model_table0
                .unpivot(
                    index=['beta', 'y2_m'],
                    on=['y1_link', 'y1_st_adj_link', 'syn_link', 'gen3_link',
                        'y1_est', 'y1_st_adj_est', 'syn_est', 'gen3_est', 
                        'y1_otm', 'y1_st_adj_otm', 'syn_otm', 'gen3_otm', 
                        'y1_weight', 'y1_st_adj_weight', 'syn_weight', 'gen3_weight',], #variables that will be pivoted. all others dropped
                    variable_name="temp_col", # holds the column names from before unpivot
                    value_name="val", # holds all the values
                )
                .with_columns(
                    # [
                        model = pl.col("temp_col").str.replace_all(r"_[^_]*$", ""),
                        prefix = pl.col("temp_col").str.replace_all(r"^.*_", ""),
                        # pl.col("temp_col").str.head(-3).alias("prefix"),
                        # pl.col("temp_col").str.tail(2).alias("suffix"),
                    # ]
                )
                .pivot(
                    on="prefix",  # this is going to be the column headings
                    index=['beta', 'y2_m', "model"],  # this is going to be the row headings (1st column)
                    values="val",  # this is all the values
                ).select(
                    pl.col.model.replace({'y1': 'Y1 (Sample)', 'y1_st_adj': 'State Adj', 'syn': 'Synth', 'gen3': 'Gen 3' }),
                    pl.col.link,
                    pl.col.weight,
                    pl.col.est.cast(pl.Int64),
                    pl.col.otm.cast(pl.Int64),
                    pl.col.beta,
                    pl.col.y2_m
                )
            )
            print('g3modelinfo', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
        return modelinfo
    
    model_info_df: pl.DataFrame = get_model_info(selected)

    DATATYPE_LABELS = {
        "01": "AE",
        "85": "ESS",
    }

    CLOSING_LABELS = {
        "1": "P",
        "2": "F",
        "3": "R",
    }

    def selected_cell_value(selected: dict[str, str]) -> tuple[str, str]:
        # Builds the combined "selection id" shown in the first Series Info cell.
        state = (
            selected["state"].zfill(2) if selected["state"].isdigit() else selected["state"]
        )
        area = selected["area"].zfill(5) if selected["area"].isdigit() else selected["area"]
        series = selected["series"].zfill(8) if selected["series"].isdigit() else selected["series"]
        year = selected['year']
        datatype = DATATYPE_LABELS.get(selected["datatype"], selected["datatype"])
        month = (
            selected["month"].zfill(2) if selected["month"].isdigit() else selected["month"]
        )
        closing = CLOSING_LABELS.get(selected["closing"], selected["closing"])
        link = (
            aces_estreview
            + f"?q={state};{bmrkyr};{area};{series};{year};{month};{selected['closing']};{selected['datatype']};0'"
        )
        label = f"{state}-{area}-{series}-{datatype}-{year}-{month}-{closing}"
        return link, label

    aceslink, serieslabel = selected_cell_value(selected)

    series_info_df = (
        series_info_df
        .select(
                [ pl.lit(serieslabel).alias('series'),
                    'series_type_code', 'estimation_type_code', 'birth_death_factor', 'ws_flag',
                    pl.col("state_verified_by").str.replace(r"[.@].*$", "").str.to_titlecase().str.replace('Ces_Sa', '*Auto').alias("junior"),
                    pl.col("ro_verified_by").str.replace(r"[.@].*$", "").str.to_titlecase().str.replace('Ces_Sa', '*Auto').alias("senior"),

                    # pl.col.state_verified_by.str.slice(0,6).str.to_lowercase().alias('junior'),
                    # pl.col.ro_verified_by.str.slice(0,6).str.to_lowercase().alias('senior'),
                    pl.col('estimate_type_code').replace(CLOSING_LABELS, default='').alias('PFR'), 
                    'sample_treatment', 'estimate_adjustment', 'analyst_comment', 'nse', 'ratio_adjustment', 
                    pl.lit(aceslink).alias('_aceslink')
                ]
            )
        .rename(
            {'series_type_code': 'STC', 'estimation_type_code': 'Estimator', 'birth_death_factor': 'BDF',
            'analyst_comment': 'Adj Comment', 'ws_flag': 'WS',
            'sample_treatment': "Sample Adj", 'estimate_adjustment': "Est Adj", 'nse': 'NSE', 'ratio_adjustment': 'Ratio Adj', }
        )
    )
            
    
    if sample_summary_df["Sample"].item(0) == "A":
        pm = sample_summary_df["pm"].item(0)
        cm = sample_summary_df["cm"].item(0)
    else:
        pm = 0
        cm = 0
    
    if sample_summary_df["Sample"].item(0) == "T":
        wpm = sample_summary_df["pm"].item(0)
        wcm = sample_summary_df["cm"].item(0)
    elif sample_summary_df["Sample"].item(1) == "T":
        wpm = sample_summary_df["pm"].item(1)
        wcm = sample_summary_df["cm"].item(1)
    else:
        wpm = 0
        wcm = 0


    """
    'pm_est', 
        'y1_link', 'y1_st_adj_link', 'syn_link', 'gen3_link', 
        'y1_est', 'y1_st_adj_est', 'syn_est', 'gen3_est',
        'y1_weight', 'y1_st_adj_weight', 'syn_weight', 'gen3_weight', 
        'y1_otm', 'y1_st_adj_otm', 'syn_otm', 'gen3_otm',
    """
    g3_model_table0: pl.DataFrame | None = None

    if this_estimator == 'G' and g3_model_table0:
        _, \
            _, stadjlink, synthlink, _, \
            _, _,_,_, \
            y1wght, stadjwght, synthwght, _, \
            __,_,_,_ = g3_model_table0.rows(0) # this has 17 variables???????
    else:
        _, \
            _, stadjlink, synthlink, _, \
            _, _,_,_, \
            y1wght, stadjwght, synthwght, _, \
            __,_,_,_ = [0]*17
        y1wght = 1
        # cm,pm,py,stadjlink,synthlink,y1wght,stadjwght,synthwght,twpm,twcm,apm,acm,bdf,ncedef,nse

    sample_and_model_info = pl.DataFrame(
        {
            'apm': pm,
            'acm': cm,
            'twpm': wpm,
            'twcm': wcm,
            'stadjlink': stadjlink,
            'synthlink': synthlink,
            'y1wght': y1wght,
            'stadjwght': stadjwght,
            'synthwght': synthwght,
            'ncedef': 0
        }
    )

    est_calc_df = (
        pl.concat(
            [
                this_closing_series_info_row.select(
                    'cm', 'pm', 'py', pl.col.birth_death_factor.alias('bdf'), pl.col.non_sample_adjustment.alias('nse')
                ), 
                sample_and_model_info
            ], 
            how='horizontal'
        ) # g3_model_table0 sdm_model_table0,
    )
    print('etc', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
    # sdb_rep_df = sample_detail_by_report_lf.drop('selsize', 'pm_size', 'cm_size',).collect()
    # print('rep', f"Total loading time: {time.perf_counter() - xstart_counter:.2f} seconds")
    datareturn_dfdict = {
        "est_calc": est_calc_df,
        "series_info": series_info_df,
        "est_comparison": est_compare_df,
        "sample_summary": sample_summary_df,
        "sample_detail_by_ui": sample_detail_by_ui_df,
        'line_graph': series_history_df,
    }

    if this_estimator in ['S', 'Q', 'G']:
        datareturn_dfdict['model_info'] = model_info_df

    return datareturn_dfdict, sample_history_lf, sample_detail_by_report_lf.drop('selsize', 'pm_size', 'cm_size',)

if __name__ == "__main__":
    finaloutdata, sample_history0, detaillf = get_input_data(
        {
            "state": "01",
            # "area": "41304",
            # "area": "36740",
            # "series": "60560000",
            'area': '00000',
            'series': '10000000',
            "datatype": "85",
            "top_level": "Y",
            "year": "2021",
            "month": "07",
            "closing": "2",
        }
    )

    # finaloutdata['series_info'].write_csv('worklib/aseriesinfo.csv')
    # print(finaloutdata['sample_detail'].collect_schema())

    # 1. Set Polars config to show all rows and columns
    # pl.Config.set_tbl_rows(-1)
    # pl.Config.set_tbl_cols(-1)


    # 2. Print the dictionary
    # pprint(finaloutdata)
