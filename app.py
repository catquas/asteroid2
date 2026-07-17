from __future__ import annotations

# import uvicorn
# from pprint import pprint

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlencode

import os
os.environ["POLARS_VERBOSE_TRACEBACK"] = "0"
import polars as pl
from polars import selectors as cs
import get_estimate_data
from dropdown_logic import (
    first_or_current,
    max_or_current,
    max_value,
    month_target,
    numeric_previous_next,
    previous_next,
)
from transforms import add_sample_weights
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel


from operator import itemgetter
import logging
import traceback

from rich.logging import RichHandler
from rich.traceback import install

import time

start_counter = time.perf_counter()



# 1. Set Polars config to show all rows and columns
pl.Config.set_tbl_rows(-1)
pl.Config.set_tbl_cols(-1)

class OnlyMyAppFilter(logging.Filter):
    def filter(self, record):
        # Check if this log record contains an active exception traceback
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            
            # Format the original traceback into individual lines
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
            
            clean_lines = []
            # Keep the initial "Traceback (most recent call last):" header
            clean_lines.append(tb_lines[0]) 
            
            # Loop through the traceback frames
            for line in tb_lines[1:-1]:
                # Exclude any third-party framework or virtual environment paths
                if ".venv" not in line and "site-packages" not in line:
                    clean_lines.append(line)
                    
            # Append the final error message line (e.g., KeyError: 'sample_detail')
            clean_lines.append(tb_lines[-1])
            
            # Inject our strictly cleaned traceback string back into the log record
            record.exc_text = "".join(clean_lines)
            
            # Wipe exc_info so Uvicorn's default formatter doesn't re-render the full stack
            record.exc_info = None 
        return True

# Apply our strict filter directly to Uvicorn's error logger stream
uvicorn_logger = logging.getLogger("uvicorn.error")
uvicorn_logger.addFilter(OnlyMyAppFilter())




# 1. Configure the global Rich traceback hook for any raw Python crashes
install(suppress=["uvicorn", "starlette", "fastapi", "pydantic", "anyio"])

# 2. Force Uvicorn's error loggers to use Rich's handler with traceback filtering
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(
            rich_tracebacks=True,
            # This keyword array tells Rich what paths to collapse/hide
            tracebacks_suppress=["uvicorn", "starlette", "fastapi", "pydantic", "anyio"]
        )
    ]
)

# 3. Clear Uvicorn's default handlers so they don't print duplicate logs
for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logger = logging.getLogger(logger_name)
    logger.handlers = []
    logger.propagate = True


print('topmatter', f"Total loading time: {time.perf_counter() - start_counter:.2f} seconds")

# --- Data setup and display labels ---

BASE_DIR = Path(__file__).resolve().parent




# needed for dropdowns and table display
MONTH_LABELS = {
    "01": "Jan",
    "02": "Feb",
    "03": "Mar",
    "04": "Apr",
    "05": "May",
    "06": "Jun",
    "07": "Jul",
    "08": "Aug",
    "09": "Sep",
    "10": "Oct",
    "11": "Nov",
    "12": "Dec",
}

CLOSING_LABELS = {
    "1": "P",
    "2": "F",
    "3": "R",
}

startyear = 2017
max_closing_dict = get_estimate_data.getclosing()
print('max closing', max_closing_dict)
maxyear = max_closing_dict.get('year', '')
maxmonth = max_closing_dict.get('month', '')
maxclosing = max_closing_dict.get('closing', '')

year_options = [str(y) for y in range(int(maxyear), startyear, -1)]

maxyear_months = [
    {'label': str(mon).zfill(2)+'-'+MONTH_LABELS[str(mon).zfill(2)], 'value': str(mon).zfill(2)}
    for mon in range(int(maxmonth), 0, -1)
] + [
    {'label': str(mon).zfill(2)+'-'+MONTH_LABELS[str(mon).zfill(2)], 'value': str(int(maxyear)-1)+str(mon).zfill(2)}
    for mon in range(12, int(maxmonth), -1)
]
prevyear_months = [
    {'label': str(mon).zfill(2)+'-'+MONTH_LABELS[str(mon).zfill(2)], 'value': str(mon).zfill(2)}
    for mon in range(12, 0, -1)
]
#if the value of the month dropdown is 6 chars, the 1st 4 chars are the year, overriding the year from the dropdown


aceslib_path = Path("/aceslib")
def get_weighted_sample_data(year, month, closing, bmrkyr) -> pl.LazyFrame:
    archive_filename = "matched_sample_archive_" + bmrkyr + '.pq'
    # Combine them into a full path
    pqfile = aceslib_path / archive_filename

    # Verify if the file exists and is not a folder
    if pqfile.is_file():
        ms_path = pqfile
    else:
        ms_path = aceslib_path / "matched_sample_current.pq"

    matched_sample_lf = pl.scan_parquet(ms_path)

    if month in ['10','11','12'] and closing == '3':
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
            pl.col("state_fips_code") == '12',
            pl.col.year == year,
            pl.col.month == month,
            pl.col.estimate_type_code == closing
        )
    )
    return weighted

w = get_weighted_sample_data('2026', '06', '01', '2025').collect()

emojis = dict(pl.read_csv('series_code_emojis.csv').select(['series_code', 'emojis']).iter_rows())
print(emojis)

print('weighted: ', f"Total loading time: {time.perf_counter() - start_counter:.2f} seconds")





















# import io
# from fastapi import FastAPI, Response
# import geopandas as gpd
# from geopandas import GeoDataFrame
# import matplotlib
# # Use the non-interactive Agg backend to avoid GUI overhead and thread issues
# matplotlib.use("Agg") 
# import matplotlib.pyplot as plt
# import base64

