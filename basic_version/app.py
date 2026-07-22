from pathlib import Path

import polars as pl
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent

# --- Input tables ---

# Sample table: one row per report. A parent_report can have multiple reports.
SAMPLE_TABLE = pl.read_csv(BASE_DIR / "sample_table.csv")

# Time series table: one row per month.
TIME_SERIES_TABLE = pl.read_csv(BASE_DIR / "time_series_table.csv")

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --- FastAPI setup ---

app = FastAPI(title="Basic Version")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

DATA_SERIES_OPTIONS = (
    TIME_SERIES_TABLE.get_column("data_series").unique(maintain_order=True).to_list()
)
SAMPLE_GROUP_OPTIONS = (
    SAMPLE_TABLE.get_column("sample_group").unique(maintain_order=True).to_list()
)


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request, data_series: str = "", sample_group: str = ""
) -> HTMLResponse:
    # The form submits data_series/sample_group as query params; invalid or
    # missing values fall back to the first option so the page always renders.
    if data_series not in DATA_SERIES_OPTIONS:
        data_series = DATA_SERIES_OPTIONS[0]
    if sample_group not in SAMPLE_GROUP_OPTIONS:
        sample_group = SAMPLE_GROUP_OPTIONS[0]

    time_series_df = TIME_SERIES_TABLE.filter(pl.col("data_series") == data_series)
    sample_df = SAMPLE_TABLE.filter(pl.col("sample_group") == sample_group)

    # Sum the report-level sample rows up to one row per parent_report.
    parent_report_df = (
        sample_df.group_by("parent_report")
        .agg(
            pl.len().alias("report_count"),
            pl.col("pm").sum(),
            pl.col("cm").sum(),
            pl.col("otm").sum(),
        )
        .sort("parent_report")
    )
    parent_report_rows = parent_report_df.to_dicts()

    # Chart.js payload: labels and one dataset per line.
    sorted_ts_df = time_series_df.sort("year", "month")
    line_graph = {
        "labels": [
            f"{MONTH_LABELS[row['month'] - 1]} {row['year']}"
            for row in sorted_ts_df.to_dicts()
        ],
        "datasets": [
            {
                "label": "Estimate",
                "data": sorted_ts_df.get_column("estimate").to_list(),
                "borderColor": "#f97316",
            },
            {
                "label": "Benchmark",
                "data": sorted_ts_df.get_column("benchmark").to_list(),
                "borderColor": "#15803d",
            },
        ],
    }

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "data_series_options": DATA_SERIES_OPTIONS,
            "sample_group_options": SAMPLE_GROUP_OPTIONS,
            "selected_data_series": data_series,
            "selected_sample_group": sample_group,
            "line_graph": line_graph,
            "parent_report_columns": ["parent_report", "report_count", "pm", "cm", "otm"],
            "parent_report_rows": parent_report_rows,
        },
    )


@app.post("/api/parent-report-details", response_class=HTMLResponse)
async def api_parent_report_details(parent_report: str) -> HTMLResponse:
    # Return rendered <tr> elements for the reports behind one parent_report.
    details_df = SAMPLE_TABLE.filter(
        pl.col("parent_report") == parent_report
    ).sort("report")
    html = templates.env.get_template("_parent_report_detail_rows.html").render(
        detail_rows=details_df.to_dicts(),
        parent_report=parent_report,
    )
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
