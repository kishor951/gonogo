"""Per-person limits, so one visitor can't run up the Gemini and Google Search bill or keep rewriting the rules.

Each IP address may start LIMITS[kind] actions of each kind in any rolling hour. Counts live in memory on each
Cloud Run instance (max 2), so the real limit is at most twice this, and a restart resets it: fine for a demo.
"""
import math
import time

from fastapi import HTTPException, Request

CHECKS_PER_HOUR = 10
LIMITS = {"check": CHECKS_PER_HOUR, "photo": 30, "settings": 20}
WORDS = {"check": "checks", "photo": "photo reads", "settings": "saves"}
WINDOW = 3600
_checks: dict[str, list[float]] = {}   # "kind:ip" -> times of recent actions


def client_ip(request: Request) -> str:
    """The visitor's address. Cloud Run appends the real one to X-Forwarded-For, after anything the client sent."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "?"


def check_limit(request: Request, kind: str = "check") -> None:
    """Count one action for this visitor, or stop with 429 and say when they can try again."""
    key, now = f"{kind}:{client_ip(request)}", time.monotonic()
    limit = LIMITS[kind]
    recent = [t for t in _checks.get(key, []) if now - t < WINDOW]
    if len(recent) >= limit:
        _checks[key] = recent
        wait = max(1, math.ceil((recent[0] + WINDOW - now) / 60))
        verb = "run" if kind == "check" else "made"
        raise HTTPException(status_code=429, detail=(
            f"You've {verb} {limit} {WORDS[kind]} in the last hour, the limit for this demo. "
            f"You can try again in {wait} minute{'s' if wait != 1 else ''}."))
    recent.append(now)
    _checks[key] = recent
    if len(_checks) > 5000:   # forget visitors with no checks in the last hour
        for old in [k for k, v in _checks.items() if not v or now - v[-1] >= WINDOW]:
            del _checks[old]
