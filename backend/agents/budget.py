"""Experiment budget: how much the shop can afford to put into trying new products, worked out in code
from its own numbers (never by Gemini):

  1. Monthly profit run-rate, last 90 days: revenue after returns - cost of goods - platform fees
     - shipping on every order - return shipping (both ways).
  2. Base budget = experiment_pct % of that profit.
  3. Growth: last 90 days vs the same 90 days last year. Growing 10%+ -> x1.2; shrinking -> x0.7.
  4. Slow stock: cash in dead stock + overstock as a share of all stock. Over 30% -> x0.7; over 15% -> x0.85.
  5. Monthly budget (rounded to ₹1,000), and a per-launch cap = monthly budget / launches_per_month.

The raw numbers are cached for 10 minutes; the sum is redone with the rules of each request.
"""
import asyncio
import time

from config import MOCK
from agents import bq, mock
from agents.common import evidence, inr, pct

_cache: tuple[float, dict, list] | None = None


async def _inputs():
    global _cache
    if _cache and time.monotonic() - _cache[0] < 600:
        return _cache[1], _cache[2]
    if MOCK:
        sales, stock = mock.budget_inputs(), mock.inventory_status()
    else:
        sales, stock = await asyncio.gather(bq.run("budget_inputs"), bq.run("inventory_status"))
    _cache = (time.monotonic(), sales[0], stock)
    return sales[0], stock


def growth_factor(growth):
    if growth is None:
        return 1.0, "no year-ago sales to compare"
    if growth >= 0.10:
        return 1.2, f"growing {growth * 100:+.0f}% year on year: room to test more"
    if growth >= 0:
        return 1.0, f"steady ({growth * 100:+.0f}% year on year)"
    return 0.7, f"shrinking ({growth * 100:+.0f}% year on year): test less"


def stock_factor(slow_share):
    if slow_share > 0.30:
        return 0.7, f"{slow_share * 100:.0f}% of stock value is dead or overstocked: free that cash first"
    if slow_share > 0.15:
        return 0.85, f"{slow_share * 100:.0f}% of stock value is dead or overstocked"
    return 1.0, f"only {slow_share * 100:.0f}% of stock value is slow: healthy"


def compute_budget(s: dict, stock: list[dict], a: dict) -> dict:
    months = 3.0
    revenue = (s.get("revenue_90") or 0) / months
    cogs = (s.get("cogs_90") or 0) / months
    fees = revenue * a["platform_fee_pct"] / 100
    shipping = (s.get("orders_90") or 0) / months * a["shipping_per_unit"]
    returns = (s.get("returned_units_90") or 0) / months * a["shipping_per_unit"] * 2
    profit = revenue - cogs - fees - shipping - returns

    base = max(0.0, profit) * a["experiment_pct"] / 100
    ly = s.get("revenue_ly_90") or 0
    growth = (s["revenue_90"] - ly) / ly if ly else None
    g_factor, g_reason = growth_factor(growth)

    stock_value = sum(r["stock_value"] for r in stock)
    slow_value = sum(r["stock_value"] for r in stock if r["status"] in ("dead", "overstock"))
    slow_share = slow_value / stock_value if stock_value else 0.0
    s_factor, s_reason = stock_factor(slow_share)

    monthly = round(base * g_factor * s_factor / 1000) * 1000
    launches = max(1, int(a["launches_per_month"]))
    per_launch = round(monthly / launches / 1000) * 1000

    steps = [
        ["Revenue per month (last 90 days, after returns)", inr(revenue)],
        ["- Cost of goods", f"- {inr(cogs)}"],
        [f"- Platform and payment fees ({a['platform_fee_pct']:g}%)", f"- {inr(fees)}"],
        [f"- Shipping ({inr(a['shipping_per_unit'])} per order)", f"- {inr(shipping)}"],
        ["- Return shipping (both ways)", f"- {inr(returns)}"],
        ["= Profit per month", inr(profit)],
        [f"Base budget: {a['experiment_pct']:g}% of profit", inr(base)],
        [f"Growth x{g_factor:g}", g_reason],
        [f"Slow stock x{s_factor:g}", s_reason],
        ["= Experiment budget per month", inr(monthly)],
        [f"Per launch ({launches} a month)", inr(per_launch)],
    ]
    return {
        "profit_per_month": round(profit),
        "revenue_per_month": round(revenue),
        "growth": None if growth is None else round(growth, 4),
        "slow_stock_share": round(slow_share, 4),
        "slow_stock_value": round(slow_value),
        "stock_value": round(stock_value),
        "base": round(base),
        "growth_factor": g_factor,
        "stock_factor": s_factor,
        "monthly_budget": monthly,
        "per_launch": per_launch,
        "launches_per_month": launches,
        "experiment_pct": a["experiment_pct"],
        "steps": steps,
        "data_until": s.get("data_until"),
        "evidence": evidence(
            summary=steps,
            note="Worked out in code from the shop's last 90 days of sales and today's stock. "
                 "Change the share and launches per month on the Business page.",
        ),
    }


async def get_budget(a: dict) -> dict:
    s, stock = await _inputs()
    return compute_budget(s, stock, a)
