from pathlib import Path

import polars as pl
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent

# --- Input tables ---

# Sample table: one row per report. A parent_report can have multiple reports.
SAMPLE_TABLE = pl.read_csv(
    BASE_DIR / "sample_table.csv",
    schema_overrides={"parent_report": pl.String, "report": pl.String},
)

# Time series table: one row per month.
TIME_SERIES_TABLE = pl.read_csv(BASE_DIR / "time_series_table.csv")

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def sum_by_parent_report(sample_df: pl.DataFrame) -> pl.DataFrame:
    # Sum the report-level sample rows up to one row per parent_report.
    return (
        sample_df.group_by("parent_report")
        .agg(
            pl.len().alias("report_count"),
            pl.col("pm").sum(),
            pl.col("cm").sum(),
            pl.col("otm").sum(),
        )
        .sort("parent_report")
    )


def line_graph_context(ts_df: pl.DataFrame) -> dict:
    # Chart.js payload: labels and one dataset.
    sorted_df = ts_df.sort("year", "month")
    labels = [
        f"{MONTH_LABELS[row['month'] - 1]} {row['year']}" for row in sorted_df.to_dicts()
    ]
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Estimate",
                "data": sorted_df.get_column("estimate").to_list(),
                "borderColor": "#f97316",
            },
            {
                "label": "Benchmark",
                "data": sorted_df.get_column("benchmark").to_list(),
                "borderColor": "#15803d",
            },
        ],
    }


# --- FastAPI setup ---

app = FastAPI(title="Basic Version")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


class ParentReportDetailsRequest(BaseModel):
    parent_report: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "line_graph": line_graph_context(TIME_SERIES_TABLE),
            "parent_report_columns": ["parent_report", "report_count", "pm", "cm", "otm"],
            "parent_report_rows": sum_by_parent_report(SAMPLE_TABLE).to_dicts(),
        },
    )


@app.post("/api/parent-report-details", response_class=HTMLResponse)
async def api_parent_report_details(payload: ParentReportDetailsRequest) -> HTMLResponse:
    # Return rendered <tr> elements for the reports behind one parent_report.
    details_df = SAMPLE_TABLE.filter(
        pl.col("parent_report") == payload.parent_report
    ).sort("report")
    html = templates.env.get_template("_parent_report_detail_rows.html").render(
        detail_rows=details_df.to_dicts(),
        parent_report=payload.parent_report,
    )
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
