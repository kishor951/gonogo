"""Sample data for GONOGO_MOCK=1, so the page can be built and tested without Google Cloud.
Shapes match the real BigQuery rows (one function per .sql file) and Gemini replies exactly."""
import datetime as dt
import hashlib
import random

_CATEGORIES = {
    "Women": ["Activewear Tops", "Dresses", "Jeans", "Kurtas", "Leggings", "Outerwear", "Sarees"],
    "Men": ["Activewear", "Formal Trousers", "Jeans", "Outerwear", "Shirts", "T-Shirts"],
}
_SLOW = {"Outerwear", "Formal Trousers"}
_GROWING = {"Leggings", "Activewear Tops", "Activewear", "Kurtas"}
_RETURNS = {"Dresses": 0.24, "Jeans": 0.21}


def _rng(*parts):
    seed = int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def categories():
    return [{"department": d, "category": c, "products": 14, "avg_price_inr": float(_PRICES.get(c, 1999)),
             "min_price_inr": round(_PRICES.get(c, 1999) * 0.6, -2) - 1, "max_price_inr": round(_PRICES.get(c, 1999) * 1.6, -2) - 1}
            for d, cats in _CATEGORIES.items() for c in cats]


_NOT_APPAREL = ("diya", "lamp", "phone case", "mug", "toy", "bottle", "candle")


def _what(text):
    return next((w for w in _NOT_APPAREL if w in text), None)


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
        "category": cat or allowed.get(dept, ["T-Shirts"])[0],
        "product_type": req.name[:40],
        "key_attributes": ["sample attribute", "mock mode"],
        "short_description": req.description or req.name,
        "search_query": req.name,
        "fits_shop": _what(text) is None,
        "what_it_is": _what(text) or req.name[:40],
    }


# --- Demand: comparables.sql, demand_stats.sql, segment_monthly.sql ---

def comparables(p):
    r = _rng(p["category"], p["department"], round(p["price"]))
    slow = p["category"] in _SLOW
    rows = []
    for i in range(r.randint(4, 9)):
        units = max(0, int(r.gauss(60 if slow else 260, 80)))
        rows.append({"sku": f"MOCK-{i + 1:03d}", "name": f"Sample {p['category']} item {i + 1}",
                     "brand": r.choice(["Urban Loom", "Loom Active", "Northpeak"]),
                     "price_inr": round(p["price"] * r.uniform(0.75, 1.25)), "status": "active",
                     "units_12m": units, "returned_12m": int(units * _RETURNS.get(p["category"], 0.11))})
    return sorted(rows, key=lambda x: -x["units_12m"])


def demand_stats(p):
    comps = comparables(p)
    seg_units = sum(c["units_12m"] for c in comps)
    growth = 0.3 if p["category"] in _GROWING else -0.2 if p["category"] == "Formal Trousers" else 0.05
    last3 = round(seg_units * 0.25)
    return [{
        "shop_units": 40000, "shop_sku_months": 166 * 12.0, "shop_skus": 166,
        "cat_units": seg_units * 2, "cat_sku_months": len(comps) * 2 * 12.0, "cat_skus": len(comps) * 2,
        "seg_units": seg_units, "seg_sku_months": len(comps) * 12.0, "seg_skus": len(comps),
        "seg_units_all": seg_units, "seg_returned": sum(c["returned_12m"] for c in comps),
        "seg_last_3m": last3, "seg_prev_3m": round(last3 / (1 + growth / 4)), "seg_ly_3m": round(last3 / (1 + growth)),
        "shop_last_3m": 10500, "shop_prev_3m": 10100, "shop_ly_3m": 9300,
    }]


def segment_monthly(p):
    total = sum(c["units_12m"] for c in comparables(p))
    winter = p["category"] == "Outerwear"
    rows = []
    for b in range(12):
        month = (dt.date.today().month - b - 1) % 12          # 0 = Jan
        w = (2.2 if month in (10, 11, 0) else 0.1 if 3 <= month <= 7 else 0.8) if winter else 1 + 0.02 * (11 - b)
        rows.append({"bucket": b, "seg_units": w})
    scale = total / sum(r["seg_units"] for r in rows)
    return [{"bucket": r["bucket"], "seg_units": round(r["seg_units"] * scale)} for r in rows]


# --- Fit: basket.sql, segment_mix.sql ---

