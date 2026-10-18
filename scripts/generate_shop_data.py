"""Generate Urban Loom, GoNoGo's demo shop, as CSV files for BigQuery.

    python scripts/generate_shop_data.py                       # sales up to yesterday
    python scripts/generate_shop_data.py --end-date 2026-10-14

Urban Loom is a synthetic mid-size Indian online fashion shop selling women's and men's apparel
on its own website, Myntra and Amazon. Prices are native rupees.

Standard library only. The random seed is fixed, so the shop is the same on every run; only the
dates move with --end-date. Sales cover two years, so the Business page can compare the last
12 months with the 12 months before. Writes scripts/data/<table>.csv.
"""
import argparse
import csv
import datetime as dt
import json
import math
import pathlib
import random
from collections import Counter, defaultdict

SEED = 511
DAYS = 730                 # two years of sales
TARGET_LINES = 53000       # about 40,000 lines per 18 months
N_CUSTOMERS = 6000
OUT = pathlib.Path(__file__).resolve().parent / "data"

SHOP_NAME = "Urban Loom"
# Same as DEFAULT_ASSUMPTIONS in backend/config.py (the app fills in anything missing).
DEFAULT_RULES = {
    "launch_cost": 10000, "shipping_per_unit": 60, "platform_fee_pct": 15,
    "lead_time_weeks": 2, "cover_weeks": 4, "min_margin_pct": 20,
    "max_breakeven_weeks": 12, "min_velocity": 0.7, "price_band_pct": 30,
    "experiment_pct": 10, "launches_per_month": 2,
}

# Demand multiplier by month (Jan..Dec).
SEASON = {
    "flat":    [1.0, 0.95, 1.0, 1.0, 1.0, 0.95, 1.0, 1.0, 1.0, 1.05, 1.05, 1.0],
    "winter":  [2.2, 1.0, 0.35, 0.06, 0.03, 0.03, 0.04, 0.08, 0.35, 0.9, 2.0, 2.6],
    "active":  [1.8, 1.25, 1.05, 0.95, 0.9, 0.95, 0.85, 0.85, 0.9, 0.95, 0.9, 0.95],
    "festive": [0.9, 0.9, 1.1, 1.1, 0.8, 0.7, 0.7, 1.0, 1.1, 1.6, 1.6, 1.0],
    "summer":  [0.7, 0.8, 1.1, 1.35, 1.4, 1.3, 1.0, 0.95, 0.9, 1.0, 0.9, 0.8],
    "wedding": [1.2, 1.2, 0.9, 0.9, 1.0, 0.7, 0.7, 0.9, 1.0, 1.4, 1.6, 1.3],
}

SUPPLIERS = [
    # supplier_id, name, city, lead_time_days, moq
    ("S01", "Tiruppur Knit Works", "Tiruppur", 12, 300),
    ("S02", "Kongu Activewear", "Tiruppur", 14, 250),
    ("S03", "Ludhiana Woollen Mills", "Ludhiana", 35, 100),
    ("S04", "Punjab Outerwear Co", "Ludhiana", 30, 80),
    ("S05", "Jaipur Block Prints", "Jaipur", 21, 150),
    ("S06", "Sanganer Textiles", "Jaipur", 18, 120),
    ("S07", "Surat Silk House", "Surat", 25, 60),
    ("S08", "Bengaluru Denim Lab", "Bengaluru", 20, 200),
    ("S09", "Peenya Garments", "Bengaluru", 15, 250),
    ("S10", "Okhla Fashion Exports", "New Delhi", 10, 150),
    ("S11", "Bhiwandi Apparel", "Mumbai", 7, 100),
    ("S12", "Kolkata Tailoring Co", "Kolkata", 28, 80),
]

