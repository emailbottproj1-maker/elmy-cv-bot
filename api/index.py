"""
Flask app — single entrypoint for all /api/* routes on Vercel.
Replaces the individual BaseHTTPRequestHandler files in web/api/.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import sys
import time

# Make bot/ importable (sits one level above this file, same project root)
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from flask import Flask, Response, jsonify, make_response, request

from bot.supabase_db import SupabaseDB, SupabaseError

_public = os.path.join(_root, "public")
app = Flask(__name__)


# ─── Static files ────────────────────────────────────────────────────────────

def _serve(filename: str, mime: str):
    path = os.path.join(_public, filename)
    try:
        with open(path, "rb") as f:
            return Response(f.read(), mimetype=mime)
    except FileNotFoundError:
        return Response(f"Not found: {path}", status=404)


@app.route("/")
@app.route("/index.html")
def index():
    return _serve("index.html", "text/html; charset=utf-8")


@app.route("/app.js")
def appjs():
    return _serve("app.js", "application/javascript; charset=utf-8")


@app.route("/style.css")
def stylecss():
    return _serve("style.css", "text/css; charset=utf-8")


# ─── Auth ────────────────────────────────────────────────────────────────────

COOKIE_NAME = "elmy_auth"
COOKIE_TTL_DAYS = 7
ONE_PIXEL_GIF = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


def _auth_secret() -> str:
    return os.environ.get("SITE_PASSWORD", "") + "|elmy-cv-bot|v1"


def _make_auth_token() -> str:
    expires_at = int(time.time()) + COOKIE_TTL_DAYS * 86400
    payload = str(expires_at)
    sig = hmac.new(_auth_secret().encode(), payload.encode(),
                   hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _is_authed() -> bool:
    cookie_val = request.cookies.get(COOKIE_NAME, "")
    if not cookie_val:
        return False
    try:
        payload, sig = cookie_val.split(".", 1)
        expires_at = int(payload)
    except (ValueError, AttributeError):
        return False
    if expires_at < time.time():
        return False
    expected = hmac.new(_auth_secret().encode(), payload.encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def _require_auth():
    if not _is_authed():
        return jsonify({"error": "unauthorized"}), 401
    return None


def _db() -> SupabaseDB:
    return SupabaseDB()


# ─── /api/login ──────────────────────────────────────────────────────────────

@app.route("/api/login", methods=["POST", "DELETE"])
def login():
    if request.method == "DELETE":
        resp = make_response(jsonify({"ok": True}))
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp
    body = request.get_json(force=True, silent=True) or {}
    provided = (body.get("password") or "").strip()
    expected = os.environ.get("SITE_PASSWORD", "")
    if not expected:
        return jsonify({"error": "SITE_PASSWORD not configured"}), 500
    if provided != expected:
        return jsonify({"error": "wrong password"}), 401
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie(COOKIE_NAME, _make_auth_token(),
                    max_age=COOKIE_TTL_DAYS * 86400,
                    httponly=True, samesite="Lax", secure=True, path="/")
    return resp


# ─── /api/me ─────────────────────────────────────────────────────────────────

@app.route("/api/me", methods=["GET"])
def me():
    if _is_authed():
        return jsonify({"authed": True})
    return jsonify({"authed": False}), 401


# ─── /api/campaigns ──────────────────────────────────────────────────────────

@app.route("/api/campaigns", methods=["GET", "POST", "PATCH"])
def campaigns():
    err = _require_auth()
    if err:
        return err
    try:
        db = _db()
        if request.method == "GET":
            camps = db.list_campaigns()
            out = [{**c, "counts": db.campaign_counts(c["id"])} for c in camps]
            return jsonify({"campaigns": out})

        if request.method == "POST":
            body = request.get_json(force=True, silent=True) or {}
            required = ("customer_label", "cv_storage_path", "sender_name",
                        "subject_ar", "subject_en", "cover_letter_ar",
                        "cover_letter_en")
            missing = [k for k in required if not body.get(k)]
            if missing:
                return jsonify({"error": "missing fields", "fields": missing}), 400
            pkg_raw = body.get("package_size")
            if pkg_raw in (None, "", "all"):
                pkg = None
            else:
                try:
                    pkg = int(pkg_raw)
                    if pkg <= 0:
                        pkg = None
                except (TypeError, ValueError):
                    return jsonify({"error": "package_size must be a positive integer or 'all'"}), 400
            sector_raw = body.get("target_sector")
            sector = (sector_raw.strip()
                      if isinstance(sector_raw, str)
                      and sector_raw.strip()
                      and sector_raw.strip().lower() != "any"
                      else None)
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
            return jsonify({
                "campaign": camp,
                "targeted": result["targeted"],
                "overlap": result["overlap"],
            })

        # PATCH
        cid_str = request.args.get("id", "")
        try:
            cid = int(cid_str)
        except ValueError:
            return jsonify({"error": "bad id"}), 400
        body = request.get_json(force=True, silent=True) or {}
        status = (body.get("status") or "").strip()
        valid = {"active", "paused", "stopped", "done", "draft"}
        if status not in valid:
            return jsonify({"error": f"status must be one of {sorted(valid)}"}), 400
        db.set_campaign_status(cid, status)
        return jsonify({"ok": True, "id": cid, "status": status})

    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/companies ──────────────────────────────────────────────────────────

@app.route("/api/companies", methods=["GET", "POST"])
def companies():
    err = _require_auth()
    if err:
        return err
    try:
        db = _db()
        if request.method == "GET":
            rows = db.list_companies(limit=5000)
            return jsonify({"companies": rows, "count": len(rows)})
        body = request.get_json(force=True, silent=True) or {}
        rows = body if isinstance(body, list) else body.get("companies") or []
        if not rows:
            return jsonify({"error": "no companies provided"}), 400
        clean = [r for r in rows if r.get("company_name") and r.get("email")]
        db.upsert_companies(clean)
        return jsonify({"submitted": len(clean), "skipped": len(rows) - len(clean)})
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/sectors ────────────────────────────────────────────────────────────

SECTOR_LABELS = {
    "Healthcare": "صحة",
    "Marketing": "تسويق وإعلان",
    "Technology": "تقنية وبرمجة",
    "Finance": "مالية وبنوك",
    "Engineering": "هندسة ومقاولات",
    "Legal": "قانون",
    "Retail": "تجزئة وتجارة",
    "Education": "تعليم",
    "HR": "موارد بشرية",
    "Hospitality": "ضيافة وفنادق",
    "Logistics": "لوجستيك وشحن",
}


@app.route("/api/sectors", methods=["GET"])
def sectors():
    err = _require_auth()
    if err:
        return err
    try:
        db = _db()
        rows = db._select("/companies?select=sector&limit=100000")
        counts: dict[str, int] = {}
        for r in rows:
            s = (r.get("sector") or "").strip()
            if s:
                counts[s] = counts.get(s, 0) + 1
        result = [
            {"code": code, "label_ar": SECTOR_LABELS.get(code, code),
             "count": counts.get(code, 0)}
            for code in SECTOR_LABELS
        ]
        for code in sorted(counts.keys()):
            if code not in SECTOR_LABELS:
                result.append({"code": code, "label_ar": code,
                                "count": counts[code]})
        return jsonify({"sectors": result})
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/upload ─────────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def upload():
    err = _require_auth()
    if err:
        return err
    MAX_BYTES = 10 * 1024 * 1024
    data = request.get_data()
    if not data or len(data) > MAX_BYTES:
        return jsonify({"error": "file too large or empty", "max_mb": 10}), 413
    if not data.startswith(b"%PDF"):
        return jsonify({"error": "not a PDF (must start with %PDF)"}), 400
    filename = (request.headers.get("X-Filename") or "cv.pdf").strip()
    try:
        db = _db()
        path = db.upload_cv(data, filename)
        return jsonify({"path": path, "size": len(data)})
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/stats ──────────────────────────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def stats():
    err = _require_auth()
    if err:
        return err
    cid_str = request.args.get("campaign_id", "")
    try:
        cid = int(cid_str)
    except ValueError:
        return jsonify({"error": "bad campaign_id"}), 400
    try:
        db = _db()
        counts = db.campaign_counts(cid)
        opens = db.campaign_opens(cid, limit=100)
        return jsonify({"counts": counts, "opens": opens})
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/tick ───────────────────────────────────────────────────────────────

@app.route("/api/tick", methods=["GET"])
def tick():
    from bot.web_engine import run_tick
    provided = (request.args.get("token") or "").strip()
    expected = os.environ.get("CRON_TOKEN", "")
    if not expected or provided != expected:
        return jsonify({"error": "forbidden"}), 403
    try:
        db = _db()
        result = run_tick(
            db,
            gmail_address=os.environ.get("GMAIL_ADDRESS", ""),
            app_password=os.environ.get("GMAIL_APP_PASSWORD", ""),
            pixel_base_url=os.environ.get("PIXEL_BASE_URL", ""),
            pixel_token=os.environ.get("PIXEL_TOKEN", ""),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        )
        return jsonify({
            "action": result.action,
            "reason": result.reason,
            "campaign_id": result.campaign_id,
            "company": result.company,
            "source": result.source,
            "sent_today": result.sent_today,
            "daily_cap": result.daily_cap,
        })
    except SupabaseError as exc:
        return jsonify({"error": str(exc)}), 500


# ─── /api/pixel ──────────────────────────────────────────────────────────────

@app.route("/api/pixel", methods=["GET"])
def pixel():
    uid = (request.args.get("id") or "").strip()
    if uid:
        try:
            db = _db()
            db._post("/email_opens", {
                "email_uuid": uid,
                "ip": request.remote_addr or "",
                "user_agent": request.headers.get("User-Agent", ""),
            })
        except Exception:
            pass
    return Response(
        ONE_PIXEL_GIF,
        mimetype="image/gif",
        headers={"Cache-Control": "no-store, no-cache", "Pragma": "no-cache"},
    )
