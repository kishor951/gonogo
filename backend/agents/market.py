"""Market agent: Gemini with Grounding with Google Search finds what similar products sell for
online in India right now, which competitor products exist, and keeps the sources.

Competitor links are never invented: each product is linked to a real page that Google Search
returned (matched by store and product words). If no matching page was found, the link is a
search on that store for the product name, and is labelled as a search.
"""
import asyncio
import re
import ssl
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


def _ssl_context():
    """Verified HTTPS using certifi's certificates (python.org builds on macOS ship without any)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


SSL = _ssl_context()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _resolve(url: str) -> str:
    """Grounding sources are Google redirect links; find the real page address behind them."""
    if "grounding-api-redirect" not in url:
        return url
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=SSL))
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
        rating, reviews = _num(p.get("rating")), _num(p.get("reviews"))
        linked.append({"name": name, "store": store or "-", "price_inr": _num(p.get("price_inr")),
                       "url": url, "link_type": kind,
                       "rating": rating if rating and 0 < rating <= 5 else None,
                       "reviews": int(reviews) if reviews and reviews >= 1 else None,
                       "rating_source": "Google results" if rating and 0 < rating <= 5 else None,
                       "image": None})
    return linked[:8]


# Product-page addresses on the big marketplaces (search and category pages don't match).
STORE_PAGES = [
    ("myntra.com", "Myntra", re.compile(r"myntra\.com/.+/\d+/buy")),
    ("flipkart.com", "Flipkart", re.compile(r"flipkart\.com/.+/p/itm")),
    ("ajio.com", "Ajio", re.compile(r"ajio\.com/.+/p/")),
    ("amazon.in", "Amazon.in", re.compile(r"amazon\.in/.*(/dp/|/gp/product/)")),
]


async def find_product_pages(query: str) -> list[dict]:
    """One Google Search per marketplace, at the same time, keeping only real product pages it returned."""
    async def one(domain, label, pattern):
        try:
            raw = await llm.search_pages(f"Find individual product pages on {domain} for: {query}. "
                                         "List each product with its price.")
        except Exception:
            return []
        pages = await resolve_sources(raw[:8])
        return [{"store": label, "url": p["url"]} for p in pages if pattern.search(p["url"])]
    found = await asyncio.gather(*(one(*s) for s in STORE_PAGES))
    seen, out = set(), []
    for page in (p for group in found for p in group):
        key = page["url"].split("?")[0]
        if key not in seen:
            seen.add(key)
            out.append({**page, "url": key})
    return out


def _slug_name(url: str) -> str:
    """A readable product name from a product page address (when the page itself can't be read)."""
    path = urllib.parse.urlparse(url).path
    parts = [p for p in path.split("/") if p and not re.fullmatch(r"\d+|buy|p|dp|itm\w+|[\w]*\d{6,}[\w]*", p)]
    slug = max(parts, key=len, default="")
    return " ".join(w.capitalize() for w in slug.replace("_", "-").split("-") if w)[:90]


_IMG = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)', re.I)
_IMG2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']', re.I)
_TITLE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', re.I)
_LDJSON = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)


def _ld_product(html: str) -> dict:
    """The page's own structured product data (schema.org Product): name, price, rating."""
    import json
    def walk(x):
        if isinstance(x, list):
            for i in x:
                yield from walk(i)
        elif isinstance(x, dict):
            t = x.get("@type")
            if t == "Product" or (isinstance(t, list) and "Product" in t):
                yield x
            for v in x.values():
                if isinstance(v, (list, dict)):
                    yield from walk(v)
    for block in _LDJSON.findall(html):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for prod in walk(data):
            out = {"name": prod.get("name")}
            offers = prod.get("offers") or {}
            offers = offers[0] if isinstance(offers, list) and offers else offers
            out["price"] = _num((offers or {}).get("price") or (offers or {}).get("lowPrice"))
            rating = prod.get("aggregateRating") or {}
            out["rating"] = _num(rating.get("ratingValue"))
            out["reviews"] = _num(rating.get("ratingCount") or rating.get("reviewCount"))
            return out
    return {}