# dept, category, sku code, number of SKUs, list price range (₹), return rate, growth per year,
# season, share of unit demand, suppliers, name words, product nouns
CATEGORIES = [
    ("Women", "Leggings", "LEG", 16, 599, 1799, 0.10, 0.28, "active", 0.10, ["S01", "S02"],
     ["High-waist", "Seamless", "Ankle-length", "Side-pocket", "Ribbed", "Flared", "Printed", "Cotton", "Thermal", "Sculpt"],
     ["Leggings", "Yoga Leggings", "Active Leggings", "Gym Tights"]),
    ("Women", "Activewear Tops", "ATP", 14, 499, 1499, 0.12, 0.32, "active", 0.07, ["S01", "S02"],
     ["Racerback", "Cropped", "Dry-fit", "Seamless", "Longline", "Mesh-panel", "Training", "Breathable"],
     ["Sports Bra", "Tank Top", "Gym Tee", "Crop Top"]),
    ("Women", "Kurtas", "KUR", 20, 799, 2999, 0.14, 0.30, "festive", 0.12, ["S05", "S06", "S12"],
     ["Block-print", "Chikankari", "A-line", "Straight", "Anarkali", "Mirror-work", "Cotton", "Rayon", "Festive"],
     ["Kurta", "Kurta Set", "Long Kurta", "Kurti"]),
    ("Women", "Dresses", "DRS", 16, 999, 3499, 0.25, 0.10, "summer", 0.07, ["S10", "S11"],
     ["Wrap", "Tiered", "Floral", "Shirt", "Bodycon", "Smocked", "Linen", "Puff-sleeve"],
     ["Dress", "Sundress", "Midi Dress", "Maxi Dress"]),
    ("Women", "Jeans", "WJN", 12, 1199, 2999, 0.22, 0.08, "flat", 0.06, ["S08", "S09"],
     ["High-rise", "Mom-fit", "Straight", "Wide-leg", "Skinny", "Bootcut", "Distressed"],
     ["Jeans", "Denim Jeans"]),
    ("Women", "Outerwear", "WOW", 12, 2499, 9999, 0.12, 0.04, "winter", 0.03, ["S03", "S04"],
     ["Wool-blend", "Quilted", "Puffer", "Longline", "Belted", "Faux-fur", "Teddy", "Trench"],
     ["Coat", "Jacket", "Overcoat", "Shrug"]),
    ("Women", "Sarees", "SAR", 12, 1299, 6999, 0.08, 0.08, "wedding", 0.05, ["S07", "S05"],
     ["Banarasi", "Chiffon", "Georgette", "Cotton", "Kanjeevaram-style", "Linen", "Organza"],
     ["Saree", "Silk Saree", "Party Saree"]),
    ("Men", "T-Shirts", "TSH", 18, 399, 1299, 0.09, 0.12, "summer", 0.14, ["S01", "S09"],
     ["Crew-neck", "Oversized", "Polo", "Henley", "Graphic", "Slub", "Striped", "Pique", "Pocket"],
     ["T-Shirt", "Tee", "Polo T-Shirt"]),
    ("Men", "Shirts", "SHR", 14, 899, 2499, 0.12, 0.06, "flat", 0.08, ["S09", "S10"],
     ["Oxford", "Linen", "Checked", "Mandarin-collar", "Denim", "Printed", "Slim-fit"],
     ["Shirt", "Casual Shirt", "Formal Shirt"]),
    ("Men", "Jeans", "MJN", 12, 1299, 3299, 0.20, 0.06, "flat", 0.08, ["S08", "S09"],
     ["Slim", "Tapered", "Straight", "Relaxed", "Stretch", "Dark-wash", "Light-wash"],
     ["Jeans", "Denim Jeans"]),
    ("Men", "Activewear", "MAC", 12, 599, 1999, 0.10, 0.30, "active", 0.07, ["S01", "S02"],
     ["Dry-fit", "Training", "Running", "Compression", "Gym", "Track"],
     ["Joggers", "T-Shirt", "Shorts", "Track Pants"]),
    ("Men", "Outerwear", "MOW", 10, 2499, 9999, 0.12, 0.0, "winter", 0.03, ["S03", "S04"],
     ["Wool-blend", "Quilted", "Puffer", "Bomber", "Double-breasted", "Leather-look", "Hooded"],
     ["Jacket", "Overcoat", "Coat", "Gilet"]),
    ("Men", "Formal Trousers", "FTR", 12, 999, 2799, 0.15, -0.26, "flat", 0.06, ["S10", "S11", "S12"],
     ["Slim-fit", "Pleated", "Flat-front", "Wool-blend", "Stretch", "Classic"],
     ["Formal Trousers", "Office Trousers", "Suit Trousers"]),
]
COLOURS = ["Black", "Navy", "Olive", "Charcoal", "Maroon", "Teal", "Ivory", "Rust", "Grey", "Mustard",
           "Indigo", "Blush", "Sage", "Wine"]
THIRD_PARTY = ["Northpeak", "Kinaara", "Rangreza"]