# # Load data once at startup to keep endpoint response times ultra-fast
# COUNTIES: GeoDataFrame = gpd.read_file(
#     "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_us_county_20m.zip"
# )
# MSAS: GeoDataFrame = gpd.read_file(
#     "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_us_cbsa_20m.zip"
# )

# def get_msa_map(msa_fips: str, state_fips: str = "12"):
#     # 1. Filter and spatial join
#     state_counties: GeoDataFrame = COUNTIES.loc[COUNTIES["STATEFP"] == state_fips].copy()  # type: ignore
    
#     msa_filtered = MSAS[MSAS["GEOID"] == msa_fips]
#     if msa_filtered.empty:
#         return Response(status_code=404)
        
#     msa = msa_filtered.iloc[0]
#     msa_name = msa["NAME"]
    
#     msa_geom = gpd.GeoDataFrame([msa], geometry="geometry", crs=MSAS.crs)
#     in_msa = gpd.sjoin(state_counties, msa_geom, how="inner", predicate="intersects")
    
#     # 2. Plot exactly like your original script
#     fig, ax = plt.subplots(figsize=(10, 8))
#     state_counties.plot(ax=ax, color="lightgrey", edgecolor="white", linewidth=0.5)
#     in_msa.plot(ax=ax, color="steelblue", edgecolor="white", linewidth=0.5)
    
#     ax.set_title(f"{msa_fips} - {msa_name}", fontsize=13)
#     ax.axis("off")
#     plt.tight_layout()

#     # # 3. Save the plot to an in memory buffer
#     buf = io.BytesIO()
#     plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
#     plt.close(fig) # Free memory immediately
#     buf.seek(0)
    
#     # Encode the raw bytes directly to a base64 string
#     map_base64 = base64.b64encode(buf.read()).decode('utf-8')
#     return map_base64





















# --- FastAPI setup ---

# FastAPI serves the HTML page, static CSS/JS, and row fragments loaded on demand.
app = FastAPI(title="Asteroid Estimate Review")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


class SampleDetailRowsRequest(BaseModel):
    # JSON payload sent when a summary sample-detail row is expanded.
    reptstate: str #TODO: ADD THIS TO PAYLOAD FROM JAVASCRIPT
    ui: str
    flag: str
    is_knr: bool
    detail_group: str


# --- DataFrame helpers and normalization ---


def label_dict(df: pl.DataFrame, code_column: str, label_column: str) -> dict[str, str]:
    if df.is_empty() or code_column not in df.columns or label_column not in df.columns:
        return {}

    return {
        str(row[code_column]): str(row[label_column])
        for row in df.select([code_column, label_column]).to_dicts()
        if row[code_column] and row[label_column]
    }


def state_option_items(df: pl.DataFrame) -> list[dict[str, str]]:
    if df.is_empty() or "state" not in df.columns or "statename" not in df.columns:
        return []

    return [
        {"value": state, "label": f"{state}-{row['statename']}"}
        for row in df.select(["state", "statename"]).to_dicts()
        if (state := str(row["state"]).zfill(2)) and row["statename"]
    ]


# --- preload and lookup tables ---

# These are the main sources for the filter options.
STATE_AREA_SERIES_LF = get_estimate_data.get_state_area_series_lf()
YEAR_MONTH_CLOSING_DF = get_estimate_data.get_year_month_closing_df()

# These are lookup tables for display labels and drill-through links.
STATE_STATENAME_DF = get_estimate_data.get_state_statename_df()
AREA_AREANAME_DF = get_estimate_data.get_area_areaname_df()
SERIES_SERIESNAME_DF = get_estimate_data.get_series_seriesname_df()

# These are the final forms of the lookup tables used for filter option labels and drill-through links.
STATE_OPTIONS = state_option_items(STATE_STATENAME_DF.collect())
AREA_LABELS = label_dict(AREA_AREANAME_DF.collect(), "area", "areaname")
SERIES_LABELS = label_dict(SERIES_SERIESNAME_DF.collect(), "series", "seriesname")

print('preload', f"Total loading time: {time.perf_counter() - start_counter:.2f} seconds")

# --- Shared numeric helpers ---


def parse_decimal(value: Any) -> Decimal | None:
    # Bad or blank numeric cells become None instead of raising everywhere.
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def absolute_decimal(value: str) -> Decimal:
    return abs(parse_decimal(value) or Decimal("0"))


def row_dict_by_heading(df: pl.DataFrame, heading: str) -> dict[str, str]:
    # Middle-table tables use their first column as the row label.
    if df.is_empty():
        return {}

    heading_column = df.columns[0]
    rows = df.filter(pl.col(heading_column) == heading).head(1)
    return rows.to_dicts()[0] if rows.height else {}


# --- Middle table builders: Estimate Comparison, Sample Summary, Model Info ---


