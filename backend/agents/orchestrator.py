"""Runs the agents in order:

  Product  ->  Demand + Fit + Market (in parallel)  ->  Profit  ->  Verdict

One failed agent never crashes the request: it is marked "failed" and the others carry on.
"""
import asyncio
import time

from config import DEFAULT_ASSUMPTIONS
from agents.catalog import get_categories
from agents.common import inr
from agents.demand import run_demand
from agents.fit import run_fit
from agents.market import run_market
from agents.product import run_product
from agents.profit import run_profit
from agents.verdict import build_checks, decide, fallback_text, run_verdict


async def evaluate(req) -> dict:
    started = time.perf_counter()
    a = {**DEFAULT_ASSUMPTIONS, **{k: v for k, v in (req.assumptions or {}).items()
                                   if k in DEFAULT_ASSUMPTIONS and v is not None}}
    agents: dict[str, dict] = {}

    async def timed(name, coro):
        t0 = time.perf_counter()
        try:
            out = await coro
            result, ev = out if isinstance(out, tuple) else (out, {})
            agents[name] = {"status": "done", "ms": round((time.perf_counter() - t0) * 1000),
                            "result": result, "evidence": ev}
            return result
        except Exception as exc:  # keep going with the other agents
            agents[name] = {"status": "failed", "ms": round((time.perf_counter() - t0) * 1000),
                            "error": f"{type(exc).__name__}: {exc}"[:300]}
            return None

    # 1. Product agent
    categories = await get_categories()
    product = await timed("product", run_product(req, categories))
    if product is None:
        if req.department and req.category:
            product = {"department": req.department, "category": req.category,
                       "product_type": req.name, "key_attributes": [], "short_description": req.description or req.name,
                       "search_query": req.name}
        else:
            raise ValueError("The Product agent failed. Choose a department and category and try again.")

    price_assumed = not req.price
    price = float(req.price) if req.price else float(round(req.cost * 2.2 / 10) * 10)

    # 2. Specialists in parallel
    demand, fit, market = await asyncio.gather(
        timed("demand", run_demand(product, price, a)),
        timed("fit", run_fit(product, price, a)),
        timed("market", run_market(product, price)),
    )

    # 3. Profit (needs demand)
    async def _profit():
        return run_profit(float(req.cost), price, demand, a)
    profit = await timed("profit", _profit())

    # 4. Verdict
    checks = build_checks(demand, profit, market, a)
    verdict = decide(checks, demand)
    facts = {
        "product": {"name": req.name, **(product or {})},
        "price_inr": price, "price_was_assumed": price_assumed, "cost_inr": float(req.cost),
        "demand": {k: v for k, v in (demand or {}).items() if k != "monthly_segment_units"},
        "fit": fit, "market": market, "profit": profit,
        "assumptions": a,
    }
    text = await timed("verdict", run_verdict(verdict, checks, facts))
    if not text:
        text = fallback_text(verdict, checks, profit, demand)
        agents["verdict"]["note"] = "Gemini was unavailable, so the explanation was written from the rule checks."

    agents["verdict"]["evidence"] = {
        "summary": [[c["label"], f"{c['value']} - {'pass' if c['passed'] else 'FAIL'}{'' if c['hard'] else ' (soft rule)'}"]
                    for c in checks] + [["Verdict from the rules", verdict]],
        "note": "The rules decide the verdict in code; Gemini writes the explanation and may not change it.",
    }
    reasons = [{**r, "evidence": agents.get(r["agent"], {}).get("evidence", {})} for r in text.get("reasons", [])]

    return {
        "verdict": verdict,
        "headline": text.get("headline", ""),
        "reasons": reasons,
        "conditions": text.get("conditions", []),
        "advice": text.get("advice", ""),
        "checks": checks,
        "key_numbers": {
            "price": price,
            "price_assumed": price_assumed,
            "price_label": inr(price),
            "expected_monthly_units": (demand or {}).get("expected_monthly_units"),
            "margin": (profit or {}).get("margin"),
            "breakeven_weeks": (profit or {}).get("breakeven_weeks"),
            "opening_stock": (profit or {}).get("opening_stock"),
            "cash_tied": (profit or {}).get("cash_tied"),
        },
        "trend": (demand or {}).get("monthly_segment_units", []),
        "competitor_products": (market or {}).get("competitor_products", []),
        "market_range": {k: (market or {}).get(k) for k in ("low_inr", "high_inr", "typical_inr")},
        "agents": agents,
        "assumptions": a,
        "timing_ms": round((time.perf_counter() - started) * 1000),
    }
