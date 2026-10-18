"""Settings for GoNoGo. Override any of these with environment variables on Cloud Run."""
import os

# Set GONOGO_MOCK=1 to run with sample data and no Google Cloud calls (useful for UI work).
MOCK = os.getenv("GONOGO_MOCK") == "1"

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "us-central1")

# Access code for the live demo: set GONOGO_ACCESS_CODE on Cloud Run (never in the repo). Empty = open (local use).
ACCESS_CODE = os.getenv("GONOGO_ACCESS_CODE", "").strip()

# The shop's own BigQuery dataset (load it with scripts/load_to_bigquery.py). Prices are rupees.
DATASET = os.getenv("GONOGO_DATASET", "gonogo-511.gonogo_shop")
DEFAULT_SHOP_NAME = "Urban Loom"

# What the shop is: saved from the Shop profile page, and given to the Product and Verdict agents so they
# judge a new product against the brand, not just against the category list.
DEFAULT_PROFILE = {
    "tagline": "Everyday and ethnic fashion for young urban India",
    "description": "An online fashion shop selling women's and men's clothing: activewear, ethnic wear, denim, "
                   "shirts and T-shirts, workwear and winter wear, at mid-market prices.",
    "target_customer": "Women and men aged 22 to 40 in India's big cities who want good-looking everyday "
                       "clothes without paying premium-brand prices.",
    "positioning": "mid",
    "style": "Comfortable, modern and easy to care for; solid colours, block prints and clean cuts.",
    "never_sells": "Kids' wear, innerwear, footwear, jewellery, bags, home and puja items",
    "based_in": "Bengaluru",
    "founded": "2019",
}


def project_id():
    """Project from the environment, or from the Cloud Run / Cloud Shell credentials."""
    pid = os.getenv("GOOGLE_CLOUD_PROJECT")
    if pid or MOCK:
        return pid or "mock-project"
    try:
        import google.auth
        _, pid = google.auth.default()
    except Exception:
        pid = None
    return pid


# The seller's rules and assumptions. The Business page saves them to BigQuery (settings table).
DEFAULT_ASSUMPTIONS = {
    "avg_units_per_product": 15,   # fallback only: monthly units used if the Demand agent fails
    "launch_cost": 10000,          # one-off cost to launch: samples, photos, listing, first promotion (INR)
    "shipping_per_unit": 60,       # INR per order
    "platform_fee_pct": 15,        # marketplace + payment fees, % of selling price
    "lead_time_weeks": 2,          # supplier lead time
    "cover_weeks": 4,              # weeks of stock to hold after launch
    "min_margin_pct": 20,          # rule: margin after all costs must be at least this
    "max_breakeven_weeks": 12,     # rule: launch cost must be earned back within this
    "min_velocity": 0.7,           # rule: comparable products must sell at least 0.7x the shop average
    "price_band_pct": 30,
    "experiment_pct": 10,          # experiment budget = this % of monthly profit (then adjusted, see agents/budget.py)
    "launches_per_month": 2,       # per-launch budget = monthly experiment budget / this          # comparables = same category, price within +/- this %
}
