"""
Verify every Vercel handler in web/api/ imports cleanly.

We import each as if Vercel were loading it: sys.path = api dir + project root,
env vars set to dummy values so any module-level code that touches them works.
"""
import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
API_DIR = os.path.join(ROOT, "web", "api")

# Dummy env so SupabaseDB instantiation doesn't crash at import (it only
# instantiates inside handler methods anyway, but be safe).
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "dummy-key")
os.environ.setdefault("SITE_PASSWORD", "test")
os.environ.setdefault("CRON_TOKEN", "test")
os.environ.setdefault("STATS_TOKEN", "test")

# Mimic Vercel: api dir on sys.path so `from _helpers import ...` works.
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def load(name: str):
    path = os.path.join(API_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"api_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    names = ["login", "me", "campaigns", "companies", "sectors", "upload",
             "stats", "tick", "pixel"]
    failures = []
    for n in names:
        try:
            mod = load(n)
            assert hasattr(mod, "handler"), f"{n}: no handler class"
            print(f"  [PASS] api/{n}.py imports + exposes handler")
        except Exception as exc:
            failures.append((n, exc))
            print(f"  [FAIL] api/{n}.py: {exc}")
    if failures:
        raise SystemExit(f"{len(failures)} handler(s) failed to import")
    print("\nALL API HANDLERS IMPORT CLEANLY ✅")


if __name__ == "__main__":
    main()
