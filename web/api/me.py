"""GET /api/me → 200 if cookie valid, 401 otherwise (for the web UI to check)."""
from http.server import BaseHTTPRequestHandler

from _helpers import is_authed, write_json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if is_authed(self.headers):
            write_json(self, 200, {"authed": True})
        else:
            write_json(self, 401, {"authed": False})

    def log_message(self, *args): pass
