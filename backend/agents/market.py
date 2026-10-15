"""Market agent: Gemini with Grounding with Google Search finds what similar products sell for
online in India right now, which competitor products exist, and keeps the sources.

Competitor links are never invented: each product is linked to a real page that Google Search
returned (matched by store and product words). If no matching page was found, the link is a
search on that store for the product name, and is labelled as a search.
"""
import asyncio
import re
import urllib.error
import urllib.parse
import urllib.request

from config import MOCK
from agents import llm, mock
from agents.common import evidence, inr

STORE_SEARCH = {
    "amazon": "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "myntra": "https://www.myntra.com/{slug}",
    "ajio": "https://www.ajio.com/search/?text={q}",
    "meesho": "https://www.meesho.com/search?q={q}",
}
_STOP = {"for", "the", "and", "with", "women", "womens", "men", "mens", "buy", "online", "india", "in", "of", "a"}


def _num(value):
    try:
        return float(str(value).replace(",", "").replace("₹", "").replace("Rs.", "").strip())
    except (TypeError, ValueError):
        return None


def _store_key(store: str) -> str:
    words = re.findall(r"[a-z]+", (store or "").lower())
    return words[0] if words else ""


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2 and t not in _STOP}


def search_link(store: str, name: str) -> str:
    q = urllib.parse.quote_plus(name)
    template = STORE_SEARCH.get(_store_key(store))
    if template:
        return template.format(q=q, slug=re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))
    return "https://www.google.com/search?tbm=shop&q=" + urllib.parse.quote_plus(f"{store} {name}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _resolve(url: str) -> str:
    """Grounding sources are Google redirect links; find the real page address behind them."""
    if "grounding-api-redirect" not in url:
        return url
    opener = urllib.request.build_opener(_NoRedirect)
    for method in ("HEAD", "GET"):
        try:
            opener.open(urllib.request.Request(url, method=method, headers={"User-Agent": "Mozilla/5.0"}), timeout=4)
        except urllib.error.HTTPError as exc:
            location = exc.headers.get("Location")
            if location:
                return location
        except Exception:
            pass
    return url


async def resolve_sources(sources: list[dict]) -> list[dict]:
    urls = await asyncio.gather(*(asyncio.to_thread(_resolve, s["url"]) for s in sources))
    out = []
    for s, real in zip(sources, urls):
        domain = urllib.parse.urlparse(real).netloc.replace("www.", "")
        if "grounding-api-redirect" in real:
            domain = s["title"]
        out.append({"title": domain or s["title"], "url": real})
    return out


def link_products(products: list[dict], sources: list[dict]) -> list[dict]:
    """Attach a real search-result page to each product where one matches; otherwise a store search."""
    linked = []
    for p in products:
        name, store = p.get("name", "").strip(), p.get("store", "").strip()
        if not name:
            continue
        key, want = _store_key(store), _tokens(name)
        best, best_score = None, 0
        for s in sources:
            if key and key in s["url"].lower():
                score = len(want & _tokens(urllib.parse.urlparse(s["url"]).path))
                if score > best_score:
                    best, best_score = s, score
        if best and best_score >= 2:
            url, kind = best["url"], "product"
        else:
            url, kind = search_link(store, name), "search"
        linked.append({"name": name, "store": store or "-", "price_inr": _num(p.get("price_inr")),
                       "url": url, "link_type": kind})
    return linked[:6]


async def run_market(product: dict, price_inr: float):
    if MOCK:
        data, sources = mock.market(product, price_inr)
    else:
        prompt = f"""You are the Market agent in GoNoGo. Search the web for products similar to this one
that are currently sold online in India (Amazon.in, Flipkart, Myntra, Ajio, Nykaa Fashion, Meesho, brand sites).

Product: {product.get("product_type")} - {product.get("short_description")}
Search phrase: {product.get("search_query")}
Department: {product.get("department")}, category: {product.get("category")}

Reply with ONLY a JSON object, no other text:
{{
  "low_inr": <lowest typical price in rupees, number>,
  "high_inr": <highest typical price in rupees, number>,
  "typical_inr": <most common price in rupees, number>,
  "demand_signal": "rising" | "steady" | "falling" | "unclear",
  "competitors": [<up to 4 brand or store names>],
  "products": [
    {{"name": "<exact product title as listed>", "store": "<store name, e.g. Myntra>", "price_inr": <number>}}
  ],
  "summary": "<one sentence on the market, in plain words>"
}}
List 4 to 6 real competing products you found, with their listed prices. Do not include URLs.
Use only prices you actually found. If you are unsure, use "unclear" and give your best range."""
        data, raw_sources = await llm.generate_json([prompt], search=True, temperature=0.2)
        sources = await resolve_sources(raw_sources[:10])

    products = link_products(data.get("products", []), sources)

    low, high, typical = _num(data.get("low_inr")), _num(data.get("high_inr")), _num(data.get("typical_inr"))
    if low and high and low > high:
        low, high = high, low

    position = None
    if low and high:
        position = "below" if price_inr < low else "above" if price_inr > high else "within"

    result = {
        "low_inr": low,
        "high_inr": high,
        "typical_inr": typical,
        "price_position": position,
        "demand_signal": data.get("demand_signal", "unclear"),
        "competitors": data.get("competitors", [])[:4],
        "competitor_products": products,
        "summary": data.get("summary", ""),
        "source_count": len(sources),
    }
    ev = evidence(
        summary=[
            ["Online price range", f"{inr(low)} to {inr(high)}" if low and high else "not found"],
            ["Most common price", inr(typical)],
            ["Your price", f"{inr(price_inr)} ({position} the range)" if position else inr(price_inr)],
            ["Demand signal", result["demand_signal"]],
            ["Competitors seen", ", ".join(result["competitors"]) or "-"],
        ],
        tables=[{
            "title": "Competitor products",
            "columns": ["Product", "Store", "Price", "Link"],
            "rows": [[p["name"], p["store"], inr(p["price_inr"]),
                      {"text": "View product" if p["link_type"] == "product" else f"Search {p['store']}", "url": p["url"]}]
                     for p in products],
        }] if products else None,
        links=sources[:8],
        note=(result["summary"] + " " if result["summary"] else "")
        + "Found with Gemini and Grounding with Google Search. 'View product' links are pages Google Search returned; "
          "'Search' links open that store's search for the product.",
    )
    return result, ev
