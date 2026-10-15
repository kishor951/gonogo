"""Fit agent: basket analysis (what else buyers of comparable products put in the same order)
and customer segments (who buys them). Both straight from BigQuery."""
import asyncio

from config import MOCK
from agents import bq, mock
from agents.common import evidence
from agents.demand import segment_params


async def run_fit(product: dict, price_inr: float, a: dict):
    params = segment_params(product, price_inr, a)
    if MOCK:
        basket, buyers = mock.basket(params), mock.buyers(params)
    else:
        basket, buyers = await asyncio.gather(bq.run("basket", params), bq.run("buyers", params))

    seg_orders = basket[0]["seg_orders"] if basket else 0
    total_buyers = sum(r["units"] for r in buyers) or 1
    top_age = buyers[0]["age_band"] if buyers else None
    top_age_share = buyers[0]["units"] / total_buyers if buyers else 0

    result = {
        "bought_with": [r["category"] for r in basket[:3]],
        "top_age_band": top_age,
        "top_age_share": round(top_age_share, 3),
    }
    ev = evidence(
        summary=[
            ["Orders with a comparable product", f"{seg_orders:,}"],
            ["Biggest buyer group", f"{top_age} ({top_age_share * 100:.0f}% of units)" if top_age else "-"],
        ],
        tables=[t for t in [
            {
                "title": "Bought in the same order",
                "columns": ["Category", "Orders", "Share of orders"],
                "rows": [[r["category"], r["orders"], f"{r['orders'] / seg_orders * 100:.1f}%" if seg_orders else "-"]
                         for r in basket],
            } if basket else None,
            {
                "title": "Who buys comparable products",
                "columns": ["Age band", "Units", "Share"],
                "rows": [[r["age_band"], r["units"], f"{r['units'] / total_buyers * 100:.0f}%"] for r in buyers],
            } if buyers else None,
        ] if t],
        note="BigQuery: orders and customers of the thelook_ecommerce sample store, last 360 days.",
    )
    return result, ev
