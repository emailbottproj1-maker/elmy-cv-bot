"""
Push the local sample company list into Supabase.

Usage:
  SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python tools/seed_companies.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.excel_reader import read_companies
from bot.supabase_db import SupabaseDB

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data",
                      "companies_sample_list.xlsx")


def main(path: str = SAMPLE):
    if not os.path.exists(path):
        print(f"Excel not found: {path}")
        sys.exit(1)
    res = read_companies(path)
    print(f"Parsed {res.valid_count} valid, {res.error_count} skipped from {path}")
    for e in res.errors[:5]:
        print(f"  ! {e}")
    if not res.recipients:
        sys.exit("nothing to upload.")

    db = SupabaseDB()
    n = db.upsert_companies(res.recipients)
    print(f"Submitted {n} rows to Supabase (duplicates by email are ignored).")
    print(f"Total companies in DB now: {db.count_companies()}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else SAMPLE)
