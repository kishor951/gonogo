"""Fit agent: basket analysis (what else buyers of comparable products put in the same order)
and who buys them (age bands, channels, cities). All straight from BigQuery."""
import asyncio

from config import MOCK
from agents import bq, mock
from agents.common import evidence
from agents.demand import segment_params

CHANNELS = {"website": "Website", "myntra": "Myntra", "amazon": "Amazon"}


def _share_rows(rows, label=lambda x: x):
    total = sum(r["units"] for r in rows) or 1
    return [[label(r["label"]), r["units"], f"{r['units'] / total * 100:.0f}%"] for r in rows], total


async def run_fit(product: dict, price_inr: float, a: dict):
    params = segment_params(product, price_inr, a)
    if MOCK:
        basket, mix = mock.basket(params), mock.segment_mix(params)
    else:
        basket, mix = await asyncio.gather(bq.run("basket", params), bq.run("segment_mix", params))

    by_dim = {"age_band": [], "channel": [], "city": []}
    for r in mix:
        by_dim.setdefault(r["dimension"], []).append(r)
    for rows in by_dim.values():
        rows.sort(key=lambda r: -r["units"])
    ages, channels, cities = by_dim["age_band"], by_dim["channel"], by_dim["city"][:5]

    seg_orders = basket[0]["seg_orders"] if basket else 0
    age_rows, age_total = _share_rows(ages)
    channel_rows, channel_total = _share_rows(channels, lambda c: CHANNELS.get(c, c))
    city_total = sum(r["units"] for r in by_dim["city"]) or 1

    top = lambda rows, total: (rows[0]["label"], round(rows[0]["units"] / total, 3)) if rows else (None, 0)
    top_age, top_age_share = top(ages, age_total)
    top_channel, top_channel_share = top(channels, channel_total)

    result = {
        "bought_with": [r["category"] for r in basket[:3]],
        "top_age_band": top_age,
        "top_age_share": top_age_share,
        "top_channel": CHANNELS.get(top_channel, top_channel),
        "top_channel_share": top_channel_share,
        "top_cities": [r["label"] for r in cities[:3]],
    }
    ev = evidence(
        summary=[
            ["Orders with a comparable product", f"{seg_orders:,}"],
            ["Biggest buyer group", f"{top_age} ({top_age_share * 100:.0f}% of units)" if top_age else "-"],
            ["Main channel", f"{result['top_channel']} ({top_channel_share * 100:.0f}% of units)" if top_channel else "-"],
            ["Top cities", ", ".join(result["top_cities"]) or "-"],
        ],
        tables=[t for t in [
            {
                "title": "Bought in the same order",
                "columns": ["Category", "Orders", "Share of orders"],
                "rows": [[f"{r['category']} ({r['department']})", r["orders"],
                          f"{r['orders'] / seg_orders * 100:.1f}%" if seg_orders else "-"] for r in basket],
            } if basket else None,
            {"title": "Who buys comparable products", "columns": ["Age band", "Units", "Share"], "rows": age_rows}
            if ages else None,
            {"title": "Where they sell", "columns": ["Channel", "Units", "Share"], "rows": channel_rows}
            if channels else None,
            {"title": "Top cities", "columns": ["City", "Units", "Share"],
             "rows": [[r["label"], r["units"], f"{r['units'] / city_total * 100:.0f}%"] for r in cities]}
            if cities else None,
        ] if t],
        note="BigQuery: the shop's orders and customers, last 12 months.",
    )
    return result, ev
