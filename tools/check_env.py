"""
Pre-deployment environment checker.

Run BEFORE pushing to production to catch missing/bad config quickly.
Tests each required environment variable + does a live ping to each service.

Usage:
    export SUPABASE_URL=... SUPABASE_SERVICE_KEY=... GMAIL_ADDRESS=...
    python tools/check_env.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

REQUIRED = [
    ("SUPABASE_URL", "Supabase project URL"),
    ("SUPABASE_SERVICE_KEY", "Supabase service_role key (server-only!)"),
    ("SITE_PASSWORD", "site login password (Mm123456@@)"),
    ("GMAIL_ADDRESS", "sender Gmail address (mddx90@gmail.com)"),
    ("GMAIL_APP_PASSWORD", "Gmail 16-char App Password"),
    ("GEMINI_API_KEY", "Google AI Studio key (free tier)"),
    ("CRON_TOKEN", "shared secret protecting /api/tick"),
]
OPTIONAL = [
    ("PIXEL_BASE_URL", "tracking-pixel host (defaults to Vercel URL)"),
    ("PIXEL_TOKEN", "stats endpoint token (only if separate pixel service)"),
]


def red(s): return f"\033[31m{s}\033[0m"
def grn(s): return f"\033[32m{s}\033[0m"
def ylw(s): return f"\033[33m{s}\033[0m"


def check_env() -> list[str]:
    problems = []
    print("=== Environment variables ===")
    for key, desc in REQUIRED:
        v = os.environ.get(key, "").strip()
        if v:
            shown = v if len(v) <= 8 else (v[:4] + "..." + v[-4:])
            print(f"  [{grn('OK')}] {key:<22} {shown}")
        else:
            problems.append(f"{key} missing  ({desc})")
            print(f"  [{red('--')}] {key:<22} MISSING  ({desc})")
    for key, desc in OPTIONAL:
        v = os.environ.get(key, "").strip()
        mark = grn("ok") if v else ylw("--")
        print(f"  [{mark}] {key:<22} {'set' if v else 'unset'}  ({desc})")
    return problems


def check_supabase() -> list[str]:
    problems = []
    print("\n=== Supabase connectivity ===")
    try:
        from bot.supabase_db import SupabaseDB
        db = SupabaseDB()
        # cheap call: select 1 row from companies
        rows = db._select("/companies?select=id&limit=1")
        print(f"  [{grn('OK')}] connected; companies table has at least "
              f"{len(rows)} sample row.")
        # check sectors view & opens view exist
        try:
            db._select("/email_opens_agg?select=email_uuid&limit=1")
            print(f"  [{grn('OK')}] email_opens_agg view present.")
        except Exception as exc:
            problems.append(f"email_opens_agg view missing: {exc}")
            print(f"  [{red('--')}] email_opens_agg view: {exc}")
    except Exception as exc:
        problems.append(f"Supabase connect failed: {exc}")
        print(f"  [{red('--')}] connect failed: {exc}")
    return problems


def check_gmail() -> list[str]:
    problems = []
    print("\n=== Gmail SMTP (App Password) ===")
    gmail = os.environ.get("GMAIL_ADDRESS", "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not gmail or not pw:
        print(f"  [{ylw('--')}] skipping (missing env)")
        return problems
    try:
        from bot.email_sender import EmailSender, EmailConfigError
        # use a tiny temp 'cv' so the sender can construct cleanly
        import tempfile
        with tempfile.NamedTemporaryFile(prefix="cv_", suffix=".pdf",
                                         delete=False) as f:
            f.write(b"%PDF-1.4 test"); cv_path = f.name
        try:
            sender = EmailSender(gmail, pw, "Test", cv_path)
            sender.verify_login()
            print(f"  [{grn('OK')}] Gmail login succeeded.")
        except EmailConfigError as exc:
            problems.append(f"Gmail login: {exc}")
            print(f"  [{red('--')}] {exc}")
        finally:
            os.unlink(cv_path)
    except Exception as exc:
        problems.append(f"Gmail check error: {exc}")
        print(f"  [{red('--')}] {exc}")
    return problems


def check_gemini() -> list[str]:
    problems = []
    print("\n=== Gemini API key ===")
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print(f"  [{ylw('--')}] skipping (missing env)")
        return problems
    try:
        from bot.language_handler import LanguageHandler
        from bot.ai_writer import AIWriter
        lh = LanguageHandler("data/cover_letter_ar.txt",
                             "data/cover_letter_en.txt")
        w = AIWriter(lh, api_key=key, enabled=True)
        body, _rtl, source = w.generate(
            {"company_name": "Test Co", "language": "en", "sector": "Tech"},
            "Tester")
        if source == "ai":
            print(f"  [{grn('OK')}] Gemini responded (len={len(body)}).")
        else:
            problems.append("Gemini fell back to template — check key/quota.")
            print(f"  [{red('--')}] Gemini did NOT generate — fell back to template.")
    except Exception as exc:
        problems.append(f"Gemini error: {exc}")
        print(f"  [{red('--')}] {exc}")
    return problems


def main():
    p = []
    p += check_env()
    if not any(x.startswith("SUPABASE_") for x in p):
        p += check_supabase()
    p += check_gmail()
    p += check_gemini()
    print()
    if p:
        print(red(f"FAIL: {len(p)} issue(s):"))
        for i in p:
            print(f"  - {i}")
        sys.exit(1)
    print(grn("ALL CHECKS PASSED — safe to deploy."))


if __name__ == "__main__":
    main()
