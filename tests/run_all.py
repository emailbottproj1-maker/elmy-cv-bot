"""
Master test runner — runs every module self-test + integration tests.
Exit code 0 = all green. Use this before any delivery.
"""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PY = sys.executable

ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")

STEPS = [
    # ---- desktop-edition modules (kept for reuse + archive) ----
    ("config save/load", ["bot/config.py"]),
    ("excel reader", ["bot/excel_reader.py", "data/companies_sample.xlsx"]),
    ("database (SQLite)", ["bot/database.py"]),
    ("language handler", ["bot/language_handler.py"]),
    ("tracker", ["bot/tracker.py"]),
    ("email build", ["bot/email_sender.py"]),
    ("rate limiter", ["bot/rate_limiter.py"]),
    ("campaign engine (desktop)", ["tests/test_campaign.py"]),
    ("pixel service (local http)", ["tests/test_pixel_local.py"]),
    ("gui smoke (Tkinter)", ["tests/test_gui_smoke.py"]),
    # ---- web edition ----
    ("ai_writer fallback", ["-m", "bot.ai_writer"]),
    ("supabase_db env guard", ["-m", "bot.supabase_db"]),
    ("web engine E2E (global cap, FIFO, AI fallback)", ["tests/test_web_engine.py"]),
    ("package selection (non-overlap + recycle)", ["tests/test_package_selection.py"]),
    ("Vercel API handlers import", ["tests/test_api_imports.py"]),
    ("sector alias map (AR/EN normalisation)", ["-m", "bot.sector_aliases"]),
]


def main():
    # ensure sample excel exists
    subprocess.run([PY, "tests/make_sample_excel.py"], cwd=ROOT, env=ENV,
                   capture_output=True)
    passed, failed = 0, 0
    print("=" * 60)
    for name, args in STEPS:
        proc = subprocess.run([PY] + args, cwd=ROOT, env=ENV,
                              capture_output=True, text=True, encoding="utf-8")
        ok = proc.returncode == 0
        status = "PASS ✅" if ok else "FAIL ❌"
        print(f"[{status}] {name}")
        if not ok:
            failed += 1
            print("  --- stdout ---")
            print("  " + (proc.stdout or "").replace("\n", "\n  "))
            print("  --- stderr ---")
            print("  " + (proc.stderr or "").replace("\n", "\n  "))
        else:
            passed += 1
    print("=" * 60)
    print(f"RESULT: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