def middle_table_context(
    title: str,
    df: pl.DataFrame,
    ratio_row_indexes: set[int] | None = None,
    hidden_columns: set[str] | None = None,
    inline_ratio_columns: dict[str, str] | None = None,
    highlighted_cells: set[tuple[str, str]] | None = None,
    decimal_columns: set[str] | None = None,
    row_classes: dict[str, str] | None = None,
    link_value: str = "",
    betaval: float | None = None,
    y2val: float | None = None,
    # betaval: str = 
) -> dict[str, Any]:
    # Used by index() to convert the final DataFrame into the structure
    # index.html expects.
    ratio_row_indexes = ratio_row_indexes or set()
    hidden_columns = hidden_columns or set()
    inline_ratio_columns = inline_ratio_columns or {}
    highlighted_cells = highlighted_cells or set()
    decimal_columns = decimal_columns or set()
    row_classes = row_classes or {}
    if df.is_empty():
        return {
            "title": title,
            "heading_column": "",
            "columns": [],
            "rows": [],
            "link_value": link_value,
            'betaval': betaval,
            'y2val': y2val
        }

    rows = df.to_dicts()
    fieldnames = df.columns
    heading_column = fieldnames[0]
    value_columns = [
        fieldname for fieldname in fieldnames[1:] if fieldname not in hidden_columns
    ]
    table_rows = []
    for index, row in enumerate(rows, start=1):
        is_ratio = index in ratio_row_indexes
        cells = []
        heading = row.get(heading_column, "")
        for column in value_columns:
            value = row.get(column, "")
            # Columns like OTM show the main number plus a bracketed percent
            # that lives in a hidden companion column; the template formats both.
            ratio_value = (
                row.get(inline_ratio_columns[column], "")
                if column in inline_ratio_columns
                else ""
            )
            cells.append(
                {
                    "column": column,
                    "value": value,
                    "ratio_value": ratio_value,
                    "is_decimal": column in decimal_columns,
                    "is_highlighted": (heading, column) in highlighted_cells,
                }
            )
        table_rows.append(
            {
                "heading": heading,
                "cells": cells,
                "is_ratio": is_ratio,
                "class": row_classes.get(heading, ""),
            }
        )

    return {
        "title": title,
        "heading_column": heading_column,
        "columns": value_columns,
        "rows": table_rows,
        "link_value": link_value,
        'betaval': betaval,
        'y2val': y2val
    }


def estimate_comparison_highlighted_cells(df: pl.DataFrame) -> set[tuple[str, str]]:
    # Highlight the tolerance row that the pub est value has crossed.
    if df.is_empty():
        return set()

    pubest = Decimal(row_dict_by_heading(df, "pub").get("est", "") or "0")
    hi_tol = Decimal(row_dict_by_heading(df, "hi-tol").get("est", "") or "0")
    lo_tol = Decimal(row_dict_by_heading(df, "lo-tol").get("est", "") or "0")
    highlighted_cells: set[tuple[str, str]] = set()

    if pubest > hi_tol:
        highlighted_cells.add(("hi-tol", "est"))
    if pubest < lo_tol:
        highlighted_cells.add(("lo-tol", "est"))

    return highlighted_cells


# --- Sample detail table builders ---


def sample_detail_summary(df: pl.DataFrame) -> list[dict[str, Any]]:
    # Group related sample detail rows so duplicate ids can be shown as one
    # expandable summary row. Detail rows are loaded lazily by endpoint.
    if df.is_empty():
        return []

    return df.to_dicts()


def sample_detail_details(
    lf: pl.LazyFrame, reptstate: str, ui: str, flag: str, is_knr: bool
) -> pl.DataFrame:
    # Return the raw rows behind one expandable summary group.
    
    detail_df = (lf
        .filter(
            (pl.col.reptstate == reptstate)
            & (pl.col("ui") == ui)
            & (pl.col("flag") == flag)
            & (pl.col("_is_knr") == is_knr)
        )
        .sort(
            ['flag', "_abs_wotm", "reptstate", "ui", 'report'], 
            descending=[False, True, False, False, False]
        )
        .collect()
    )
    return detail_df


# --- Line graph and graph-data table builders ---


def month_name(value: str) -> str:
    # Convert numeric month values to the abbreviated labels shown in charts.
    return MONTH_LABELS.get(value.zfill(2), value)


def short_year(value: str) -> str:
    # Keep table column labels compact by displaying the final two year digits.
    return value[-2:] if len(value) >= 2 else value


def parse_int(value: Any) -> int | None:
    # Parse optional numbers without making every caller handle exceptions.
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_float(value: Any) -> float | None:
    # Chart.js accepts nulls, so invalid numeric cells become None upstream.
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def previous_month_key(year: int, month: int) -> tuple[int, int]:
    # Represent a month as (year, month) so ranges can cross year boundaries.
    if month == 1:
        return year - 1, 12
    return year, month - 1


def next_month_key(year: int, month: int) -> tuple[int, int]:
    # Advance one month while wrapping December into the next year.
    if month == 12:
        return year + 1, 1
    return year, month + 1


def month_key_range(
    start: tuple[int, int], end: tuple[int, int]
) -> list[tuple[int, int]]:
    # Build the complete set of month positions needed for sparse line segments.
    keys = []
    current = start
    while current <= end:
        keys.append(current)
        current = next_month_key(*current)
    return keys


def month_key_label(key: tuple[int, int]) -> str:
    # Full labels are used on chart axes and tooltips.
    year, month = key
    return f"{month_name(str(month))} {year}"


def month_key_short_label(key: tuple[int, int]) -> str:
    # Short labels identify each sample-history segment in the legend.
    year, month = key
    return f"{month_name(str(month))}'{str(year)[-2:]}"


def sorted_line_graph_df(df: pl.DataFrame) -> pl.DataFrame:
    # Sort by numeric year/month so chart points are chronological.
    return df.sort(
        pl.col("year").cast(pl.Int64, strict=False),
        pl.col("month").cast(pl.Int64, strict=False),
    )


