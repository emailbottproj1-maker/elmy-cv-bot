"""
Tests for the package_size + non-overlap selection logic in
SupabaseDB.populate_campaign_sends().

We mock the network: subclass SupabaseDB and override the few HTTP-touching
methods it uses, so we can run pure-logic tests offline.

Critical cases:
  1. Non-overlap: two back-to-back campaigns of size 5 from a master of 10
     produce DISJOINT recipient sets.
  2. Pool exhaustion → recycle: third campaign of size 5 has no unclaimed
     companies left → all 5 are recycled, overlap == 5.
  3. Partial exhaustion: second campaign of 7 from master of 10 with 5 used
     → takes the 5 unclaimed + 2 recycled, overlap == 2.
  4. Full-list mode (package_size=None) still works → all companies, overlap=0.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.supabase_db import SupabaseDB


class FakeDB(SupabaseDB):
    """In-memory subclass that bypasses the network."""
    def __init__(self, n_companies: int, sectors: list[str] | None = None):
        # Skip the real __init__'s env check by setting state directly.
        sectors = sectors or ["Test"]
        self._companies = [{"id": i + 1, "company_name": f"Co{i+1}",
                            "email": f"c{i+1}@x.com", "language": "en",
                            "sector": sectors[i % len(sectors)], "city": "X"}
                           for i in range(n_companies)]
        self._sends: list[dict] = []
        self._next_send_id = 1
        self._campaigns: dict[int, dict] = {}
        self._next_campaign_id = 1

    # ---- overrides used by populate_campaign_sends ----
    def list_companies(self, limit: int = 1000000,
                       sector: str | None = None) -> list[dict]:
        rows = list(self._companies)
        if sector:
            rows = [c for c in rows if c.get("sector") == sector]
        return rows

    def used_company_ids(self) -> set[int]:
        return {s["company_id"] for s in self._sends}

    def _insert_many(self, table: str, rows: list[dict]) -> None:
        assert table == "campaign_sends"
        for r in rows:
            self._sends.append({**r, "id": self._next_send_id})
            self._next_send_id += 1

    def _update(self, table: str, filt: str, patch: dict):
        if table == "campaigns":
            cid = int(filt.split("eq.")[-1])
            if cid in self._campaigns:
                self._campaigns[cid].update(patch)

    def _insert(self, table: str, row: dict, returning: bool = True):
        cid = self._next_campaign_id
        self._next_campaign_id += 1
        rec = {**row, "id": cid}
        if table == "campaigns":
            self._campaigns[cid] = rec
        return [rec]


def _ids_in_campaign(db: FakeDB, campaign_id: int) -> set[int]:
    return {s["company_id"] for s in db._sends if s["campaign_id"] == campaign_id}


def test_non_overlap_two_campaigns():
    db = FakeDB(n_companies=10)
    # Create two campaigns of size 5
    c1 = db.create_campaign(customer_label="A", cv_storage_path="a", sender_name="A",
                            subject_ar="", subject_en="", cover_letter_ar="",
                            cover_letter_en="", package_size=5)
    r1 = db.populate_campaign_sends(c1["id"], package_size=5)
    c2 = db.create_campaign(customer_label="B", cv_storage_path="b", sender_name="B",
                            subject_ar="", subject_en="", cover_letter_ar="",
                            cover_letter_en="", package_size=5)
    r2 = db.populate_campaign_sends(c2["id"], package_size=5)

    s1 = _ids_in_campaign(db, c1["id"])
    s2 = _ids_in_campaign(db, c2["id"])
    assert len(s1) == 5 and len(s2) == 5, (len(s1), len(s2))
    assert s1.isdisjoint(s2), f"OVERLAP DETECTED: {s1 & s2}"
    assert r1["overlap"] == 0 and r2["overlap"] == 0
    print(f"  [PASS] non-overlap: {sorted(s1)} ∩ {sorted(s2)} = ∅")


def test_recycle_on_exhaustion():
    db = FakeDB(n_companies=10)
    # First campaign claims ALL 10
    c1 = db.create_campaign(customer_label="A", cv_storage_path="a", sender_name="A",
                            subject_ar="", subject_en="", cover_letter_ar="",
                            cover_letter_en="", package_size=10)
    db.populate_campaign_sends(c1["id"], package_size=10)
    # Second campaign of 5 → no unclaimed → all 5 recycled
    c2 = db.create_campaign(customer_label="B", cv_storage_path="b", sender_name="B",
                            subject_ar="", subject_en="", cover_letter_ar="",
                            cover_letter_en="", package_size=5)
    r2 = db.populate_campaign_sends(c2["id"], package_size=5)
    s2 = _ids_in_campaign(db, c2["id"])
    assert len(s2) == 5
    assert r2["overlap"] == 5, f"expected all 5 recycled, got {r2['overlap']}"
    assert db._campaigns[c2["id"]]["overlap_count"] == 5
    print(f"  [PASS] recycle on exhaustion: overlap={r2['overlap']}/5")


def test_partial_exhaustion():
    db = FakeDB(n_companies=10)
    # First campaign claims 5
    c1 = db.create_campaign(customer_label="A", cv_storage_path="a", sender_name="A",
                            subject_ar="", subject_en="", cover_letter_ar="",
                            cover_letter_en="", package_size=5)
    db.populate_campaign_sends(c1["id"], package_size=5)
    # Second wants 7 → only 5 unclaimed → 5 fresh + 2 recycled
    c2 = db.create_campaign(customer_label="B", cv_storage_path="b", sender_name="B",
                            subject_ar="", subject_en="", cover_letter_ar="",
                            cover_letter_en="", package_size=7)
    r2 = db.populate_campaign_sends(c2["id"], package_size=7)
    s2 = _ids_in_campaign(db, c2["id"])
    s1 = _ids_in_campaign(db, c1["id"])
    assert len(s2) == 7
    assert r2["overlap"] == 2, f"expected overlap=2, got {r2['overlap']}"
    # 5 of s2 should be fresh (disjoint from s1), 2 should be from s1
    overlap_with_s1 = s2 & s1
    assert len(overlap_with_s1) == 2, f"expected 2 from s1, got {len(overlap_with_s1)}"
    print(f"  [PASS] partial exhaustion: 5 fresh + 2 recycled = 7")


def test_full_list_mode_unchanged():
    db = FakeDB(n_companies=4)
    c1 = db.create_campaign(customer_label="A", cv_storage_path="a", sender_name="A",
                            subject_ar="", subject_en="", cover_letter_ar="",
                            cover_letter_en="", package_size=None)
    r1 = db.populate_campaign_sends(c1["id"], package_size=None)
    s1 = _ids_in_campaign(db, c1["id"])
    assert len(s1) == 4
    assert r1["overlap"] == 0
    # Second full-list campaign also gets all 4 (each campaign targets full list)
    c2 = db.create_campaign(customer_label="B", cv_storage_path="b", sender_name="B",
                            subject_ar="", subject_en="", cover_letter_ar="",
                            cover_letter_en="", package_size=None)
    r2 = db.populate_campaign_sends(c2["id"], package_size=None)
    s2 = _ids_in_campaign(db, c2["id"])
    assert len(s2) == 4
    assert r2["overlap"] == 0
    print("  [PASS] full-list mode: each campaign still gets all 4 companies")


def test_package_size_larger_than_list_falls_back_to_full():
    db = FakeDB(n_companies=3)
    c1 = db.create_campaign(customer_label="A", cv_storage_path="a", sender_name="A",
                            subject_ar="", subject_en="", cover_letter_ar="",
                            cover_letter_en="", package_size=100)
    r1 = db.populate_campaign_sends(c1["id"], package_size=100)
    assert len(_ids_in_campaign(db, c1["id"])) == 3
    assert r1["overlap"] == 0
    print("  [PASS] package_size > list → returns all available, no overlap")


def test_sector_filter_isolates_correctly():
    """Sector-filtered campaigns only see companies of their sector."""
    db = FakeDB(n_companies=15,
                sectors=["Healthcare", "Marketing", "Technology"])
    # 5 in each sector. Campaign for Healthcare wants 3.
    c1 = db.create_campaign(customer_label="hc", cv_storage_path="a",
                            sender_name="A", subject_ar="", subject_en="",
                            cover_letter_ar="", cover_letter_en="",
                            package_size=3, target_sector="Healthcare")
    r1 = db.populate_campaign_sends(c1["id"], package_size=3,
                                    target_sector="Healthcare")
    chosen = _ids_in_campaign(db, c1["id"])
    chosen_sectors = {db._companies[i - 1]["sector"] for i in chosen}
    assert len(chosen) == 3, len(chosen)
    assert chosen_sectors == {"Healthcare"}, chosen_sectors
    assert r1["overlap"] == 0
    print("  [PASS] sector filter: campaign only got Healthcare companies")


def test_sector_pool_exhaustion_recycles_within_sector():
    """When a sector's pool is empty, recycling stays within that sector."""
    db = FakeDB(n_companies=10, sectors=["A", "B"])
    # 5 in sector A. First campaign takes all 5.
    c1 = db.create_campaign(customer_label="x", cv_storage_path="a",
                            sender_name="X", subject_ar="", subject_en="",
                            cover_letter_ar="", cover_letter_en="",
                            package_size=5, target_sector="A")
    db.populate_campaign_sends(c1["id"], package_size=5, target_sector="A")
    # Second campaign for sector A wants 3 → all recycled FROM SECTOR A only.
    c2 = db.create_campaign(customer_label="y", cv_storage_path="a",
                            sender_name="Y", subject_ar="", subject_en="",
                            cover_letter_ar="", cover_letter_en="",
                            package_size=3, target_sector="A")
    r2 = db.populate_campaign_sends(c2["id"], package_size=3, target_sector="A")
    chosen = _ids_in_campaign(db, c2["id"])
    chosen_sectors = {db._companies[i - 1]["sector"] for i in chosen}
    assert chosen_sectors == {"A"}, f"recycled across sectors! {chosen_sectors}"
    assert r2["overlap"] == 3
    print("  [PASS] recycle stays within sector (never bleeds to other sector)")


if __name__ == "__main__":
    print("Running package selection tests...")
    test_non_overlap_two_campaigns()
    test_recycle_on_exhaustion()
    test_partial_exhaustion()
    test_full_list_mode_unchanged()
    test_package_size_larger_than_list_falls_back_to_full()
    test_sector_filter_isolates_correctly()
    test_sector_pool_exhaustion_recycles_within_sector()
    print("\nALL PACKAGE SELECTION TESTS PASSED ✅")
