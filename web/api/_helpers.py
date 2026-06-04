"""
Shared helpers for the web API handlers.

Centralises:
  * JSON response writing
  * cookie-based site password auth
  * lazy SupabaseDB construction with friendly errors

The auth is intentionally simple — the site is a single-tenant tool for one
person (Mohammed). One shared password, one HMAC-signed cookie. No accounts.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from http.cookies import SimpleCookie
from typing import Any

# Ensure project root on path so `bot/` imports work in Vercel runtime.
import sys as _sys
import os as _os
_root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".."))
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from bot.supabase_db import SupabaseDB, SupabaseError  # noqa: E402

COOKIE_NAME = "elmy_auth"
COOKIE_TTL_DAYS = 7


# ---------- JSON helpers ----------
def write_json(self, status: int, body: dict | list, *, set_cookie: str = ""):
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(payload)))
    self.send_header("Cache-Control", "no-store")
    if set_cookie:
        self.send_header("Set-Cookie", set_cookie)
    self.end_headers()
    self.wfile.write(payload)


def read_json(self, max_bytes: int = 5_000_000) -> dict:
    length = int(self.headers.get("Content-Length", 0) or 0)
    if length <= 0 or length > max_bytes:
        return {}
    raw = self.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}


# ---------- auth ----------
def _auth_secret() -> str:
    # Use SITE_PASSWORD + a stable salt as the cookie-signing key.
    return os.environ.get("SITE_PASSWORD", "") + "|elmy-cv-bot|v1"


def make_auth_cookie() -> str:
    expires_at = int(time.time()) + COOKIE_TTL_DAYS * 86400
    payload = str(expires_at)
    sig = hmac.new(_auth_secret().encode(), payload.encode(),
                   hashlib.sha256).hexdigest()
    value = f"{payload}.{sig}"
    return (f"{COOKIE_NAME}={value}; Path=/; HttpOnly; SameSite=Lax; "
            f"Max-Age={COOKIE_TTL_DAYS * 86400}; Secure")


def clear_auth_cookie() -> str:
    return f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Secure"


def is_authed(headers) -> bool:
    raw = headers.get("Cookie", "")
    if not raw:
        return False
    cookie = SimpleCookie()
    try:
        cookie.load(raw)
    except Exception:
        return False
    morsel = cookie.get(COOKIE_NAME)
    if not morsel:
        return False
    try:
        payload, sig = morsel.value.split(".", 1)
        expires_at = int(payload)
    except (ValueError, AttributeError):
        return False
    if expires_at < time.time():
        return False
    expected = hmac.new(_auth_secret().encode(), payload.encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def require_auth(handler) -> bool:
    if is_authed(handler.headers):
        return True
    write_json(handler, 401, {"error": "unauthorized"})
    return False


# ---------- DB factory ----------
def make_db() -> SupabaseDB:
    """Construct a SupabaseDB or raise SupabaseError (caught by handlers)."""
    return SupabaseDB()
