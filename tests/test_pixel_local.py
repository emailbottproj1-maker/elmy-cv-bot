"""
Run the Vercel pixel + stats handlers in a local HTTP server and hit them with
real requests. Verifies:
  * /api/pixel returns a valid 1x1 GIF with no-cache headers
  * /api/stats rejects bad token (403) and accepts good token (200)
Supabase calls are skipped (no env set) -> _record_open / _fetch return early.
"""
import importlib.util
import os
import sys
import threading
from http.server import HTTPServer

import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load(modpath, name):
    spec = importlib.util.spec_from_file_location(name, modpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pixel_mod = load(os.path.join(ROOT, "vercel-pixel", "api", "pixel.py"), "pixel_mod")
stats_mod = load(os.path.join(ROOT, "vercel-pixel", "api", "stats.py"), "stats_mod")


def serve(handler_cls):
    srv = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


def test_pixel():
    srv, port = serve(pixel_mod.handler)
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/pixel?id=test-uuid-123", timeout=5)
        assert r.status_code == 200, r.status_code
        assert r.headers["Content-Type"] == "image/gif"
        assert r.content[:6] == b"GIF89a", "not a valid GIF"
        assert len(r.content) == 43, f"pixel size {len(r.content)}"
        assert "no-store" in r.headers.get("Cache-Control", "")
        print(f"  [PASS] pixel: valid {len(r.content)}-byte GIF, no-cache headers OK")
    finally:
        srv.shutdown()


def test_stats():
    os.environ["STATS_TOKEN"] = "secret123"
    srv, port = serve(stats_mod.handler)
    try:
        bad = requests.get(f"http://127.0.0.1:{port}/api/stats?token=wrong", timeout=5)
        assert bad.status_code == 403, f"expected 403, got {bad.status_code}"

        good = requests.get(f"http://127.0.0.1:{port}/api/stats?token=secret123", timeout=5)
        assert good.status_code == 200, good.status_code
        body = good.json()
        assert "opens" in body and isinstance(body["opens"], list)
        print("  [PASS] stats: rejects bad token (403), accepts good token (200, JSON)")
    finally:
        srv.shutdown()
        del os.environ["STATS_TOKEN"]


if __name__ == "__main__":
    print("Testing Vercel pixel service locally...")
    test_pixel()
    test_stats()
    print("\nPIXEL SERVICE TESTS PASSED ✅")