def line_graph_context(df: pl.DataFrame) -> dict[str, Any]:
    # Used by index() to build the Chart.js payload. The values are sorted
    # chronologically so the plotted line moves left-to-right through time.
    chart_df = sorted_line_graph_df(df).with_columns(
        label=pl.col("month").map_elements(month_name, return_dtype=pl.String)
        + " "
        + pl.col("year").cast(pl.String),
        rvalue_int=pl.col("rvalue").cast(pl.Int64, strict=False),
        lotol_int=pl.col("lotol").cast(pl.Int64, strict=False),
        hitol_int=pl.col("hitol").cast(pl.Int64, strict=False),
    )
    if chart_df.is_empty():
        return {"labels": [], "datasets": []}

    labels = chart_df.get_column("label").to_list()
    # Closing 4 and all other closings are split into separate datasets so the
    # chart can draw them with different colors.
    benchmarkline = (
        chart_df.select(
            pl.when(pl.col("closing") == "4")
            .then(pl.col("rvalue_int"))
            .otherwise(None)
            .alias("value")
        )
        .get_column("value")
        .to_list()
    )
    estimatehistline = (
        chart_df.select(
            pl.when(pl.col("closing") != "4")
            .then(pl.col("rvalue_int"))
            .otherwise(None)
            .alias("value")
        )
        .get_column("value")
        .to_list()
    )
    lotol = chart_df.get_column("lotol_int").to_list()
    hitol = chart_df.get_column("hitol_int").to_list()

    first_closing_other_index = next(
        (index for index, value in enumerate(estimatehistline) if value is not None),
        None,
    )
    if (
        first_closing_other_index
        and benchmarkline[first_closing_other_index - 1] is not None
    ):
        # Duplicate the previous Closing 4 point into the Estimates line so the
        # orange line visually connects from the benchmark series.
        estimatehistline[first_closing_other_index - 1] = benchmarkline[
            first_closing_other_index - 1
        ]

    return {
        "labels": labels,
        "datasets": [
            {"label": "Benchmark", "data": benchmarkline, "borderColor": "#15803d"},
            {"label": "Estimates", "data": estimatehistline, "borderColor": "#f97316"},
            {
                "label": "lo-tol",
                "data": lotol,
                "borderColor": "#111827",
                "borderDash": [5, 5],
            },
            {
                "label": "hi-tol",
                "data": hitol,
                "borderColor": "#111827",
                "borderDash": [5, 5],
            },
        ],
    }


def line_graph_table_context(df: pl.DataFrame) -> dict[str, Any]:
    # This is the one-row numeric table below the chart, using the same order as
    # the graph.
    series_hist_df = (
        sorted_line_graph_df(df)
        .sort('year', 'month')
        .tail(18)
        .with_columns(
            pl.col("rvalue").cast(pl.Int64, strict=False).alias('Pub Est'),
            label = pl.col("month").map_elements(month_name, return_dtype=pl.String)
            + "-"
            + pl.col("year").map_elements(short_year, return_dtype=pl.String),
        ).unpivot(
            index='label', on=['Orig Est', 'Sample Adj', 'NSE', 'Est Adj', 'Ratio Adj', 'Pub Est'],
            variable_name='rowtitle', value_name='emp'
        ).pivot(
            index='rowtitle', on='label', values='emp'
        )
    )

    return {
        'columns': series_hist_df.columns,
        'rows' : series_hist_df.to_dicts()
    }


# --- Filter bar option and navigation helpers ---


def filter_df(df: pl.DataFrame, filters: dict[str, str]) -> pl.DataFrame:
    # Apply exact-match filters in Polars.
    filtered = df
    for field, value in filters.items():
        if not value or field not in filtered.columns:
            continue
        filtered = filtered.filter(pl.col(field) == value)
    return filtered


def unique_values(df: pl.DataFrame, field: str) -> list[str]:
    # Preserve order while removing duplicates.
    if field not in df.columns:
        return []

    return (
        df.select(pl.col(field))
        .filter(pl.col(field) != "")
        .unique(maintain_order=True)
        .get_column(field)
        .to_list()
    )


def code_label(
    value: str,
    labels: dict[str, str] | None = None,
    width: int | None = None,
    separator: str = "-",
) -> str:
    # Combines a code and optional friendly name, for example "01-Jan".
    labels = labels or {}
    display_value = value.zfill(width) if width and value.isdigit() else value
    label = labels.get(display_value) or labels.get(value)
    return f"{display_value}{separator}{label}" if label else display_value


def option_items(
    options: list[str],
    labels: dict[str, str] | None = None,
    width: int | None = None,
    separator: str = "-",
) -> list[dict[str, str]]:
    # Convert raw option values into the common value/label shape used by Jinja.
    return [
        {
            "value": option,
            "label": code_label(option, labels, width, separator),
        }
        for option in options
    ]


def series_label(value: str, seriestype: str) -> str:
    # Series codes are easier to read when split after the first two digits.
    display_value = f"{value[:2]}-{value[2:]}" if len(value) == 8 else value
    label = SERIES_LABELS.get(value)
    return f"{display_value}-{seriestype}-{label}" if label else display_value


def series_option_items(options: list[str], seriestypes: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "value": option,
            "label": series_label(option, seriestypes.get(option, '')),
        }
        for option in options
    ]

def datatype_button_items(
    options: list[str], selected: dict[str, str]
) -> list[dict[str, Any]]:
    # Datatype is rendered as compact fixed-choice buttons. Unavailable choices
    # are omitted so the surrounding filters have more room.
    available = set(options)
    return [
        {
            "value": value,
            "label": label,
            "is_active": value == selected["datatype"],
            "url": selection_url(selected, datatype=value),
        }
        for value, label in (("85", "ESS"), ("01", "AE"))
        if value in available
    ]


def closing_button_items(
    options: list[str], selected: dict[str, str]
) -> list[dict[str, Any]]:
    # Closing uses fixed P/F/R buttons in the same way datatype uses ESS/AE.
    available = set(options)
    return [
        {
            "value": value,
            "label": label,
            "is_active": value == selected["closing"],
            "url": selection_url(selected, closing=value),
        }
        for value, label in (("1", "P"), ("2", "F"), ("3", "R"))
        if value in available
    ]


FLAG_CHG_UIS_PATTERN = re.compile(r"([ATX])\s*:\s*(\d+)")

def flag_chg_uis_badges(value: Any) -> list[dict[str, str]]:
    text = str(value or "").strip()
    if not text:
        return []

    badges = [
        {"flag": match.group(1), "count": match.group(2)}
        for match in FLAG_CHG_UIS_PATTERN.finditer(text)
    ]
    remainder = FLAG_CHG_UIS_PATTERN.sub("", text)
    if not badges or remainder.strip(" ,"):
        return []

    return badges