def basket(p):
    r = _rng("basket", p["category"])
    cats = [c for c in _CATEGORIES[p["department"]] if c != p["category"]]
    r.shuffle(cats)
    return [{"department": p["department"], "category": c, "orders": r.randint(20, 160), "seg_orders": 900}
            for c in cats[:5]]


def segment_mix(p):
    r = _rng("mix", p["category"])
    rows = [{"dimension": "age_band", "label": b, "units": r.randint(40, 400)}
            for b in ["18-24", "25-34", "35-44", "45-54", "55+"]]
    rows += [{"dimension": "channel", "label": c, "units": r.randint(200, 600)} for c in ["website", "myntra", "amazon"]]
    rows += [{"dimension": "city", "label": c, "units": r.randint(30, 200)}
             for c in ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai"]]
    return rows


# --- Start from a photo: Gemini vision (autofill) + price_suggestion.sql ---

def autofill(hint, allowed):
    """Two products in one photo (clothing the shop sells + shoes it doesn't), like a real outfit shot."""
    text = (hint or "").lower()
    dept = "Men" if " men" in f" {text}" else "Women"
    cat = next((c for c in allowed.get(dept, []) if c.lower().split(" ")[0].rstrip("s") in text), None)
    cat = cat or ("Leggings" if dept == "Women" else "T-Shirts")
    if _what(text):
        return {"items": [{"box_2d": [150, 250, 850, 750], "fits_shop": False, "what_it_is": _what(text),
                           "reason": "(mock) The shop sells clothing, not this.",
                           "name": f"Sample {_what(text)}", "description": "(mock) Not apparel.", "department": dept,
                           "category": "T-Shirts", "product_type": _what(text), "key_attributes": ["mock mode"]}]}
    return {"items": [
        {"box_2d": [80, 300, 620, 700], "fits_shop": True, "what_it_is": cat.lower(), "reason": "",
         "name": f"Sample {cat[:-1] if cat.endswith('s') else cat} from photo",
         "description": "(mock) Read from the photo in mock mode, not by Gemini.", "department": dept,
         "category": cat, "product_type": cat.lower(), "key_attributes": ["mock mode", "sample"]},
        {"box_2d": [820, 330, 960, 680], "fits_shop": False, "what_it_is": "black sneakers",
         "reason": "(mock) Footwear is on the shop's never-sells list.",
         "name": "Black Canvas Sneakers", "description": "(mock) Shoes in the same photo.", "department": dept,
         "category": cat, "product_type": "sneakers", "key_attributes": ["mock mode"]},
    ]}


def price_suggestion(p):
    r = _rng("price", p["department"], p["category"])
    base = _PRICES.get(p["category"], 1499)
    rows = [{"sku": f"MOCK-{i}", "name": f"Sample {p['category']} {i + 1}", "price_inr": round(base * r.uniform(0.6, 1.6), -2) - 1,
             "units_12m": r.randint(0, 600)} for i in range(10)]
    return sorted(rows, key=lambda x: x["price_inr"])


# --- Market (Gemini + Google Search) ---

def market(prod, price):
    r = _rng("market", prod["category"], round(price))
    low = round(price * r.uniform(0.55, 0.8), -1)
    high = round(price * r.uniform(1.05, 1.5), -1)
    kind = prod.get("product_type") or prod["category"]
    data = {"low_inr": low, "high_inr": high, "typical_inr": round((low + high) / 2, -1),
            "demand_signal": r.choice(["rising", "steady"]), "competitors": ["Brand A", "Brand B", "Store C"],
            "products": [
                {"name": f"Brand A {kind}", "store": "Myntra", "price_inr": round(price * 0.9, -1), "rating": 4.2, "reviews": 1873},
                {"name": f"Brand B {kind}", "store": "Amazon.in", "price_inr": round(price * 1.1, -1), "rating": 3.9, "reviews": 412},
                {"name": f"Store C {kind}", "store": "Ajio", "price_inr": low, "rating": None, "reviews": None},
            ],
            "summary": "Mock mode: sample market data, not a real search."}
    return data, [{"title": "amazon.in", "url": "https://www.amazon.in/brand-b-" + kind.lower().replace(" ", "-") + "/dp/MOCK"}]


# --- Business page: business_kpis.sql, business_monthly.sql, business_categories.sql, business_channels.sql ---

def _until():
    return dt.date.today() - dt.timedelta(days=1)


def business_kpis():
    until = _until()
    meta = {"data_until": until.isoformat(), "data_from": (until - dt.timedelta(days=729)).isoformat(), "active_skus": 166}
    return [
        {"period": "cur", "revenue": 4_86_20_000, "cost": 2_31_40_000, "units": 32150, "returned_units": 4180,
         "orders": 22870, "customers": 4890, **meta},
        {"period": "prev", "revenue": 4_21_70_000, "cost": 2_02_10_000, "units": 28440, "returned_units": 3620,
         "orders": 20410, "customers": 4310, **meta},
    ]


def business_monthly():
    month_end = _until().replace(day=1)
    if (_until() + dt.timedelta(days=1)).day == 1:
        month_end = _until() + dt.timedelta(days=1)
    rows, m = [], month_end
    for i in range(18):
        m = (m - dt.timedelta(days=1)).replace(day=1)
        bump = {10: 1.35, 11: 1.3, 12: 1.2, 1: 1.25, 7: 1.1}.get(m.month, 1.0)
        revenue = round(3_400_000 * (1 + 0.012 * (18 - i)) * bump, -3)
        rows.append({"month": m.strftime("%Y-%m"), "revenue": revenue, "units": round(revenue / 1520)})
    return rows[::-1]


def business_categories():
    r = _rng("business-categories")
    out = []
    for dept, cats in _CATEGORIES.items():
        for c in cats:
            revenue = r.randint(12, 70) * 1_00_000
            growth = 0.3 if c in _GROWING else -0.18 if c == "Formal Trousers" else r.uniform(-0.05, 0.12)
            units = round(revenue / r.randint(900, 3500))
            out.append({"department": dept, "category": c, "revenue": revenue, "cost": round(revenue * r.uniform(0.42, 0.55)),
                        "units": units, "returned_units": round(units * _RETURNS.get(c, 0.11)),
                        "revenue_prev": round(revenue / (1 + growth))})
    return sorted(out, key=lambda x: -x["revenue"])


def business_channels():
    return [
        {"channel": "myntra", "revenue": 1_78_40_000, "orders": 8520, "units": 11900, "revenue_prev": 1_66_20_000},
        {"channel": "website", "revenue": 1_66_10_000, "orders": 7380, "units": 10560, "revenue_prev": 1_29_90_000},
        {"channel": "amazon", "revenue": 1_41_70_000, "orders": 6970, "units": 9690, "revenue_prev": 1_25_60_000},
    ]


# --- Shop pages: one function per sql/<name>.sql, all from one small sample catalogue ---

_PRICES = {"Leggings": 1099, "Activewear Tops": 799, "Kurtas": 1499, "Dresses": 1899, "Jeans": 1999, "Outerwear": 4999,
           "Sarees": 2999, "T-Shirts": 699, "Shirts": 1499, "Activewear": 1199, "Formal Trousers": 1699}
_SUPPLIERS = [("S01", "Tiruppur Knit Works", "Tiruppur", 12, 300), ("S03", "Ludhiana Woollen Mills", "Ludhiana", 35, 100),
              ("S05", "Jaipur Block Prints", "Jaipur", 21, 150), ("S08", "Bengaluru Denim Lab", "Bengaluru", 20, 200),
              ("S10", "Okhla Fashion Exports", "New Delhi", 10, 150)]


def _catalogue():
    r = _rng("catalogue")
    until = _until()
    out = []
    for dept, cats in _CATEGORIES.items():
        for cat in cats:
            for i in range(3):
                price = round(_PRICES[cat] * r.uniform(0.7, 1.4), -2) - 1
                cost = round(price * r.uniform(0.35, 0.6), -1)
                units = 0 if r.random() < 0.08 else int(r.lognormvariate(5, 0.9))
                if cat in _SLOW:
                    units //= 4
                weekly = round(units / 52 * r.uniform(0.6, 1.4), 1)
                on_hand = int(weekly * r.uniform(2, 30)) if units else r.randint(20, 90)
                status = "active" if r.random() > 0.07 else "discontinued"
                sup = _SUPPLIERS[(len(out)) % len(_SUPPLIERS)]
                out.append({
                    "sku": f"{dept[0]}-{cat[:3].upper()}-{i + 1:03d}", "name": f"Sample {cat} {i + 1}", "department": dept,
                    "category": cat, "brand": r.choice(["Urban Loom", "Loom Active", "Northpeak"]), "price_inr": price,
                    "cost_inr": cost, "status": status, "units": units, "weekly": weekly,
                    "returned": int(units * _RETURNS.get(cat, 0.11)), "on_hand": on_hand if status == "active" else 0,
                    "on_order": int(weekly * 3) if r.random() < 0.3 else 0, "reorder_point": int(weekly * 4) + 2,
                    "launch_date": until - dt.timedelta(days=r.randint(60, 900)), "supplier": sup,
                    "last_sale": until - dt.timedelta(days=0 if units else r.randint(95, 300)),
                })
    return out


def inventory_status():
    rows = []
    for p in _catalogue():
        if p["status"] != "active":
            continue
        cover = p["on_hand"] / (p["weekly"] / 7) if p["weekly"] else None
        units_90d = round(p["weekly"] * 13)
        status = ("dead" if p["on_hand"] and not units_90d else
                  "reorder" if p["on_hand"] + p["on_order"] < p["reorder_point"] else
                  "overstock" if p["on_hand"] and (cover is None or cover > 120) else "healthy")
        rows.append({
            "sku": p["sku"], "name": p["name"], "department": p["department"], "category": p["category"],
            "cost_inr": p["cost_inr"], "price_inr": p["price_inr"], "supplier": p["supplier"][1],
            "lead_time_days": p["supplier"][3], "on_hand": p["on_hand"], "on_order": p["on_order"],
            "reorder_point": p["reorder_point"], "last_received_date": _until() - dt.timedelta(days=30),
            "weekly_sales": p["weekly"], "units_90d": units_90d, "last_sale": p["last_sale"], "cover_days": cover,
            "sell_through_90d": units_90d / (units_90d + p["on_hand"]) if units_90d + p["on_hand"] else None,
            "stock_value": p["on_hand"] * p["cost_inr"], "on_order_value": p["on_order"] * p["cost_inr"], "status": status,
        })
    order = {"dead": 0, "reorder": 1, "overstock": 2, "healthy": 3}
    return sorted(rows, key=lambda x: (order[x["status"]], -x["stock_value"]))


def products_list():
    rows = [{
        "sku": p["sku"], "name": p["name"], "department": p["department"], "category": p["category"],
        "brand": p["brand"], "price_inr": p["price_inr"], "cost_inr": p["cost_inr"],
        "list_margin": (p["price_inr"] - p["cost_inr"]) / p["price_inr"], "status": p["status"],
        "launch_date": p["launch_date"], "supplier": p["supplier"][1], "units_12m": p["units"],
        "revenue_12m": round(p["units"] * p["price_inr"] * 0.82), "return_rate": p["returned"] / p["units"] if p["units"] else None,
        "last_sale": p["last_sale"],
    } for p in _catalogue()]
    return sorted(rows, key=lambda x: -x["revenue_12m"])


def sales_period():
    until = _until().isoformat()
    return [
        {"period": "cur", "revenue": 33_80_000, "gross": 38_10_000, "list_value": 42_40_000, "orders": 1740,
         "units": 2790, "customers": 1490, "data_until": until},
        {"period": "prev", "revenue": 31_20_000, "gross": 35_30_000, "list_value": 38_90_000, "orders": 1650,
         "units": 2610, "customers": 1420, "data_until": until},
    ]


def sales_monthly():
    rows = []
    for m in business_monthly():
        gross = round(m["revenue"] * 1.13)
        rows.append({"month": m["month"], "orders": round(m["units"] / 1.6), "units": m["units"], "revenue": m["revenue"],
                     "gross": gross, "list_value": round(gross * 1.11), "returned_units": round(m["units"] * 0.13),
                     "data_until": _until().isoformat()})
    return rows[::-1]


def sales_recent():
    r = _rng("recent")
    cat = _catalogue()
    rows = []
    for i in range(100):
        items = r.sample(cat, r.choice([1, 1, 1, 2, 3]))
        rows.append({"order_id": f"UL{190000 - i}", "order_date": _until() - dt.timedelta(days=i // 60),
                     "channel": r.choice(["website", "myntra", "amazon"]), "customer_id": f"C{r.randint(1, 6000):05d}",
                     "units": len(items), "value": sum(p["price_inr"] for p in items), "has_return": r.random() < 0.12,
                     "items": ", ".join(p["name"] for p in items)})
    return rows


def returns_breakdown():
    rows = []
    for dept, cats in _CATEGORIES.items():
        for c in cats:
            units = _rng("ret", dept, c).randint(500, 4600)
            ret = round(units * _RETURNS.get(c, 0.11))
            rows.append({"dimension": "category", "department": dept, "label": c, "units": units,
                         "returned_units": ret, "returned_value": ret * _PRICES[c]})
    for ch, rate in [("website", 0.12), ("myntra", 0.15), ("amazon", 0.13)]:
        rows.append({"dimension": "channel", "department": None, "label": ch, "units": 10500,
                     "returned_units": round(10500 * rate), "returned_value": round(10500 * rate * 1700)})
    return rows


def returns_products():
    rows = [{"sku": p["sku"], "name": p["name"], "department": p["department"], "category": p["category"],
             "units": p["units"], "returned_units": p["returned"], "return_rate": p["returned"] / p["units"],
             "returned_value": p["returned"] * p["price_inr"]} for p in _catalogue() if p["units"] >= 30]
    return sorted(rows, key=lambda x: -x["return_rate"])[:25]


def customers_summary():
    return [{"customers": 6000, "new_12m": 2950, "active_12m": 4890, "repeat_12m": 3420,
             "orders_12m": 20160, "revenue_12m": 3_93_30_000}]


def customers_segments():
    rows = [{"dimension": "age_band", "label": b, "customers": n, "orders": n * 4, "revenue": n * 4 * 1950}
            for b, n in [("18-24", 1150), ("25-34", 1860), ("35-44", 1120), ("45-54", 520), ("55+", 240)]]
    rows += [{"dimension": "city", "label": c, "customers": n, "orders": n * 4, "revenue": n * 4 * 1940}
             for c, n in [("Bengaluru", 690), ("Mumbai", 640), ("Delhi", 590), ("Hyderabad", 440), ("Pune", 390),
                          ("Chennai", 380), ("Kolkata", 300), ("Ahmedabad", 250)]]
    return rows


def customers_top():
    r = _rng("top-customers")
    rows = []
    for i in range(50):
        orders = r.randint(8, 24)
        rows.append({"customer_id": f"C{r.randint(1, 6000):05d}", "age_band": r.choice(["25-34", "35-44", "18-24"]),
                     "city": r.choice(["Bengaluru", "Mumbai", "Delhi", "Pune"]),
                     "first_order_date": _until() - dt.timedelta(days=r.randint(200, 720)), "orders": orders,
                     "units": round(orders * 1.6), "revenue": orders * r.randint(1900, 3200),
                     "returned_units": r.randint(0, 4), "last_order": _until() - dt.timedelta(days=r.randint(0, 40))})
    return sorted(rows, key=lambda x: -x["revenue"])


def suppliers_list():
    cat = _catalogue()
    rows = []
    for sid, name, city, lead, moq in _SUPPLIERS:
        mine = [p for p in cat if p["supplier"][0] == sid]
        rows.append({"supplier_id": sid, "name": name, "city": city, "lead_time_days": lead, "moq": moq,
                     "active_products": sum(p["status"] == "active" for p in mine),
                     "categories": ", ".join(sorted({p["category"] for p in mine})),
                     "units_12m": sum(p["units"] for p in mine),
                     "revenue_12m": round(sum(p["units"] * p["price_inr"] * 0.82 for p in mine)),
                     "stock_value": sum(p["on_hand"] * p["cost_inr"] for p in mine),
                     "on_order_value": sum(p["on_order"] * p["cost_inr"] for p in mine)})
    return sorted(rows, key=lambda x: -x["revenue_12m"])


# --- Experiment budget: budget_inputs.sql (stock comes from inventory_status) ---

def budget_inputs():
    return [{"revenue_90": 1_01_40_000, "cogs_90": 51_30_000, "orders_90": 5160, "returned_units_90": 1110,
             "revenue_ly_90": 86_70_000, "data_until": _until().isoformat()}]


# --- Settings: settings_get.sql, settings_save.sql (kept in memory) ---

_settings: dict = {}


def settings_get():
    return [dict(_settings)] if _settings else []


def settings_save(params):
    _settings.update(shop_name=params["shop_name"], rules_json=params["rules_json"], profile_json=params["profile_json"],
                     updated_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


# --- Verdict text (Gemini) ---

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
