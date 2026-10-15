# GoNoGo

**Know if a product will sell before you stock it.**

GoNoGo is an AI launch-decision agent for retailers. A seller proposes a new product. Specialist agents built on Gemini check it against real sales history in BigQuery and today's online prices, then a verdict agent applies the seller's own rules and returns **Go**, **No-go** or **Go, with conditions**, with three reasons. Every reason opens to the numbers or sources behind it.

Built for the Google Cloud AI Builder Cup 2026, Retail & Commerce theme.

**Live app:** https://gonogo-389639819210.asia-south1.run.app

## Two pages

- **Discovery** (`/`): propose a product and get the verdict, the reasons with evidence, competitor products with links, and your rule checks.
- **Organisation** (`/organisation`): your business data at a glance (catalogue, units sold, orders, customers, return rate and best-selling categories from BigQuery) and your shop's numbers and rules, which every Discovery verdict uses.

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
| Demand | How fast would it sell? | BigQuery: comparable products (same category, price within ±30%), sales speed vs store average, 3-month trend, return rate |
| Fit | Who buys it, and with what? | BigQuery: basket analysis and buyer age bands |
| Profit | Does it make money? | Python: margin after fees, shipping and returns; break-even; opening order; cash tied up |
| Verdict | Go or no-go? | The seller's rules are checked in code (so verdicts are consistent); Gemini writes the headline, reasons and conditions and may not change the verdict |

**Numbers are calculated, never generated.** Gemini understands, searches and explains; BigQuery and Python produce every figure.

## Google Cloud services

- **Gemini on Vertex AI** (google-genai SDK)
- **Grounding with Google Search**
- **BigQuery** with the public `thelook_ecommerce` dataset as the sample store
- **Cloud Run** (one service: API + web page)
- **Cloud Build** and **Artifact Registry** (used automatically by `gcloud run deploy --source`)
- **IAM**: the Cloud Run service account calls Vertex AI and BigQuery; no keys in the code

## Project layout

```
backend/
  main.py              FastAPI app: GET /, GET /health, GET /api/categories, POST /api/evaluate
  config.py            model, region, currency rate, default seller rules
  agents/              one file per agent + orchestrator.py
  sql/                 the BigQuery queries
  static/index.html    the web page (plain HTML + JavaScript)
  test_local.py        run the two demo cases from the command line
  Dockerfile
```

## Run it

In Cloud Shell, or anywhere with the Google Cloud CLI:

```bash
cd backend
pip install -r requirements.txt
gcloud auth application-default login     # not needed in Cloud Shell

python test_local.py                       # two demo cases, real Gemini + BigQuery
uvicorn main:app --port 8080               # then open http://localhost:8080
```

`GONOGO_MOCK=1` runs everything on sample data with no Google Cloud calls.

## Deploy

```bash
cd backend
gcloud run deploy gonogo --source . --region asia-south1 --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
```

The Cloud Run service account needs `roles/aiplatform.user`, `roles/bigquery.jobUser` and `roles/bigquery.dataViewer`.

## Assumptions and limits

- The sample store sells clothing and accessories only, so comparables exist for apparel.
- Its prices are in US dollars; GoNoGo converts at ₹88 per US$ (`USD_INR` setting).
- Expected sales = how fast comparable products sell relative to the store average, multiplied by how many units a typical product of the seller's sells per month. The seller sets that figure, and every other rule, on the page.

## Next steps

Connect a seller's own sales data (point-of-sale exports, Shopify, ONDC catalogues), compare each launch's real sales with the forecast to improve future verdicts, suggest products from basket gaps, and support regional languages.
