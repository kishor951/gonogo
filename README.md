# GoNoGo

**Know if a product will sell before you stock it.**

A shop owner is offered a new product and has to decide how many to buy, usually on gut feel. If they buy and it doesn't sell, their cash sits on the shelf. If they pass on a winner, a competitor gets the sales.

GoNoGo is an AI launch-decision agent for retailers. The seller adds a photo (or a name) and the purchase price. A team of six agents checks the idea against the shop's own sales, stock and customers in BigQuery and against live online prices found with Google Search. The seller gets **Go**, **No-go** or **Go, with conditions** in about a minute, with three plain reasons. Each reason links to the numbers and pages behind it.

Built for the Google Cloud AI Builder Cup 2026 (Retail & Commerce).

**Live app:** https://gonogo-389639819210.asia-south1.run.app (open; 10 checks per person per hour)

## The core idea: AI explains, code decides

- **Every number comes from SQL or Python**, never from the model. Gemini reads, searches and explains; prompts pass numbers in and say "never invent numbers".
- **The verdict comes from the seller's own rules, checked in code** ([`agents/verdict.py`](backend/agents/verdict.py)). Gemini writes the headline and reasons but cannot change the verdict.
- **Links are never invented.** Competitor products are real product pages that Google Search returned; each row's name, price and picture are read from that page.

## What it does

**Discovery** (`/`) is a chat:

1. **Add the product.** Type it, or upload or paste a photo. Gemini finds every product in the photo and numbers them; the seller picks one and only that crop is checked.
2. **Enter the purchase price.** A selling price is suggested from the shop's own prices in that category (SQL).
3. **Watch the team work.** Results stream in as each agent finishes:

| Agent | Question | How |
|---|---|---|
| Iris · Product | What is it, and does this shop sell that kind of thing? | Gemini (vision + JSON), checked against the shop's own catalogue in code |
| Scout · Market | What do similar products sell for online? | Gemini with Grounding with Google Search, one search per marketplace; prices and pictures read from the product pages |
| Ledger · Demand | How fast do similar products sell here? | BigQuery: comparable products (same category, price within ±30%), sales speed vs the shop average, trend vs last year, returns |
| Echo · Fit | Who buys it, and through which channels? | BigQuery: baskets, age bands, channels, cities |
| Penny · Profit | Does it make money, and can the shop afford it? | Python: margin after fees, shipping and returns; break-even; opening order; cash needed; test budget |
| Vera · Verdict | Go or no-go? | Rule checks in code; Gemini writes the explanation |

4. **Read the answer**: the verdict, how many to order to start, the cash needed and three reasons. **References** holds the proof: similar products online, every rule check, and the shop's own sales.

### The rules

Hard rules (any failure is a No-go):

| Rule | Default |
|---|---|
| The shop sells this kind of product | from the shop profile and catalogue |
| Margin after all costs | at least 20% |
| Launch cost earned back | within 12 weeks |
| Similar products sell at least this fast | 0.7× the shop's average product |
| Opening order + launch cost fit the test budget | per-launch budget (below) |
| Not already sitting in stock unsold | the same product, or the same style in other colours, with no sale in 90 days |

Soft rules turn a Go into **Go, with conditions**: similar products sell slower than average (0.7–1×), sales are falling against the rest of the shop, or the price is outside the online range.

**Test budget.** Monthly profit run-rate (last 90 days) × the share the owner sets for experiments (default 10%), adjusted for growth and slow stock, then split across planned launches per month ([`agents/budget.py`](backend/agents/budget.py)). The Business page shows how it's worked out.

### The other pages

- **Business** (`/business`): the last 12 months against the 12 before, monthly revenue, categories, channels, the test budget and the rules. Rules are saved in BigQuery, so every verdict uses the same ones.
- **Shop profile** (`/shop`): what the shop is, who it sells to and what it never sells. The Product and Verdict agents judge against this.
- **Products, Inventory, Sales, Returns, Customers, Suppliers**: the shop's data with search, filters and pages. Inventory flags products to reorder, overstock and dead stock.
- **Recent checks** in the sidebar: the latest three, with search, Go / Conditions / No-go filters and delete. Saved in the browser.
- **SOP**: a short slide guide on the empty Discovery page, telling the story through Priya, a shop owner, then how to use the tool.

## The demo shop: Urban Loom

Urban Loom is a **synthetic** mid-size Indian online fashion shop (women's and men's apparel; website, Myntra and Amazon; prices in rupees). [`scripts/generate_shop_data.py`](scripts/generate_shop_data.py) creates 24 months of data with realistic patterns: a long tail of slow sellers, winter outerwear, January activewear peaks, growing and declining categories, 8–26% returns, discounts, and stock problems.

| Table | Rows | What it holds |
|---|---|---|
| `suppliers` | 12 | lead times, minimum order quantities |
| `products` | 180 | SKU, department, category, brand, cost and list price, launch date, status |
| `customers` | 6,000 | age band, city, first order date (no names or contact details) |
| `sales` | ~53,000 | order lines: date, SKU, quantity, price paid, channel, customer, returned |
| `inventory` | 180 | on hand, on order, reorder point, last received |
| `settings` | 1 | shop name, rules and shop profile (written by the app) |

