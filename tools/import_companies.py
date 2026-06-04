"""
Bulk-import the client's company file into Supabase.

Workflow:
  1. Read .xlsx or .csv (auto-detect headers, supports Arabic column names).
  2. Apply sector_aliases.normalise_sector to each row.
  3. Skip invalid emails + duplicates.
  4. Push to Supabase in chunks of 500.

Modes:
  --dry-run    : show what WOULD happen, no network calls.
  --keep-unknown : import rows whose sector can't be auto-classified
                   (left as the raw label so you can fix them later).
                   Default: such rows are SKIPPED to keep the sector filter clean.

Usage:
  export SUPABASE_URL=... SUPABASE_SERVICE_KEY=...
  python tools/import_companies.py path/to/file.xlsx
  python tools/import_companies.py path/to/file.xlsx --dry-run
  python tools/import_companies.py path/to/file.xlsx --keep-unknown
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.excel_reader import EMAIL_RE
from bot.sector_aliases import normalise_sector

# Reuse the readers we already built.
from tools.preview_import import read_csv_rows, read_xlsx_rows, detect_columns


def build_rows(rows: list[dict], cols: dict, *,
               keep_unknown: bool) -> tuple[list[dict], dict]:
    """Convert raw rows to the SupabaseDB.upsert_companies shape.

    Returns (clean_rows, report).
    """
    report = {
        "total": len(rows), "valid": 0, "skipped_invalid_email": 0,
        "skipped_duplicates": 0, "skipped_missing_fields": 0,
        "skipped_unknown_sector": 0, "kept_unknown_sector": 0,
        "matched_sectors": 0, "by_sector": {},
    }
    out: list[dict] = []
    seen: set[str] = set()
    e = cols.get("email"); c = cols.get("company_name")
    s = cols.get("sector"); l = cols.get("language"); ci = cols.get("city")

    if not e or not c:
        sys.exit("file is missing required columns (company_name and email).")

    for r in rows:
        email = (r.get(e, "") or "").strip().lower()
        company = (r.get(c, "") or "").strip()
        if not email or not company:
            report["skipped_missing_fields"] += 1; continue
        if not EMAIL_RE.match(email):
            report["skipped_invalid_email"] += 1; continue
        if email in seen:
            report["skipped_duplicates"] += 1; continue
        seen.add(email)

        sector = None
        if s:
            raw_sector = (r.get(s, "") or "").strip()
            if raw_sector:
                canon = normalise_sector(raw_sector)
                if canon:
                    sector = canon
                    report["matched_sectors"] += 1
                    report["by_sector"][canon] = report["by_sector"].get(canon, 0) + 1
                elif keep_unknown:
                    sector = raw_sector
                    report["kept_unknown_sector"] += 1
                else:
                    report["skipped_unknown_sector"] += 1
                    continue

        lang = (r.get(l, "") or "").strip().lower() if l else ""
        if lang not in ("ar", "en"):
            lang = "en"
        city = (r.get(ci, "") or "").strip() if ci else None

        out.append({
            "company_name": company, "email": email, "language": lang,
            "sector": sector, "city": city,
        })
        report["valid"] += 1
    return out, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--sector-col", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-unknown", action="store_true",
                    help="import unknown-sector rows verbatim instead of skipping")
    ap.add_argument("--chunk", type=int, default=500)
    args = ap.parse_args()

    if not os.path.exists(args.path):
        sys.exit(f"file not found: {args.path}")
    ext = os.path.splitext(args.path)[1].lower()
    if ext == ".xlsx":
        headers, rows = read_xlsx_rows(args.path)
    elif ext in (".csv", ".tsv"):
        headers, rows = read_csv_rows(args.path)
    else:
        sys.exit(f"unsupported extension: {ext}")

    cols = detect_columns(headers, args.sector_col)
    clean, report = build_rows(rows, cols, keep_unknown=args.keep_unknown)

    print(f"\nFile : {args.path}")
    print(f"Read : {report['total']:,} rows  -> {report['valid']:,} valid for import\n")
    for k in ("skipped_invalid_email", "skipped_duplicates",
              "skipped_missing_fields", "skipped_unknown_sector",
              "kept_unknown_sector", "matched_sectors"):
        if report[k]:
            print(f"  {k:<28} {report[k]:>7,}")
    if report["by_sector"]:
        print("\nBy sector:")
        for code, n in sorted(report["by_sector"].items(), key=lambda x: -x[1]):
            print(f"  {code:<14} {n:>6,}")

    if args.dry_run:
        print("\n--dry-run: not contacting Supabase. First 3 prepared rows:")
        for r in clean[:3]:
            print("  ", r)
        return

    if not clean:
        sys.exit("no valid rows to import.")

    # Real upload
    from bot.supabase_db import SupabaseDB
    db = SupabaseDB()
    before = db.count_companies()
    print(f"\nSupabase already has {before:,} companies. Uploading in chunks of {args.chunk}...")
    for i in range(0, len(clean), args.chunk):
        chunk = clean[i:i + args.chunk]
        db.upsert_companies(chunk)
        print(f"  chunk {i // args.chunk + 1}: pushed {len(chunk)} (cumulative {i + len(chunk):,})")
    after = db.count_companies()
    print(f"\nDone. Companies in DB: {before:,} -> {after:,} (added {after - before:,}).")


if __name__ == "__main__":
    main()
