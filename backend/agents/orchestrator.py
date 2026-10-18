"""Runs the agents in order:

  Product  ->  Demand + Fit + Market (in parallel)  ->  Profit  ->  Verdict

One failed agent never crashes the request: it is marked "failed" and the others carry on.

Pass `emit` (an async callback) to hear about each agent as it starts and finishes, for the live
agent board on Discovery: {"type": "start" | "done" | "failed" | "skipped", "agent", "ms", "summary", "evidence"}.
"""
import asyncio
import time

from config import DEFAULT_ASSUMPTIONS, MOCK
from agents.budget import get_budget
from agents.catalog import (_split, allowed_by_department, category_suppliers, get_catalog, get_categories,
                            get_stock, match_catalog, same_style_variants)
from agents.common import inr
from agents.demand import run_demand
from agents.fit import run_fit
from agents.market import run_market
from agents.product import run_product
from agents.profit import run_profit
from agents.settings import load_brief
from agents.verdict import build_checks, decide, fallback_text, run_verdict


# In mock mode everything is instant; on the live board a short pause per agent shows the flow.
MOCK_PAUSE = {"product": 0.9, "market": 2.6, "demand": 1.4, "fit": 1.1, "profit": 0.5, "verdict": 1.0}
WORD = {"go": "Go", "no_go": "No-go", "go_with_conditions": "Go, with conditions"}


def _plain_age(band: str) -> str:
    return band.replace("-", "–") + (" year-olds" if band[:1].isdigit() else "")


def agent_summary(name: str, r: dict | None) -> str:
    """One plain sentence per finished agent for the live board. Built in code from the agent's own numbers."""
    if not r:
        return ""
    if name == "product":
        if r.get("fits_shop") is False:
            return f"This is {r.get('what_it_is') or 'not clothing'}, which your shop doesn't sell."
        kind = r.get("product_type") or ""
        line = f"It's {r.get('department')}'s {r.get('category')}" + (f": {kind.lower()}." if kind else ".")
        return line + (f" You already sell {r['catalog_match']}." if r.get("catalog_match") else "")
    if name == "market":
        lo, hi = r.get("low_inr"), r.get("high_inr")
        found = len(r.get("competitor_products") or [])
        if not (lo and hi):
            return "Couldn't find clear prices online for this."
        return f"Similar products sell online for {inr(lo)} to {inr(hi)}." + (f" Found {found} to compare." if found else "")
    if name == "demand":
        v, units, trend = r.get("velocity") or 0, r.get("expected_monthly_units") or 0, r.get("trend")
        pace = ("faster than" if v >= 1.1 else "slower than" if v < 0.9 else "about as fast as")
        ex, own = r.get("existing"), (r.get("own_closest") or [None])[0]
        if ex and ex.get("kind") == "style":
            others = ", ".join(_split(v["name"])[1] or v["name"] for v in ex["variants"])
            line = {
                "dead": f"You already stock the {ex['name']} in {others}: {ex['on_hand']} unsold, no sale in 90 days (dead stock). ",
                "mixed": f"You already stock the {ex['name']} in {others}; some colours aren't selling ({', '.join(ex['dead_names'])}). ",
                "selling": f"You already sell the {ex['name']} in {others}, about {ex['per_month']:.0f} a month. ",
            }[ex["status"]]
        elif ex:
            st, n_ = ex["status"], ex.get("on_hand")
            line = {
                "dead": f"You already stock {ex['name']}: {n_} unsold, no sale in 90 days (dead stock). ",
                "overstock": f"You already stock {ex['name']}: {n_} in stock, about {ex.get('cover_days') or 0} days' worth. ",
                "reorder": f"You already sell {ex['name']} and only {n_} are left: reorder it rather than launch it again. ",
                "healthy": f"You already sell {ex['name']}: {n_} in stock, about {ex['per_month']:.0f} sold a month. ",
                "discontinued": f"You used to sell {ex['name']} and stopped. ",
            }.get(st, f"You already sell {ex['name']}. ")
        elif own and own["score"] >= 0.6:
            line = f"Your {own['name']} sold {own['units_12m']:,} in the last 12 months (about {own['per_month']:.0f} a month). "
        else:
            line = ""
        if (r.get("basis") or "").startswith("all your"):
            line += f"None of your products are at this price; your {r['basis'][9:].split(' (')[0]} sell about {units:.0f} a month each, {pace} your average product."
        else:
            line += f"Similar products in your shop sell about {units:.0f} a month, {pace} your average product."
        if trend is not None and trend > 0.05:
            line += " Lately they're doing better than the rest of your shop."
        elif trend is not None and trend < -0.05:
            line += " Lately they're slowing down compared with the rest of your shop."
        return line
    if name == "fit":
        parts = []
        if r.get("bought_with"):
            parts.append(f"often bought with {r['bought_with'][0]}")
        if r.get("top_age_band"):
            parts.append(f"mostly by {_plain_age(r['top_age_band'])}")
        if r.get("top_channel"):
            ch = r["top_channel"]
            parts.append("mostly on your website" if ch == "Website" else f"mostly on {ch}")
        line = ", ".join(parts)
        return (line[:1].upper() + line[1:] + ".") if line else ""
    if name == "profit":
        cap = r.get("budget_per_launch")
        n = r.get("opening_stock") or 0
        order = f"Order {n} unit{'' if n == 1 else 's'} to start ({inr(n * r['cost'])})" if n else "Don't order any stock yet: no sales expected"
        line = f"You'd keep {inr(r['unit_profit'])} on each sale ({r['margin'] * 100:.0f}%). {order}. Launching needs {inr(r['cash_needed'])}"
        if cap is None:
            return line + "."
        return line + (f", which fits your {inr(cap)} test budget." if r["cash_needed"] <= cap
                       else f", more than your {inr(cap)} test budget.")
    return ""



