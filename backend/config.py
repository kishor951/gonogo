"""Settings for GoNoGo. Override any of these with environment variables on Cloud Run."""
import os

# Set GONOGO_MOCK=1 to run with sample data and no Google Cloud calls (useful for UI work).
MOCK = os.getenv("GONOGO_MOCK") == "1"

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "us-central1")

# The sample store (thelook_ecommerce) prices products in US dollars.
# GoNoGo shows everything in rupees, converted at this rate (an assumption, shown in the evidence).
USD_INR = float(os.getenv("USD_INR", "88"))

DATASET = "bigquery-public-data.thelook_ecommerce"


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


# The seller's rules and assumptions. The web page lets the seller change every one of these.
DEFAULT_ASSUMPTIONS = {
    "avg_units_per_product": 30,   # units a typical product in the seller's shop sells per month
    "launch_cost": 10000,          # one-off cost to launch: samples, photos, listing, first promotion (INR)
    "shipping_per_unit": 60,       # INR per order
    "platform_fee_pct": 15,        # marketplace + payment fees, % of selling price
    "lead_time_weeks": 2,          # supplier lead time
    "cover_weeks": 4,              # weeks of stock to hold after launch
    "min_margin_pct": 20,          # rule: margin after all costs must be at least this
    "max_breakeven_weeks": 12,     # rule: launch cost must be earned back within this
    "min_velocity": 0.7,           # rule: comparable products must sell at least 0.7x the store average
    "price_band_pct": 30,          # comparables = same category, price within +/- this %
}