def series_info_context(selected: dict[str, str], df: pl.DataFrame) -> dict[str, Any]:
    # The first Series Info row is displayed, but its first cell is replaced
    # with the current selection id.
    if df.is_empty():
        return {"columns": [], "row": {}, "flag_chg_uis": {}}

    row = df.head(1).to_dicts()[0]
    columns = list(row)
    flag_chg_uis = {
        column: flag_chg_uis_badges(row[column])
        for column in columns
        if column.strip() == "Flag Chg Uis"
    }
    rows = [row]
    if selected['closing'] in ['2','3']:
        rows.append(df.tail(1).to_dicts()[0])

    return {"columns": columns, "rows": rows, "flag_chg_uis": flag_chg_uis}


def selection_url(selected: dict[str, str], **overrides: str) -> str:
    # Builds links for button/dropdown navigation while preserving the rest of
    # the current selection.
    values = {**selected, **overrides}
    ordered_values = {
        "state": values["state"],
        "area": values["area"],
        "series": values["series"],
        "datatype": values["datatype"],
        "year": values["year"],
        "month": values["month"] if not (values['year']==maxyear and values['month']>maxmonth) else maxmonth,
        "closing": values["closing"],
    }
    if values.get("top_level") == "Y":
        ordered_values["top_level"] = "Y"
    if values.get("oot") == "Y":
        ordered_values["oot"] = "Y"
    return f"/?{urlencode(ordered_values)}"


def max_datatype_for_area_series(state_df: pl.DataFrame, area: str, series: str) -> str:
    rows = filter_df(state_df, {"area": area, "series": series})
    options = unique_values(rows, "datatype")
    return max_value(options) if options else ""


def state_area_series_dt_context(query: Mapping[str, str | None]) -> dict[str, Any]:
    # Builds the left side of the top filter bar: state, area, series, datatype,
    # and the TOP checkbox. Invalid query values fall back to usable defaults.
    selected_top_level = "Y" if query.get("top_level") == "Y" else ""
    selected_oot = "Y" if query.get("oot") == "Y" else ""
    state_options = sorted(STATE_OPTIONS, key=itemgetter('value'))
    state_values = [option["value"] for option in state_options]
    selected_state = first_or_current(state_values, query.get("state"))

    state_df = (
        STATE_AREA_SERIES_LF
        .filter(pl.col.state == selected_state)
    )
    if selected_top_level:
        # TOP limits the state rows before area and series choices are computed.
        state_df = (
            state_df
            .filter(pl.col.toplev == 'Y')
        )
    if selected_oot:
        # TOP limits the state rows before area and series choices are computed.
        state_df = (
            state_df
            .filter(pl.col.oot == 'Y')
        )

    def get_sorted_list(lf: pl.LazyFrame, column: str) -> list:
        """Helper to get non-empty, sorted, unique values as a list."""
        return (
            lf.select(pl.col(column))
            .filter(pl.col(column) != "")
            .unique(maintain_order=True)
            .sort(column)
            .collect()
            .get_column(column)
            .to_list()
        )

    # 1. Area filtering
    area_options = get_sorted_list(state_df, 'area')
    selected_area = first_or_current(area_options, query.get("area"))
    series_df = state_df.filter(pl.col.area == selected_area)

    seriestypes = dict(series_df.select('series', 'seriestype').collect().iter_rows())
    # print(seriestypes)

    # 2. Series filtering
    series_options = get_sorted_list(series_df, 'series')
    selected_series = first_or_current(series_options, query.get("series"), bestop=True)
    datatype_df = series_df.filter(pl.col.series == selected_series)

    # 3. Datatype filtering
    datatype_options = get_sorted_list(datatype_df, 'datatype')
    selected_datatype = max_or_current(datatype_options, query.get("datatype"))
    
    return {
        "state_options": sorted(state_options, key=itemgetter('value')),
        "area_options": area_options,
        "area_option_items": option_items(area_options, AREA_LABELS, 5),
        "series_options": series_options,
        "series_option_items": series_option_items(series_options, seriestypes),
        "datatype_options": datatype_options,
        "selected": {
            "state": selected_state,
            "area": selected_area,
            "series": selected_series,
            "datatype": selected_datatype,
            "top_level": selected_top_level,
            "oot": selected_oot,
        },
    }


def date_context(query: Mapping[str, str | None]) -> dict[str, Any]:
    # Builds the right side of the top filter bar: year, month, and closing.

    qyear = query.get('year')
    qmonth = query.get('month')
    qclosing = query.get('closing')

    # if we selected a month in the prior year from the current year's month dropdown
    if qmonth and len(qmonth) > 2:
        qyear = qmonth[:4]
        qmonth = qmonth[-2:]
    
    # if we jumped to a month that has not happened yet, instead go to max month available
    qmonth = maxmonth if (qmonth and qmonth > maxmonth and qyear == maxyear) else qmonth

    print('qy  ', qyear, 'qm  ', qmonth, 'qc ', qclosing)

    # --- YEAR ---
    selected_year = first_or_current(year_options, qyear)

    # --- MONTH ---
    if selected_year == maxyear:
        month_options_value_label = maxyear_months
    else:
        month_options_value_label = prevyear_months

    month_options = [item['value'][-2:] for item in month_options_value_label]
    selected_month = first_or_current(month_options, qmonth)

    # --- CLOSING ---
    if selected_year == maxyear and selected_month == maxmonth:
        rangec=maxclosing
    elif selected_month in ['10','11','12'] and (maxclosing=='3' or maxmonth < '10'):
        rangec = '3'
    else:
        rangec = '2'

    skipm=2 if selected_month == '12' else None    
    closing_options = [str(c) for c in range(int(rangec),0,-1) if c != skipm]
    print(closing_options)

    # closing_df = filter_df(month_df, {"month": selected_month})
    # closing_options = unique_values(closing_df, "closing")
    selected_closing = max_or_current(closing_options, qclosing)

    return {
        "year_options": year_options,
        "year_option_items": option_items(year_options),
        # "month_options": month_options,
        # "month_option_items": option_items(month_options, MONTH_LABELS),
        "month_option_items": month_options_value_label,
        "closing_options": closing_options,
        "selected": {
            "year": selected_year,
            "month": selected_month,
            "closing": selected_closing,
        },
    }


