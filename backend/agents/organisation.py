"""The organisation's business data at a glance, for the Organisation page. Read once and cached."""
import asyncio

from config import DATASET, MOCK, USD_INR
from agents import bq, mock

_cache: dict | None = None


async def get_overview() -> dict:
    global _cache
    if _cache is None:
        if MOCK:
            raw = mock.organisation()
        else:
            summary, top = await asyncio.gather(bq.run("store_summary"), bq.run("top_categories"))
            raw = {"summary": summary[0], "top_categories": top}
        s = raw["summary"]
        _cache = {
            "source": f"BigQuery · {DATASET}",
            "data_until": s["data_until"],
            "usd_inr": USD_INR,
            "summary": {
                "products": s["products"],
                "categories": s["categories"],
                "units_12m": s["units_12m"],
                "orders_12m": s["orders_12m"],
                "customers_12m": s["customers_12m"],
                "return_rate": round(float(s["return_rate"] or 0), 4),
                "avg_sale_inr": round(float(s["avg_sale_usd"] or 0) * USD_INR),
            },
            "top_categories": [
                {"department": r["department"], "category": r["category"], "units_12m": r["units_12m"],
                 "avg_sale_inr": round(float(r["avg_sale_usd"]) * USD_INR)}
                for r in raw["top_categories"]
            ],
        }
    return _cache