def _style(name: str) -> str:
    return _split(name)[0]


async def evaluate(req, emit=None) -> dict:
    started = time.perf_counter()

    async def tell(event: dict):
        if emit:
            try:
                await emit(event)
            except Exception:
                pass   # a closed browser tab must never stop the evaluation
    a = {**DEFAULT_ASSUMPTIONS, **{k: v for k, v in (req.assumptions or {}).items()
                                   if k in DEFAULT_ASSUMPTIONS and v is not None}}
    agents: dict[str, dict] = {}

    async def timed(name, coro, announce=True):
        t0 = time.perf_counter()
        await tell({"type": "start", "agent": name})
        try:
            if MOCK and emit:
                await asyncio.sleep(MOCK_PAUSE.get(name, 0.5))
            out = await coro
            result, ev = out if isinstance(out, tuple) else (out, {})
            agents[name] = {"status": "done", "ms": round((time.perf_counter() - t0) * 1000),
                            "result": result, "evidence": ev}
            if announce:
                await tell({"type": "done", "agent": name, "ms": agents[name]["ms"],
                            "summary": agent_summary(name, result), "evidence": ev})
            return result
        except Exception as exc:  # keep going with the other agents
            agents[name] = {"status": "failed", "ms": round((time.perf_counter() - t0) * 1000),
                            "error": f"{type(exc).__name__}: {exc}"[:300]}
            await tell({"type": "failed", "agent": name, "ms": agents[name]["ms"], "error": agents[name]["error"]})
            return None

    # 1. Product agent
    categories = await get_categories()
    brief = await load_brief(allowed_by_department(categories))   # what the shop is, for the agents
    try:
        catalog = await get_catalog()
    except Exception:
        catalog = []

    async def product_step():
        data, ev = await run_product(req, categories, brief)
        # The shop's own catalogue is the best evidence of fit: if it already sells something this close,
        # the product fits, in that product's department and category (decided in code).
        best = next(iter(match_catalog(req.name, [r for r in catalog if r.get("status") == "active"], limit=1)), None)
        if best and best["score"] >= 0.6:
            if data.get("fits_shop") is False or (data.get("department"), data.get("category")) != (best["department"], best["category"]):
                data.update(fits_shop=True, department=best["department"], category=best["category"],
                            catalog_match=best["name"])
                ev.setdefault("summary", []).append(
                    ["Already in your catalogue", f"{best['name']} ({best['department']} · {best['category']})"])
        return data, ev

    product = await timed("product", product_step())
    if product is None:   # Gemini errors are often one-offs: try once more
        product = await timed("product", product_step())
    if product is None:
        if req.department and req.category:
            # We couldn't check what the product is, so never assume it fits the shop (fits_shop=None
            # fails the hard rule); the other agents still run so the seller sees the numbers.
            product = {"department": req.department, "category": req.category, "fits_shop": None,
                       "what_it_is": "", "product_type": req.name, "key_attributes": [],
                       "short_description": req.description or req.name, "search_query": req.name}
        else:
            raise ValueError("The Product agent failed. Choose a department and category and try again.")

    # Does the shop already sell this product, or the same style in another colour? Then its own stock matters:
    # buying more of a style that isn't selling (dead stock) is a No-go, whatever colour it comes in.
    existing = None
    try:
        stock = await get_stock()
    except Exception:
        stock = {}

    def stock_of(r):
        row = stock.get(r["sku"]) or {}
        return {"name": r["name"], "sku": r["sku"], "price_inr": r.get("price_inr"),
                "units_12m": r.get("units_12m") or 0, "per_month": r["per_month"],
                "status": row.get("status") or ("discontinued" if r.get("status") != "active" else "unknown"),
                "on_hand": row.get("on_hand"), "on_order": row.get("on_order"),
                "cover_days": None if row.get("cover_days") is None else round(row["cover_days"]),
                "last_sale": str(row.get("last_sale") or r.get("last_sale") or "") or None}

    exact = next(iter(match_catalog(req.name, catalog, limit=1)), None)
    if exact and exact["score"] >= 0.85 and exact["same_style"] and exact["same_colour"]:
        existing = {**stock_of(exact), "kind": "same"}
    else:
        variants = [stock_of(r) for r in same_style_variants(req.name, catalog)]
        known = [v for v in variants if v["status"] not in ("unknown", "discontinued")]
        if known:
            dead = [v for v in known if v["status"] == "dead"]
            existing = {"kind": "style", "name": _style(known[0]["name"]), "variants": known,
                        "status": "dead" if len(dead) == len(known) else "mixed" if dead else "selling",
                        "on_hand": sum(v.get("on_hand") or 0 for v in dead) if dead else None,
                        "per_month": round(sum(v["per_month"] for v in known), 1),
                        "dead_names": [v["name"] for v in dead]}

    price_assumed = not req.price
    price = float(req.price) if req.price else float(round(req.cost * 2.2 / 10) * 10)

    if product.get("fits_shop") is not False:
        # 2. Specialists in parallel
        async def _budget():   # the shop's experiment budget, from its own numbers (not an agent card)
            try:
                return await get_budget(a)
            except Exception:
                return None
        demand, fit, market, budget = await asyncio.gather(
            timed("demand", run_demand(product, price, a, catalog, req.name, existing)),
            timed("fit", run_fit(product, price, a)),
            timed("market", run_market(product, price)),
            _budget(),
        )

        # 3. Profit (needs demand and the budget)
        try:
            suppliers = await category_suppliers(product["category"])
        except Exception:
            suppliers = []

        async def _profit():
            return run_profit(float(req.cost), price, demand, a, budget, suppliers)
        profit = await timed("profit", _profit())
    else:
        # Not something the shop sells: comparing it with an unrelated category would be meaningless.
        demand = fit = market = profit = budget = None
        why = f"Skipped: the Product agent found this is {product.get('what_it_is') or 'not apparel'}, not something the shop sells."
        for name in ("market", "demand", "fit", "profit"):
            agents[name] = {"status": "skipped", "ms": 0, "note": why, "evidence": {}}
            await tell({"type": "skipped", "agent": name, "summary": why})

    # 4. Verdict
    checks = build_checks(demand, profit, market, a, product)
    verdict = decide(checks, demand)
    facts = {
        "product": {"name": req.name, **(product or {}),
                    **({"department": None, "category": None} if product.get("fits_shop") is False else {})},
        "shop_categories": {d: cats for d, cats in allowed_by_department(categories).items()},
        "shop_definition": brief,
        "price_inr": price, "price_was_assumed": price_assumed, "cost_inr": float(req.cost),
        "demand": {k: v for k, v in (demand or {}).items() if k != "monthly_segment_units"},
        "fit": fit, "market": market, "profit": profit,
        "experiment_budget": {k: v for k, v in (budget or {}).items() if k not in ("steps", "evidence")},
        "assumptions": a,
    }
    text = await timed("verdict", run_verdict(verdict, checks, facts), announce=False)
    if not text:
        text = fallback_text(verdict, checks, profit, demand)
        agents["verdict"]["note"] = "Gemini was unavailable, so the explanation was written from the rule checks."

    agents["verdict"]["evidence"] = {
        "summary": [[c["label"], f"{c['value']} - {'pass' if c['passed'] else 'FAIL'}{'' if c['hard'] else ' (soft rule)'}"]
                    for c in checks] + [["Verdict from the rules", verdict]],
        "note": "The rules decide the verdict in code; Gemini writes the explanation and may not change it.",
    }
    agents["verdict"]["summary"] = f"{WORD[verdict]}: {text.get('headline', '')}"
    await tell({"type": "done", "agent": "verdict", "ms": agents["verdict"]["ms"], "verdict": verdict,
                "summary": agents["verdict"]["summary"], "evidence": agents["verdict"]["evidence"]})
    for name, a_ in agents.items():
        if a_.get("status") == "done" and name != "verdict":
            a_["summary"] = agent_summary(name, a_.get("result"))
        elif a_.get("status") == "skipped":
            a_["summary"] = a_.get("note", "")
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
            "cash_needed": (profit or {}).get("cash_needed"),
            "cost": float(req.cost),
            "launch_cost": a["launch_cost"],
            "cover_weeks_total": (profit or {}).get("cover_weeks_total"),
            "supplier_moq": (profit or {}).get("supplier_moq"),
            "supplier_name": (profit or {}).get("supplier_name"),
            "moq_cash_needed": (profit or {}).get("moq_cash_needed"),
            "budget_per_launch": (profit or {}).get("budget_per_launch"),
        },
        "trend": (demand or {}).get("monthly_segment_units", []),
        "competitor_products": (market or {}).get("competitor_products", []),
        "market_range": {k: (market or {}).get(k) for k in ("low_inr", "high_inr", "typical_inr")},
        "agents": agents,
        "assumptions": a,
        "timing_ms": round((time.perf_counter() - started) * 1000),
    }
