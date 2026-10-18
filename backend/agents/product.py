"""Product agent: turns the seller's words (and optional photo) into structured attributes,
mapped onto a real category of the store so the other agents can find comparables."""
import base64
import difflib

from pydantic import BaseModel

from config import MOCK
from agents import llm, mock
from agents.catalog import allowed_by_department
from agents.common import evidence


class ProductOut(BaseModel):
    fits_shop: bool
    what_it_is: str
    department: str
    category: str
    product_type: str
    key_attributes: list[str]
    short_description: str
    search_query: str


def _image_part(data_url: str):
    from google.genai import types
    header, b64 = data_url.split(",", 1)
    mime = header.split(";")[0].replace("data:", "") or "image/jpeg"
    return types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime)


def _closest(value: str | None, options: list[str]) -> str:
    match = difflib.get_close_matches(value or "", options, n=1, cutoff=0)
    return match[0] if match else options[0]


async def run_product(req, categories, brief: str = ""):
    allowed = allowed_by_department(categories)

    if MOCK:
        data = mock.product(req, allowed)
    else:
        lines = "\n".join(f"- {dept}: {', '.join(cats)}" for dept, cats in allowed.items())
        prompt = f"""You are the Product agent in GoNoGo, a tool that helps a retailer decide whether to launch a new product.
Turn the seller's product idea into structured attributes.

The shop (judge the product against this definition):
{brief or '(not given)'}

Product name: {req.name}
Description: {req.description or "(none)"}
Department chosen by the seller: {req.department or "(not given)"}
Category chosen by the seller: {req.category or "(not given)"}
A product photo is attached: {"yes" if req.image else "no"}

Allowed departments and categories (copy them exactly):
{lines}

Rules:
- department must be exactly one of: {", ".join(allowed)}.
- category must be copied exactly from the allowed list for that department.
- If the seller already chose a valid department or category, keep it.
- product_type: two to four words, e.g. "high-waist leggings".
- key_attributes: three to five short attributes (material, fit, use, style).
- short_description: one plain sentence a shopper would understand.
- search_query: the phrase an Indian online shopper would type to find this product.
- what_it_is: two to five plain words naming what the product actually is, e.g. "brass puja lamp".
- fits_shop: true only if the product genuinely is the kind of item in the chosen category, the shop sells
  that kind of item at all, and it is not on the shop's "never sells" list. A brass lamp, a phone case or a toy is not apparel, even if the seller
  picked a category for it. Judge from the photo and description, not the category the seller chose."""
        parts = [prompt]
        if req.image:
            parts.append(_image_part(req.image))
        data, _ = await llm.generate_json(parts, schema=ProductOut, temperature=0.1)

    # Never trust the model blindly: force a valid department and category.
    dept = req.department if req.department in allowed else data.get("department")
    if dept not in allowed:
        dept = _closest(dept, list(allowed))
    cat = req.category if req.category in allowed[dept] else data.get("category")
    if cat not in allowed[dept]:
        cat = _closest(cat, allowed[dept])
    data.update(department=dept, category=cat)
    data["fits_shop"] = data.get("fits_shop") is not False
    data.setdefault("what_it_is", data.get("product_type", ""))

    ev = evidence(
        summary=[
            ["Department", dept],
            ["Category in store data", cat],
            ["Product type", data.get("product_type", "-")],
            ["Fits a category the shop sells", "yes" if data["fits_shop"] else f"no: {data['what_it_is']}"],
            ["Attributes", ", ".join(data.get("key_attributes", [])) or "-"],
        ],
        note="Read from the seller's description" + (" and photo" if req.image else "") + " by Gemini.",
    )
    return data, ev
