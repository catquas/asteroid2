from pathlib import Path

import polars as pl
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent

# --- Input tables ---

# Sample table: one row per report. A ui can have multiple reports.
SAMPLE_TABLE = pl.read_csv(
    BASE_DIR / "sample_table.csv",
    schema_overrides={"ui": pl.String, "report": pl.String},
)

# Time series table: one row per month.
TIME_SERIES_TABLE = pl.read_csv(BASE_DIR / "time_series_table.csv")

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def sum_by_ui(sample_df: pl.DataFrame) -> pl.DataFrame:
    # Sum the report-level sample rows up to one row per ui.
    return (
        sample_df.group_by("ui")
        .agg(
            pl.len().alias("report_count"),
            pl.col("pm").sum(),
            pl.col("cm").sum(),
            pl.col("otm").sum(),
        )
        .sort("ui")
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
                "label": "Employment",
                "data": sorted_df.get_column("emp").to_list(),
                "borderColor": "#f97316",
            }
        ],
    }


# --- FastAPI setup ---

app = FastAPI(title="Basic Version")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


class UiDetailsRequest(BaseModel):
    ui: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "line_graph": line_graph_context(TIME_SERIES_TABLE),
            "ui_columns": ["ui", "report_count", "pm", "cm", "otm"],
            "ui_rows": sum_by_ui(SAMPLE_TABLE).to_dicts(),
        },
    )


@app.post("/api/ui-details", response_class=HTMLResponse)
async def api_ui_details(payload: UiDetailsRequest) -> HTMLResponse:
    # Return rendered <tr> elements for the reports behind one ui.
    details_df = SAMPLE_TABLE.filter(pl.col("ui") == payload.ui).sort("report")
    html = templates.env.get_template("_ui_detail_rows.html").render(
        detail_columns=["report", "pm", "cm", "otm"],
        detail_rows=details_df.to_dicts(),
        ui=payload.ui,
    )
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
