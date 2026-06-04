"""
GET  /api/companies          → list master companies
POST /api/companies          → bulk-add companies (array of {company_name,email,...})
"""
from http.server import BaseHTTPRequestHandler

from _helpers import require_auth, make_db, read_json, write_json
from bot.supabase_db import SupabaseError


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not require_auth(self):
            return
        try:
            db = make_db()
            rows = db.list_companies(limit=5000)
            write_json(self, 200, {"companies": rows, "count": len(rows)})
        except SupabaseError as exc:
            write_json(self, 500, {"error": str(exc)})

    def do_POST(self):
        if not require_auth(self):
            return
        body = read_json(self)
        rows = body if isinstance(body, list) else body.get("companies") or []
        if not rows:
            write_json(self, 400, {"error": "no companies provided"})
            return
        # very light validation; supabase_db.upsert_companies relies on these
        clean = [r for r in rows if r.get("company_name") and r.get("email")]
        try:
            db = make_db()
            db.upsert_companies(clean)
            write_json(self, 200, {"submitted": len(clean), "skipped": len(rows) - len(clean)})
        except SupabaseError as exc:
            write_json(self, 500, {"error": str(exc)})

    def log_message(self, *args): pass
