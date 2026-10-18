"""The shop's departments and categories, and its whole catalogue (for "do we already sell this?").
Read from BigQuery and cached."""
import datetime as dt
import re
import time

from config import MOCK
from agents import bq, mock

_cache: list[dict] | None = None
_catalog: tuple[float, list[dict]] | None = None
_STOP = {"for", "the", "and", "with", "men", "mens", "women", "womens", "a", "of", "in", "new", "pack"}


async def get_categories() -> list[dict]:
    global _cache
    if _cache is None:
        _cache = mock.categories() if MOCK else await bq.run("categories")
    return _cache


async def get_catalog() -> list[dict]:
    """Every product with its last 12 months of sales (sql/products_list.sql). Cached for 10 minutes."""
    global _catalog
    if _catalog and time.monotonic() - _catalog[0] < 600:
        return _catalog[1]
    rows = mock.products_list() if MOCK else await bq.run("products_list")
    _catalog = (time.monotonic(), rows)
    return rows


_stock: tuple[float, dict] | None = None
_suppliers: tuple[float, list] | None = None


async def category_suppliers(category: str) -> list[dict]:
    """Suppliers that already make products in this category, with their minimum order (moq)."""
    global _suppliers
    if not (_suppliers and time.monotonic() - _suppliers[0] < 600):
        rows = mock.suppliers_list() if MOCK else await bq.run("suppliers_list")
        _suppliers = (time.monotonic(), rows)
    return [r for r in _suppliers[1] if category in [c.strip() for c in (r.get("categories") or "").split(",")]]


async def get_stock() -> dict[str, dict]:
    """Stock position of every active product by SKU (sql/inventory_status.sql). Cached for 10 minutes."""
    global _stock
    if _stock and time.monotonic() - _stock[0] < 600:
        return _stock[1]
    rows = mock.inventory_status() if MOCK else await bq.run("inventory_status")
    _stock = (time.monotonic(), {r["sku"]: r for r in rows})
    return _stock[1]


def _tokens(text: str) -> set[str]:
    words = {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", (text or "").lower())}
    return {w for w in words if len(w) > 2 and w not in _STOP}


def months_on_sale(row: dict) -> float:
    """Months the product was on sale in the last 12 (at least 1)."""
    launch = row.get("launch_date")
    try:
        launch = launch if isinstance(launch, dt.date) else dt.date.fromisoformat(str(launch)[:10])
        days = (dt.date.today() - launch).days
    except (TypeError, ValueError):
        return 12.0
    return max(1.0, min(12.0, days / 30.4))


def match_catalog(name: str, catalog: list[dict], department=None, category=None, limit=3) -> list[dict]:
    """The shop's own products closest to `name`, by shared words (code, not Gemini).
    score = share of the new product's words found in the existing product's name (0 to 1)."""
    want = _tokens(name)
    if not want:
        return []
    out = []
    for row in catalog:
        if department and row["department"] != department:
            continue
        if category and row["category"] != category:
            continue
        score = len(want & _tokens(row["name"])) / len(want)
        if score > 0:
            months = months_on_sale(row)
            out.append({**row, "score": round(score, 2),
                         "per_month": round((row.get("units_12m") or 0) / months, 1)})
    out.sort(key=lambda r: (-r["score"], -(r.get("units_12m") or 0)))
    return out[:limit]


def allowed_by_department(categories: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in categories:
        out.setdefault(row["department"], []).append(row["category"])
    return {dept: sorted(set(cats)) for dept, cats in out.items()}
