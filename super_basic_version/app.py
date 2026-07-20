from pathlib import Path

import polars as pl
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent

# Sample table: one row per report.
SAMPLE_TABLE = pl.read_csv(
    BASE_DIR / "sample_table.csv",
    schema_overrides={"parent_report": pl.String, "report": pl.String},
)

app = FastAPI(title="Super Basic Version")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "columns": SAMPLE_TABLE.columns,
            "rows": SAMPLE_TABLE.to_dicts(),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
