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


def build_checks(demand, profit, market, a) -> list[dict]:
    """Each check: what was tested, the result, whether it passed, and whether failing it is a deal-breaker."""
    checks = []
    if profit:
        checks.append({
            "id": "margin", "agent": "profit", "hard": True,
            "label": f"Margin at least {a['min_margin_pct']}%",
            "value": pct(profit["margin"], 1),
            "passed": profit["margin"] * 100 >= a["min_margin_pct"],
        })
        bw = profit["breakeven_weeks"]
        checks.append({
            "id": "breakeven", "agent": "profit", "hard": True,
            "label": f"Launch cost back within {a['max_breakeven_weeks']} weeks",
            "value": f"{bw:.1f} weeks" if bw is not None else "never",
            "passed": bw is not None and bw <= a["max_breakeven_weeks"],
        })
    if demand:
        checks.append({
            "id": "velocity", "agent": "demand", "hard": True,
            "label": f"Comparables sell at least {a['min_velocity']}x the store average",
            "value": f"{demand['velocity']:.2f}x",
            "passed": demand["velocity"] >= a["min_velocity"],
        })
        if demand["trend"] is not None:
            checks.append({
                "id": "trend", "agent": "demand", "hard": False,
                "label": "Demand keeping pace with the store (at most 15% behind)",
                "value": f"{demand['trend'] * 100:+.0f}%",
                "passed": demand["trend"] >= -0.15,
            })
    if market and market.get("price_position"):
        checks.append({
            "id": "price", "agent": "market", "hard": False,
            "label": "Price within the online market range",
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
grouping (₹1,299 and ₹3,51,000). Round weeks to one decimal. The demand "trend" is growth relative to the
whole store (e.g. +8% means comparables grew 8% faster than the shop); describe it that way, never as raw market growth.
- headline: at most 90 characters. For go / go_with_conditions include the price, units to order and the
  break-even week. For no_go, name the main reason.
- reasons: exactly 3. Each must quote at least one specific number from the facts or checks.
  Each has "agent": the one agent the number came from, one of {AGENTS}.
  Put the most decisive reason first. Every reason must support the verdict: for no_go, use the failed checks
  and other risks (never a strength); for go, use the strengths. A strength in a no_go belongs in the advice.
- conditions: for go_with_conditions, 1 to 3 concrete conditions (e.g. start with a smaller first order,
  test the price). For go or no_go, an empty list.
- advice: one sentence. For no_go, say what would have to change to make it a go (price, cost, or a
  different product). For go, the one thing to watch after launch.
Never invent numbers that are not in the facts."""
    data, _ = await llm.generate_json([prompt], schema=VerdictOut, temperature=0.2)
    for r in data.get("reasons", []):
        if r.get("agent") not in AGENTS:
            r["agent"] = "profit"
    data["reasons"] = data.get("reasons", [])[:3]
    return data
