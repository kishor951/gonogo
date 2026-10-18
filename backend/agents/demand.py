"""Demand agent: finds comparable products in the shop's own sales history (BigQuery) and
estimates how many units the new product would sell. All numbers are calculated, not generated."""
import asyncio

from config import MOCK
from agents import bq, mock
from agents.catalog import match_catalog
from agents.common import evidence, inr, pct


def segment_params(product: dict, price_inr: float, a: dict) -> dict:
    return {
        "category": product["category"],
        "department": product["department"],
        "price": float(price_inr),
        "band": float(a["price_band_pct"] / 100),
    }


def cat_rate_early(s: dict) -> float:
    return s["cat_units"] / s["cat_sku_months"] if s["cat_sku_months"] else 0


def _growth(now, before):
    return (now - before) / before if before else None


def _relative(seg, shop):
    """Segment growth relative to the shop's: +10% means comparables grew 10% faster than the shop."""
    if seg is None:
        return None
    return seg if shop is None else (1 + seg) / (1 + shop) - 1


async def run_demand(product: dict, price_inr: float, a: dict, catalog: list | None = None, name: str = "",
                     existing: dict | None = None):
    params = segment_params(product, price_inr, a)
    if MOCK:
        comps, stats, monthly = mock.comparables(params), mock.demand_stats(params), mock.segment_monthly(params)
    else:
        comps, stats, monthly = await asyncio.gather(
            bq.run("comparables", params), bq.run("demand_stats", params), bq.run("segment_monthly", params))

    s = {k: (v or 0) for k, v in stats[0].items()}
    shop_rate = s["shop_units"] / s["shop_sku_months"] if s["shop_sku_months"] else 0
    seg_rate = s["seg_units"] / s["seg_sku_months"] if s["seg_sku_months"] else 0
    cat_rate = s["cat_units"] / s["cat_sku_months"] if s["cat_sku_months"] else 0
    # No products of yours at this price: compare with the whole category instead of calling it zero.
    basis = "similar products at this price"
    if not s["seg_sku_months"] and s["cat_sku_months"]:
        seg_rate, basis = cat_rate_early(s), f"all your {product['category']} (none at this price)"
    velocity = seg_rate / shop_rate if shop_rate else 0          # 1.0 = sells like the shop's average product
    cat_velocity = cat_rate / shop_rate if shop_rate else 0

    # Trend: last 3 months vs the same 3 months last year (so seasons cancel out), relative to the shop.
    # Without last year's numbers (a new segment), fall back to the previous 3 months.
    seg_yoy = _growth(s["seg_last_3m"], s["seg_ly_3m"])
    shop_yoy = _growth(s["shop_last_3m"], s["shop_ly_3m"])
    seg_q = _growth(s["seg_last_3m"], s["seg_prev_3m"])
    shop_q = _growth(s["shop_last_3m"], s["shop_prev_3m"])
    if seg_yoy is not None:
        trend, trend_basis = _relative(seg_yoy, shop_yoy), "same 3 months last year"
    else:
        trend, trend_basis = _relative(seg_q, shop_q), "previous 3 months"

    return_rate = s["seg_returned"] / s["seg_units_all"] if s["seg_units_all"] else 0.0
    expected_monthly = seg_rate                                   # units per comparable product per month
    confidence = "good" if s["seg_skus"] >= 4 and s["seg_units"] >= 60 else "low"
    if basis != "similar products at this price":
        confidence = "low"
    by_bucket = {r["bucket"]: r["seg_units"] for r in monthly}

    # The shop's own products closest to this one (same department and category, by name), with their sales.
    own = [r for r in match_catalog(name, catalog or [], product["department"], product["category"])
           if r["score"] >= 0.34]
    own_rows = [{"name": r["name"], "units_12m": r.get("units_12m") or 0, "per_month": r["per_month"],
                 "price_inr": r.get("price_inr"), "status": r.get("status"), "score": r["score"]} for r in own]

    result = {
        "comparables": s["seg_skus"],
        "segment_units_12m": s["seg_units"],
        "velocity": round(velocity, 2),
        "category_velocity": round(cat_velocity, 2),
        "shop_avg_monthly_units": round(shop_rate, 1),
        "trend": None if trend is None else round(trend, 3),
        "trend_meaning": f"comparables' growth in the last 3 months vs the {trend_basis}, relative to the whole shop's growth",
        "segment_growth_yoy": None if seg_yoy is None else round(seg_yoy, 3),
        "shop_growth_yoy": None if shop_yoy is None else round(shop_yoy, 3),
        "segment_growth_vs_prev_3m": None if seg_q is None else round(seg_q, 3),
        "return_rate": round(return_rate, 3),
        "expected_monthly_units": round(expected_monthly, 1),
        "confidence": confidence,
        # oldest -> newest, for the sparkline on the page
        "monthly_segment_units": [by_bucket.get(b, 0) for b in range(11, -1, -1)],
        "own_closest": own_rows,
        "basis": basis,
        "existing": existing,     # this exact product, if the shop already stocks it
        "shop_avg_monthly": round(shop_rate, 1),
    }

    def signed(x):
        return "-" if x is None else f"{x * 100:+.0f}%"

    top = [[r["name"], r["brand"] or "-", inr(r["price_inr"]), r["units_12m"]]
           for r in comps if r["status"] == "active"][:8]
    ev = evidence(
        summary=[
            ["Comparable products", f"{s['seg_skus']} active in {product['category']} ({product['department']}), "
                                    f"priced {inr(price_inr * (1 - params['band']))} to {inr(price_inr * (1 + params['band']))}"],
            ["Units they sold, last 12 months", f"{s['seg_units']:,}"],
            ["Sales per product per month", f"{seg_rate:.1f} (shop average {shop_rate:.1f}; whole category {cat_rate:.1f})"],
            ["Sales speed vs shop average", f"{velocity:.2f}x (whole category: {cat_velocity:.2f}x)"],
            ["Trend vs the whole shop", f"{signed(trend)} (last 3 months vs {trend_basis})"],
            ["Comparables, last 3 months", f"{signed(seg_yoy)} vs last year, {signed(seg_q)} vs previous 3 months "
                                           f"(shop: {signed(shop_yoy)} and {signed(shop_q)})"],
            ["Return rate of comparables", pct(return_rate, 1)],
            ["Expected units per month", f"{expected_monthly:.0f} (what a comparable product sells)"],
            ["Data confidence", confidence],
        ],
        tables=[t for t in [{
            "title": "Your closest products (already in your shop)",
            "columns": ["Product", "Price", "Units (12 mo)", "A month", "vs your average"],
            "rows": [[r["name"] + ("" if r["status"] == "active" else " (discontinued)"), inr(r["price_inr"]),
                      r["units_12m"], f"{r['per_month']:.0f}",
                      f"{r['per_month'] / shop_rate:.1f}×" if shop_rate else "-"] for r in own_rows],
        } if own_rows else None, {
            "title": "Best-selling comparable products",
            "columns": ["Product", "Brand", "Price", "Units (12 mo)"],
            "rows": top,
        } if top else None] if t] or None,
        note="BigQuery: the shop's own sales, last 12 months. Speed counts only the months each product was on sale.",
    )
    return result, ev
