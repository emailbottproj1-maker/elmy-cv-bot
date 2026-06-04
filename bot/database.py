"""
SQLite persistence layer.

Responsibilities:
  * Track every recipient + send status (pending / sent / failed).
  * Enable RESUME: when the app restarts, we know exactly who is already done.
  * Enforce the daily cap by counting how many were sent "today".
  * Store the tracking UUID per email so opens can be matched back to a company.

The DB is the single source of truth for a campaign. The Excel file is only
imported once (into the `recipients` table); after that we work from the DB so
the campaign survives restarts.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

DEFAULT_DB = "data/tracking.db"


def _now_iso() -> str:
    """Timezone-aware UTC timestamp (ISO 8601)."""
    return datetime.now(timezone.utc).isoformat()


def _utc_today() -> str:
    """Current UTC date as YYYY-MM-DD (matches substr of _now_iso)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    excel_path      TEXT,
    created_at      TEXT,
    total           INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recipients (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name    TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    language        TEXT DEFAULT 'en',
    extra_json      TEXT,                       -- extra placeholder columns
    tracking_uuid   TEXT UNIQUE,                -- assigned when sent
    status          TEXT DEFAULT 'pending',     -- pending | sent | failed
    error           TEXT,
    sent_at         TEXT,
    attempts        INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_recipients_status ON recipients(status);
CREATE INDEX IF NOT EXISTS idx_recipients_uuid   ON recipients(tracking_uuid);

-- Local cache of opens fetched from the Vercel pixel service.
CREATE TABLE IF NOT EXISTS opens (
    tracking_uuid   TEXT PRIMARY KEY,
    first_open_at   TEXT,
    open_count      INTEGER DEFAULT 0,
    last_seen_at    TEXT
);
"""


class Database:
    """Thread-safe-ish wrapper. One connection guarded by a lock.

    The sending engine runs in a background thread while the GUI reads stats
    from the main thread, so all access goes through a single lock.
    """

    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        self._lock = threading.RLock()
        # check_same_thread=False because GUI thread + worker thread share it,
        # serialized by self._lock.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ---------- campaign import ----------
    def import_recipients(self, recipients: list[dict[str, Any]], excel_path: str) -> int:
        """Insert recipients that are not already present (idempotent by email).

        Returns the number of NEW rows inserted. Existing emails keep their
        status (so re-importing the same file doesn't resend).
        """
        import json

        inserted = 0
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO campaign(id, excel_path, created_at, total) "
                "VALUES (1, ?, ?, 0)",
                (excel_path, _now_iso()),
            )
            for r in recipients:
                extra = {
                    k: v for k, v in r.items()
                    if k not in ("company_name", "email", "language")
                }
                cur.execute(
                    "INSERT OR IGNORE INTO recipients"
                    "(company_name, email, language, extra_json) VALUES (?,?,?,?)",
                    (r["company_name"], r["email"], r.get("language", "en"),
                     json.dumps(extra, ensure_ascii=False) if extra else None),
                )
                inserted += cur.rowcount
            cur.execute(
                "UPDATE campaign SET total = (SELECT COUNT(*) FROM recipients) WHERE id = 1"
            )
            self._conn.commit()
        return inserted

    # ---------- sending workflow ----------
    def next_pending(self) -> Optional[dict[str, Any]]:
        """Return the next recipient to send to, or None if none left."""
        import json

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM recipients WHERE status = 'pending' ORDER BY id LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("extra_json"):
            try:
                d.update(json.loads(d["extra_json"]))
            except (ValueError, TypeError):
                pass
        return d

    def pending_in_random_order(self) -> list[int]:
        """Return pending recipient IDs shuffled (anti-spam best practice)."""
        import random

        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM recipients WHERE status = 'pending'"
            ).fetchall()
        ids = [r["id"] for r in rows]
        random.shuffle(ids)
        return ids

    def get_recipient(self, rid: int) -> Optional[dict[str, Any]]:
        import json

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM recipients WHERE id = ?", (rid,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("extra_json"):
            try:
                d.update(json.loads(d["extra_json"]))
            except (ValueError, TypeError):
                pass
        return d

    def assign_uuid(self, rid: int) -> str:
        """Assign (or reuse) a tracking UUID for a recipient and return it."""
        with self._lock:
            row = self._conn.execute(
                "SELECT tracking_uuid FROM recipients WHERE id = ?", (rid,)
            ).fetchone()
            if row and row["tracking_uuid"]:
                return row["tracking_uuid"]
            new_uuid = uuid.uuid4().hex
            self._conn.execute(
                "UPDATE recipients SET tracking_uuid = ? WHERE id = ?", (new_uuid, rid)
            )
            self._conn.commit()
            return new_uuid

    def mark_sent(self, rid: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE recipients SET status='sent', sent_at=?, error=NULL, "
                "attempts = attempts + 1 WHERE id = ?",
                (_now_iso(), rid),
            )
            self._conn.commit()

    def mark_failed(self, rid: int, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE recipients SET status='failed', error=?, "
                "attempts = attempts + 1 WHERE id = ?",
                (str(error)[:500], rid),
            )
            self._conn.commit()

    def reset_failed_to_pending(self) -> int:
        """Re-queue all failed recipients. Returns how many were reset."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE recipients SET status='pending', error=NULL WHERE status='failed'"
            )
            self._conn.commit()
            return cur.rowcount

    # ---------- daily cap ----------
    def sent_today(self) -> int:
        """Count emails marked sent with today's (UTC) date."""
        today = _utc_today()
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM recipients "
                "WHERE status='sent' AND substr(sent_at,1,10) = ?",
                (today,),
            ).fetchone()
        return row["c"] if row else 0

    # ---------- stats ----------
    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS c FROM recipients GROUP BY status"
            ).fetchall()
            total = self._conn.execute(
                "SELECT COUNT(*) AS c FROM recipients"
            ).fetchone()["c"]
            opens = self._conn.execute(
                "SELECT COUNT(*) AS c FROM opens WHERE open_count > 0"
            ).fetchone()["c"]
        by = {r["status"]: r["c"] for r in rows}
        return {
            "total": total,
            "sent": by.get("sent", 0),
            "failed": by.get("failed", 0),
            "pending": by.get("pending", 0),
            "opened": opens,
        }

    # ---------- opens (synced from Vercel) ----------
    def upsert_opens(self, opens: list[dict[str, Any]]) -> None:
        """opens: list of {tracking_uuid, first_open_at, open_count, last_seen_at}."""
        with self._lock:
            for o in opens:
                self._conn.execute(
                    "INSERT INTO opens(tracking_uuid, first_open_at, open_count, last_seen_at) "
                    "VALUES (:tracking_uuid, :first_open_at, :open_count, :last_seen_at) "
                    "ON CONFLICT(tracking_uuid) DO UPDATE SET "
                    "open_count=excluded.open_count, last_seen_at=excluded.last_seen_at",
                    {
                        "tracking_uuid": o.get("tracking_uuid"),
                        "first_open_at": o.get("first_open_at"),
                        "open_count": o.get("open_count", 1),
                        "last_seen_at": o.get("last_seen_at"),
                    },
                )
            self._conn.commit()

    def opened_companies(self, limit: int = 100) -> list[dict[str, Any]]:
        """Join opens back to recipients to show which companies opened."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT r.company_name, r.email, o.open_count, o.first_open_at "
                "FROM opens o JOIN recipients r ON r.tracking_uuid = o.tracking_uuid "
                "WHERE o.open_count > 0 "
                "ORDER BY o.first_open_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def recent_logs(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT company_name, email, status, sent_at, error "
                "FROM recipients WHERE status != 'pending' "
                "ORDER BY sent_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


if __name__ == "__main__":
    # quick smoke test
    import os

    test_path = "data/_test.db"
    if os.path.exists(test_path):
        os.remove(test_path)
    db = Database(test_path)
    db.import_recipients(
        [
            {"company_name": "A", "email": "a@x.com", "language": "en"},
            {"company_name": "B", "email": "b@x.com", "language": "ar", "position": "Dev"},
        ],
        "data/companies_sample.xlsx",
    )
    print("counts after import:", db.counts())
    nxt = db.next_pending()
    print("next pending:", nxt["email"])
    u = db.assign_uuid(nxt["id"])
    print("assigned uuid:", u)
    db.mark_sent(nxt["id"])
    print("sent today:", db.sent_today())
    print("counts after 1 sent:", db.counts())
    db.upsert_opens([{"tracking_uuid": u, "first_open_at": "2026-05-31T10:00:00",
                      "open_count": 2, "last_seen_at": "2026-05-31T11:00:00"}])
    print("opened companies:", db.opened_companies())
    db.close()
    os.remove(test_path)
    print("OK - database smoke test passed")
