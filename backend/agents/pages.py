"""Data for the shop pages in the sidebar: Products, Inventory, Sales, Returns, Customers, Suppliers.

Every page has the same shape, rendered generically by static/data.js:
{
  "title": str, "intro": str, "data_until": "YYYY-MM-DD",
  "kpis":   [{"label", "value", "format", "note"}],
  "tables": [{"id", "title", "note", "columns": [{"key", "label", "format"}], "rows": [{...}],
              "search": [keys], "filters": [keys], "sort": [key, "asc"|"desc"]}]
}
Formats: text, inr, num, dec1, pct, days, date, month, status, yesno. Numbers come from SQL or plain arithmetic here.
Each page is cached for 10 minutes.
"""
import asyncio
import datetime as dt
import time

from config import MOCK
from agents import bq, mock

CHANNELS = {"website": "Website", "myntra": "Myntra", "amazon": "Amazon"}
VS = "vs previous 30 days"
_cache: dict[str, tuple[float, dict]] = {}


def col(key, label, fmt="text"):
    return {"key": key, "label": label, "format": fmt}


def kpi(label, value, fmt="num", note="", change=None, higher_is_better=True):
    """change: growth vs the previous period (0.12 = +12%), shown with an arrow next to the note."""
    return {"label": label, "value": value, "format": fmt, "note": note,
            "change": None if change is None else round(change, 4), "higher_is_better": higher_is_better}


def _div(a, b):
    return a / b if b else None


async def _run(*names):
    if MOCK:
        return [getattr(mock, n)() for n in names]
    return await asyncio.gather(*(bq.run(n) for n in names))


async def inventory_page():
    (rows,) = await _run("inventory_status")
    by = lambda s: [r for r in rows if r["status"] == s]
    value = lambda rs: sum(r["stock_value"] for r in rs)
    return {
        "title": "Inventory",
        "intro": "Stock for every active product. Sales speed is the last 8 weeks; cover = days the stock on hand lasts at that speed.",
        "kpis": [
            kpi("Stock value", value(rows), "inr", "on hand, at cost"),
            kpi("Products in stock", sum(1 for r in rows if r["on_hand"] > 0), "num", f"of {len(rows)} active"),
            kpi("Units on hand", sum(r["on_hand"] for r in rows), "num", f"{sum(r['on_order'] for r in rows):,} more on order"),
            kpi("To reorder", len(by("reorder")), "num", "below the reorder point"),
            kpi("Overstock value", value(by("overstock")), "inr", f"{len(by('overstock'))} products, over 120 days of cover"),
            kpi("Dead stock value", value(by("dead")), "inr", f"{len(by('dead'))} products, no sale in 90 days"),
        ],
        "tables": [{
            "id": "stock", "title": "Stock by product",
            "columns": [col("name", "Product"), col("category", "Category"), col("department", "Dept"),
                        col("on_hand", "On hand", "num"), col("on_order", "On order", "num"),
                        col("weekly_sales", "Sales / week", "dec1"), col("cover_days", "Cover", "days"),
                        col("sell_through_90d", "Sell-through 90d", "pct"), col("stock_value", "Stock value", "inr"),
                        col("status", "Status", "status")],
            "rows": rows, "search": ["name", "sku", "supplier"], "filters": ["department", "category", "status"],
            "note": "Sell-through = units sold in 90 days ÷ (units sold + units on hand). Stock value is at cost price.",
        }],
    }


async def products_page():
    (rows,) = await _run("products_list")
    active = [r for r in rows if r["status"] == "active"]
    anchor = max((r["last_sale"] for r in rows if r["last_sale"]), default=None)
    new = [r for r in rows if anchor and (_d(anchor) - _d(r["launch_date"])).days < 365]
    return {
        "title": "Products",
        "intro": "The whole catalogue with list prices and the last 12 months of sales.",
        "kpis": [
            kpi("Active products", len(active), "num", f"{len(rows) - len(active)} discontinued"),
            kpi("Categories", len({(r['department'], r['category']) for r in active}), "num", "across Women and Men"),
            kpi("Average list price", _div(sum(r["price_inr"] for r in active), len(active)), "inr", "active products"),
            kpi("Average list margin", _div(sum(r["list_margin"] for r in active), len(active)), "pct", "list price vs cost"),
            kpi("Launched in 12 months", len(new), "num", "new products"),
            kpi("Revenue, 12 months", sum(r["revenue_12m"] for r in rows), "inr", "after returns"),
        ],
        "tables": [{
            "id": "products", "title": "Catalogue",
            "columns": [col("name", "Product"), col("category", "Category"), col("department", "Dept"),
                        col("brand", "Brand"), col("price_inr", "Price", "inr"), col("cost_inr", "Cost", "inr"),
                        col("list_margin", "List margin", "pct"), col("units_12m", "Units (12 mo)", "num"),
                        col("revenue_12m", "Revenue (12 mo)", "inr"), col("return_rate", "Returns", "pct"),
                        col("launch_date", "Launched", "date"), col("status", "Status", "status")],
            "rows": rows, "search": ["name", "sku", "brand", "supplier"],
            "filters": ["department", "category", "brand", "status"],
            "note": "List margin = (list price − cost) ÷ list price, before discounts, fees and shipping.",
        }],
    }