## Google Cloud

- **Gemini 2.5 Flash on Vertex AI** (`google-genai`, `us-central1`): photo reading, product understanding, explanations
- **Grounding with Google Search**: live prices and competitor product pages
- **BigQuery** (`gonogo_shop`, `asia-south1`): all shop data and settings; every query is a parameterised `.sql` file in [`backend/sql/`](backend/sql/)
- **Cloud Run** (`asia-south1`): one FastAPI service for the pages and the API, scaling to zero, at most 2 instances
- **Cloud Build** and **Artifact Registry**: used by `gcloud run deploy --source`
- **IAM**: the app runs as its own service account with only the roles it needs (below); Application Default Credentials, no keys in the code

```
Browser (HTML + CSS + JS, no build step)
   │  HTTPS · results streamed as NDJSON
   ▼
Cloud Run · FastAPI ── per-person limits
   ├─ Orchestrator (asyncio): runs the agents in parallel, streams start / done / failed for each
   │    ├─ Product, Market, Verdict, Autofill ─► Gemini on Vertex AI (+ Google Search grounding)
   │    ├─ Market ─► reads the product pages Search returned (price, picture, rating)
   │    ├─ Demand, Fit, Budget, shop pages ─► BigQuery
   │    └─ Profit, rule checks ─► Python
   └─ Settings (rules + shop profile) ◄─► BigQuery
```

One agent failing never stops a check: it's marked as failed and the others carry on.

## Project layout

```
backend/
  main.py           FastAPI app: pages and /api/* routes
  config.py         model, regions, dataset, default rules
  limits.py         per-person hourly limits
  access.py         optional access-code gate (off unless GONOGO_ACCESS_CODE is set)
  agents/           one file per agent; orchestrator.py runs them
    llm.py          Gemini helper (JSON output, search grounding)
    bq.py           runs backend/sql/<name>.sql with parameters
    mock.py         sample data for GONOGO_MOCK=1
  sql/              one parameterised query per file
  static/           the pages: index.html (Discovery), business.html, shop.html, data.html + data.js,
                    agents.js (the agent team), shared.js (sidebar, settings), app.css
  test_local.py     runs demo cases from the command line
scripts/
  generate_shop_data.py   creates the Urban Loom CSVs in scripts/data/
  load_to_bigquery.py     loads them into BigQuery
```

## Run it locally

You need Python 3.11 and the Google Cloud CLI.

```bash
gcloud auth application-default login

# once: create and load the demo shop
python scripts/generate_shop_data.py
python scripts/load_to_bigquery.py

# the app
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
GOOGLE_CLOUD_PROJECT=gonogo-511 uvicorn main:app --reload --port 8080
```

Open http://localhost:8080. To run without Google Cloud on sample data, add `GONOGO_MOCK=1`.

## Deploy

```bash
cd backend
gcloud run deploy gonogo --source . --region asia-south1 --allow-unauthenticated --max-instances=2 \
  --service-account gonogo-run@gonogo-511.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_CLOUD_PROJECT=gonogo-511
```

The `gonogo-run` service account needs only:

| Role | Where | Why |
|---|---|---|
| `roles/aiplatform.user` | project | call Gemini |
| `roles/bigquery.jobUser` | project | run queries |
| `roles/bigquery.dataViewer` | project | read the shop's data |
| `roles/bigquery.dataEditor` | the `gonogo_shop` dataset only | save the rules and shop profile |

To use another dataset, set `GONOGO_DATASET=project.dataset`. To put the demo behind a code, add `GONOGO_ACCESS_CODE=<code>` to the environment variables; keep the code out of the repo.

## Safety

- No keys or credentials in the repo: Application Default Credentials only, and `.gitignore` blocks `.env`, `*.json` and key files.
- Per-person hourly limits on everything that costs money or changes data: 10 checks, 30 photo reads, 20 settings saves ([`limits.py`](backend/limits.py)).
- The server fetches only `https://` product pages on the known marketplaces' own hosts.
- Text from the model and from store pages is escaped before it's shown.

## Assumptions and limits

- Urban Loom's numbers are realistic but made up, and it sells apparel only.
- Expected sales = what comparable products (same category, similar price) sell per product per month over the last 12 months, counting only the months each was on sale.
- Trend compares the last 3 months with the same 3 months a year earlier, relative to the whole shop, so seasons cancel out.
- Some stores block automated visits from cloud servers, so the live site can show fewer product pictures than a local run.
- Recent checks are kept in the browser, not in the cloud.

## What's next

- **Make it a Go:** for a No-go, work out the smallest change that passes every rule (cost, price, opening order).
- **Compare ideas:** check up to three products at once and rank them by margin, speed, cash and risk.
- **Connect real shops:** Shopify, WooCommerce and marketplace seller APIs instead of the demo data.
- **Learn from outcomes:** compare each launch's real sales with the forecast and tune the rules.
