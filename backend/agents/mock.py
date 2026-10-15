"""Sample data for GONOGO_MOCK=1, so the page can be built and tested without Google Cloud.
Shapes match the real BigQuery rows and Gemini replies exactly."""
import hashlib
import random

_CATEGORIES = {
    "Women": ["Accessories", "Active", "Blazers & Jackets", "Dresses", "Fashion Hoodies & Sweatshirts",
              "Intimates", "Jeans", "Leggings", "Outerwear & Coats", "Pants & Capris", "Shorts", "Skirts",
              "Sleep & Lounge", "Sweaters", "Swim", "Tops & Tees"],
    "Men": ["Accessories", "Active", "Fashion Hoodies & Sweatshirts", "Jeans", "Outerwear & Coats", "Pants",
            "Shorts", "Sleep & Lounge", "Socks", "Suits & Sport Coats", "Sweaters", "Swim", "Tops & Tees",
            "Underwear"],
}
_SLOW = {"Outerwear & Coats", "Suits & Sport Coats", "Blazers & Jackets"}


def _rng(*parts):
    seed = int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def categories():
    return [{"department": d, "category": c, "products": 900, "avg_price_usd": 45.0}
            for d, cats in _CATEGORIES.items() for c in cats]


def product(req, allowed):
    text = f"{req.name} {req.description}".lower()
    dept = req.department or ("Men" if " men" in f" {text}" else "Women")
    cat = req.category
    if not cat:
        for c in allowed.get(dept, []):
            if c.lower().split(" ")[0].rstrip("s") in text:
                cat = c
                break
    return {
        "department": dept,
        "category": cat or allowed.get(dept, ["Tops & Tees"])[0],
        "product_type": req.name[:40],
        "key_attributes": ["sample attribute", "mock mode"],
        "short_description": req.description or req.name,
        "search_query": req.name,
    }


def comparables(p):
    r = _rng(p["category"], p["department"], round(p["price_usd"]))
    slow = p["category"] in _SLOW
    rows = []
    for i in range(r.randint(25, 60)):
        units = max(0, int(r.gauss(3 if slow else 9, 3)))
        rows.append({"id": i, "name": f"Sample {p['category']} item {i + 1}", "brand": r.choice(["Aurel", "Kestrel", "Nova", "Tidewell"]),
                     "retail_price": p["price_usd"] * r.uniform(0.75, 1.25), "units_12m": units,
                     "returned_12m": int(units * r.uniform(0.05, 0.14))})
    return sorted(rows, key=lambda x: -x["units_12m"])


def segment_stats(p):
    comps = comparables(p)
    r = _rng("stats", p["category"], p["department"])
    seg_total = sum(c["units_12m"] for c in comps)
    growth = r.uniform(-0.25, 0.35)
    weights = [1 + growth * (11 - b) / 11 for b in range(12)][::-1]
    total_w = sum(weights)
    rows = []
    for b in range(12):
        seg = round(seg_total * weights[b] / total_w)
        rows.append({"bucket": b, "cat_units": seg * 4, "seg_units": seg, "store_bucket_units": 5000 + 40 * (11 - b),
                     "store_units": 60000, "store_skus": 29000, "cat_skus": len(comps) * 4, "seg_skus": len(comps)})
    return rows


def basket(p):
    r = _rng("basket", p["category"])
    cats = [c for c in _CATEGORIES[p["department"]] if c != p["category"]]
    r.shuffle(cats)
    return [{"category": c, "orders": r.randint(8, 40), "seg_orders": 220} for c in cats[:5]]


def buyers(p):
    r = _rng("buyers", p["category"])
    bands = ["Under 25", "25-34", "35-44", "45-54", "55+"]
    rows = [{"age_band": b, "units": r.randint(20, 90)} for b in bands]
    return sorted(rows, key=lambda x: -x["units"])


def market(prod, price):
    r = _rng("market", prod["category"], round(price))
    low = round(price * r.uniform(0.55, 0.8), -1)
    high = round(price * r.uniform(1.05, 1.5), -1)
    kind = prod.get("product_type") or prod["category"]
    data = {"low_inr": low, "high_inr": high, "typical_inr": round((low + high) / 2, -1),
            "demand_signal": r.choice(["rising", "steady"]), "competitors": ["Brand A", "Brand B", "Store C"],
            "products": [
                {"name": f"Brand A {kind}", "store": "Myntra", "price_inr": round(price * 0.9, -1)},
                {"name": f"Brand B {kind}", "store": "Amazon.in", "price_inr": round(price * 1.1, -1)},
                {"name": f"Store C {kind}", "store": "Ajio", "price_inr": low},
            ],
            "summary": "Mock mode: sample market data, not a real search."}
    return data, [{"title": "amazon.in", "url": "https://www.amazon.in/brand-b-" + kind.lower().replace(" ", "-") + "/dp/MOCK"}]


def organisation():
    return {
        "summary": {"products": 29120, "categories": 46, "units_12m": 61234, "orders_12m": 42110,
                    "customers_12m": 35870, "return_rate": 0.101, "avg_sale_usd": 59.4, "data_until": "2026-10-14"},
        "top_categories": [
            {"department": d, "category": c, "units_12m": u, "avg_sale_usd": p}
            for d, c, u, p in [("Women", "Intimates", 5210, 38.2), ("Men", "Jeans", 4320, 72.5), ("Women", "Tops & Tees", 3980, 41.0),
                               ("Men", "Fashion Hoodies & Sweatshirts", 3810, 55.1), ("Women", "Swim", 3600, 61.3),
                               ("Men", "Sleep & Lounge", 3420, 49.8), ("Women", "Shorts", 3300, 33.4), ("Men", "Sweaters", 3150, 88.0)]
        ],
    }


def verdict_text(verdict, checks, facts):
    from agents.common import inr
    failed = [c for c in checks if not c["passed"]]
    ordered = (failed + [c for c in checks if c["passed"]])[:3]
    profit = facts.get("profit") or {}
    head = {
        "go": f"Launch at {inr(facts['price_inr'])}, order {profit.get('opening_stock')} units, break-even week {round(profit.get('breakeven_weeks') or 0)}",
        "go_with_conditions": f"Launch at {inr(facts['price_inr'])} with a small first order of {profit.get('opening_stock')} units",
        "no_go": f"Don't launch: {failed[0]['label'].lower()} fails ({failed[0]['value']})" if failed else "Don't launch",
    }[verdict]
    return {
        "headline": head,
        "reasons": [{"text": f"(mock) {c['label']}: {c['value']}", "agent": c["agent"]} for c in ordered],
        "conditions": ["(mock) Start with half the opening order and reorder only if it sells."] if verdict == "go_with_conditions" else [],
        "advice": "(mock) This text comes from mock mode, not Gemini.",
    }
