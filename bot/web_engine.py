"""
Web-edition campaign engine — invoked once per /tick HTTP request.

Unlike the desktop campaign loop, this is STATELESS: one invocation processes
*at most one* email and returns. The cron service (cron-job.org) hits /tick
every minute so the global pacing happens at the cron cadence, with random
jitter added on top of the configured min/max delay.

This module is the orchestrator that wires together:
  SupabaseDB  – state, queue, global counters
  AIWriter    – generates body (with template fallback)
  EmailSender – builds + sends Gmail MIME
  Tracker     – pixel URL injection

It deliberately does NO threading and NO sleeping. The HTTP layer just calls
`run_tick(...)` and returns whatever the result says.
"""
from __future__ import annotations

import os
import random
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .ai_writer import AIWriter
from .email_sender import EmailConfigError, EmailSender
from .language_handler import LanguageHandler
from .supabase_db import SupabaseDB
from .tracker import Tracker


@dataclass
class TickResult:
    action: str          # "sent" | "failed" | "skipped" | "idle" | "config_error"
    reason: str = ""
    campaign_id: int | None = None
    company: str = ""
    source: str = ""     # "ai" | "template" | ""
    sent_today: int = 0
    daily_cap: int = 0


def _coerce_int(value: Any, default: int) -> int:
    """Convert config value to int, preserving 0 (which `x or default` would lose)."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _iso_to_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # Supabase returns timezone-aware isoformat strings
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _spacing_ok(last_iso: str | None, min_delay: int, max_delay: int) -> bool:
    """Random spacing gate: must have waited at least a sampled delay."""
    if not last_iso:
        return True
    last = _iso_to_dt(last_iso)
    if last is None:
        return True
    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    sample = random.uniform(min_delay, max_delay)
    return elapsed >= sample


def run_tick(
    db: SupabaseDB,
    *,
    gmail_address: str,
    app_password: str,
    pixel_base_url: str = "",
    pixel_token: str = "",
    gemini_api_key: str = "",
    cover_letter_ar_default: str = "",
    cover_letter_en_default: str = "",
) -> TickResult:
    """Process one tick. Always returns a TickResult; never raises."""
    # ---------- global gate ----------
    state = db.get_global_state()
    cap = _coerce_int(state.get("daily_cap"), 50)
    min_d = _coerce_int(state.get("min_delay_sec"), 60)
    max_d = _coerce_int(state.get("max_delay_sec"), 180)
    sent_today = _coerce_int((state.get("sent_today") or {}).get("count"), 0)

    if sent_today >= cap:
        return TickResult("skipped", reason="daily cap reached",
                          sent_today=sent_today, daily_cap=cap)
    if not _spacing_ok(state.get("last_global_send_at"), min_d, max_d):
        return TickResult("skipped", reason="spacing not elapsed yet",
                          sent_today=sent_today, daily_cap=cap)

    # ---------- pick work ----------
    job = db.next_pending_send()
    if not job:
        return TickResult("idle", reason="no pending across active campaigns",
                          sent_today=sent_today, daily_cap=cap)

    send_id = job["id"]
    company = job["company"]
    campaign = job["campaign"]
    cname = company["company_name"]

    # ---------- prepare CV (download from Storage to temp file) ----------
    try:
        cv_bytes = db.download_cv(campaign["cv_storage_path"])
        tmp = tempfile.NamedTemporaryFile(prefix="cv_", suffix=".pdf",
                                          delete=False)
        tmp.write(cv_bytes)
        tmp.close()
        cv_path = tmp.name
    except Exception as exc:
        db.mark_failed(send_id, f"cv download failed: {exc}")
        return TickResult("failed", reason=str(exc),
                          campaign_id=campaign["id"], company=cname,
                          sent_today=sent_today, daily_cap=cap)

    # ---------- build dynamic LanguageHandler from the campaign's templates ----------
    # We write the campaign templates to temp files because LanguageHandler reads paths.
    ar_path = _write_temp(campaign.get("cover_letter_ar") or cover_letter_ar_default
                          or "Hello {company_name},\n\n{sender_name}")
    en_path = _write_temp(campaign.get("cover_letter_en") or cover_letter_en_default
                          or "Hello {company_name},\n\n{sender_name}")
    try:
        lh = LanguageHandler(ar_path, en_path)
    except Exception as exc:
        db.mark_failed(send_id, f"template load failed: {exc}")
        _cleanup(cv_path, ar_path, en_path)
        return TickResult("failed", reason=str(exc),
                          campaign_id=campaign["id"], company=cname,
                          sent_today=sent_today, daily_cap=cap)

    # ---------- AI or template body ----------
    writer = AIWriter(lh, api_key=gemini_api_key,
                      enabled=bool(campaign.get("use_ai", True)))
    body, is_rtl, source = writer.generate(company, campaign["sender_name"])

    # ---------- pixel ----------
    tracker = Tracker(pixel_base_url, pixel_token)
    tracking_uuid = db.assign_uuid(send_id)
    pixel_html = tracker.pixel_html(tracking_uuid)

    # ---------- send ----------
    try:
        sender = EmailSender(
            gmail_address=gmail_address,
            app_password=app_password,
            sender_name=campaign["sender_name"],
            cv_path=cv_path,
            subject_ar=campaign.get("subject_ar", ""),
            subject_en=campaign.get("subject_en", ""),
        )
        sender.connect()
        sender.send(company, body, is_rtl, pixel_html)
        sender.close()
    except EmailConfigError as exc:
        db.mark_failed(send_id, f"config: {exc}", body)
        _cleanup(cv_path, ar_path, en_path)
        return TickResult("config_error", reason=str(exc),
                          campaign_id=campaign["id"], company=cname,
                          sent_today=sent_today, daily_cap=cap)
    except Exception as exc:
        db.mark_failed(send_id, str(exc), body)
        _cleanup(cv_path, ar_path, en_path)
        return TickResult("failed", reason=str(exc),
                          campaign_id=campaign["id"], company=cname,
                          source=source, sent_today=sent_today, daily_cap=cap)

    # ---------- success ----------
    db.mark_sent(send_id, body)
    db.bump_sent_today()
    _cleanup(cv_path, ar_path, en_path)
    return TickResult("sent", campaign_id=campaign["id"], company=cname,
                      source=source, sent_today=sent_today + 1, daily_cap=cap)


def _write_temp(text: str) -> str:
    tmp = tempfile.NamedTemporaryFile(prefix="tpl_", suffix=".txt",
                                      delete=False, mode="w",
                                      encoding="utf-8")
    tmp.write(text)
    tmp.close()
    return tmp.name


def _cleanup(*paths: str) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass
