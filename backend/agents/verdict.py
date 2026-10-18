"""Verdict agent.

1. The seller's rules are checked in code, so the go / no-go decision is consistent run to run.
2. Gemini then explains the decision: a headline, three reasons that each cite a real number,
   and the conditions or advice. It is told the verdict and may not change it.
"""
import json

from pydantic import BaseModel

from config import MOCK
from agents import llm, mock
from agents.common import inr, pct

AGENTS = ["product", "market", "demand", "fit", "profit"]


class Reason(BaseModel):
    text: str
    agent: str


class VerdictOut(BaseModel):
    headline: str
    reasons: list[Reason]
    conditions: list[str]
    advice: str


def build_checks(demand, profit, market, a, product=None) -> list[dict]:
    """Each check: what was tested, the result, whether it passed, and whether failing it is a deal-breaker."""
    checks = []
    if product is not None:
        fits = product.get("fits_shop")      # None = the Product agent failed, so it couldn't be checked
        checks.append({
            "id": "fits_shop", "agent": "product", "hard": True,
            "label": "It's something your shop sells",
            "value": f"{product['category']} ({product['department']})" if fits
                     else "couldn't check: the Product agent failed, try again" if fits is None
                     else f"no: {product.get('what_it_is') or 'not apparel'}",
            "passed": fits is True,
        })
    if profit:
        checks.append({
            "id": "margin", "agent": "profit", "hard": True,
            "label": f"You keep at least {a['min_margin_pct']}% of each sale",
            "value": pct(profit["margin"], 1),
            "passed": profit["margin"] * 100 >= a["min_margin_pct"],
        })
        bw = profit["breakeven_weeks"]
        checks.append({
            "id": "breakeven", "agent": "profit", "hard": True,
            "label": f"Launch costs earned back within {a['max_breakeven_weeks']} weeks",
            "value": f"{bw:.1f} weeks" if bw is not None else "never",
            "passed": bw is not None and bw <= a["max_breakeven_weeks"],
        })
    if profit and profit.get("budget_per_launch") is not None:
        checks.append({
            "id": "budget", "agent": "profit", "hard": True,
            "label": f"The launch fits your test budget ({inr(profit['budget_per_launch'])})",
            "value": f"needs {inr(profit['cash_needed'])}",
            "passed": profit["cash_needed"] <= profit["budget_per_launch"],
        })
    ex = (demand or {}).get("existing")
    if ex and ex.get("status") in ("dead", "overstock", "reorder", "healthy", "discontinued"):
        st = ex["status"]
        checks.append({
            "id": "existing_stock", "agent": "demand", "hard": st == "dead",
            "label": "You don't already hold slow-moving stock of it",
            "value": {"dead": f"{ex.get('on_hand')} unsold, no sale in 90 days",
                      "overstock": f"{ex.get('on_hand')} in stock, about {ex.get('cover_days') or 0} days' worth",
                      "reorder": f"only {ex.get('on_hand')} left: reorder it",
                      "healthy": f"{ex.get('on_hand')} in stock, selling",
                      "discontinued": "you stopped selling it before"}[st],
            "passed": st in ("reorder", "healthy"),
        })
    if demand:
        checks.append({
            "id": "velocity", "agent": "demand", "hard": True,
            "label": f"Similar products sell at least {a['min_velocity']}× as fast as your average product",
            "value": f"{demand['velocity']:.2f}x",
            "passed": demand["velocity"] >= a["min_velocity"],
        })
        if demand["velocity"] >= a["min_velocity"]:   # the moderate band only; below it the hard rule already fails
          checks.append({
            "id": "velocity_avg", "agent": "demand", "hard": False,
            "label": "Similar products sell at least as fast as your average product",
            "value": f"{demand['velocity']:.2f}×",
            "passed": demand["velocity"] >= 1.0,
          })
        if demand["trend"] is not None:
            checks.append({
                "id": "trend", "agent": "demand", "hard": False,
                "label": "Similar products are keeping up with the rest of your shop",
                "value": f"{demand['trend'] * 100:+.0f}%",
                "passed": demand["trend"] >= -0.15,
            })
    if market and market.get("price_position"):
        checks.append({
            "id": "price", "agent": "market", "hard": False,
            "label": "Your price is within the online price range",
            "value": f"{market['price_position']} {inr(market['low_inr'])}-{inr(market['high_inr'])}",
            "passed": market["price_position"] != "above",
        })
    return checks


