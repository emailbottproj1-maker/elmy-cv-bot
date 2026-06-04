"""
GET  /api/campaigns               → list campaigns + counts + recent opens
POST /api/campaigns               → create a new campaign (after CV upload)
PATCH /api/campaigns?id=X         → update status (start/pause/stop) or fields
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from _helpers import require_auth, make_db, read_json, write_json
from bot.supabase_db import SupabaseError


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if not require_auth(self):
            return
        try:
            db = make_db()
            camps = db.list_campaigns()
            out = []
            for c in camps:
                counts = db.campaign_counts(c["id"])
                out.append({**c, "counts": counts})
            write_json(self, 200, {"campaigns": out})
        except SupabaseError as exc:
            write_json(self, 500, {"error": str(exc)})

    def do_POST(self):
        if not require_auth(self):
            return
        body = read_json(self)
        required = ("customer_label", "cv_storage_path", "sender_name",
                    "subject_ar", "subject_en", "cover_letter_ar",
                    "cover_letter_en")
        missing = [k for k in required if not body.get(k)]
        if missing:
            write_json(self, 400, {"error": "missing fields",
                                   "fields": missing})
            return
        # validate package_size (None | 50 | 100 | 200, or any positive int)
        pkg_raw = body.get("package_size")
        pkg: int | None
        if pkg_raw in (None, "", "all"):
            pkg = None
        else:
            try:
                pkg = int(pkg_raw)
                if pkg <= 0:
                    pkg = None
            except (TypeError, ValueError):
                write_json(self, 400, {"error": "package_size must be a positive integer or 'all'"})
                return

        # target_sector is optional ("any" or empty == no filter)
        sector_raw = body.get("target_sector")
        sector = sector_raw.strip() if isinstance(sector_raw, str) and sector_raw.strip() and sector_raw.strip().lower() != "any" else None

        try:
            db = make_db()
            camp = db.create_campaign(
                customer_label=body["customer_label"],
                cv_storage_path=body["cv_storage_path"],
                sender_name=body["sender_name"],
                subject_ar=body["subject_ar"],
                subject_en=body["subject_en"],
                cover_letter_ar=body["cover_letter_ar"],
                cover_letter_en=body["cover_letter_en"],
                use_ai=bool(body.get("use_ai", True)),
                package_size=pkg,
                target_sector=sector,
            )
            result = db.populate_campaign_sends(
                camp["id"], package_size=pkg, target_sector=sector
            )
            write_json(self, 200, {
                "campaign": camp,
                "targeted": result["targeted"],
                "overlap": result["overlap"],
            })
        except SupabaseError as exc:
            write_json(self, 500, {"error": str(exc)})

    def do_PATCH(self):
        if not require_auth(self):
            return
        qs = parse_qs(urlparse(self.path).query)
        try:
            cid = int(qs.get("id", [""])[0])
        except ValueError:
            write_json(self, 400, {"error": "bad id"})
            return
        body = read_json(self)
        status = (body.get("status") or "").strip()
        valid = {"active", "paused", "stopped", "done", "draft"}
        if status not in valid:
            write_json(self, 400, {"error": f"status must be one of {sorted(valid)}"})
            return
        try:
            db = make_db()
            db.set_campaign_status(cid, status)
            write_json(self, 200, {"ok": True, "id": cid, "status": status})
        except SupabaseError as exc:
            write_json(self, 500, {"error": str(exc)})

    def log_message(self, *args): pass
