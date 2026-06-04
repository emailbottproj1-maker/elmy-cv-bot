"""
Supabase data-access layer for the web edition.

Wraps the Supabase REST + Storage APIs using only stdlib (urllib) so the same
module runs in Vercel serverless functions without extra deps.

Tables: companies | campaigns | campaign_sends | email_opens | app_config
Storage bucket: cvs

Key responsibilities:
  * create a campaign + bulk-insert one send row per company (full-list targeting)
  * pick the next pending send across all active campaigns (FIFO/round-robin)
  * enforce GLOBAL daily cap + GLOBAL min-spacing (one Gmail across all campaigns)
  * record sent/failed + tracking_uuid + generated_body (for audit)
  * upload/sign CV files in the cvs bucket
  * sync opens from email_opens_agg
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class SupabaseError(Exception):
    pass


class SupabaseDB:
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = (url or os.environ.get("SUPABASE_URL") or "").rstrip("/")
        self.key = key or os.environ.get("SUPABASE_SERVICE_KEY") or ""
        if not self.url or not self.key:
            raise SupabaseError("SUPABASE_URL / SUPABASE_SERVICE_KEY missing.")
        self._rest = f"{self.url}/rest/v1"
        self._storage = f"{self.url}/storage/v1"

    # ---------- low-level HTTP ----------
    def _headers(self, prefer: str = "") -> dict[str, str]:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def _request(self, method: str, path: str, *, body: Any = None,
                 headers: Optional[dict] = None, raw_body: Optional[bytes] = None,
                 timeout: int = 20) -> Any:
        url = path if path.startswith("http") else f"{self._rest}{path}"
        data: Optional[bytes]
        if raw_body is not None:
            data = raw_body
        elif body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        else:
            data = None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=headers or self._headers())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                ct = resp.headers.get("Content-Type", "")
                if "application/json" in ct:
                    return json.loads(raw.decode("utf-8"))
                return raw
        except urllib.error.HTTPError as exc:
            try:
                err = exc.read().decode("utf-8")
            except Exception:
                err = str(exc)
            raise SupabaseError(f"{exc.code} {method} {path}: {err}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SupabaseError(f"network error {method} {path}: {exc}") from exc

    def _select(self, path: str) -> list:
        result = self._request("GET", path)
        return result if isinstance(result, list) else []

    def _insert(self, table: str, row: dict, returning: bool = True) -> Any:
        prefer = "return=representation" if returning else "return=minimal"
        return self._request("POST", f"/{table}", body=[row],
                             headers=self._headers(prefer))

    def _insert_many(self, table: str, rows: list[dict]) -> None:
        # use minimal return for big batches
        for i in range(0, len(rows), 500):
            chunk = rows[i:i + 500]
            self._request("POST", f"/{table}", body=chunk,
                          headers=self._headers("return=minimal"))

    def _update(self, table: str, filt: str, patch: dict) -> Any:
        return self._request(
            "PATCH", f"/{table}?{filt}", body=patch,
            headers=self._headers("return=representation"),
        )

    # ---------- companies (master list) ----------
    def upsert_companies(self, recipients: list[dict]) -> int:
        """Bulk-insert companies; existing emails (unique) are ignored."""
        if not recipients:
            return 0
        rows = [{
            "company_name": r["company_name"],
            "email": r["email"].lower(),
            "language": r.get("language", "en"),
            "sector": r.get("sector"),
            "city": r.get("city"),
            "source": r.get("source", "import"),
        } for r in recipients]
        for i in range(0, len(rows), 500):
            chunk = rows[i:i + 500]
            self._request(
                "POST", "/companies", body=chunk,
                headers=self._headers(
                    "resolution=ignore-duplicates,return=minimal"),
            )
        return len(rows)

    def list_companies(self, limit: int = 5000,
                       sector: str | None = None) -> list[dict]:
        """List companies. If `sector` is given, filter to that sector only."""
        url = (f"/companies?select=id,company_name,email,language,sector,city"
               f"&order=id&limit={limit}")
        if sector:
            from urllib.parse import quote
            url += f"&sector=eq.{quote(sector)}"
        return self._select(url)

    def list_sectors(self) -> list[str]:
        """Distinct, non-null sectors present in the companies table."""
        rows = self._select("/companies?select=sector&limit=100000")
        seen = sorted({(r.get("sector") or "").strip()
                       for r in rows if r.get("sector")})
        return [s for s in seen if s]

    def count_companies(self) -> int:
        # use HEAD + Range trick: cheaper alternative is select with limit 1 and
        # Prefer count=exact returning headers, but stdlib makes this awkward.
        rows = self._select("/companies?select=id&limit=100000")
        return len(rows)

    # ---------- campaigns ----------
    def create_campaign(self, *, customer_label: str, cv_storage_path: str,
                        sender_name: str, subject_ar: str, subject_en: str,
                        cover_letter_ar: str, cover_letter_en: str,
                        use_ai: bool = True,
                        package_size: int | None = None,
                        target_sector: str | None = None) -> dict:
        row = {
            "customer_label": customer_label,
            "cv_storage_path": cv_storage_path,
            "sender_name": sender_name,
            "subject_ar": subject_ar,
            "subject_en": subject_en,
            "cover_letter_ar": cover_letter_ar,
            "cover_letter_en": cover_letter_en,
            "use_ai": use_ai,
            "package_size": package_size,
            "target_sector": target_sector,
            "status": "draft",
        }
        rows = self._insert("campaigns", row)
        if not rows:
            raise SupabaseError("create_campaign returned no row")
        return rows[0]

    def used_company_ids(self) -> set[int]:
        """Return every company_id already targeted by ANY previous campaign.

        Used to enforce 'no-overlap' selection: a new campaign picks only from
        companies that have never been queued before.
        """
        # Fetch only the column; small payload even at 100k rows.
        rows = self._select(
            "/campaign_sends?select=company_id&limit=1000000"
        )
        return {r["company_id"] for r in rows if r.get("company_id") is not None}

    def populate_campaign_sends(
        self,
        campaign_id: int,
        package_size: int | None = None,
        target_sector: str | None = None,
    ) -> dict:
        """Pick targets for a campaign and insert one campaign_sends row each.

        Behaviour:
          * `target_sector=X` → only consider companies whose sector == X.
          * `package_size=None` → target the full (filtered) list (legacy mode).
          * `package_size=N` → pick N companies at random, **preferring those
            never targeted by previous campaigns**. If the unclaimed pool is
            smaller than N, take ALL unclaimed plus enough random "recycled"
            (already-used) companies to fill the package, and report the
            number of recycled rows so the UI can warn the user.

        Returns {"targeted": int, "overlap": int}.
        The overlap count is also stored on `campaigns.overlap_count` so the
        UI can re-render the warning later without recomputing.
        """
        import random as _random

        # Sector filter happens at the DB level for efficiency.
        all_companies = self.list_companies(limit=1000000, sector=target_sector)
        if not all_companies:
            return {"targeted": 0, "overlap": 0}

        # ---- legacy: full-list targeting ----
        if package_size is None or package_size <= 0 or package_size >= len(all_companies):
            chosen = all_companies
            overlap = 0
        else:
            used = self.used_company_ids()
            unclaimed = [c for c in all_companies if c["id"] not in used]
            _random.shuffle(unclaimed)

            if len(unclaimed) >= package_size:
                chosen = unclaimed[:package_size]
                overlap = 0
            else:
                # Pool exhausted: take everything unclaimed, then recycle
                # randomly from the used pool to fill the package.
                chosen = list(unclaimed)
                need = package_size - len(chosen)
                already_ids = {c["id"] for c in chosen}
                recycle_pool = [c for c in all_companies
                                if c["id"] not in already_ids]
                _random.shuffle(recycle_pool)
                chosen.extend(recycle_pool[:need])
                overlap = need

        rows = [{
            "campaign_id": campaign_id,
            "company_id": c["id"],
            "status": "pending",
        } for c in chosen]
        if rows:
            self._insert_many("campaign_sends", rows)

        # persist overlap counter on the campaign for later display
        self._update("campaigns", f"id=eq.{campaign_id}",
                     {"overlap_count": overlap})
        return {"targeted": len(rows), "overlap": overlap}

    def list_campaigns(self) -> list[dict]:
        return self._select(
            "/campaigns?select=*&order=created_at.desc"
        )

    def get_campaign(self, campaign_id: int) -> Optional[dict]:
        rows = self._select(f"/campaigns?id=eq.{campaign_id}&select=*")
        return rows[0] if rows else None

    def set_campaign_status(self, campaign_id: int, status: str) -> None:
        self._update("campaigns", f"id=eq.{campaign_id}", {"status": status})

    def campaign_counts(self, campaign_id: int) -> dict:
        rows = self._select(
            f"/campaign_sends?campaign_id=eq.{campaign_id}"
            f"&select=status&limit=100000"
        )
        c = {"total": len(rows), "sent": 0, "failed": 0, "pending": 0}
        for r in rows:
            c[r["status"]] = c.get(r["status"], 0) + 1
        return c

    # ---------- next pending across all active campaigns ----------
    def next_pending_send(self) -> Optional[dict]:
        """Pick the oldest pending send from any active campaign.

        Returns a joined dict: send row + company + campaign fields.
        """
        # First get active campaign ids
        camps = self._select(
            "/campaigns?status=eq.active&select=id&order=created_at"
        )
        if not camps:
            return None
        ids = ",".join(str(c["id"]) for c in camps)
        # Embedded select to pull company and campaign in one round-trip.
        rows = self._select(
            f"/campaign_sends?status=eq.pending&campaign_id=in.({ids})"
            f"&select=id,campaign_id,company_id,attempts,"
            f"company:companies(id,company_name,email,language,sector,city),"
            f"campaign:campaigns(id,sender_name,subject_ar,subject_en,"
            f"cover_letter_ar,cover_letter_en,cv_storage_path,use_ai,status)"
            f"&order=id&limit=1"
        )
        return rows[0] if rows else None

    def assign_uuid(self, send_id: int) -> str:
        new_uuid = uuid.uuid4().hex
        self._update("campaign_sends", f"id=eq.{send_id}",
                     {"tracking_uuid": new_uuid})
        return new_uuid

    def mark_sent(self, send_id: int, body: str) -> None:
        self._update("campaign_sends", f"id=eq.{send_id}", {
            "status": "sent",
            "sent_at": _now(),
            "generated_body": body[:8000],
            "error": None,
            "attempts": 1,  # bumped via separate increment if retried
        })

    def mark_failed(self, send_id: int, error: str, body: str = "") -> None:
        self._update("campaign_sends", f"id=eq.{send_id}", {
            "status": "failed",
            "error": str(error)[:500],
            "generated_body": body[:8000] if body else None,
        })

    # ---------- global rate-limit state (app_config) ----------
    def get_config(self, key: str, default: Any = None) -> Any:
        rows = self._select(f"/app_config?key=eq.{urllib.parse.quote(key)}&select=value")
        if not rows:
            return default
        return rows[0].get("value", default)

    def set_config(self, key: str, value: Any) -> None:
        body = [{"key": key, "value": value, "updated_at": _now()}]
        self._request("POST", "/app_config", body=body,
                      headers=self._headers(
                          "resolution=merge-duplicates,return=minimal"))

    def get_global_state(self) -> dict:
        """Returns {daily_cap, min_delay_sec, max_delay_sec, last_global_send_at,
                    sent_today: {date, count}}."""
        keys = ("daily_cap", "min_delay_sec", "max_delay_sec",
                "last_global_send_at", "sent_today")
        out = {}
        for k in keys:
            out[k] = self.get_config(k)
        # normalise sent_today against today (reset if date changed)
        st = out.get("sent_today") or {}
        if st.get("date") != _utc_today():
            st = {"date": _utc_today(), "count": 0}
            self.set_config("sent_today", st)
            out["sent_today"] = st
        return out

    def bump_sent_today(self) -> None:
        st = self.get_config("sent_today") or {}
        if st.get("date") != _utc_today():
            st = {"date": _utc_today(), "count": 0}
        st["count"] = int(st.get("count", 0)) + 1
        self.set_config("sent_today", st)
        self.set_config("last_global_send_at", _now())

    # ---------- opens cache (read via aggregated view) ----------
    def fetch_opens_agg(self) -> list[dict]:
        rows = self._select(
            "/email_opens_agg?select=email_uuid,open_count,first_open_at,last_seen_at"
        )
        return rows

    def campaign_opens(self, campaign_id: int, limit: int = 100) -> list[dict]:
        rows = self._select(
            f"/campaign_sends?campaign_id=eq.{campaign_id}"
            f"&tracking_uuid=not.is.null&select=tracking_uuid,"
            f"company:companies(company_name,email)&limit={limit}"
        )
        agg = {r["email_uuid"]: r for r in self.fetch_opens_agg()}
        opens = []
        for r in rows:
            a = agg.get(r["tracking_uuid"])
            if not a:
                continue
            opens.append({
                "company_name": r["company"]["company_name"],
                "email": r["company"]["email"],
                "open_count": a["open_count"],
                "first_open_at": a["first_open_at"],
            })
        opens.sort(key=lambda x: x["first_open_at"] or "", reverse=True)
        return opens[:limit]

    # ---------- storage ----------
    def upload_cv(self, file_bytes: bytes, filename: str,
                  bucket: str = "cvs") -> str:
        """Upload a CV; returns the storage path (bucket-relative)."""
        # unique path per upload
        safe = "".join(c for c in filename if c.isalnum() or c in "._-") or "cv.pdf"
        path = f"{uuid.uuid4().hex}_{safe}"
        url = f"{self._storage}/object/{bucket}/{path}"
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/pdf",
            "x-upsert": "false",
        }
        req = urllib.request.Request(url, data=file_bytes, method="POST",
                                     headers=headers)
        try:
            urllib.request.urlopen(req, timeout=30).read()
        except urllib.error.HTTPError as exc:
            raise SupabaseError(f"upload failed: {exc.code} {exc.read()}") from exc
        return path

    def download_cv(self, path: str, bucket: str = "cvs") -> bytes:
        url = f"{self._storage}/object/{bucket}/{path}"
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        req = urllib.request.Request(url, method="GET", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise SupabaseError(f"download failed: {exc.code}") from exc


if __name__ == "__main__":
    # offline import smoke test
    try:
        SupabaseDB(url="", key="")
    except SupabaseError as e:
        print(f"OK - SupabaseDB requires env vars (got expected error): {e}")
