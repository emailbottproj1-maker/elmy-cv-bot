"""
GET /api/tick?token=<CRON_TOKEN> → process exactly one pending email.

Called by an external cron service (cron-job.org) every minute. Spacing and the
daily cap are enforced GLOBALLY inside run_tick().
"""
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from _helpers import make_db, write_json
from bot.supabase_db import SupabaseError
from bot.web_engine import run_tick


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        provided = (qs.get("token", [""])[0] or "").strip()
        expected = os.environ.get("CRON_TOKEN", "")
        if not expected or provided != expected:
            write_json(self, 403, {"error": "forbidden"})
            return
        try:
            db = make_db()
            result = run_tick(
                db,
                gmail_address=os.environ.get("GMAIL_ADDRESS", ""),
                app_password=os.environ.get("GMAIL_APP_PASSWORD", ""),
                pixel_base_url=os.environ.get("PIXEL_BASE_URL", ""),
                pixel_token=os.environ.get("PIXEL_TOKEN", ""),
                gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            )
            write_json(self, 200, {
                "action": result.action,
                "reason": result.reason,
                "campaign_id": result.campaign_id,
                "company": result.company,
                "source": result.source,
                "sent_today": result.sent_today,
                "daily_cap": result.daily_cap,
            })
        except SupabaseError as exc:
            write_json(self, 500, {"error": str(exc)})

    def log_message(self, *args): pass
