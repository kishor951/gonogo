"""GoNoGo web server on Cloud Run.

Pages:  /              Discovery: propose a product, get the verdict
        /shop          Shop profile: what the shop is (the definition the agents judge products against)
        /business      Business: the shop's numbers and its rules (/organisation redirects here)
        /products, /inventory, /sales, /returns, /customers, /suppliers   shop data (one shared page, data.html)
API:    GET /api/categories, GET /api/business, GET /api/pages/<name>, GET/PUT /api/settings,
        POST /api/autofill (photo -> product details + suggested price), POST /api/evaluate,
        POST /api/evaluate/stream (same, with live agent events), GET /health
"""
import asyncio
import json
import pathlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from access import check_code, gate
from limits import check_limit
from config import DEFAULT_ASSUMPTIONS, GEMINI_MODEL, MOCK
from agents.autofill import run_autofill
from agents.budget import get_budget
from agents.business import get_overview
from agents.catalog import allowed_by_department, get_categories
from agents.orchestrator import evaluate
from agents.pages import PAGES, get_page
from agents.settings import clean_rules, get_settings, save_settings, shop_brief

STATIC = pathlib.Path(__file__).resolve().parent / "static"

app = FastAPI(title="GoNoGo", description="Know if a product will sell before you stock it.")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AccessRequest(BaseModel):
    code: str = Field("", max_length=100)


@app.middleware("http")
async def revalidate_pages(request, call_next):
    """Pages, scripts and styles change with every deploy: browsers must re-check them (an unchanged file
    still comes back as a quick 304), so nobody runs a new page with an old cached shared.js or app.css."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


class EvaluateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str = Field("", max_length=600)
    department: str | None = None
    category: str | None = None
    cost: float = Field(..., gt=0)
    price: float | None = Field(None, gt=0)
    image: str | None = None            # optional data URL (data:image/jpeg;base64,...)
    assumptions: dict | None = None     # the shop's numbers and rules (from /api/settings)


class AutofillRequest(BaseModel):
    image: str = Field(..., min_length=30)     # data URL (data:image/jpeg;base64,...)
    hint: str = Field("", max_length=300)      # optional words from the seller


class SettingsRequest(BaseModel):
    # Send only what changed: the Business page sends rules, the Shop profile page sends name + profile.
    shop_name: str | None = Field(None, max_length=80)
    rules: dict | None = None
    profile: dict | None = None


def _short(exc: Exception) -> str:
    return str(exc).split("\n")[0][:300]


# The access-code gate runs first (it is added last, so it wraps everything else).
app.middleware("http")(gate)


@app.get("/access")
def access_page():
    return FileResponse(STATIC / "access.html")


@app.post("/api/access")
async def access(req: AccessRequest, request: Request):
    return check_code(request, req.code)


@app.get("/")
def discovery_page():
    return FileResponse(STATIC / "index.html")


@app.get("/business")
def business_page():
    return FileResponse(STATIC / "business.html")


def _data_page():
    return FileResponse(STATIC / "data.html")


for _name in PAGES:
    app.add_api_route(f"/{_name}", _data_page, methods=["GET"], include_in_schema=False)


@app.get("/shop")
def shop_page():
    return FileResponse(STATIC / "shop.html")


@app.get("/organisation")
def organisation_page():
    return RedirectResponse("/business", status_code=308)


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
        raise HTTPException(status_code=502, detail=f"Could not read categories from BigQuery: {_short(exc)}")


@app.get("/api/business")
async def business():
    try:
        return await get_overview()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not read the shop's data from BigQuery: {_short(exc)}. "
                                                    "Check the dataset is loaded (scripts/load_to_bigquery.py).")


@app.get("/api/pages/{name}")
async def page_data(name: str):
    if name not in PAGES:
        raise HTTPException(status_code=404, detail=f"There is no '{name}' page.")
    try:
        return await get_page(name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not read the {name} data from BigQuery: {_short(exc)}. "
                                                    "Check the dataset is loaded (scripts/load_to_bigquery.py).")


@app.get("/api/budget")
async def budget():
    """The experiment budget with the shop's saved rules, and every step of the sum."""
    try:
        try:
            rules = (await get_settings())["rules"]
        except Exception:
            rules = clean_rules({})
        return await get_budget(rules)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not work out the budget from BigQuery: {_short(exc)}")


@app.get("/api/settings")
async def read_settings():
    try:
        s = await get_settings()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not read the shop's rules from BigQuery: {_short(exc)}")
    try:   # the exact definition the agents read, shown on the Shop profile page
        s["brief"] = shop_brief(s["shop_name"], s["profile"], allowed_by_department(await get_categories()))
    except Exception:
        s["brief"] = None
    return s


@app.put("/api/settings")
async def write_settings(req: SettingsRequest, request: Request):
    check_limit(request, "settings")
    try:
        return await save_settings(req.shop_name, req.rules, req.profile)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not save the rules to BigQuery: {_short(exc)}. "
                                                    "The service account needs roles/bigquery.dataEditor.")


@app.post("/api/autofill")
async def autofill(req: AutofillRequest, request: Request):
    if len(req.image) > 6_000_000:
        raise HTTPException(status_code=413, detail="The photo is too large. Use one under 4 MB.")
    check_limit(request, "photo")
    if not req.image.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="That file isn't a photo. Use a JPG or PNG image.")
    try:
        return await run_autofill(req.image, req.hint)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't read the photo: {_short(exc)}. "
                                                    "Try again, or type the product name instead.")


@app.post("/api/evaluate/stream")
async def evaluate_stream(req: EvaluateRequest, request: Request):
    """The same evaluation, streamed as one JSON object per line while the agents work:
    start / done / failed / skipped events for each agent, then {"type": "result", "data": ...}
    (or {"type": "error", "detail": ...})."""
    if req.image and len(req.image) > 6_000_000:
        raise HTTPException(status_code=413, detail="The photo is too large. Use one under 4 MB.")
    check_limit(request)
    queue: asyncio.Queue = asyncio.Queue()

    async def run():
        try:
            out = await evaluate(req, emit=queue.put)
            await queue.put({"type": "result", "data": out})
        except ValueError as exc:
            await queue.put({"type": "error", "detail": str(exc)})
        except Exception as exc:
            await queue.put({"type": "error", "detail": f"Something went wrong: {_short(exc)}. Try again."})
        finally:
            await queue.put(None)

    async def lines():
        task = asyncio.create_task(run())
        try:
            while (event := await queue.get()) is not None:
                yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/evaluate")
async def evaluate_product(req: EvaluateRequest, request: Request):
    if req.image and len(req.image) > 6_000_000:
        raise HTTPException(status_code=413, detail="The photo is too large. Use one under 4 MB.")
    check_limit(request)
    try:
        return await evaluate(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
