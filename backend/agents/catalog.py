"""The shop's departments and categories, and its whole catalogue (for "do we already sell this?").
Read from BigQuery and cached."""
import datetime as dt
import re
import time

from config import MOCK
from agents import bq, mock

_cache: list[dict] | None = None
_catalog: tuple[float, list[dict]] | None = None
_STOP = {"for", "the", "and", "with", "men", "mens", "women", "womens", "a", "of", "in", "new", "pack",
         # describing words that don't make it a different product
         "color", "colour", "colored", "coloured", "shade", "variant", "version"}


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
    # plural to singular ("shirts" -> "shirt"), but never "brass" -> "bra" or "dress" -> "dre"
    words = {w[:-1] if w.endswith("s") and not w.endswith("ss") and len(w) > 3 else w
             for w in re.findall(r"[a-z0-9]+", (text or "").lower())}
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


# Colour words: a colour makes a variant of a product, not a different product. The shop's own names are
# "Style - Colour", so their colour parts are added to these at match time.
_COLOURS = {"black", "white", "red", "blue", "green", "yellow", "pink", "purple", "orange", "brown", "grey", "gray",
            "navy", "olive", "beige", "cream", "maroon", "wine", "teal", "sage", "mustard", "rust", "indigo", "khaki",
            "charcoal", "ivory", "peach", "lavender", "mint", "coral", "tan", "camel", "burgundy", "silver", "gold",
            "multi", "multicolour", "multicolor", "off", "light", "dark"}


def _split(name: str) -> tuple[str, str]:
    """'Longline Coat - Olive' -> ('Longline Coat', 'Olive'). Names without ' - ' have no colour part."""
    style, sep, colour = (name or "").rpartition(" - ")
    return (style, colour) if sep else (name or "", "")


def _colour_words(catalog: list[dict]) -> set[str]:
    words = set(_COLOURS)
    for row in catalog:
        words |= _tokens(_split(row["name"])[1])
    return words


def match_catalog(name: str, catalog: list[dict], department=None, category=None, limit=3) -> list[dict]:
    """The shop's own products closest to `name`, by shared words (code, not Gemini). Colours are left out of
    the score, so "Longline Coat - Black" matches "Longline Coat - Olive" (same style), not "Longline Gym Tee - Black".
    score = share of the new product's style words found in the existing product's style (0 to 1). If every word of an
    existing style (2+ words) is in `name`, it's the same style even with extra description: score 0.9+.
    same_style: the same style, any colour. same_colour: every colour word of that product is in `name` too."""
    colours = _colour_words(catalog)
    words = _tokens(name)
    want = words - colours
    if not want:
        return []
    out = []
    for row in catalog:
        if department and row["department"] != department:
            continue
        if category and row["category"] != category:
            continue
        style, colour = _split(row["name"])
        have = _tokens(style) - colours
        if not have:
            continue
        shared = len(want & have)
        score = shared / len(want)
        same_style = have == want or (len(have) >= 2 and have <= want)
        if same_style:
            score = max(score, 0.9)   # the whole existing style is in the question
        if score > 0:
            row_colours = _tokens(colour)
            months = months_on_sale(row)
            out.append({**row, "score": round(score, 2), "same_style": same_style,
                        "same_colour": bool(row_colours) and row_colours <= words,
                        "per_month": round((row.get("units_12m") or 0) / months, 1)})
    out.sort(key=lambda r: (-r["score"], not r["same_style"], not r["same_colour"], -(r.get("units_12m") or 0)))
    return out[:limit]


def same_style_variants(name: str, catalog: list[dict]) -> list[dict]:
    """Every active product of the same style as `name`, in any colour."""
    return [r for r in match_catalog(name, [r for r in catalog if r.get("status") == "active"], limit=50)
            if r["same_style"]]


def allowed_by_department(categories: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in categories:
        out.setdefault(row["department"], []).append(row["category"])
    return {dept: sorted(set(cats)) for dept, cats in out.items()}
