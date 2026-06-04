"""POST /api/login { password } → sets cookie, 200 ok / 401."""
import os
from http.server import BaseHTTPRequestHandler

from _helpers import make_auth_cookie, clear_auth_cookie, write_json, read_json


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = read_json(self)
        provided = (body.get("password") or "").strip()
        expected = os.environ.get("SITE_PASSWORD", "")
        if not expected:
            write_json(self, 500, {"error": "SITE_PASSWORD not configured"})
            return
        if provided != expected:
            write_json(self, 401, {"error": "wrong password"})
            return
        write_json(self, 200, {"ok": True}, set_cookie=make_auth_cookie())

    def do_DELETE(self):
        # logout
        write_json(self, 200, {"ok": True}, set_cookie=clear_auth_cookie())

    def log_message(self, *args): pass
