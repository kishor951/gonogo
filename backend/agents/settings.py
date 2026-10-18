"""The shop's name, rules and profile, saved in BigQuery (settings table) so every browser and every
agent uses the same ones."""
import json

from config import DEFAULT_ASSUMPTIONS, DEFAULT_PROFILE, DEFAULT_SHOP_NAME, MOCK
from agents import bq, mock

POSITIONING = {"value": "value (low prices)", "mid": "mid-market", "premium": "premium"}
PROFILE_LIMITS = {"tagline": 120, "description": 600, "target_customer": 400, "style": 300,
                  "never_sells": 300, "based_in": 60, "founded": 10}
_migrated = False


def clean_rules(rules: dict | None) -> dict:
    """Known rules only, as non-negative numbers; anything missing or invalid falls back to the default."""
    out = dict(DEFAULT_ASSUMPTIONS)
    for key, default in DEFAULT_ASSUMPTIONS.items():
        try:
            value = float((rules or {}).get(key))
        except (TypeError, ValueError):
            continue
        if value != value or value < 0 or value == float("inf"):
            continue
        out[key] = int(value) if isinstance(default, int) and value.is_integer() else value
    return out


def clean_profile(profile: dict | None) -> dict:
    """Known fields only, as trimmed text; positioning is one of value / mid / premium."""
    out = dict(DEFAULT_PROFILE)
    for key, limit in PROFILE_LIMITS.items():
        value = (profile or {}).get(key)
        if isinstance(value, str):
            out[key] = value.strip()[:limit]
    if (profile or {}).get("positioning") in POSITIONING:
        out["positioning"] = profile["positioning"]
    return out


def _load(text, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


async def _ensure_profile_column():
    """Settings tables loaded before the Shop profile page have no profile_json column: add it once."""
    global _migrated
    if not _migrated and not MOCK:
        try:
            await bq.run("settings_migrate")
        except Exception:
            pass   # no permission to alter the table: reads below will say what went wrong
        _migrated = True


async def get_settings() -> dict:
    await _ensure_profile_column()
    rows = mock.settings_get() if MOCK else await bq.run("settings_get")
    if not rows:
        return {"shop_name": DEFAULT_SHOP_NAME, "rules": dict(DEFAULT_ASSUMPTIONS),
                "profile": dict(DEFAULT_PROFILE), "updated_at": None}
    row = rows[0]
    return {"shop_name": row["shop_name"] or DEFAULT_SHOP_NAME,
            "rules": clean_rules(_load(row.get("rules_json"), {})),
            "profile": clean_profile(_load(row.get("profile_json"), {})),
            "updated_at": row["updated_at"]}


async def save_settings(shop_name: str | None = None, rules: dict | None = None, profile: dict | None = None) -> dict:
    """Save what was sent and keep the rest, so the Business page (rules) and the Shop profile page
    (name + profile) never overwrite each other."""
    current = await get_settings()
    params = {
        "shop_name": (shop_name or "").strip() or current["shop_name"],
        "rules_json": json.dumps(clean_rules(rules if rules is not None else current["rules"])),
        "profile_json": json.dumps(clean_profile({**current["profile"], **profile} if profile is not None
                                                 else current["profile"])),
    }
    if MOCK:
        mock.settings_save(params)
    else:
        await bq.run("settings_save", params)
    return await get_settings()


async def load_brief(allowed: dict[str, list[str]]) -> str:
    """The saved shop definition for the agents; the default one if the settings can't be read."""
    try:
        s = await get_settings()
        return shop_brief(s["shop_name"], s["profile"], allowed)
    except Exception:
        return shop_brief(DEFAULT_SHOP_NAME, DEFAULT_PROFILE, allowed)


def shop_brief(name: str, profile: dict, allowed: dict[str, list[str]]) -> str:
    """The shop's definition, as plain text for the agents' prompts."""
    p = clean_profile(profile)
    cats = "; ".join(f"{dept}: {', '.join(c)}" for dept, c in allowed.items())
    return (f"Shop: {name}. {p['tagline']}.\n"
            f"What it is: {p['description']}\n"
            f"Customers: {p['target_customer']}\n"
            f"Price positioning: {POSITIONING[p['positioning']]}. Style: {p['style']}\n"
            f"Categories it sells: {cats}\n"
            f"It never sells: {p['never_sells'] or '(nothing listed)'}")
