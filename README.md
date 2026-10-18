# GoNoGo

**Know if a product will sell before you stock it.**

GoNoGo is an AI launch-decision agent for retailers. A seller proposes a new product. Specialist agents built on Gemini check it against real sales history in BigQuery and today's online prices, then a verdict agent applies the seller's own rules and returns **Go**, **No-go** or **Go, with conditions**, with three reasons. Every reason opens to the numbers or sources behind it.

Built for the Google Cloud AI Builder Cup 2026, Retail & Commerce theme.

**Live app:** https://gonogo-389639819210.asia-south1.run.app

## Pages

- **Discovery** (`/`): propose a product and get the verdict, the reasons with evidence, competitor products with links, and your rule checks.
A sidebar on every page links them all.

- **Products, Inventory, Sales, Returns, Customers, Suppliers** (`/products`, `/inventory`, ...): the shop's data, each with key numbers and tables you can search, filter and sort. Inventory flags products to reorder, overstock (over 120 days of cover) and dead stock (no sale in 90 days).
- **Business** (`/business`): the shop's key numbers for the last 12 months with change vs the 12 months before, monthly revenue, category performance, channel split, and the shop's rules. Rules are saved in BigQuery, so every browser and every Discovery verdict uses the same ones. (`/organisation` redirects here.)

## The demo shop: Urban Loom

Urban Loom is a **synthetic** mid-size Indian online fashion shop (women's and men's apparel, sold on its website, Myntra and Amazon, prices in rupees). `scripts/generate_shop_data.py` creates two years of data with realistic patterns: a long tail of slow sellers, winter outerwear, January activewear peaks, kurtas and activewear growing ~30% a year, formal trousers declining, 8-26% returns by category, discounts, and stock problems (items to reorder, overstock, dead stock).

| Table | Rows | What it holds |
|---|---|---|
| `suppliers` | 12 | lead times and minimum order quantities |
| `products` | 180 | SKU, department, category, brand, cost and list price, launch date, status |
| `customers` | 6,000 | age band, city, first order date |
| `sales` | ~53,000 | order lines: date, SKU, qty, price paid, channel, customer, returned |
| `inventory` | 180 | on hand, on order, reorder point, last received |
| `settings` | 1 | shop name and rules (written by the Business page) |

## How it works

```
Seller input ──► Product agent ──► Market agent  (Gemini + Google Search grounding) ──┐
 (name, photo,   (Gemini: maps      Demand agent  (BigQuery: comparable sales)       ├──► Profit agent ──► Verdict agent
  cost, price)    to a category)    Fit agent     (BigQuery: basket + buyer ages)   ─┘    (Python maths)    (rules in code,
                                    ...these three run in parallel                                           Gemini explains)
```

| Agent | What it answers | How |
|---|---|---|
| Product | What exactly is this product? | Gemini reads the description and optional photo, maps it to a store category |
| Market | What do similar products sell for online, and who sells them? | Gemini with Grounding with Google Search; competitor products linked to the real pages Search returned (or to a store search when no page matched) |
| Demand | How fast would it sell? | BigQuery: comparable products (same category, price within ±30%), units per product per month vs the shop average, last 3 months vs the same months last year, return rate |
| Fit | Who buys it, and with what? | BigQuery: basket analysis, buyer age bands, channels and top cities |
| Profit | Does it make money? | Python: margin after fees, shipping and returns; break-even; opening order; cash tied up |
| Verdict | Go or no-go? | The seller's rules are checked in code (so verdicts are consistent); Gemini writes the headline, reasons and conditions and may not change the verdict |

**Numbers are calculated, never generated.** Gemini understands, searches and explains; BigQuery and Python produce every figure.

## Google Cloud services

- **Gemini on Vertex AI** (google-genai SDK)
- **Grounding with Google Search**
- **BigQuery** with the shop's own dataset (`gonogo_shop`, in `asia-south1`)
- **Cloud Run** (one service: API + web page)
- **Cloud Build** and **Artifact Registry** (used automatically by `gcloud run deploy --source`)
- **IAM**: the Cloud Run service account calls Vertex AI and BigQuery; no keys in the code

## Project layout

```
backend/
  main.py              FastAPI app: pages, /api/categories, /api/business, /api/settings, /api/evaluate
  config.py            model, region, dataset, default seller rules
  agents/              one file per agent + orchestrator.py, business.py, settings.py
  sql/                 the BigQuery queries ({dataset} is filled in from GONOGO_DATASET)
  static/              index.html (Discovery), business.html, app.css, shared.js
  test_local.py        run the two demo cases from the command line
  Dockerfile
scripts/
  generate_shop_data.py  creates the Urban Loom CSVs in scripts/data/
  load_to_bigquery.py    loads them into BigQuery
```

## Run it

Load the demo shop once (from the repo root, with the backend's virtual environment active):

```bash
gcloud auth application-default login
python scripts/generate_shop_data.py       # writes scripts/data/*.csv
python scripts/load_to_bigquery.py         # creates gonogo-511.gonogo_shop and loads every table
```

Then run the app:

```bash
cd backend
pip install -r requirements.txt
export GOOGLE_CLOUD_PROJECT=gonogo-511

python test_local.py                       # two demo cases, real Gemini + BigQuery
uvicorn main:app --port 8080               # then open http://localhost:8080
```

`GONOGO_MOCK=1` runs everything on sample data with no Google Cloud calls.

## Deploy

The live demo is locked with an access code, so only evaluators can use it (and nobody else can spend the Gemini quota
or change the rules). Choose a code, keep it out of the repo, and pass it at deploy time:

```bash
cd backend
gcloud run deploy gonogo --source . --region asia-south1 --allow-unauthenticated --max-instances=2 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=gonogo-511,GONOGO_ACCESS_CODE=YOUR-CODE
```

Change the code later (everyone has to enter the new one):

```bash
gcloud run services update gonogo --region asia-south1 --update-env-vars GONOGO_ACCESS_CODE=NEW-CODE
```

Without `GONOGO_ACCESS_CODE` (for example on your laptop) the app is open.

### Older deploy notes

```bash
cd backend
gcloud run deploy gonogo --source . --region asia-south1 --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
```

The Cloud Run service account needs `roles/aiplatform.user`, `roles/bigquery.jobUser`, `roles/bigquery.dataViewer`, and `roles/bigquery.dataEditor` (the Business page saves the rules to the `settings` table):

```bash
gcloud projects add-iam-policy-binding gonogo-511 \
  --member="serviceAccount:389639819210-compute@developer.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"
```

To use another dataset, set `GONOGO_DATASET=project.dataset` on the service.

## Assumptions and limits

- Urban Loom is synthetic: the numbers are realistic but made up. It sells apparel only, so comparables exist for apparel.
- Expected sales = what comparable products (same category, similar price) sell per product per month in the last 12 months, counting only the months each was on sale.
- The trend compares the last 3 months with the same 3 months a year earlier, relative to the whole shop, so seasons cancel out.

## Next steps

Connect a seller's own sales data (point-of-sale exports, Shopify, ONDC catalogues), compare each launch's real sales with the forecast to improve future verdicts, suggest products from basket gaps, and support regional languages.