# What else goes in the same order: (dept, category) -> [(dept, category, weight)]
BASKET = {
    ("Women", "Leggings"): [("Women", "Activewear Tops", 5), ("Women", "Kurtas", 4), ("Women", "Leggings", 1)],
    ("Women", "Activewear Tops"): [("Women", "Leggings", 6), ("Women", "Activewear Tops", 1)],
    ("Women", "Kurtas"): [("Women", "Leggings", 5), ("Women", "Sarees", 2), ("Women", "Kurtas", 2)],
    ("Women", "Dresses"): [("Women", "Outerwear", 2), ("Women", "Jeans", 2), ("Women", "Dresses", 2)],
    ("Women", "Jeans"): [("Women", "Activewear Tops", 2), ("Women", "Outerwear", 2), ("Women", "Dresses", 2)],
    ("Women", "Outerwear"): [("Women", "Jeans", 4), ("Women", "Dresses", 2)],
    ("Women", "Sarees"): [("Women", "Kurtas", 4), ("Women", "Sarees", 2)],
    ("Men", "T-Shirts"): [("Men", "Jeans", 4), ("Men", "Activewear", 2), ("Men", "T-Shirts", 3)],
    ("Men", "Shirts"): [("Men", "Formal Trousers", 4), ("Men", "Jeans", 3), ("Men", "Shirts", 2)],
    ("Men", "Jeans"): [("Men", "T-Shirts", 5), ("Men", "Shirts", 3)],
    ("Men", "Activewear"): [("Men", "T-Shirts", 3), ("Men", "Activewear", 3)],
    ("Men", "Outerwear"): [("Men", "Jeans", 3), ("Men", "Shirts", 2), ("Men", "T-Shirts", 1)],
    ("Men", "Formal Trousers"): [("Men", "Shirts", 6), ("Men", "Formal Trousers", 1)],
}

AGE_BANDS = ["18-24", "25-34", "35-44", "45-54", "55+"]
AGE_MIX = {
    "active": [30, 42, 18, 7, 3],
    "Kurtas": [15, 35, 30, 14, 6],
    "Sarees": [6, 24, 34, 24, 12],
    "Formal Trousers": [8, 38, 32, 16, 6],
    "Outerwear": [18, 36, 26, 14, 6],
    "default": [24, 38, 22, 11, 5],
}
CITIES = [("Bengaluru", 14), ("Mumbai", 13), ("Delhi", 12), ("Hyderabad", 9), ("Pune", 8), ("Chennai", 8),
          ("Kolkata", 6), ("Ahmedabad", 5), ("Gurugram", 4), ("Jaipur", 4), ("Lucknow", 4), ("Noida", 3),
          ("Kochi", 3), ("Chandigarh", 3), ("Indore", 3), ("Bhubaneswar", 2)]


def poisson(rng, mean):
    if mean <= 0:
        return 0
    if mean < 30:
        limit, k, p = math.exp(-mean), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1
    return max(0, round(rng.gauss(mean, math.sqrt(mean))))


def x99(value):
    return int(round(value / 100) * 100 - 1)


