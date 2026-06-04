"""
GET /api/sectors → returns distinct sectors + count of companies per sector.

Response:
  { "sectors": [ {"code":"Healthcare","label_ar":"صحة","count":42}, ... ] }

The Arabic labels are bundled in this file so the UI doesn't need separate
config. If you add a new sector to a company row, it shows up automatically
(label_ar falls back to the code).
"""
from http.server import BaseHTTPRequestHandler

from _helpers import require_auth, make_db, write_json
from bot.supabase_db import SupabaseError

# Canonical English code -> Arabic display label
SECTOR_LABELS = {
    "Healthcare":   "صحة",
    "Marketing":    "تسويق وإعلان",
    "Technology":   "تقنية وبرمجة",
    "Finance":      "مالية وبنوك",
    "Engineering":  "هندسة ومقاولات",
    "Legal":        "قانون",
    "Retail":       "تجزئة وتجارة",
    "Education":    "تعليم",
    "HR":           "موارد بشرية",
    "Hospitality":  "ضيافة وفنادق",
    "Logistics":    "لوجستيك وشحن",
}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not require_auth(self):
            return
        try:
            db = make_db()
            # one cheap query — we count in Python (~500 rows is nothing)
            rows = db._select("/companies?select=sector&limit=100000")
            counts: dict[str, int] = {}
            for r in rows:
                s = (r.get("sector") or "").strip()
                if s:
                    counts[s] = counts.get(s, 0) + 1
            sectors = [
                {"code": code,
                 "label_ar": SECTOR_LABELS.get(code, code),
                 "count": counts.get(code, 0)}
                for code in SECTOR_LABELS.keys()
            ]
            # also include any "unknown" sectors found in DB (in case the
            # client adds new ones we don't have a label for yet)
            for code in sorted(counts.keys()):
                if code not in SECTOR_LABELS:
                    sectors.append({"code": code, "label_ar": code,
                                    "count": counts[code]})
            write_json(self, 200, {"sectors": sectors})
        except SupabaseError as exc:
            write_json(self, 500, {"error": str(exc)})

    def log_message(self, *args): pass
