"""Profit agent: unit economics, break-even and opening stock. Pure Python arithmetic,
so the numbers are exact and every line of the calculation is shown as evidence."""
import math

from agents.common import evidence, inr, pct


def run_profit(cost: float, price: float, demand: dict | None, a: dict):
    return_rate = (demand or {}).get("return_rate", 0.0)
    monthly = (demand or {}).get("expected_monthly_units", a["avg_units_per_product"])

    fee = price * a["platform_fee_pct"] / 100
    shipping = a["shipping_per_unit"]
    returns = return_rate * 2 * shipping          # a return costs shipping both ways
    unit_profit = price - cost - fee - shipping - returns
    margin = unit_profit / price if price else 0

    weekly = monthly * 12 / 52
    breakeven_units = math.ceil(a["launch_cost"] / unit_profit) if unit_profit > 0 else None
    breakeven_weeks = breakeven_units / weekly if breakeven_units and weekly > 0 else None

    opening_stock = max(1, math.ceil(weekly * (a["lead_time_weeks"] + a["cover_weeks"])))
    reorder_point = max(1, math.ceil(weekly * (a["lead_time_weeks"] + 1)))
    cash_tied = opening_stock * cost

    result = {
        "price": price,
        "cost": cost,
        "unit_profit": round(unit_profit, 2),
        "margin": round(margin, 4),
        "weekly_units": round(weekly, 1),
        "breakeven_units": breakeven_units,
        "breakeven_weeks": None if breakeven_weeks is None else round(breakeven_weeks, 1),
        "opening_stock": opening_stock,
        "reorder_point": reorder_point,
        "cash_tied": round(cash_tied),
    }
    ev = evidence(
        tables=[{
            "title": "Profit per unit",
            "columns": ["Line", "Amount"],
            "rows": [
                ["Selling price", inr(price)],
                ["Cost price", f"- {inr(cost)}"],
                [f"Platform and payment fees ({a['platform_fee_pct']}%)", f"- {inr(fee)}"],
                ["Shipping", f"- {inr(shipping)}"],
                [f"Returns ({return_rate * 100:.1f}% x shipping both ways)", f"- {inr(returns)}"],
                ["Profit per unit", inr(unit_profit)],
                ["Margin", pct(margin, 1)],
            ],
        }],
        summary=[
            ["Launch cost to recover", inr(a["launch_cost"])],
            ["Break-even", f"{breakeven_units} units, about {breakeven_weeks:.1f} weeks at {weekly:.1f} units/week"
             if breakeven_weeks else "never: each unit loses money" if unit_profit <= 0 else "not enough sales to estimate"],
            ["Opening order", f"{opening_stock} units ({a['lead_time_weeks']} weeks lead time + {a['cover_weeks']} weeks cover)"],
            ["Reorder when stock falls to", f"{reorder_point} units"],
            ["Cash tied up in opening stock", inr(cash_tied)],
        ],
        note="Calculated in code from the seller's inputs and the Demand agent's numbers.",
    )
    return result, ev
