"""
Tiny local server that:
  * serves /public/* static files
  * stubs every /api/* endpoint with fake data (no Supabase, no Gmail)
Used by the GUI smoke test and for manual eyeballing.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PUBLIC = os.path.join(ROOT, "web", "public")

STATE = {
    "authed": False,
    "next_id": 1,
    "campaigns": [],   # list of {id, customer_label, sender_name, status, ...}
    "sends": [],       # {campaign_id, company_id, status}
}

PASS = "test"
N_COMPANIES = 5


def _json(self, status, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)


class FakeAPI(BaseHTTPRequestHandler):
    # ---------- static ----------
    def _serve_static(self, path):
        if path == "/" or path == "":
            path = "/public/index.html"
        if not path.startswith("/public/"):
            self.send_response(404); self.end_headers(); return
        fp = os.path.join(PUBLIC, path[len("/public/"):])
        if not os.path.isfile(fp):
            self.send_response(404); self.end_headers(); return
        with open(fp, "rb") as f:
            data = f.read()
        ext = os.path.splitext(fp)[1]
        ct = {".html": "text/html; charset=utf-8",
              ".css": "text/css; charset=utf-8",
              ".js": "application/javascript; charset=utf-8"}.get(ext, "text/plain")
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---------- helpers ----------
    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n == 0: return {}
        raw = self.rfile.read(n)
        try: return json.loads(raw.decode("utf-8"))
        except Exception: return {}

    # ---------- request dispatch ----------
    def do_GET(self):
        p = self.path.split("?")[0]
        if not p.startswith("/api/"): return self._serve_static(p)
        if p == "/api/me":
            return _json(self, 200 if STATE["authed"] else 401,
                         {"authed": STATE["authed"]})
        if p == "/api/campaigns":
            if not STATE["authed"]: return _json(self, 401, {"error": "auth"})
            camps = []
            for c in STATE["campaigns"]:
                sends = [s for s in STATE["sends"] if s["campaign_id"] == c["id"]]
                counts = {"total": len(sends),
                          "sent": sum(1 for s in sends if s["status"] == "sent"),
                          "failed": sum(1 for s in sends if s["status"] == "failed"),
                          "pending": sum(1 for s in sends if s["status"] == "pending")}
                camps.append({**c, "counts": counts})
            return _json(self, 200, {"campaigns": camps})
        if p == "/api/stats":
            qs = self.path.split("?", 1)[-1]
            cid = int(dict(x.split("=") for x in qs.split("&")).get("campaign_id", "0"))
            sends = [s for s in STATE["sends"] if s["campaign_id"] == cid]
            counts = {"total": len(sends),
                      "sent": sum(1 for s in sends if s["status"] == "sent"),
                      "failed": sum(1 for s in sends if s["status"] == "failed"),
                      "pending": sum(1 for s in sends if s["status"] == "pending")}
            return _json(self, 200, {"counts": counts, "opens": []})
        return _json(self, 404, {"error": "not found"})

    def do_POST(self):
        p = self.path.split("?")[0]
        if p == "/api/login":
            b = self._body()
            if b.get("password") == PASS:
                STATE["authed"] = True
                return _json(self, 200, {"ok": True})
            return _json(self, 401, {"error": "wrong"})
        if p == "/api/upload":
            length = int(self.headers.get("Content-Length", 0) or 0)
            data = self.rfile.read(length)
            assert data.startswith(b"%PDF") or True
            return _json(self, 200, {"path": "fake_cv.pdf", "size": len(data)})
        if p == "/api/campaigns":
            if not STATE["authed"]: return _json(self, 401, {"error": "auth"})
            b = self._body()
            cid = STATE["next_id"]; STATE["next_id"] += 1
            camp = {"id": cid, "status": "draft", **b}
            STATE["campaigns"].append(camp)
            for i in range(N_COMPANIES):
                STATE["sends"].append({"campaign_id": cid, "company_id": i+1,
                                       "status": "pending"})
            return _json(self, 200, {"campaign": camp, "targeted": N_COMPANIES})
        return _json(self, 404, {"error": "not found"})

    def do_PATCH(self):
        p = self.path.split("?")[0]
        if p == "/api/campaigns":
            qs = self.path.split("?", 1)[-1]
            cid = int(dict(x.split("=") for x in qs.split("&")).get("id", "0"))
            b = self._body()
            for c in STATE["campaigns"]:
                if c["id"] == cid:
                    c["status"] = b.get("status", c["status"])
                    return _json(self, 200, {"ok": True, "status": c["status"]})
        return _json(self, 404, {"error": "not found"})

    def do_DELETE(self):
        if self.path.split("?")[0] == "/api/login":
            STATE["authed"] = False
            return _json(self, 200, {"ok": True})
        return _json(self, 404, {"error": "not found"})

    def log_message(self, *args): pass


def main(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), FakeAPI)
    print(f"serving on http://127.0.0.1:{srv.server_address[1]}/", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    main(port)