def make_products(rng, start, end):
    products = []
    for (dept, cat, code, n, lo, hi, ret, growth, season, share, sups, words, nouns) in CATEGORIES:
        names = set()
        for i in range(n):
            while True:
                name = f"{rng.choice(words)} {rng.choice(nouns)} - {rng.choice(COLOURS)}"
                if name not in names:
                    names.add(name)
                    break
            # most products sit in the lower-middle of the range, a few at the top
            price = min(hi, max(lo, x99(math.exp(rng.triangular(math.log(lo), math.log(hi), math.log(lo) + 0.4 * math.log(hi / lo))))))
            cost = int(round(price * rng.uniform(0.35, 0.60) / 10) * 10)
            if rng.random() < 0.2:
                brand = rng.choice(THIRD_PARTY)
            elif season == "active":
                brand = "Loom Active"
            elif cat in ("Kurtas", "Sarees"):
                brand = "Loom Ethnic"
            else:
                brand = "Urban Loom"
            if rng.random() < 0.78:
                launch = start - dt.timedelta(days=rng.randint(30, 900))
            else:
                launch = start + dt.timedelta(days=rng.randint(0, DAYS - 60))
            weight = rng.lognormvariate(0, 1.15)
            if rng.random() < 0.12:
                weight *= 0.06            # the long tail: products that barely sell
            products.append({
                "sku": f"{dept[0]}-{code}-{i + 1:03d}", "name": name, "department": dept, "category": cat,
                "brand": brand, "cost_inr": cost, "price_inr": price, "launch_date": launch,
                "supplier_id": rng.choice(sups), "status": "active",
                "weight": weight, "stop": None, "role": "normal",
            })

    # Discontinued products stop selling part-way through the two years.
    older = [p for p in products if p["launch_date"] < start]
    favour = {"Formal Trousers": 4, "Jeans": 2, "T-Shirts": 2}
    for p in weighted_sample(rng, older, [favour.get(p["category"], 1) for p in older], 14):
        p["status"], p["role"] = "discontinued", "discontinued"
        p["stop"] = start + dt.timedelta(days=rng.randint(120, DAYS - 150))

    # Dead stock: still listed with stock on hand, but no sale for 100+ days. Slow outerwear adds a
    # few more on its own, because it barely sells out of season.
    pick = lambda cat, dept, k: rng.sample(
        [p for p in older if p["category"] == cat and p["department"] == dept and p["role"] == "normal"], k)
    dead = pick("Formal Trousers", "Men", 2) + pick("Dresses", "Women", 1)
    for p in dead:
        p["role"] = "dead"
        p["stop"] = end - dt.timedelta(days=rng.randint(100, 200))
    return products


def weighted_sample(rng, items, weights, k):
    items, weights, out = list(items), list(weights), []
    for _ in range(k):
        i = rng.choices(range(len(items)), weights=weights)[0]
        out.append(items.pop(i))
        weights.pop(i)
    return out


def season_of(cat_row):
    return cat_row[8]


def make_sales(rng, products, start, end):
    cat_rows = {(c[0], c[1]): c for c in CATEGORIES}
    by_cat = defaultdict(list)
    for i, p in enumerate(products):
        by_cat[(p["department"], p["category"])].append(i)

    days = [start + dt.timedelta(days=d) for d in range(DAYS)]

    def event(day):
        md = (day.month, day.day)
        if (10, 15) <= md <= (11, 12):
            return 1.25, "festive"          # Diwali season
        if (1, 1) <= md <= (1, 14) or (6, 25) <= md <= (7, 10):
            return 1.35, "eoss"             # end-of-season sale
        return 1.0, None

    # Expected demand per product per day.
    demand = []
    for d, day in enumerate(days):
        boost, _ = event(day)
        boost *= 1.12 if day.weekday() >= 5 else 1.0
        live = [not (p["launch_date"] > day or (p["stop"] and day >= p["stop"])) for p in products]
        # A category's demand is shared by the products on sale that day, so launches and
        # discontinued products move demand around rather than changing the category's trend.
        cat_weight = defaultdict(float)
        for p, on in zip(products, live):
            if on:
                cat_weight[(p["department"], p["category"])] += p["weight"]
        row = []
        for p, on in zip(products, live):
            if not on:
                row.append(0.0)
                continue
            key = (p["department"], p["category"])
            c = cat_rows[key]
            share, growth, season = c[9], c[7], SEASON[c[8]][day.month - 1]
            row.append(share * season * (1 + growth) ** (d / 365) * p["weight"] / cat_weight[key] * boost)
        demand.append(row)

    lines_per_order = 1 + 0.32 + 0.32 * 0.25
    scale = TARGET_LINES / lines_per_order / sum(sum(r) for r in demand)
    orders_per_day = [poisson(rng, sum(r) * scale) for r in demand]
    total_orders = sum(orders_per_day)

    pools = {b: [] for b in AGE_BANDS}
    customers = []
    city_names, city_w = zip(*CITIES)
    sales, created, placed, order_no = [], 0, 0, 0

    for d, day in enumerate(days):
        _, kind = event(day)
        weights = demand[d]
        p_web = 0.28 + 0.12 * d / DAYS
        p_myntra = 0.40 - 0.06 * d / DAYS
        for _ in range(orders_per_day[d]):
            order_no += 1
            anchor = rng.choices(range(len(products)), weights=weights)[0]
            ap = products[anchor]
            items = [anchor]
            if rng.random() < 0.32:
                extra = BASKET[(ap["department"], ap["category"])]
                for _ in range(2 if rng.random() < 0.25 else 1):
                    dept, cat, _w = rng.choices(extra, weights=[e[2] for e in extra])[0]
                    choices = [i for i in by_cat[(dept, cat)] if weights[i] > 0 and i not in items]
                    if choices:
                        items.append(rng.choices(choices, weights=[weights[i] for i in choices])[0])

            # Customer: new or returning, with an age band that suits the product.
            c = cat_rows[(ap["department"], ap["category"])]
            mix = AGE_MIX.get("active" if season_of(c) == "active" else ap["category"], AGE_MIX["default"])
            band = rng.choices(AGE_BANDS, weights=mix)[0]
            remaining = total_orders - placed
            if created < N_CUSTOMERS and (not pools[band] or rng.random() < (N_CUSTOMERS - created) / remaining):
                created += 1
                cust = {"customer_id": f"C{created:05d}", "age_band": band,
                        "city": rng.choices(city_names, weights=city_w)[0], "first_order_date": day}
                customers.append(cust)
                pools[band].append(cust)
            else:
                pool = pools[band] or next(v for v in pools.values() if v)
                cust = rng.choice(pool)
            placed += 1

            r = rng.random()
            channel = "website" if r < p_web else "myntra" if r < p_web + p_myntra else "amazon"
            order_id = f"UL{100000 + order_no}"
            for i in items:
                p = products[i]
                c = cat_rows[(p["department"], p["category"])]
                disc_p, lo, hi = {"eoss": (0.65, 0.15, 0.30), "festive": (0.45, 0.10, 0.25)}.get(kind, (0.18, 0.10, 0.20))
                price = p["price_inr"]
                if rng.random() < disc_p:
                    price = int(round(price * (1 - rng.uniform(lo, hi))))
                qty = rng.choices([1, 2, 3], weights=[88, 10, 2])[0]
                sales.append({
                    "order_id": order_id, "order_date": day, "sku": p["sku"], "qty": qty,
                    "unit_price_inr": price, "channel": channel, "customer_id": cust["customer_id"],
                    "returned": rng.random() < c[6] * rng.uniform(0.85, 1.15),
                })
    return sales, customers


