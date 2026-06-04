"""
End-to-end tests for web_engine.run_tick using a FakeSupabaseDB and patched
EmailSender. No network. Verifies:

  * idle when nothing pending
  * daily cap is GLOBAL (sum across campaigns)
  * spacing gate respects min_delay
  * FIFO across active campaigns (oldest pending wins)
  * paused campaigns are skipped
  * AI fallback when no API key
  * full-list targeting (every company gets a send row per campaign)
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot import email_sender as es_module
from bot import web_engine


# ---------- Fakes ----------
class FakeSender:
    instances: list["FakeSender"] = []

    def __init__(self, gmail_address, app_password, sender_name, cv_path,
                 subject_ar="", subject_en=""):
        self.gmail_address = gmail_address
        self.sender_name = sender_name
        self.cv_path = cv_path
        # CV file must actually exist for parity with real code
        assert os.path.exists(cv_path), f"CV missing: {cv_path}"
        self.sent = []
        FakeSender.instances.append(self)

    def connect(self): pass
    def close(self): pass
    def send(self, recipient, body, is_rtl, pixel_html=""):
        assert "{company_name}" not in body
        assert pixel_html.startswith("<img")
        self.sent.append((recipient["email"], recipient["language"], body[:60]))


class FakeDB:
    """Minimal in-memory fake matching the SupabaseDB surface used by web_engine."""
    def __init__(self, companies, campaigns):
        self.companies = {c["id"]: c for c in companies}
        self.campaigns = {c["id"]: c for c in campaigns}
        self.sends: list[dict] = []
        self._next_send_id = 1
        self.config = {
            "daily_cap": 50,
            "min_delay_sec": 0,
            "max_delay_sec": 0,
            "last_global_send_at": None,
            "sent_today": {"date": _today(), "count": 0},
        }
        # full-list targeting: one send per (campaign, company)
        for camp in campaigns:
            for comp in companies:
                self.sends.append({
                    "id": self._next_send_id,
                    "campaign_id": camp["id"],
                    "company_id": comp["id"],
                    "status": "pending",
                    "tracking_uuid": None,
                    "generated_body": None,
                    "sent_at": None,
                    "error": None,
                    "attempts": 0,
                })
                self._next_send_id += 1
        self.cv_blob = b"%PDF-1.4 fake cv"

    def get_global_state(self):
        st = dict(self.config)
        s = st.get("sent_today") or {}
        if s.get("date") != _today():
            s = {"date": _today(), "count": 0}
            self.config["sent_today"] = s
            st["sent_today"] = s
        return st

    def next_pending_send(self):
        active_ids = {c["id"] for c in self.campaigns.values() if c["status"] == "active"}
        if not active_ids:
            return None
        for s in self.sends:
            if s["status"] == "pending" and s["campaign_id"] in active_ids:
                comp = self.companies[s["company_id"]]
                camp = self.campaigns[s["campaign_id"]]
                return {
                    "id": s["id"], "campaign_id": s["campaign_id"],
                    "company_id": s["company_id"], "attempts": s["attempts"],
                    "company": comp, "campaign": camp,
                }
        return None

    def assign_uuid(self, send_id):
        import uuid
        for s in self.sends:
            if s["id"] == send_id:
                s["tracking_uuid"] = uuid.uuid4().hex
                return s["tracking_uuid"]
        raise KeyError(send_id)

    def mark_sent(self, send_id, body):
        for s in self.sends:
            if s["id"] == send_id:
                s["status"] = "sent"
                s["generated_body"] = body
                s["sent_at"] = _now_iso()

    def mark_failed(self, send_id, error, body=""):
        for s in self.sends:
            if s["id"] == send_id:
                s["status"] = "failed"
                s["error"] = error
                if body:
                    s["generated_body"] = body

    def bump_sent_today(self):
        st = self.config.get("sent_today") or {"date": _today(), "count": 0}
        st["count"] = int(st.get("count", 0)) + 1
        self.config["sent_today"] = st
        self.config["last_global_send_at"] = _now_iso()

    def set_config(self, key, value):
        self.config[key] = value

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def download_cv(self, path):
        return self.cv_blob


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------- fixtures ----------
def make_setup(n_companies=3, campaigns=None):
    if campaigns is None:
        campaigns = [{
            "id": 1, "customer_label": "client A", "cv_storage_path": "a.pdf",
            "sender_name": "Ahmad", "subject_ar": "طلب توظيف",
            "subject_en": "Job Application",
            "cover_letter_ar": "السلام {company_name}،\n\n{sender_name}",
            "cover_letter_en": "Dear {company_name},\n\n{sender_name}",
            "use_ai": False, "status": "active",
        }]
    companies = [{
        "id": i + 1, "company_name": f"Co{i + 1}",
        "email": f"co{i + 1}@x.com",
        "language": "en" if i % 2 == 0 else "ar",
        "sector": "Tech", "city": "Riyadh",
    } for i in range(n_companies)]
    return FakeDB(companies, campaigns)


def run_one_tick(db, **overrides):
    kwargs = dict(
        gmail_address="t@gmail.com",
        app_password="x" * 16,
        pixel_base_url="https://pixel.test",
        pixel_token="tok",
        gemini_api_key="",  # disabled → template
    )
    kwargs.update(overrides)
    return web_engine.run_tick(db, **kwargs)


def patch_sender():
    FakeSender.instances.clear()
    es_module.EmailSender_original = getattr(
        web_engine, "EmailSender", es_module.EmailSender)
    web_engine.EmailSender = FakeSender


def unpatch_sender():
    if hasattr(es_module, "EmailSender_original"):
        web_engine.EmailSender = es_module.EmailSender_original


# ---------- tests ----------
def test_full_list_targeting():
    db = make_setup(n_companies=5)
    # one campaign × 5 companies → 5 send rows
    assert len(db.sends) == 5
    assert all(s["status"] == "pending" for s in db.sends)
    print("  [PASS] full-list: 1 campaign × 5 companies = 5 send rows")


def test_idle_when_no_active():
    db = make_setup(n_companies=3, campaigns=[{
        "id": 1, "customer_label": "x", "cv_storage_path": "x.pdf",
        "sender_name": "S", "subject_ar": "", "subject_en": "",
        "cover_letter_ar": "Hi {company_name},\n{sender_name}",
        "cover_letter_en": "Hi {company_name},\n{sender_name}",
        "use_ai": False, "status": "paused",  # not active
    }])
    patch_sender()
    try:
        r = run_one_tick(db)
        assert r.action == "idle", r
        assert FakeSender.instances == []
    finally:
        unpatch_sender()
    print("  [PASS] idle when no active campaign")


def test_one_tick_one_email():
    db = make_setup(n_companies=3)
    patch_sender()
    try:
        r = run_one_tick(db)
        assert r.action == "sent", r
        assert r.sent_today == 1
        sent = sum(s["status"] == "sent" for s in db.sends)
        assert sent == 1
        # second tick sends the next one
        r2 = run_one_tick(db)
        assert r2.action == "sent"
        assert sum(s["status"] == "sent" for s in db.sends) == 2
    finally:
        unpatch_sender()
    print("  [PASS] each tick sends exactly one email and advances queue")


def test_global_daily_cap():
    db = make_setup(n_companies=10)
    db.config["daily_cap"] = 3
    patch_sender()
    try:
        for _ in range(5):
            run_one_tick(db)
        sent = sum(s["status"] == "sent" for s in db.sends)
        assert sent == 3, f"expected 3 (cap), got {sent}"
        r = run_one_tick(db)
        assert r.action == "skipped" and "cap" in r.reason
    finally:
        unpatch_sender()
    print("  [PASS] global daily cap stops the loop at 3")


def test_cap_is_GLOBAL_across_campaigns():
    """The critical correctness test: 3 campaigns share one daily_cap."""
    campaigns = [
        {"id": i, "customer_label": f"c{i}", "cv_storage_path": "x.pdf",
         "sender_name": f"S{i}", "subject_ar": "", "subject_en": "",
         "cover_letter_ar": "Hi {company_name},\n{sender_name}",
         "cover_letter_en": "Hi {company_name},\n{sender_name}",
         "use_ai": False, "status": "active"}
        for i in (1, 2, 3)
    ]
    # 3 campaigns × 10 companies = 30 pending
    companies = [{"id": i, "company_name": f"Co{i}", "email": f"co{i}@x.com",
                  "language": "en"} for i in range(1, 11)]
    db = FakeDB(companies, campaigns)
    db.config["daily_cap"] = 5
    patch_sender()
    try:
        for _ in range(20):
            run_one_tick(db)
        sent_global = sum(s["status"] == "sent" for s in db.sends)
        assert sent_global == 5, (
            f"GLOBAL cap broken: 3 campaigns sent {sent_global} (must be 5)"
        )
    finally:
        unpatch_sender()
    print("  [PASS] daily cap is GLOBAL: 3 campaigns × cap 5 = 5 total (not 15)")


def test_spacing_gate():
    db = make_setup(n_companies=5)
    db.config["min_delay_sec"] = 999  # impossible delay
    db.config["max_delay_sec"] = 999
    db.config["last_global_send_at"] = _now_iso()  # just sent
    patch_sender()
    try:
        r = run_one_tick(db)
        assert r.action == "skipped" and "spacing" in r.reason, r
        # rewind last_send by 20 minutes → spacing satisfied
        past = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        db.config["last_global_send_at"] = past
        r = run_one_tick(db)
        assert r.action == "sent", r
    finally:
        unpatch_sender()
    print("  [PASS] spacing gate enforces min_delay since last send")


def test_ai_fallback_template():
    db = make_setup(n_companies=2)
    patch_sender()
    try:
        r = run_one_tick(db, gemini_api_key="")  # no key -> template
        assert r.action == "sent"
        assert r.source == "template", f"expected template, got {r.source}"
    finally:
        unpatch_sender()
    print("  [PASS] AI fallback to template when no API key")


def test_round_robin_across_campaigns():
    campaigns = [
        {"id": 1, "customer_label": "A", "cv_storage_path": "x.pdf",
         "sender_name": "A", "subject_ar": "", "subject_en": "",
         "cover_letter_ar": "Hi {company_name},\n{sender_name}",
         "cover_letter_en": "Hi {company_name},\n{sender_name}",
         "use_ai": False, "status": "active"},
        {"id": 2, "customer_label": "B", "cv_storage_path": "x.pdf",
         "sender_name": "B", "subject_ar": "", "subject_en": "",
         "cover_letter_ar": "Hi {company_name},\n{sender_name}",
         "cover_letter_en": "Hi {company_name},\n{sender_name}",
         "use_ai": False, "status": "active"},
    ]
    companies = [{"id": 1, "company_name": "Co1", "email": "c1@x.com",
                  "language": "en"}]
    db = FakeDB(companies, campaigns)
    patch_sender()
    try:
        run_one_tick(db); run_one_tick(db)
        sent_c1 = sum(1 for s in db.sends if s["campaign_id"] == 1 and s["status"] == "sent")
        sent_c2 = sum(1 for s in db.sends if s["campaign_id"] == 2 and s["status"] == "sent")
        # FIFO by send id: campaign 1's row was inserted first, then campaign 2's
        assert sent_c1 == 1 and sent_c2 == 1, (sent_c1, sent_c2)
    finally:
        unpatch_sender()
    print("  [PASS] FIFO across active campaigns (both progress fairly)")


if __name__ == "__main__":
    print("Running web engine integration tests...")
    test_full_list_targeting()
    test_idle_when_no_active()
    test_one_tick_one_email()
    test_global_daily_cap()
    test_cap_is_GLOBAL_across_campaigns()
    test_spacing_gate()
    test_ai_fallback_template()
    test_round_robin_across_campaigns()
    print("\nALL WEB ENGINE TESTS PASSED ✅")
