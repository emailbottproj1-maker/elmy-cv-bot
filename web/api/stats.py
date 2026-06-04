"""
GET /api/stats?campaign_id=X → sync opens from email_opens_agg and return:
    { "counts": {...}, "opens": [ {company_name,email,open_count,first_open_at} ] }
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from _helpers import require_auth, make_db, write_json
from bot.supabase_db import SupabaseError


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not require_auth(self):
            return
        qs = parse_qs(urlparse(self.path).query)
        try:
            cid = int(qs.get("campaign_id", [""])[0])
        except ValueError:
            write_json(self, 400, {"error": "bad campaign_id"})
            return
        try:
            db = make_db()
            counts = db.campaign_counts(cid)
            opens = db.campaign_opens(cid, limit=100)
            write_json(self, 200, {"counts": counts, "opens": opens})
        except SupabaseError as exc:
            write_json(self, 500, {"error": str(exc)})

    def log_message(self, *args): pass