def build_nav(
    selected: dict[str, str],
    state_area: dict[str, Any],
    dates: dict[str, Any],
) -> dict[str, dict[str, str | None]]:
    # Create all prev/next URLs used by the step buttons. Each URL keeps the
    # current selection valid after changing just one dimension.
    state_df = (
        STATE_AREA_SERIES_LF
        .filter(pl.col.state == selected['state'])
        .collect()
    )
    # state_df = filter_df(STATE_AREA_SERIES_LF, {"state": selected["state"]})
    if selected.get("top_level") == "Y":
        # TOP limits the state rows before area and series choices are computed.
        state_df = (
            state_df
            .filter(pl.col.toplev == 'Y')
        )
    if selected.get("oot") == "Y":
        # TOP limits the state rows before area and series choices are computed.
        state_df = (
            state_df
            .filter(pl.col.oot == 'Y')
        )
        # state_df = filter_df(state_df, {"top-level": "Y"})
    area_options = state_area["area_options"]
    series_options = state_area["series_options"]
    year_options = dates["year_options"]
    # month_options = dates["month_options"] TODO: any reason why this is needed? it was not being used
    closing_options = dates["closing_options"]

    nav: dict[str, dict[str, str | None]] = {
        "area": {"prev": None, "next": None},
        "series": {"prev": None, "next": None},
        "datatype": {"prev": None, "next": None},
        "year": {"prev": None, "next": None},
        "month": {"prev": None, "next": None},
        "closing": {"prev": None, "next": None},
    }

    valid_area_series = set(
        zip(state_df["area"].to_list(), state_df["series"].to_list())
    )
    area_candidates = [
        area for area in area_options if (area, selected["series"]) in valid_area_series
    ]
    # Area stepping only includes areas that still contain the selected series.
    for direction, area in previous_next(area_candidates, selected["area"]).items():
        if area:
            datatype = max_datatype_for_area_series(state_df, area, selected["series"])
            nav["area"][direction] = selection_url(
                selected, area=area, datatype=datatype
            )

    for direction, series in previous_next(series_options, selected["series"]).items():
        target_area = selected["area"]
        target_series = series

        if not target_series and selected["area"] in area_options:
            # If the selected series is at the edge of an area, series stepping
            # can move into the adjacent area's first/last series.
            area_index = area_options.index(selected["area"])
            adjacent_area = None
            if direction == "prev" and area_index > 0:
                adjacent_area = area_options[area_index - 1]
            elif direction == "next" and area_index < len(area_options) - 1:
                adjacent_area = area_options[area_index + 1]

            if adjacent_area:
                adjacent_series = unique_values(
                    filter_df(state_df, {"area": adjacent_area}), "series"
                )
                if adjacent_series:
                    target_area = adjacent_area
                    target_series = (
                        adjacent_series[-1]
                        if direction == "prev"
                        else adjacent_series[0]
                    )

        if target_series:
            datatype = max_datatype_for_area_series(
                state_df, target_area, target_series
            )
            nav["series"][direction] = selection_url(
                selected,
                area=target_area,
                series=target_series,
                datatype=datatype,
            )

    year_candidates = [
        year
        for year in year_options
        if selected["month"] in ([m['value'][-2:] for m in maxyear_months] if year == maxyear 
                                 else [m['value'][-2:] for m in prevyear_months])
    ]
    for direction, year in numeric_previous_next(
        year_candidates, selected["year"]
    ).items():
        if year:
            # closings = year_month_closing_options(year, selected["month"])
            if year == maxyear and selected['month'] == maxmonth:
                rangec=maxclosing
            elif selected['month'] in ['10','11','12'] and (maxclosing=='3' or maxmonth < '10'):
                rangec = '3'
            else:
                rangec = '2'
            skipm = 2 if selected['month'] == '12' else None    
            closings = [str(c) for c in range(int(rangec),0,-1) if c != skipm]
            closing = max_or_current(closings, selected["closing"])
            nav["year"][direction] = selection_url(selected, year=year, closing=closing)

    for direction in ("prev", "next"):
        target = month_target(
            selected["year"], selected["month"], direction,
            startyear=startyear, maxyear=maxyear, maxmonth=maxmonth,
        )
        print('23985472897354', 'direction ', direction, ' target ', target)
        if target:
            year, month = target
            if year == maxyear and selected['month'] == maxmonth:
                rangec=maxclosing
            elif selected['month'] in ['10','11','12'] and (maxclosing=='3' or maxmonth < '10'):
                rangec = '3'
            else:
                rangec = '2'
            skipm = 2 if selected['month'] == '12' else None    
            closings = [str(c) for c in range(int(rangec),0,-1) if c != skipm]
            nav["month"][direction] = selection_url(
                selected,
                year=year,
                month=month,
                closing=max_or_current(closings, None),
            )

    for direction, closing in numeric_previous_next(
        closing_options, selected["closing"]
    ).items():
        if closing:
            nav["closing"][direction] = selection_url(selected, closing=closing)

    return nav