async def sales_page():
    period, monthly, recent = await _run("sales_period", "sales_monthly", "sales_recent")
    by = {r["period"]: r for r in period}
    cur, prev = by.get("cur") or {}, by.get("prev") or {}
    until = (cur or prev).get("data_until")

    def change(key):
        return _change(cur.get(key), prev.get(key))

    disc = lambda p: _div(p.get("list_value", 0) - p.get("gross", 0), p.get("list_value"))
    months = [{
        **m, "aov": _div(m["revenue"], m["orders"]), "discount": _div(m["list_value"] - m["gross"], m["list_value"]),
        "return_rate": _div(m["returned_units"], m["units"]),
        "label": m["month"] + (" (to date)" if until and m["month"] == until[:7] and not _month_end(until) else ""),
    } for m in monthly]
    return {
        "title": "Sales",
        "intro": "The last 30 days compared with the 30 days before, sales by month, and the latest orders.",
        "data_until": until,
        "kpis": [
            kpi("Revenue, 30 days", cur.get("revenue"), "inr", VS, change("revenue")),
            kpi("Orders", cur.get("orders"), "num", VS, change("orders")),
            kpi("Units sold", cur.get("units"), "num", VS, change("units")),
            kpi("Average order value", _div(cur.get("revenue"), cur.get("orders")), "inr", VS,
                _change(_div(cur.get("revenue"), cur.get("orders")), _div(prev.get("revenue"), prev.get("orders")))),
            kpi("Average discount", disc(cur), "pct", "below list price"),
            kpi("Customers", cur.get("customers"), "num", "ordered in 30 days"),
        ],
        "tables": [
            {
                "id": "months", "title": "By month",
                "columns": [col("label", "Month", "month"), col("orders", "Orders", "num"), col("units", "Units", "num"),
                            col("revenue", "Revenue", "inr"), col("aov", "Avg order", "inr"),
                            col("discount", "Discount", "pct"), col("return_rate", "Returns", "pct")],
                "rows": months, "sort": ["label", "desc"],
                "note": "Revenue is after returns. Discount = how far below list price customers paid.",
            },
            {
                "id": "orders", "title": "Latest 100 orders",
                "columns": [col("order_id", "Order"), col("order_date", "Date", "date"), col("channel", "Channel"),
                            col("customer_id", "Customer"), col("items", "Items"), col("units", "Units", "num"),
                            col("value", "Value", "inr"), col("has_return", "Returned", "yesno")],
                "rows": [{**r, "channel": CHANNELS.get(r["channel"], r["channel"])} for r in recent],
                "search": ["order_id", "customer_id", "items"], "filters": ["channel"],
            },
        ],
    }


async def returns_page():
    breakdown, products = await _run("returns_breakdown", "returns_products")
    cats = [r for r in breakdown if r["dimension"] == "category"]
    chans = [r for r in breakdown if r["dimension"] == "channel"]
    units = sum(r["units"] for r in cats)
    returned = sum(r["returned_units"] for r in cats)
    for r in breakdown:
        r["return_rate"] = _div(r["returned_units"], r["units"])
        if r["dimension"] == "channel":
            r["label"] = CHANNELS.get(r["label"], r["label"])
    worst = max(cats, key=lambda r: r["return_rate"] or 0, default=None)
    return {
        "title": "Returns",
        "intro": "What comes back, from where, and which products are sent back most. Last 12 months.",
        "kpis": [
            kpi("Return rate", _div(returned, units), "pct", "of units sold"),
            kpi("Units returned", returned, "num", f"of {units:,} sold"),
            kpi("Value returned", sum(r["returned_value"] for r in cats), "inr", "at the price paid"),
            kpi("Highest category", worst["return_rate"] if worst else None, "pct",
                f"{worst['label']} ({worst['department']})" if worst else ""),
        ],
        "tables": [
            {
                "id": "categories", "title": "By category",
                "columns": [col("label", "Category"), col("department", "Dept"), col("units", "Units sold", "num"),
                            col("returned_units", "Returned", "num"), col("return_rate", "Return rate", "pct"),
                            col("returned_value", "Value returned", "inr")],
                "rows": sorted(cats, key=lambda r: -(r["return_rate"] or 0)), "filters": ["department"],
            },
            {
                "id": "channels", "title": "By channel",
                "columns": [col("label", "Channel"), col("units", "Units sold", "num"),
                            col("returned_units", "Returned", "num"), col("return_rate", "Return rate", "pct"),
                            col("returned_value", "Value returned", "inr")],
                "rows": sorted(chans, key=lambda r: -(r["return_rate"] or 0)),
            },
            {
                "id": "products", "title": "Most returned products",
                "columns": [col("name", "Product"), col("category", "Category"), col("department", "Dept"),
                            col("units", "Units sold", "num"), col("returned_units", "Returned", "num"),
                            col("return_rate", "Return rate", "pct"), col("returned_value", "Value returned", "inr")],
                "rows": products, "search": ["name", "sku"], "filters": ["category"],
                "note": "Products with at least 30 units sold in 12 months.",
            },
        ],
    }


