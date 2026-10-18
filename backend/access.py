"""The access-code gate for the live demo.

When GONOGO_ACCESS_CODE is set, every page and API call needs the code: pages redirect to /access, the API
answers 401. Entering the right code sets a cookie for 30 days. The cookie holds a signature of the code
(HMAC), never the code itself, so changing the code on Cloud Run locks everyone out until they enter the new one.
"""
import hashlib
import hmac
import time
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from config import ACCESS_CODE
from limits import client_ip

COOKIE = "gonogo_access"
MAX_AGE = 30 * 24 * 3600
OPEN_PATHS = {"/access", "/api/access", "/health", "/static/app.css"}
_attempts: dict[str, list[float]] = {}   # ip -> times of wrong tries (in memory, per instance)


def _token(code: str) -> str:
    return hmac.new(code.encode(), b"gonogo-access-v1", hashlib.sha256).hexdigest()


def has_access(request: Request) -> bool:
    if not ACCESS_CODE:
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(ACCESS_CODE))


async def gate(request: Request, call_next):
    """Middleware: let through open paths and people with the access cookie; stop everyone else."""
    path = request.url.path
    if not ACCESS_CODE or path in OPEN_PATHS or has_access(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "This demo needs an access code. Open the page and enter it first."}, status_code=401)
    target = path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/access?next={quote(target)}", status_code=303)


def too_many_tries(ip: str) -> bool:
    now = time.monotonic()
    recent = [t for t in _attempts.get(ip, []) if now - t < 600]
    _attempts[ip] = recent
    return len(recent) >= 10


def check_code(request: Request, code: str) -> JSONResponse:
    ip = client_ip(request)
    if too_many_tries(ip):
        return JSONResponse({"detail": "Too many wrong tries. Wait 10 minutes and try again."}, status_code=429)
    if not ACCESS_CODE or hmac.compare_digest(code.strip(), ACCESS_CODE):
        res = JSONResponse({"ok": True})
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        res.set_cookie(COOKIE, _token(ACCESS_CODE) if ACCESS_CODE else "", max_age=MAX_AGE,
                       httponly=True, secure=https, samesite="lax")
        return res
    _attempts.setdefault(ip, []).append(time.monotonic())
    return JSONResponse({"detail": "That code isn't right. Check the code in the submission and try again."}, status_code=401)