def dropdown_context(
    selected: dict[str, str],
    nav: dict[str, dict[str, str | None]],
    state_area: dict[str, Any],
    dates: dict[str, Any],
) -> list[dict[str, Any]]:
    # This list drives the filter form in index.html. Each dictionary describes
    # one control and whether it is a select, button group, or stepped select.
    return [
        {
            "name": "state",
            "label": "State",
            "class": "is-state",
            "options": state_area["state_options"],
            "selected": selected["state"],
        },
        {
            "name": "area",
            "label": "Area",
            "class": "is-wide",
            "options": state_area["area_option_items"],
            "selected": selected["area"],
            "nav": nav["area"],
        },
        {
            "name": "series",
            "label": "Series",
            "class": "is-wide",
            "options": state_area["series_option_items"],
            "selected": selected["series"],
            "nav": nav["series"],
            "series_nav": True,
        },
        {
            "name": "datatype",
            "label": "Datatype",
            "class": "is-datatype",
            "datatype_buttons": datatype_button_items(
                state_area["datatype_options"], selected
            ),
            "selected": selected["datatype"],
        },
        {
            "name": "year",
            "label": "Year",
            "class": "is-year",
            "options": dates["year_option_items"],
            "selected": selected["year"],
            "nav": nav["year"],
        },
        {
            "name": "month",
            "label": "Month",
            "class": "is-month",
            "options": dates["month_option_items"],
            "selected": selected["month"],
            "nav": nav["month"],
        },
        {
            "name": "closing",
            "label": "Closing",
            "class": "is-closing",
            "closing_buttons": closing_button_items(dates["closing_options"], selected),
            "selected": selected["closing"],
        },
    ]


# --- Sample history page builders ---


def sample_history_context(
    query: Mapping[str, str | None], lf: pl.LazyFrame
) -> dict[str, Any]:
    # Build the sample-history page payload from query params and filtered 
    # rows. Each history row becomes one prior-month-to-current-month chart line.

    is_summary = query.get('row_type') == 'summary'

    rows_lf = (
        lf.filter(
            pl.col("reptstate") == query.get("reptstate"),
            pl.col("ui") == query.get("ui"),
            (pl.col("_cm_flag") == query.get("flag")) & (pl.col("_cm_knr") == (query.get("knr") == "Y"))
            if is_summary
            else pl.col("report") == query.get("report")
        )
    )
        
    sample_hist_sums_df = (
        rows_lf
        .group_by('reptstate', 'ui', '_is_knr', 'year', 'month')
        .agg(
            cs.string().first(), 
            pl.col('pm', 'cm', 'otm', 'wotm').cast(pl.Decimal(precision=None, scale=3)).sum(),
            pl.col('version', 'weight', 'origdwght', 'dwght').cast(pl.String).first(),
            # cs.numeric().cast(pl.Decimal(precision=None, scale=3)).sum(),
            pl.col.report.unique().alias('reportlist'),
            pl.when(pl.col.flag==pl.lit('X')).then(pl.lit('black'))
            .when(pl.col.flag==pl.lit('A')).then(pl.lit('red'))
            .when(pl.col.dwght.is_between(0.3,0.4,closed='both')).then(pl.lit('orange'))
            .otherwise(pl.lit('blue')).alias('color')
        )
        .sort(['year', 'month'], descending=[True, True])
        .collect()
    )    

    graph_rows = []
    if {"year", "month", "pm", "cm"}.issubset(rows_lf.columns):
        for row in sample_hist_sums_df.to_dicts():
            year = parse_int(row.get("year"))
            month = parse_int(row.get("month"))
            pm = parse_float(row.get("pm"))
            cm = parse_float(row.get("cm"))
            color = row.get('color')
            if (
                year is None
                or month is None
                or month < 1
                or month > 12
                or pm is None
                or pm == 0
                or cm is None
                or cm == 0
            ):
                continue

            current_key = (year, month)
            prior_key = previous_month_key(year, month)
            graph_rows.append(
                {
                    "label": month_key_short_label(current_key),
                    "prior_key": prior_key,
                    "current_key": current_key,
                    "pm_value": pm,
                    "cm_value": cm,
                    'color': color,
                }
            )

    month_keys = (
        month_key_range(
            min(row["prior_key"] for row in graph_rows),
            max(row["current_key"] for row in graph_rows),
        )
        if graph_rows
        else []
    )
    sample_history_graph = {
        "labels": [month_key_label(key) for key in month_keys],
        'colors': [row['color'] for row in graph_rows],
        "datasets": [
            {
                "label": row["label"],
                "data": [
                    row["pm_value"]
                    if key == row["prior_key"]
                    else row["cm_value"]
                    if key == row["current_key"]
                    else None
                    for key in month_keys
                ],
            }
            for row in graph_rows
        ],
    }

    return {
        "params": query,
        'reportlist':sample_hist_sums_df.item(0,'reportlist'),
        # "columns": rows_df.columns,
        "columns": ['year', 'month', 'pm', 'cm', 'version', 'selsize', 'weight', 'origflag', 'flag', 'origdwght', 'dwght', 'cmcc', 'otm', 'wotm'],
        #aces also has version (after cm), and influence, deepsflag, and analystflag (after otm). Influence is blank for ae/ess
        "rows": sample_hist_sums_df.to_dicts(),
        "sample_history_graph": sample_history_graph,
    }


# --- Startup-computed constants (derived from static DataFrames) ---

YEAR_TO_MONTHS: dict[str, list[str]] = {
    year: unique_values(filter_df(YEAR_MONTH_CLOSING_DF, {"year": year}), "month")
    for year in year_options
}

print('startup-computed', f"Total loading time: {time.perf_counter() - start_counter:.2f} seconds")
# --- Route handlers ---


