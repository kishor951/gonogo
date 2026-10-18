"""Start from a photo: Gemini (vision) finds every product in the photo (up to 6), with a box around each
(box_2d = [ymin, xmin, ymax, xmax] on a 0-1000 scale), and for each one a name, description, department and
category from the shop's own list. The seller picks one; its suggested selling price comes from the shop's
comparable products in BigQuery, never from Gemini."""
import asyncio

from pydantic import BaseModel

from config import MOCK
from agents import bq, llm, mock
from agents.catalog import allowed_by_department, get_categories
from agents.settings import load_brief
from agents.product import _closest, _image_part


class AutofillItem(BaseModel):
    box_2d: list[int]
    fits_shop: bool
    what_it_is: str
    reason: str
    name: str
    description: str
    department: str
    category: str
    product_type: str
    key_attributes: list[str]


class AutofillOut(BaseModel):
    items: list[AutofillItem]


def _box(value) -> list[int] | None:
    """A usable box, [ymin, xmin, ymax, xmax] on 0-1000, or None."""
    try:
        y0, x0, y1, x1 = (max(0, min(1000, int(v))) for v in value)
    except (TypeError, ValueError):
        return None
    return [y0, x0, y1, x1] if y1 - y0 >= 20 and x1 - x0 >= 20 else None


def _x99(value: float) -> int:
    """Round to a shop-style price ending in 99 (₹1,199)."""
    return max(99, int(round(value / 100) * 100 - 1))


def _weighted_median(rows: list[dict]) -> float | None:
    """The price at which half of the units sold were sold (falls back to the plain median list price)."""
    total = sum(r["units_12m"] for r in rows)
    if not total:
        prices = sorted(r["price_inr"] for r in rows)
        return prices[len(prices) // 2] if prices else None
    acc = 0
    for r in sorted(rows, key=lambda r: r["price_inr"]):
        acc += r["units_12m"]
        if acc >= total / 2:
            return r["price_inr"]
    return None


def price_suggestion(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    prices = sorted(r["price_inr"] for r in rows)
    pick = lambda q: prices[min(len(prices) - 1, int(q * len(prices)))]
    typical = _weighted_median(rows)
    best = max(rows, key=lambda r: r["units_12m"])
    return {
        "suggested_inr": _x99(typical) if typical else None,
        "low_inr": pick(0.25),
        "high_inr": pick(0.75),
        "min_inr": prices[0],
        "max_inr": prices[-1],
        "products": len(rows),
        "best_seller": {"name": best["name"], "price_inr": best["price_inr"], "units_12m": best["units_12m"]},
    }


async def run_autofill(image: str, hint: str = "") -> dict:
    allowed = allowed_by_department(await get_categories())
    brief = await load_brief(allowed)
    if MOCK:
        raw = mock.autofill(hint, allowed)
    else:
        lines = "\n".join(f"- {dept}: {', '.join(cats)}" for dept, cats in allowed.items())
        prompt = f"""You are the Product agent in GoNoGo. A seller photographed product(s) they are thinking of stocking
in their Indian online fashion shop. Find every separate product in the photo that someone could sell
(each garment, and also shoes, bags, jewellery or other items), up to 6, biggest and most central first.
A person is not a product, but each thing they wear is. Ignore background and furniture.

The shop (judge each product against this definition):
{brief}

Words from the seller (may be empty): {hint or "(none)"}

The shop's departments and categories (copy them exactly):
{lines}

For each product give:
- box_2d: [ymin, xmin, ymax, xmax] around just that product, each from 0 to 1000 (a share of the photo's height/width).
- what_it_is: two to five plain words naming what it actually is, e.g. "black running shorts", "brass puja lamp".
- fits_shop: false if it is not clothing that genuinely belongs in one of these categories (shoes, a lamp, a phone,
  food or a toy are not), if it is on the shop's "never sells" list, or if it clearly doesn't suit the shop's
  range, customers or price positioning.
- reason: if fits_shop is false, one short plain sentence saying why, in the shop's terms
  (e.g. "Evening gowns are outside Urban Loom's everyday, mid-market range."); otherwise an empty string.
- name: a short shop-style product name, 3 to 6 words, e.g. "High-waist Side-pocket Leggings".
- description: one or two plain sentences on material, fit, style and use, as seen in the photo.
- department: exactly one of {", ".join(allowed)}.
- category: copied exactly from that department's list (your best match, even when fits_shop is false).
- product_type: two to four words, e.g. "high-waist leggings".
- key_attributes: three to five short attributes (material, fit, colour, style).
Do not guess prices."""
        raw, _ = await llm.generate_json([prompt, _image_part(image)], schema=AutofillOut, temperature=0.1)

    items = []
    for i, data in enumerate((raw.get("items") or [])[:6], start=1):
        # Never trust the model blindly: force a valid department and category.
        dept = data.get("department")
        if dept not in allowed:
            dept = _closest(dept, list(allowed))
        cat = data.get("category")
        if cat not in allowed[dept]:
            cat = _closest(cat, allowed[dept])
        fits = data.get("fits_shop") is not False
        items.append({**data, "n": i, "box": _box(data.get("box_2d")), "fits_shop": fits,
                      # don't squeeze a product the shop doesn't sell into the nearest category
                      "department": dept if fits else None, "category": cat if fits else None})
        items[-1].pop("box_2d", None)

    # a suggested price for each product the shop sells (one query per category)
    keys = sorted({(it["department"], it["category"]) for it in items if it["fits_shop"]})

    async def suggest(dept, cat):
        params = {"department": dept, "category": cat}
        rows = mock.price_suggestion(params) if MOCK else await bq.run("price_suggestion", params)
        return price_suggestion(rows)
    prices = dict(zip(keys, await asyncio.gather(*(suggest(d, c) for d, c in keys))))
    for it in items:
        it["price"] = prices.get((it["department"], it["category"])) if it["fits_shop"] else None

    first = next((it for it in items if it["fits_shop"]), items[0] if items else None)
    return {"items": items, "selected": first["n"] if first else None,
            # the single-product shape older pages used
            "product": first, "price": first["price"] if first else None}
