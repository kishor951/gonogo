# GoNoGo build plan

Work one batch at a time. After each batch: run locally, run `python test_local.py`, then the owner deploys.
Always keep a working version deployed. Feature freeze: **Saturday 17 Oct, 11:00 IST**.
If time runs short, cut in this order: Batch 4 (chat), then "Compare 3" from Batch 3.

## Target app

Three pages, one shared header with tabs: **Discovery · Inventory · Business**.

| Page | Route | Purpose |
|---|---|---|
| Discovery | `/` | Propose 1 to 3 products (photo or text), get verdicts, fix a no-go, ask questions |
| Inventory | `/inventory` | Every SKU's stock, cover, status; problems to act on |
| Business | `/business` | Shop profile, key numbers, trends, category performance, the shop's rules |

Agent flow:
```
Photo/text -> Product -> Market (Google Search)  -\
                         Demand (shop sales)       > -> Profit -> Verdict -> Make it a Go
                         Inventory (shop stock)    |                      -> Ask about it (chat + calculator tool)
                         Fit (shop customers)    -/
```

---

## Batch 1 — The demo shop's data + Business page

### 1a. Generate the dataset
Create `scripts/generate_shop_data.py` (standard library only, fixed random seed so data is reproducible)
writing CSVs to `scripts/data/`. The shop: **Urban Loom**, a mid-size Indian online fashion store selling
women's and men's apparel on its own website, Myntra and Amazon. Prices are native rupees.

| Table | Rows | Columns |
|---|---|---|
| `suppliers` | ~12 | supplier_id, name, city, lead_time_days (7-35), moq |
| `products` | ~180 | sku, name, department (Women/Men), category, brand, cost_inr, price_inr, launch_date, supplier_id, status (active/discontinued) |
| `customers` | ~6,000 | customer_id, age_band (18-24, 25-34, 35-44, 45-54, 55+), city, first_order_date |
| `sales` | ~40,000 lines over 18 months up to yesterday | order_id, order_date, sku, qty, unit_price_inr, channel (website/myntra/amazon), customer_id, returned (bool) |
| `inventory` | one per SKU | sku, on_hand, on_order, reorder_point, last_received_date |
| `settings` | 1 | org_id ('default'), shop_name, rules_json, updated_at |

Categories (use these exact names): Women: Leggings, Activewear Tops, Kurtas, Dresses, Jeans, Outerwear, Sarees.
Men: T-Shirts, Shirts, Jeans, Activewear, Outerwear, Formal Trousers.

Realistic patterns the data must contain (they make verdicts differ):
- Long tail: ~15% of SKUs sell 60% of units; some SKUs sell almost nothing.
- Seasonality: Outerwear peaks Nov-Jan and is near zero Apr-Aug; activewear peaks Jan (new-year fitness).
- Trends: activewear and kurtas growing ~30% year on year; formal trousers declining ~20%.
- Prices: realistic Indian ranges (leggings ₹599-1,799; kurtas ₹799-2,999; outerwear ₹2,499-9,999), cost 35-60% of price.
- Returns: 8-25% depending on category (higher for dresses and jeans).
- Inventory problems: ~10 SKUs with stock below reorder point, ~12 overstocked (more than 120 days of cover),
  ~8 dead stock (no sales in 90 days but stock on hand), mostly in Outerwear and Formal Trousers.
- Order discounts: unit_price_inr sometimes 10-30% below list price.

### 1b. Load into BigQuery
Create `scripts/load_to_bigquery.py` (Python with `google-cloud-bigquery`, so it works on Windows, macOS and Linux)
that creates dataset `gonogo_shop` in location `asia-south1` (if missing) and loads every CSV with explicit schemas,
replacing existing tables. The owner runs it once from a terminal after `gcloud auth application-default login`.
Print row counts at the end.

### 1c. Switch the app to the shop dataset
- `config.py`: `DATASET = os.getenv("GONOGO_DATASET", "gonogo-511.gonogo_shop")`; remove the USD conversion.
- Rewrite every `.sql` file to read the shop tables (use `{dataset}` placeholder filled by `bq.py`).
- Demand: comparables = same department + category, price within the band; velocity = units per SKU per month
  for comparables vs. the shop's average SKU; trend = last 3 months vs. same 3 months last year (seasonality-aware)
  and vs. previous 3 months; return rate from `returned`.
- Fit: basket (other categories in the same orders) and buyer age bands, channels, top cities.

