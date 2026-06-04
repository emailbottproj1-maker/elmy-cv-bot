"""
Vercel serverless function: open statistics.

GET /api/stats?token=<STATS_TOKEN>
  -> { "opens": [ {tracking_uuid, open_count, first_open_at, last_seen_at}, ... ] }

Reads the aggregated view `email_opens_agg` from Supabase. Protected by a shared
secret token (STATS_TOKEN) so random people can't scrape the open data.

Env vars:
  SUPABASE_URL
  SUPABASE_SERVICE_KEY
  STATS_TOKEN
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


def _fetch_aggregated() -> list:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return []
    endpoint = (
        f"{url.rstrip('/')}/rest/v1/email_opens_agg"
        "?select=email_uuid,open_count,first_open_at,last_seen_at"
    )
    req = urllib.request.Request(endpoint, method="GET")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    # normalize keys to what the desktop app expects
    return [
        {
            "tracking_uuid": r.get("email_uuid"),
            "open_count": r.get("open_count", 1),
            "first_open_at": r.get("first_open_at"),
            "last_seen_at": r.get("last_seen_at"),
        }
        for r in rows
    ]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        token = (qs.get("token", [""])[0] or "").strip()
        expected = os.environ.get("STATS_TOKEN", "")

        if not expected or token != expected:
            self._json(403, {"error": "forbidden"})
            return

        opens = _fetch_aggregated()
        self._json(200, {"opens": opens, "count": len(opens)})

    def _json(self, status: int, body: dict):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass
