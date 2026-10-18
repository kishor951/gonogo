"""The shop's business at a glance, for the Business page: key numbers with change vs the 12 months
before, monthly revenue, category performance and channel split. Cached for 10 minutes."""
import asyncio
import datetime as dt
import time

from config import DATASET, MOCK
from agents import bq, mock

CHANNELS = {"website": "Website", "myntra": "Myntra", "amazon": "Amazon"}
_cache: tuple[float, dict] | None = None


def _div(a, b):
    return a / b if b else None


def _change(now, before):
    return round((now - before) / before, 4) if now is not None and before else None


def _r(x, digits=4):
    return None if x is None else round(x, digits)


def build_overview(kpis: list[dict], monthly: list[dict], categories: list[dict], channels: list[dict]) -> dict:
    by = {r["period"]: r for r in kpis}
    cur = by.get("cur") or {}
    prev = by.get("prev") or {}
    meta = cur or prev
    # Only compare with the previous 12 months when the data really covers them.
    until, start = meta.get("data_until"), meta.get("data_from")
    full_prior = bool(until and start) and (dt.date.fromisoformat(until) - dt.date.fromisoformat(start)).days >= 728
    if not full_prior:
        prev = {}

    def figures(p):
        if not p:
            return {}
        return {
            "revenue": p["revenue"], "units": p["units"], "orders": p["orders"],
            "margin": _div(p["revenue"] - p["cost"], p["revenue"]),
            "aov": _div(p["revenue"], p["orders"]),
            "return_rate": _div(p["returned_units"], p["units"]),
        }

    c, pv = figures(cur), figures(prev)
    spec = [
        ("revenue", "Revenue", "inr", True, "after returns"),
        ("units", "Units sold", "num", True, "before returns"),
        ("margin", "Gross margin", "pct", True, "revenue minus cost of goods"),
        ("orders", "Orders", "num", True, ""),
        ("aov", "Average order value", "inr", True, "revenue per order"),
        ("return_rate", "Return rate", "pct", False, "of units sold"),
    ]
    kpi_list = []
    for key, label, fmt, up_good, note in spec:
        now, before = c.get(key), pv.get(key)
        # Margin and return rate change in percentage points; the rest as % growth.
        change = (_r(now - before) if now is not None and before is not None else None) if fmt == "pct" else _change(now, before)
        kpi_list.append({"id": key, "label": label, "format": fmt, "value": _r(now), "prev": _r(before),
                         "change": change, "change_kind": "points" if fmt == "pct" else "growth",
                         "higher_is_better": up_good, "note": note})

    total_rev = sum(r["revenue"] for r in channels) or 1
    return {
        "source": f"BigQuery · {DATASET}",
        "data_from": start,
        "data_until": until,
        "has_prior_year": full_prior,
        "active_skus": meta.get("active_skus"),
        "customers_12m": cur.get("customers"),
        "kpis": kpi_list,
        "monthly": [{"month": r["month"], "revenue": r["revenue"], "units": r["units"]} for r in monthly],
        "categories": [{
            "department": r["department"], "category": r["category"], "revenue": r["revenue"], "units": r["units"],
            "margin": _r(_div(r["revenue"] - r["cost"], r["revenue"])),
            "growth": _change(r["revenue"], r["revenue_prev"]) if full_prior else None,
            "return_rate": _r(_div(r["returned_units"], r["units"])),
        } for r in categories],
        "channels": [{
            "channel": r["channel"], "label": CHANNELS.get(r["channel"], r["channel"]), "revenue": r["revenue"],
            "share": _r(r["revenue"] / total_rev), "orders": r["orders"], "units": r["units"],
            "aov": _r(_div(r["revenue"], r["orders"]), 0),
            "growth": _change(r["revenue"], r["revenue_prev"]) if full_prior else None,
        } for r in channels],
    }


async def get_overview() -> dict:
    global _cache
    if _cache and time.monotonic() - _cache[0] < 600:
        return _cache[1]
    if MOCK:
        parts = mock.business_kpis(), mock.business_monthly(), mock.business_categories(), mock.business_channels()
    else:
        parts = await asyncio.gather(bq.run("business_kpis"), bq.run("business_monthly"),
                                     bq.run("business_categories"), bq.run("business_channels"))
    overview = build_overview(*parts)
    _cache = (time.monotonic(), overview)
    return overview