### 1d. Business page (`/business`, replaces `/organisation`; keep `/organisation` as a redirect)
- Shop profile: name, channels.
- KPIs (last 12 months): revenue, units, gross margin %, orders, average order value, return rate. Each with change vs. previous 12 months.
- Monthly revenue chart (inline SVG, last 18 months).
- Category performance table: revenue, units, margin %, growth %, return rate.
- Channel split (website / Myntra / Amazon).
- **Rules form saved to BigQuery** (`settings` table via MERGE) through `GET/PUT /api/settings`.
  Discovery reads rules from the API, not from the browser. Keep localStorage only as an offline fallback.
- Grant the Cloud Run service account `roles/bigquery.dataEditor` (document the command in README).

**Done when:** `/business` shows Urban Loom's numbers from BigQuery; saving rules in one browser shows the same rules in another.

---

## Batch 2 — Inventory page + Inventory agent

### 2a. Inventory page (`/inventory`) — done early, with the sidebar pages
- Totals: stock value at cost, SKUs, units on hand, dead-stock value, SKUs to reorder, overstock value.
- Table of all SKUs: name, category, on hand, on order, sales per week (last 8 weeks), days of cover, sell-through % (90 days),
  stock value, status pill: **Reorder** (on_hand + on_order < reorder_point), **Healthy**, **Overstock** (cover > 120 days), **Dead stock** (no sales 90 days).
- Filters: department, category, status. Sort by any column. Search by name.
- Calculations in SQL (`sql/inventory_status.sql`), not in the browser.

### 2b. Inventory agent (`agents/inventory.py`), runs in parallel with Market/Demand/Fit
Checks for the proposed product:
- **Cannibalisation:** existing active SKUs in the same category and price band; their combined weekly sales and stock.
- **Category stock health:** days of cover and dead-stock value already in that category.
- **Cash:** opening-order cost vs. a new rule `max_opening_order_inr` (default ₹1,50,000) and vs. current stock value.
New rule checks in `verdict.py`: cash (hard), category overstock (soft), cannibalisation (soft).
Evidence: table of the overlapping SKUs with links to `/inventory?sku=...`.

**Done when:** proposing a new Outerwear item shows a warning about existing overstock; Inventory page lists the problem SKUs.

---

## Batch 3 — Discovery upgrades

### 3a. Start from a photo (`POST /api/autofill`) — done
Upload a photo (or a photo + a few words) → Gemini (vision) returns name, description, department, category
(from the shop's category list), and a suggested selling price range from the shop's comparable products (SQL, not Gemini).
The form fills in; the seller can edit, then run. Make the photo the first, most prominent input.

### 3b. Make it a Go (`POST /api/fix`)
For a no-go or go-with-conditions result, compute in code the smallest change that passes every hard rule:
- **Price lever:** lowest price that meets min margin and break-even, then check it against the market range.
- **Cost lever:** highest cost price that passes at the current price ("negotiate supplier cost to ₹X").
- **Order lever:** smaller opening order that passes the cash rule and reduces risk.
Return up to 3 options, each with the recomputed checks. Gemini writes one sentence per option (numbers passed in).
UI: a "Make it a Go" button on the verdict; options as cards; "Apply" re-runs the full evaluation with the new values
and shows the verdict turning green.

### 3c. Compare up to 3 ideas
Discovery lets the seller add up to 3 products (tabs or rows). Run evaluations in parallel (`asyncio.gather`),
then show a ranking table: verdict, margin, expected units/month, break-even, cash needed, risk flags; a winner badge;
click a row to see that product's full result.

**Done when:** the demo flow works on the live URL: photo → no-go → Make it a Go → apply → Go; and a 3-way comparison ranks correctly.

---

## Batch 4 — Ask about this verdict (cut first if late)

`POST /api/ask` with `{question, result}`. Gemini answers with **function calling**, using tools implemented in Python:
- `simulate(price_inr, cost_inr, opening_units)` → recomputes profit and rule checks for the current product.
- `stock_for_category(category)` → current inventory figures from BigQuery.
Gemini must call a tool for any number it states. UI: a chat box under the result with 3 suggested questions
("What if I sell at ₹999?", "What's the biggest risk?", "How much cash do I need?").

**Done when:** "What if I sell at ₹999?" returns an answer whose numbers match the calculator.

---

## Submission (Saturday afternoon, after freeze)
- README: what it does, screenshots, architecture diagram, Google Cloud services, how to run and deploy, the demo shop is synthetic.
- Deck (PDF): problem, solution, live demo screenshots, architecture, impact, roadmap.
- 3-minute video: photo → no-go → Make it a Go → Go → Inventory and Business pages → architecture → impact.
- Check from a fresh browser: live URL, public GitHub repo with no secrets, public video link.