def make_inventory(rng, products, sales, end):
    lead = {s[0]: s[3] for s in SUPPLIERS}
    last56, last90 = Counter(), Counter()
    for s in sales:
        age = (end - s["order_date"]).days
        if age < 56:
            last56[s["sku"]] += s["qty"]
        if age < 90:
            last90[s["sku"]] += s["qty"]

    active = [p for p in products if p["status"] == "active"]
    old = end - dt.timedelta(days=120)
    eligible = [p for p in active if p["role"] == "normal" and p["launch_date"] < old and last56[p["sku"]] >= 1]
    slow = [p for p in eligible if p["category"] in ("Outerwear", "Formal Trousers")]
    over = rng.sample(slow, min(9, len(slow)))
    others = [p for p in eligible if p not in over and p["category"] in ("Sarees", "Dresses", "Shirts")]
    over += rng.sample(others, 3)
    for p in over:
        p["role"] = "overstock"
    best = sorted([p for p in active if p["role"] == "normal" and last56[p["sku"]] >= 8],
                  key=lambda p: -last56[p["sku"]])[:40]
    for p in rng.sample(best, 10):
        p["role"] = "reorder"

    rows = []
    for p in products:
        rate = last56[p["sku"]] / 56                       # units per day, last 8 weeks
        lt = lead[p["supplier_id"]]
        rp = math.ceil(rate * (lt + 14))
        on_order = 0
        if p["role"] == "discontinued":
            on_hand, rp = 0, 0
            received = p["stop"] - dt.timedelta(days=rng.randint(30, 90))
        elif p["role"] == "dead" or (p["status"] == "active" and last90[p["sku"]] == 0):
            on_hand, rp = rng.randint(25, 140), rng.randint(3, 8)
            received = end - dt.timedelta(days=rng.randint(150, 300))
        elif p["role"] == "overstock":
            on_hand = max(30, math.ceil(rate * rng.uniform(150, 320)))
            received = end - dt.timedelta(days=rng.randint(20, 120))
        elif p["role"] == "reorder":
            rp = max(rp, 4)
            on_hand = int(rate * rng.uniform(1, (lt + 14) * 0.5))
            received = end - dt.timedelta(days=rng.randint(25, 70))
        elif rate == 0:                                     # sold in 90 days but not in 8 weeks
            on_hand, rp, on_order = 0, 0, rng.randint(5, 20)
            received = end - dt.timedelta(days=rng.randint(60, 120))
        else:
            on_hand = math.ceil(rate * rng.uniform(lt + 18, 100))
            if rng.random() < 0.3:
                on_order = math.ceil(rate * rng.uniform(14, 45))
            received = end - dt.timedelta(days=rng.randint(5, 60))
        received = max(received, p["launch_date"])
        rows.append({"sku": p["sku"], "on_hand": on_hand, "on_order": on_order, "reorder_point": rp,
                     "last_received_date": received, "_rate": rate, "_last90": last90[p["sku"]]})
    return rows


