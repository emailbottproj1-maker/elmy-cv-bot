"""
Campaign engine — orchestrates the whole send loop in a background thread.

It pulls pending recipients from the DB (resume-safe), renders the cover letter,
injects the tracking pixel, sends via Gmail, records the result, then waits a
randomized delay. It honours the daily cap and supports pause / stop. All UI
updates happen through a callback so the GUI stays decoupled.

Lifecycle:
    engine = CampaignEngine(...callbacks...)
    engine.start()      # spawns the worker thread
    engine.pause()      # finish current email, then idle
    engine.resume()
    engine.stop()       # graceful stop (finishes current email)
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .database import Database
from .email_sender import EmailSender
from .language_handler import LanguageHandler
from .rate_limiter import RateLimiter
from .tracker import Tracker

# Callback signatures (all optional, all called from the worker thread):
#   on_progress(stats: dict)            -> after each send/failure
#   on_log(level: str, message: str)    -> human-readable events
#   on_state(state: str)                -> "running"|"paused"|"stopped"|"cap"|"done"|"waiting"
#   on_countdown(seconds_left: int)     -> during inter-email wait (once/sec)
ProgressCb = Callable[[dict], None]
LogCb = Callable[[str, str], None]
StateCb = Callable[[str], None]
CountdownCb = Callable[[int], None]


@dataclass
class CampaignCallbacks:
    on_progress: Optional[ProgressCb] = None
    on_log: Optional[LogCb] = None
    on_state: Optional[StateCb] = None
    on_countdown: Optional[CountdownCb] = None


class CampaignEngine:
    def __init__(
        self,
        db: Database,
        sender: EmailSender,
        language: LanguageHandler,
        tracker: Tracker,
        limiter: RateLimiter,
        sender_name: str,
        callbacks: Optional[CampaignCallbacks] = None,
    ):
        self.db = db
        self.sender = sender
        self.language = language
        self.tracker = tracker
        self.limiter = limiter
        self.sender_name = sender_name
        self.cb = callbacks or CampaignCallbacks()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()  # set == paused
        self._running = False

    # ---------- callback helpers ----------
    def _log(self, level: str, msg: str) -> None:
        if self.cb.on_log:
            self.cb.on_log(level, msg)

    def _state(self, state: str) -> None:
        if self.cb.on_state:
            self.cb.on_state(state)

    def _progress(self) -> None:
        if self.cb.on_progress:
            self.cb.on_progress(self.db.counts())

    # ---------- public controls ----------
    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(target=self._run, name="campaign", daemon=True)
        self._running = True
        self._thread.start()

    def pause(self) -> None:
        self._pause_event.set()
        self._state("paused")
        self._log("info", "تم الإيقاف المؤقت — سيتوقف بعد الإيميل الحالي.")

    def resume(self) -> None:
        self._pause_event.clear()
        self._state("running")
        self._log("info", "تم الاستئناف.")

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()  # unblock any pause wait
        self._log("info", "جاري الإيقاف...")

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    # ---------- interruptible sleep ----------
    def _sleep_with_countdown(self, seconds: float) -> None:
        """Sleep in 1s steps so stop/pause are responsive; emits countdown."""
        whole = int(seconds)
        for remaining in range(whole, 0, -1):
            if self._stop_event.is_set():
                return
            if self.cb.on_countdown:
                self.cb.on_countdown(remaining)
            time.sleep(1)
        # leftover fractional second
        frac = seconds - whole
        if frac > 0 and not self._stop_event.is_set():
            time.sleep(frac)

    def _wait_if_paused(self) -> None:
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.5)

    # ---------- main loop ----------
    def _run(self) -> None:
        self._state("running")
        self._log("info", "بدأت الحملة.")
        try:
            # Connect once up front so auth errors surface immediately.
            self.sender.connect()
            self._log("info", "تم الاتصال بـ Gmail بنجاح.")
        except Exception as exc:
            self._log("error", f"فشل الاتصال بـ Gmail: {exc}")
            self._state("stopped")
            self._running = False
            return

        consecutive_failures = 0

        try:
            while not self._stop_event.is_set():
                self._wait_if_paused()
                if self._stop_event.is_set():
                    break

                # daily cap check
                sent_today = self.db.sent_today()
                if self.limiter.cap_reached(sent_today):
                    self._log(
                        "info",
                        f"تم الوصول للحد اليومي ({self.limiter.daily_cap}). "
                        f"أوقف البرنامج وأعد تشغيله غدًا للمتابعة.",
                    )
                    self._state("cap")
                    break

                recipient = self.db.next_pending()
                if recipient is None:
                    self._log("info", "تم إرسال كل الإيميلات. اكتملت الحملة! 🎉")
                    self._state("done")
                    break

                rid = recipient["id"]
                company = recipient["company_name"]

                # render + pixel
                try:
                    body, is_rtl = self.language.render(recipient, self.sender_name)
                    tracking_uuid = self.db.assign_uuid(rid)
                    pixel = self.tracker.pixel_html(tracking_uuid)
                except Exception as exc:
                    self.db.mark_failed(rid, f"render error: {exc}")
                    self._log("error", f"{company}: خطأ في تجهيز الرسالة — {exc}")
                    self._progress()
                    continue

                # send
                try:
                    self.sender.send(recipient, body, is_rtl, pixel)
                    self.db.mark_sent(rid)
                    consecutive_failures = 0
                    sent_today += 1
                    remaining = self.limiter.remaining_today(sent_today)
                    self._log(
                        "success",
                        f"✓ أُرسل إلى {company} <{recipient['email']}> "
                        f"(اليوم: {sent_today}/{self.limiter.daily_cap})",
                    )
                    self._progress()
                except Exception as exc:
                    consecutive_failures += 1
                    self.db.mark_failed(rid, str(exc))
                    self._log("error", f"✗ فشل الإرسال إلى {company}: {exc}")
                    self._progress()

                    # too many failures in a row => backoff then stop if persists
                    if consecutive_failures >= 3:
                        delay = self.limiter.backoff_delay(consecutive_failures - 2)
                        self._log(
                            "warn",
                            f"عدة حالات فشل متتالية. انتظار {int(delay/60)} دقيقة قبل المحاولة.",
                        )
                        self._state("waiting")
                        self._sleep_with_countdown(delay)
                        if consecutive_failures >= 6:
                            self._log("error", "فشل مستمر — تم إيقاف الحملة. تحقق من الاتصال/الحساب.")
                            self._state("stopped")
                            break
                        self._state("running")
                    continue

                # check again whether more remain / cap hit before sleeping
                if self.db.next_pending() is None:
                    self._log("info", "تم إرسال كل الإيميلات. اكتملت الحملة! 🎉")
                    self._state("done")
                    break
                if self.limiter.cap_reached(self.db.sent_today()):
                    self._log("info", f"تم الوصول للحد اليومي ({self.limiter.daily_cap}).")
                    self._state("cap")
                    break

                # randomized inter-email delay
                delay = self.limiter.next_delay()
                self._state("waiting")
                self._log("info", f"الإيميل التالي بعد {int(delay)} ثانية...")
                self._sleep_with_countdown(delay)
                if not self._stop_event.is_set():
                    self._state("running")

        finally:
            self.sender.close()
            self._running = False
            if self._stop_event.is_set():
                self._state("stopped")
                self._log("info", "تم إيقاف الحملة.")
