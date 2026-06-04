"""
Vercel serverless function: tracking pixel.

GET /api/pixel?id=<tracking_uuid>
  - records an "open" event in Supabase (table: email_opens)
  - returns a 1x1 transparent GIF with aggressive anti-cache headers

Env vars (set in Vercel project settings):
  SUPABASE_URL          e.g. https://efyluvxcjchynqzytqrf.supabase.co
  SUPABASE_SERVICE_KEY  service_role key (server-side only)

Recording failures never block the pixel response — the user must always see
the image so email clients don't flag a broken resource.
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 1x1 transparent GIF (43 bytes).
PIXEL = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00, 0x80, 0x00,
    0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0x21, 0xF9, 0x04, 0x01, 0x00,
    0x00, 0x00, 0x00, 0x2C, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
    0x00, 0x02, 0x02, 0x44, 0x01, 0x00, 0x3B,
])


def _record_open(tracking_uuid: str, ip: str, ua: str) -> None:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key or not tracking_uuid:
        return
    endpoint = f"{url.rstrip('/')}/rest/v1/email_opens"
    payload = json.dumps({
        "email_uuid": tracking_uuid,
        "ip": ip[:64],
        "user_agent": ua[:300],
    }).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, method="POST")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # never block the pixel


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        tracking_uuid = (qs.get("id", [""])[0] or "").strip()
        ip = self.headers.get("x-forwarded-for", "") or self.client_address[0]
        ua = self.headers.get("user-agent", "")

        _record_open(tracking_uuid, ip, ua)

        self.send_response(200)
        self.send_header("Content-Type", "image/gif")
        self.send_header("Content-Length", str(len(PIXEL)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(PIXEL)

    def log_message(self, *args):
        pass  # silence default logging
