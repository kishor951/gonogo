"""GoNoGo web server on Cloud Run.

Pages:  /              Discovery: propose a product, get the verdict
        /organisation  Organisation: your business data and your shop's rules
API:    GET /api/categories, GET /api/organisation, POST /api/evaluate, GET /health
"""
import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import DEFAULT_ASSUMPTIONS, GEMINI_MODEL, MOCK
from agents.catalog import get_categories
from agents.orchestrator import evaluate
from agents.organisation import get_overview

STATIC = pathlib.Path(__file__).resolve().parent / "static"

app = FastAPI(title="GoNoGo", description="Know if a product will sell before you stock it.")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class EvaluateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str = Field("", max_length=600)
    department: str | None = None
    category: str | None = None
    cost: float = Field(..., gt=0)
    price: float | None = Field(None, gt=0)
    image: str | None = None            # optional data URL (data:image/jpeg;base64,...)
    assumptions: dict | None = None     # the shop's numbers and rules, from the Organisation page


@app.get("/")
def discovery_page():
    return FileResponse(STATIC / "index.html")


@app.get("/organisation")
def organisation_page():
    return FileResponse(STATIC / "organisation.html")


@app.get("/health")
def health():
    return {"status": "ok", "mock": MOCK, "model": GEMINI_MODEL}


@app.get("/api/defaults")
def defaults():
    return DEFAULT_ASSUMPTIONS


@app.get("/api/categories")
async def categories():
    try:
        return await get_categories()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not read categories from BigQuery: {exc}")


@app.get("/api/organisation")
async def organisation():
    try:
        return await get_overview()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not read the business data from BigQuery: {exc}")


@app.post("/api/evaluate")
async def evaluate_product(req: EvaluateRequest):
    if req.image and len(req.image) > 6_000_000:
        raise HTTPException(status_code=413, detail="The photo is too large. Use one under 4 MB.")
    try:
        return await evaluate(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