def decide(checks: list[dict], demand: dict | None) -> str:
    if any(c["hard"] and not c["passed"] for c in checks):
        return "no_go"
    if any(not c["passed"] for c in checks) or not demand or demand["confidence"] == "low":
        return "go_with_conditions"
    return "go"


def fallback_text(verdict, checks, profit, demand) -> dict:
    """Used if Gemini is unavailable, so the page still shows a complete answer."""
    failed = [c for c in checks if not c["passed"]]
    passed = [c for c in checks if c["passed"]]
    picks = (failed + passed)[:3]
    reasons = [{"text": f"{c['label']}: {c['value']} ({'pass' if c['passed'] else 'fail'})", "agent": c["agent"]}
               for c in picks]
    head = {"go": "Go", "no_go": "No-go", "go_with_conditions": "Go, with conditions"}[verdict]
    if profit:
        head += f": price {inr(profit['price'])}, about {demand['expected_monthly_units']:.0f} units a month" if demand else ""
    return {
        "headline": head,
        "reasons": reasons,
        "conditions": [f"Fix: {c['label'].lower()}" for c in failed if not c["hard"]],
        "advice": "",
    }


async def run_verdict(verdict, checks, facts):
    if MOCK:
        return mock.verdict_text(verdict, checks, facts)

    prompt = f"""You are the Verdict agent in GoNoGo. A retailer asked whether to launch a new product.
Specialist agents have already done the analysis. The seller's rules decided the verdict:

VERDICT: {verdict}   (go | no_go | go_with_conditions; this is final, do not change it)

Rule checks:
{json.dumps(checks, indent=2, ensure_ascii=False)}

Facts from the agents:
{json.dumps(facts, indent=2, ensure_ascii=False, default=str)}

Write for a busy shop owner. Plain words, short sentences. Write rupees with the ₹ sign and Indian digit
grouping (₹1,299 and ₹3,51,000). Round weeks to one decimal. The demand "trend" compares the last 3 months with the same 3 months
last year and is relative to the whole shop (e.g. +8% means comparables grew 8% faster than the shop);
describe it that way, never as raw market growth. All sales figures are the shop's own sales.
- headline: at most 90 characters. For go / go_with_conditions include the price, units to order and the
  break-even week. For no_go, name the main reason.
- reasons: exactly 3. Each must quote at least one specific number from the facts or checks.
  Each has "agent": the one agent the number came from, one of {AGENTS}.
  Put the most decisive reason first. Every reason must support the verdict: for no_go, use the failed checks
  and other risks (never a strength); for go, use the strengths. A strength in a no_go belongs in the advice.
- conditions: for go_with_conditions, 1 to 3 concrete conditions saying what would need to be different
  (e.g. start with a smaller first order, a lower price, a different style than the slower sellers). If
  "velocity_avg" failed, similar products sell slower than the shop's average: say so and what to change.
  For go or no_go, an empty list.
- advice: one sentence. For no_go, say what would have to change to make it a go (price, cost, or a
  different product). For go, the one thing to watch after launch.
If the "existing_stock" check failed, the shop already holds unsold stock of this exact product: lead with that,
and advise selling it first (a discount, a bundle or another channel) before buying more. If it shows the product
is running low, say a reorder is the better move.
If the "fits_shop" check failed, the product is not something this shop sells, so there are no comparable
sales and the other agents did not run. Say what the product is and that the shop sells only the
"shop_categories" in the facts (name a few), using "shop_definition" to say what the shop is. Give one clear reason per point, without repeating yourself;
the advice should suggest a product from the shop's range.
Never invent numbers that are not in the facts."""
    data, _ = await llm.generate_json([prompt], schema=VerdictOut, temperature=0.2)
    for r in data.get("reasons", []):
        if r.get("agent") not in AGENTS:
            r["agent"] = "profit"
    data["reasons"] = data.get("reasons", [])[:3]
    return data
