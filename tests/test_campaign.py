"""
Integration test for the campaign engine using a MOCK sender (no real SMTP).

Verifies:
  * daily cap stops the loop
  * sends are recorded, resume works (restart continues from pending)
  * tracking uuids are assigned and pixel injected
  * stop() is responsive
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.campaign import CampaignEngine, CampaignCallbacks
from bot.database import Database
from bot.language_handler import LanguageHandler
from bot.rate_limiter import RateLimiter
from bot.tracker import Tracker


class MockSender:
    """Stand-in for EmailSender: records sends, never touches the network."""

    def __init__(self, fail_emails=None):
        self.sent = []
        self.fail_emails = set(fail_emails or [])
        self.connected = False

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def send(self, recipient, body, is_rtl, pixel_html=""):
        if recipient["email"] in self.fail_emails:
            raise RuntimeError("simulated SMTP failure")
        assert "{company_name}" not in body, "placeholder not rendered!"
        # pixel should be present (tracker enabled in test)
        assert pixel_html.startswith("<img"), "pixel not injected!"
        self.sent.append(recipient["email"])


def make_db(path, n):
    if os.path.exists(path):
        os.remove(path)
    db = Database(path)
    recips = [
        {"company_name": f"Co{i}", "email": f"co{i}@example.com",
         "language": "ar" if i % 2 else "en"}
        for i in range(n)
    ]
    db.import_recipients(recips, "test.xlsx")
    return db


def build_engine(db, sender, daily_cap):
    lang = LanguageHandler("data/cover_letter_ar.txt", "data/cover_letter_en.txt")
    tracker = Tracker("https://example.com", "tok")  # enabled -> injects pixel
    limiter = RateLimiter(0, 0, daily_cap)  # zero delay for fast test
    logs = []
    cb = CampaignCallbacks(on_log=lambda lvl, m: logs.append((lvl, m)))
    eng = CampaignEngine(db, sender, lang, tracker, limiter, "Youssef", cb)
    return eng, logs


def run_until_idle(engine, timeout=10):
    engine.start()
    t0 = time.time()
    while engine.is_running and time.time() - t0 < timeout:
        time.sleep(0.05)
    engine.join(2)


def test_daily_cap():
    db = make_db("data/_camp1.db", 20)
    sender = MockSender()
    engine, logs = build_engine(db, sender, daily_cap=5)
    run_until_idle(engine)
    counts = db.counts()
    assert len(sender.sent) == 5, f"expected 5 sends, got {len(sender.sent)}"
    assert counts["sent"] == 5
    assert counts["pending"] == 15
    db.close()
    os.remove("data/_camp1.db")
    print("  [PASS] daily cap stops at 5, 15 still pending")


def test_resume():
    # First run caps at 5; simulate "next day" by raising cap and rerunning.
    path = "data/_camp2.db"
    db = make_db(path, 10)
    s1 = MockSender()
    e1, _ = build_engine(db, s1, daily_cap=5)
    run_until_idle(e1)
    assert db.counts()["sent"] == 5
    db.close()

    # Reopen DB (fresh process simulation) and run the rest.
    db2 = Database(path)
    s2 = MockSender()
    e2, _ = build_engine(db2, s2, daily_cap=100)
    run_until_idle(e2)
    c = db2.counts()
    # NOTE: sent_today counts BOTH runs (same UTC day), so cap=100 lets rest go.
    assert c["sent"] == 10, f"expected all 10 sent after resume, got {c['sent']}"
    assert c["pending"] == 0
    # s2 only sent the remaining 5 (resume didn't resend the first 5)
    assert len(s2.sent) == 5, f"resume resent emails! sent {len(s2.sent)}"
    db2.close()
    os.remove(path)
    print("  [PASS] resume continues from pending, no resends")


def test_failure_recorded():
    db = make_db("data/_camp3.db", 4)
    fail = "co1@example.com"
    sender = MockSender(fail_emails=[fail])
    engine, logs = build_engine(db, sender, daily_cap=100)
    run_until_idle(engine)
    c = db.counts()
    assert c["failed"] == 1, f"expected 1 failed, got {c['failed']}"
    assert c["sent"] == 3
    db.close()
    os.remove("data/_camp3.db")
    print("  [PASS] failed send recorded, others still sent")


def test_stop_responsive():
    db = make_db("data/_camp4.db", 50)
    sender = MockSender()
    # use a real delay so we can stop mid-wait
    lang = LanguageHandler("data/cover_letter_ar.txt", "data/cover_letter_en.txt")
    tracker = Tracker("https://example.com", "tok")
    limiter = RateLimiter(5, 5, 100)  # 5s between emails
    eng = CampaignEngine(db, sender, lang, tracker, limiter, "Y")
    eng.start()
    time.sleep(1)  # let it send the first one and enter the wait
    eng.stop()
    t0 = time.time()
    eng.join(4)
    elapsed = time.time() - t0
    assert not eng.is_running, "engine did not stop"
    assert elapsed < 3, f"stop took too long: {elapsed:.1f}s"
    assert len(sender.sent) >= 1
    db.close()
    os.remove("data/_camp4.db")
    print(f"  [PASS] stop responsive ({elapsed:.1f}s), sent {len(sender.sent)} before stop")


if __name__ == "__main__":
    print("Running campaign integration tests...")
    test_daily_cap()
    test_resume()
    test_failure_recorded()
    test_stop_responsive()
    print("\nALL CAMPAIGN TESTS PASSED ✅")