def write(name, rows, columns):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            out = []
            for c in columns:
                v = r[c]
                out.append("true" if v is True else "false" if v is False else v.isoformat() if isinstance(v, dt.date) else v)
            w.writerow(out)
    print(f"  {name + '.csv':16} {len(rows):>7,} rows")


def summary(products, sales, inventory, end):
    units = Counter()
    for s in sales:
        units[s["sku"]] += s["qty"]
    ranked = sorted((units[p["sku"]] for p in products), reverse=True)
    top = ranked[: round(len(ranked) * 0.15)]
    print(f"\nTop 15% of SKUs sell {sum(top) / sum(ranked):.0%} of units; "
          f"{sum(1 for u in ranked if u < 25)} SKUs sold under 25 units in two years.")

    cat_of = {p["sku"]: (p["department"], p["category"]) for p in products}
    cur, prev, ret, tot = Counter(), Counter(), Counter(), Counter()
    for s in sales:
        k = cat_of[s["sku"]]
        (cur if (end - s["order_date"]).days < 365 else prev)[k] += s["qty"]
        tot[k] += s["qty"]
        ret[k] += s["qty"] if s["returned"] else 0
    print("\nCategory                    units/yr  growth  returns")
    for c in CATEGORIES:
        k = (c[0], c[1])
        print(f"  {c[0]:5} {c[1]:20} {cur[k]:>7,}  {cur[k] / prev[k] - 1:+6.0%}  {ret[k] / tot[k]:6.1%}")

    status = Counter()
    for r in inventory:
        rate, total = r["_rate"], r["on_hand"] + r["on_order"]
        if r["_last90"] == 0 and r["on_hand"] > 0:
            status["dead stock"] += 1
        elif total < r["reorder_point"]:
            status["reorder"] += 1
        elif rate > 0 and r["on_hand"] / rate > 120:
            status["overstock"] += 1
    print(f"\nInventory: {status['reorder']} to reorder, {status['overstock']} overstocked (>120 days of cover), "
          f"{status['dead stock']} dead stock (no sale in 90 days).")


def main():
    ap = argparse.ArgumentParser(description="Generate the Urban Loom demo shop as CSV files.")
    ap.add_argument("--end-date", help="last day of sales, YYYY-MM-DD (default: yesterday)")
    args = ap.parse_args()
    end = dt.date.fromisoformat(args.end_date) if args.end_date else dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=DAYS - 1)
    rng = random.Random(SEED)

    products = make_products(rng, start, end)
    sales, customers = make_sales(rng, products, start, end)
    inventory = make_inventory(rng, products, sales, end)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")

    print(f"Urban Loom, sales {start} to {end}. Writing {OUT}")
    write("suppliers", [dict(zip(["supplier_id", "name", "city", "lead_time_days", "moq"], s)) for s in SUPPLIERS],
          ["supplier_id", "name", "city", "lead_time_days", "moq"])
    write("products", products, ["sku", "name", "department", "category", "brand", "cost_inr", "price_inr",
                                  "launch_date", "supplier_id", "status"])
    write("customers", customers, ["customer_id", "age_band", "city", "first_order_date"])
    write("sales", sales, ["order_id", "order_date", "sku", "qty", "unit_price_inr", "channel", "customer_id", "returned"])
    write("inventory", inventory, ["sku", "on_hand", "on_order", "reorder_point", "last_received_date"])
    write("settings", [{"org_id": "default", "shop_name": SHOP_NAME, "rules_json": json.dumps(DEFAULT_RULES),
                        "updated_at": now, "profile_json": ""}],   # empty: the app uses its default profile
          ["org_id", "shop_name", "rules_json", "updated_at", "profile_json"])
    summary(products, sales, inventory, end)


if __name__ == "__main__":
    main()
