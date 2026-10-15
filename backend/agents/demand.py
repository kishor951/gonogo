"""Demand agent: finds comparable products in the store's own sales history (BigQuery) and
estimates how many units the new product would sell. All numbers are calculated, not generated."""
import asyncio

from config import MOCK, USD_INR
from agents import bq, mock
from agents.common import evidence, inr, pct


def segment_params(product: dict, price_inr: float, a: dict) -> dict:
    return {
        "category": product["category"],
        "department": product["department"],
        "price_usd": float(price_inr / USD_INR),
        "band": float(a["price_band_pct"] / 100),
    }


async def run_demand(product: dict, price_inr: float, a: dict):
    params = segment_params(product, price_inr, a)
    if MOCK:
        comps, stats = mock.comparables(params), mock.segment_stats(params)
    else:
        comps, stats = await asyncio.gather(bq.run("comparables", params), bq.run("segment_stats", params))

    s0 = stats[0]
    store_units, store_skus = s0["store_units"], s0["store_skus"]
    cat_skus, seg_skus = s0["cat_skus"], s0["seg_skus"]
    seg_units = sum(r["seg_units"] for r in stats)
    cat_units = sum(r["cat_units"] for r in stats)

    store_rate = store_units / store_skus if store_skus else 0
    seg_rate = seg_units / seg_skus if seg_skus else 0
    cat_rate = cat_units / cat_skus if cat_skus else 0
    velocity = seg_rate / store_rate if store_rate else 0          # 1.0 = sells like the average product
    cat_velocity = cat_rate / store_rate if store_rate else 0

    by_bucket = {r["bucket"]: r["seg_units"] for r in stats}
    store_by_bucket = {r["bucket"]: r.get("store_bucket_units", 0) for r in stats}

    def growth(series):
        recent = sum(series.get(b, 0) for b in (0, 1, 2))
        prior = sum(series.get(b, 0) for b in (3, 4, 5))
        return (recent - prior) / prior if prior else None

    seg_growth, store_growth = growth(by_bucket), growth(store_by_bucket)
    # The whole store grows over time, so compare the segment with the store:
    # +10% means comparables are growing 10% faster than the shop overall.
    if seg_growth is not None and store_growth is not None:
        trend = (1 + seg_growth) / (1 + store_growth) - 1
    else:
        trend = seg_growth

    sold = sum(r["units_12m"] for r in comps)
    returned = sum(r["returned_12m"] for r in comps)
    return_rate = returned / sold if sold else 0.0

    expected_monthly = velocity * a["avg_units_per_product"]
    confidence = "good" if seg_skus >= 15 and seg_units >= 30 else "low"

    result = {
        "comparables": seg_skus,
        "segment_units_12m": seg_units,
        "velocity": round(velocity, 2),
        "category_velocity": round(cat_velocity, 2),
        "trend": None if trend is None else round(trend, 3),
        "trend_meaning": "comparables' growth over the last 3 months relative to the whole store's growth",
        "segment_growth_raw": None if seg_growth is None else round(seg_growth, 3),
        "store_growth_raw": None if store_growth is None else round(store_growth, 3),
        "return_rate": round(return_rate, 3),
        "expected_monthly_units": round(expected_monthly, 1),
        "confidence": confidence,
        # oldest -> newest, for the sparkline on the page
        "monthly_segment_units": [by_bucket.get(b, 0) for b in range(11, -1, -1)],
    }

    top = [
        [r["name"], r["brand"] or "-", inr(r["retail_price"] * USD_INR), r["units_12m"]]
        for r in comps[:8]
    ]
    ev = evidence(
        summary=[
            ["Comparable products", f"{seg_skus} in {product['category']} ({product['department']}), "
                                    f"priced {inr(price_inr * (1 - params['band']))} to {inr(price_inr * (1 + params['band']))}"],
            ["Units they sold, last 12 months", f"{seg_units:,}"],
            ["Sales speed vs store average", f"{velocity:.2f}x (whole category: {cat_velocity:.2f}x)"],
            ["Trend vs the whole store, last 3 months", "-" if trend is None else
             f"{trend * 100:+.0f}% (comparables {seg_growth * 100:+.0f}%, store {store_growth * 100:+.0f}%)"
             if seg_growth is not None and store_growth is not None else f"{trend * 100:+.0f}%"],
            ["Return rate of comparables", pct(return_rate, 1)],
            ["Expected units per month", f"{expected_monthly:.0f} = {velocity:.2f} x {a['avg_units_per_product']} "
                                         f"(your typical product's monthly sales)"],
            ["Data confidence", confidence],
        ],
        tables=[{
            "title": "Best-selling comparable products",
            "columns": ["Product", "Brand", "Price", "Units (12 mo)"],
            "rows": top,
        }] if top else None,
        note=f"BigQuery: thelook_ecommerce sample store, last 360 days. Prices converted at ₹{USD_INR:g} per US$.",
    )
    return result, ev
