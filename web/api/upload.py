"""
POST /api/upload  (multipart/form-data) → uploads CV to Supabase Storage.

We accept the raw PDF bytes in the request body with header X-Filename for the
filename, to keep this dependency-free (no multipart parser). The web form
sends the file via fetch() with the PDF as the body.

Response: { "path": "<storage path>" }
"""
from http.server import BaseHTTPRequestHandler

from _helpers import require_auth, make_db, write_json
from bot.supabase_db import SupabaseError

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MAGIC_PDF = b"%PDF"


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not require_auth(self):
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0 or length > MAX_BYTES:
            write_json(self, 413, {"error": "file too large or empty",
                                   "max_mb": MAX_BYTES // (1024 * 1024)})
            return
        data = self.rfile.read(length)
        if not data.startswith(MAGIC_PDF):
            write_json(self, 400, {"error": "not a PDF (must start with %PDF)"})
            return
        filename = (self.headers.get("X-Filename") or "cv.pdf").strip()
        try:
            db = make_db()
            path = db.upload_cv(data, filename)
            write_json(self, 200, {"path": path, "size": len(data)})
        except SupabaseError as exc:
            write_json(self, 500, {"error": str(exc)})

    def log_message(self, *args): pass