@app.post("/api/sample-detail-details", response_class=HTMLResponse)
async def api_sample_detail_details(payload: SampleDetailRowsRequest) -> HTMLResponse:
    # Return Jinja-rendered detail <tr> elements for one expanded summary row.
    # print(input_tables['sample_detail'])
    details_df = sample_detail_details(
        sample_detail_by_report_lf,
        payload.reptstate,
        payload.ui,
        payload.flag.strip().upper(),
        payload.is_knr,
    )
    # print('details', details_df)
    details_dict = details_df.to_dicts()
    sample_detail_cols = list(
        dict.fromkeys(
            [
                col for col in details_df.columns 
                if not (col.startswith('_') or col in ['reptstate', 'reptw', 'wpm', 'wcm'])
            ]
        )
    )
        # if not (item.startswith("_") or item == 'reptstate')
    html = templates.env.get_template("_sample_detail_detail_rows.html").render(
        sample_detail_columns=sample_detail_cols,
        sample_detail_details=details_dict,
        detail_group=payload.detail_group,
    )
    # print('html', html)
    return HTMLResponse(html)


@app.get("/sample-history", response_class=HTMLResponse)
async def sample_history(request: Request) -> HTMLResponse:
    # Drill-through page for one UI/report/flag combination from Sample Details.
    return templates.TemplateResponse(
        request,
        "sample_history.html",
        sample_history_context(
            dict(request.query_params), sample_history_lf
        ),
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    global async_start_counter
    async_start_counter = time.perf_counter()
    # print('appget', f"Total loading time: {time.perf_counter() - start_counter:.2f} seconds")
    # Main page route: gather current selections, build every table/chart data
    # object, and hand all of it to the Jinja template.
    query = dict(request.query_params)
    state_area_series_dt = state_area_series_dt_context(query)
    dates = date_context(query)
    selected = {**state_area_series_dt["selected"], **dates["selected"]}
    print(selected)
    nav = build_nav(selected, state_area_series_dt, dates)
    print('nav', f"Total loading time: {time.perf_counter() - async_start_counter:.2f} seconds")
    #####################################################################################
    global input_tables
    global sample_history_lf
    global sample_detail_by_report_lf
    input_tables, sample_history_lf, sample_detail_by_report_lf = get_estimate_data.get_input_data(selected)
    print('input tables', f"Total loading time: {time.perf_counter() - async_start_counter:.2f} seconds")
    SAMPLE_DETAIL_COLS = [
        item
        for item in input_tables["sample_detail_by_ui"].columns
        if not (item.startswith("_") or item == 'reptstate')
    ]
    SAMPLE_DETAIL_SUMMARY_ROWS = input_tables["sample_detail_by_ui"].to_dicts()
    LINE_GRAPH = line_graph_context(input_tables["line_graph"])
    LINE_GRAPH_TABLE = line_graph_table_context(input_tables["line_graph"])
    EST_CALC = (
        input_tables["est_calc"].head(1).to_dicts()[0]
        if not input_tables["est_calc"].is_empty()
        else {}
    )
    sample_link = (
        input_tables["sample_summary"]
        .head(1)
        .with_columns(
            (pl.col.wcm.cast(pl.Int64) / pl.col.wpm.cast(pl.Int64))
            .round(4)
            .alias("Link")
        )
        .item(0, "Link")
        if not input_tables["sample_summary"].is_empty()
        else ""
    )
    cov_row_ind = (
        input_tables["sample_summary"]
        .select(pl.arg_where(pl.col.Sample == pl.lit("Coverage")))
        .item(0, 0)
        + 1
    )
    MIDDLE_TABLES = [
        middle_table_context(
            "Estimate Comparison",
            input_tables["est_comparison"],
            hidden_columns={"otm_pct", "oty_pct"},
            inline_ratio_columns={
                "otm": "otm_pct",
                "oty": "oty_pct",
            },
            highlighted_cells=estimate_comparison_highlighted_cells(
                input_tables["est_comparison"]
            ),
            row_classes={"P-Pub": "has-section-separator"},
        ),
        middle_table_context(
            "Sample Summary",
            input_tables["sample_summary"],
            {cov_row_ind, cov_row_ind+1},
            link_value=sample_link,
        ),
    ]

    if 'model_info' in input_tables:
        isg3 = 'beta' in input_tables['model_info'].columns
        betaval = None if not isg3 else input_tables['model_info'].item(0, 'beta')
        y2val = None if not isg3 else input_tables['model_info'].item(0, 'y2_m')
        MIDDLE_TABLES = MIDDLE_TABLES + [
            middle_table_context(
                "Model Info", input_tables["model_info"].select(pl.exclude('beta', 'y2_m')), 
                decimal_columns={"Link", "Weight"},
                betaval = betaval,
                y2val = y2val
            ),
       ]
    # print('emojis: ', emojis.get(int(selected['series']), "none"))
    # msa_map = get_msa_map(selected['area'], selected['state'])
    print('before return templates', f"Total loading time: {time.perf_counter() - async_start_counter:.2f} seconds")
    #####################################################################################
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            **state_area_series_dt,
            **dates,
            "selected": selected,
            "nav": nav,
            "dropdowns": dropdown_context(selected, nav, state_area_series_dt, dates),
            "series_info": series_info_context(selected, input_tables["series_info"]),
            "middle_tables": MIDDLE_TABLES,
            "line_graph": LINE_GRAPH,
            "line_graph_table": LINE_GRAPH_TABLE,
            "est_calc": EST_CALC,
            # 'sample_detail_columns': [col for col in SAMPLE_DETAIL_COLS if col != 'reptw'], 
            'sample_detail_columns': list(dict.fromkeys([col for col in SAMPLE_DETAIL_COLS if col not in ['reptw', 'wpm', 'wcm']])),
            "sample_detail_rows": SAMPLE_DETAIL_SUMMARY_ROWS,
            'emojis': emojis.get(int(selected['series']), ""),
            # 'mapimg': msa_map
        },
    )