def _page_details(url: str) -> dict:
    """Picture and rating from a real product page: its share image (og:image) and its own structured rating.
    Many stores block automated visits; then we simply have nothing (never a made-up image)."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept-Language": "en-IN,en;q=0.9"})
        html = urllib.request.urlopen(req, timeout=4, context=SSL).read(800_000).decode("utf-8", "ignore")
    except Exception:
        return {}
    out = {}
    m = _IMG.search(html) or _IMG2.search(html)
    if m and m.group(1).startswith("https://"):
        out["image"] = m.group(1)
    ld = _ld_product(html)
    t = _TITLE.search(html)
    name = ld.get("name") or (t.group(1) if t else None)
    if name:
        out["page_name"] = re.split(r"\s+[|\-–]\s+(?:Buy|Shop|Online|Myntra|Flipkart|Ajio|Amazon)", name)[0].strip()[:120]
    if ld.get("price") and ld["price"] > 0:
        out["page_price"] = ld["price"]
    # only a real product rating, with how many people gave it
    if ld.get("rating") and 0 < ld["rating"] <= 5 and ld.get("reviews") and ld["reviews"] >= 1:
        out["rating"], out["reviews"], out["rating_source"] = ld["rating"], int(ld["reviews"]), "store page"
    return out


async def add_page_details(products: list[dict]) -> list[dict]:
    """Picture, price and rating straight from each real product page (when the store lets us read it)."""
    pages = [p for p in products if p["link_type"] == "product"]
    found = await asyncio.gather(*(asyncio.to_thread(_page_details, p["url"]) for p in pages))
    for p, extra in zip(pages, found):
        if extra.get("page_price"):
            p["price_inr"], p["price_source"] = extra["page_price"], "store page"
        if extra.get("page_name") and p.get("from_page_only"):
            p["name"] = extra["page_name"]
        p.update({k: v for k, v in extra.items() if k in ("image", "rating", "reviews", "rating_source") and v is not None})
    return products


def merge_store_pages(products: list[dict], pages: list[dict]) -> list[dict]:
    """Real product pages first: Gemini's products matched to a page keep their listed price; pages
    nobody named are added with what the page says. Store searches only fill the gaps."""
    used = {p["url"] for p in products if p["link_type"] == "product"}
    for p in products:   # match a named product to a store page by the words in its address
        if p["link_type"] == "product":
            continue
        key, want = _store_key(p["store"]), _tokens(p["name"])
        best, best_score = None, 0
        for page in pages:
            if page["url"] in used or key not in page["url"]:
                continue
            score = len(want & _tokens(urllib.parse.urlparse(page["url"]).path))
            if score > best_score:
                best, best_score = page, score
        if best and best_score >= 3:
            p["url"], p["link_type"] = best["url"], "product"
            used.add(best["url"])
    extra = [{"name": _slug_name(pg["url"]), "store": pg["store"], "price_inr": None, "url": pg["url"],
              "link_type": "product", "rating": None, "reviews": None, "rating_source": None, "image": None,
              "from_page_only": True} for pg in pages if pg["url"] not in used]
    real = [p for p in products if p["link_type"] == "product"] + extra
    # take turns between stores (at most 3 each) so one marketplace doesn't fill the list
    by_store: dict[str, list] = {}
    for p in real:
        by_store.setdefault(p["store"], []).append(p)
    mixed = [group[i] for i in range(3) for group in by_store.values() if i < len(group)]
    return (mixed + [p for p in products if p["link_type"] != "product"])[:10]


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
    {{"name": "<exact product title as listed>", "store": "<store name, e.g. Myntra>", "price_inr": <number>,
      "rating": <star rating out of 5 exactly as shown, or null>, "reviews": <number of ratings or reviews as shown, or null>}}
  ],
  "summary": "<one sentence on the market, in plain words>"
}}
List 4 to 6 real competing products you found, with their listed prices. Do not include URLs.
Use only prices you actually found. If you are unsure, use "unclear" and give your best range.
Give a rating and review count only if the search results show them for that product; otherwise null. Never guess them."""
        query = product.get("search_query") or product.get("product_type") or ""
        (data, raw_sources), store_pages = await asyncio.gather(
            llm.generate_json([prompt], search=True, temperature=0.2), find_product_pages(query))
        sources = await resolve_sources(raw_sources[:10])

    products = link_products(data.get("products", []), sources)
    if not MOCK:
        products = merge_store_pages(products, store_pages)
        products = await add_page_details(products)
        # a page we couldn't read and nobody priced isn't much use: keep it only if it has a price or picture
        products = [p for p in products if not p.get("from_page_only") or p.get("price_inr") or p.get("image")][:8]

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
            "columns": ["Product", "Store", "Price", "Rating", "Link"],
            "rows": [[p["name"], p["store"], inr(p["price_inr"]),
                      f"{p['rating']:g}★" + (f" ({p['reviews']:,})" if p.get("reviews") else "") if p.get("rating") else "-",
                      {"text": "View product" if p["link_type"] == "product" else f"Search {p['store']}", "url": p["url"]}]
                     for p in products],
        }] if products else None,
        links=sources[:8],
        note=(result["summary"] + " " if result["summary"] else "")
        + "Found with Gemini and Grounding with Google Search. 'View product' links are pages Google Search returned; "
          "'Search' links open that store's search for the product.",
    )
    return result, ev