async def customers_page():
    summary, segments, top = await _run("customers_summary", "customers_segments", "customers_top")
    s = summary[0] if summary else {}
    for r in segments:
        r["aov"] = _div(r["revenue"], r["orders"])
        r["per_customer"] = _div(r["revenue"], r["customers"])
    ages = sorted([r for r in segments if r["dimension"] == "age_band"], key=lambda r: r["label"])
    cities = sorted([r for r in segments if r["dimension"] == "city"], key=lambda r: -r["revenue"])
    return {
        "title": "Customers",
        "intro": "Who buys from the shop. Activity is the last 12 months.",
        "kpis": [
            kpi("Customers", s.get("customers"), "num", "all time"),
            kpi("Active", s.get("active_12m"), "num", "ordered in 12 months"),
            kpi("New", s.get("new_12m"), "num", "first order in 12 months"),
            kpi("Repeat buyers", _div(s.get("repeat_12m"), s.get("active_12m")), "pct", "of active, 2+ orders"),
            kpi("Orders per customer", _div(s.get("orders_12m"), s.get("active_12m")), "dec1", "12 months"),
            kpi("Spend per customer", _div(s.get("revenue_12m"), s.get("active_12m")), "inr", "12 months, after returns"),
        ],
        "tables": [
            {
                "id": "ages", "title": "By age band",
                "columns": [col("label", "Age band"), col("customers", "Customers", "num"), col("orders", "Orders", "num"),
                            col("revenue", "Revenue", "inr"), col("aov", "Avg order", "inr"),
                            col("per_customer", "Per customer", "inr")],
                "rows": ages,
            },
            {
                "id": "cities", "title": "By city",
                "columns": [col("label", "City"), col("customers", "Customers", "num"), col("orders", "Orders", "num"),
                            col("revenue", "Revenue", "inr"), col("aov", "Avg order", "inr"),
                            col("per_customer", "Per customer", "inr")],
                "rows": cities, "search": ["label"],
            },
            {
                "id": "top", "title": "Top 50 customers",
                "columns": [col("customer_id", "Customer"), col("age_band", "Age band"), col("city", "City"),
                            col("first_order_date", "Customer since", "date"), col("orders", "Orders", "num"),
                            col("units", "Units", "num"), col("revenue", "Spend", "inr"),
                            col("returned_units", "Returned", "num"), col("last_order", "Last order", "date")],
                "rows": top, "search": ["customer_id", "city"], "filters": ["city", "age_band"],
                "note": "Spend is the last 12 months, after returns.",
            },
        ],
    }


async def suppliers_page():
    (rows,) = await _run("suppliers_list")
    leads = [r["lead_time_days"] for r in rows]
    return {
        "title": "Suppliers",
        "intro": "Who makes the products, how long they take, and how much of the shop depends on each.",
        "kpis": [
            kpi("Suppliers", len(rows), "num", f"{len({r['city'] for r in rows})} cities"),
            kpi("Average lead time", _div(sum(leads), len(leads)), "days", f"{min(leads, default=0)} to {max(leads, default=0)} days"),
            kpi("Stock value", sum(r["stock_value"] for r in rows), "inr", "on hand, at cost"),
            kpi("On order", sum(r["on_order_value"] for r in rows), "inr", "at cost"),
        ],
        "tables": [{
            "id": "suppliers", "title": "All suppliers",
            "columns": [col("name", "Supplier"), col("city", "City"), col("lead_time_days", "Lead time", "days"),
                        col("moq", "Min order", "num"), col("active_products", "Products", "num"),
                        col("categories", "Categories"), col("units_12m", "Units (12 mo)", "num"),
                        col("revenue_12m", "Revenue (12 mo)", "inr"), col("stock_value", "Stock value", "inr"),
                        col("on_order_value", "On order", "inr")],
            "rows": rows, "search": ["name", "city", "categories"], "filters": ["city"],
        }],
    }


PAGES = {
    "inventory": inventory_page, "products": products_page, "sales": sales_page,
    "returns": returns_page, "customers": customers_page, "suppliers": suppliers_page,
}


async def get_page(name: str) -> dict:
    hit = _cache.get(name)
    if hit and time.monotonic() - hit[0] < 600:
        return hit[1]
    page = await PAGES[name]()
    _cache[name] = (time.monotonic(), page)
    return page


def _d(value) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value)[:10])


def _month_end(iso: str) -> bool:
    return (_d(iso) + dt.timedelta(days=1)).day == 1


def _change(now, before):
    return (now - before) / before if now is not None and before else None
