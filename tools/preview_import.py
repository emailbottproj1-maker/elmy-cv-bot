"""
Preview-import tool.

Run BEFORE actually pushing a company file to Supabase. Reads Excel (.xlsx) or
CSV, runs the same validation excel_reader.py uses, applies the sector alias
map, and prints a human-readable report:

    Total rows scanned     : 20,134
    Valid email & company  : 19,478
    Invalid emails         :    412  (will be skipped)
    Duplicate emails       :    244  (will be skipped)
    Missing sector         :  3,120
    Unknown sector labels  :    482   - 12 distinct labels (see below)

    Distribution by canonical sector:
      Healthcare    : 1,820
      Marketing     : 1,455
      ...

    Top 10 unknown sector labels (need manual mapping or AI categorisation):
      'تكنولوجيا متقدمة' : 142
      ...

Use:
    python tools/preview_import.py path/to/file.xlsx
    python tools/preview_import.py path/to/file.csv --sector-col القطاع
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from bot.excel_reader import EMAIL_RE, COLUMN_ALIASES, _normalize_header
from bot.sector_aliases import normalise_sector


def read_csv_rows(path: str) -> tuple[list[str], list[dict]]:
    """Read a CSV file with auto-detected delimiter and return (headers, rows)."""
    with open(path, "rb") as f:
        sample = f.read(8192).decode("utf-8-sig", errors="replace")
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(sample, delimiters=",;\t|")
    except csv.Error:
        class _D(csv.excel):
            delimiter = ","
        dialect = _D()
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, dialect)
        rows_raw = list(reader)
    if not rows_raw:
        return [], []
    headers = rows_raw[0]
    data = [dict(zip(headers, r)) for r in rows_raw[1:] if any(r)]
    return headers, data


def read_xlsx_rows(path: str) -> tuple[list[str], list[dict]]:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    iters = ws.iter_rows(values_only=True)
    try:
        header_row = next(iters)
    except StopIteration:
        return [], []
    headers = [str(h) if h is not None else "" for h in header_row]
    data = []
    for r in iters:
        if r is None or all(c is None or str(c).strip() == "" for c in r):
            continue
        d = {h: (str(v).strip() if v is not None else "")
             for h, v in zip(headers, r)}
        data.append(d)
    wb.close()
    return headers, data


def detect_columns(headers: list[str], sector_col_hint: str | None) -> dict:
    """Map header text → canonical field names (company_name/email/language/sector/city)."""
    found = {}
    for raw in headers:
        canon = _normalize_header(raw)
        if canon in ("company_name", "email", "language") and canon not in found:
            found[canon] = raw
    # sector / city are not in COLUMN_ALIASES; detect heuristically
    for raw in headers:
        if not raw:
            continue
        low = str(raw).strip().lower()
        if "sector" not in found and low in (
            "sector", "industry", "category",
            "التخصص", "تخصص", "القطاع", "قطاع", "المجال"):
            found["sector"] = raw
        if "city" not in found and low in (
            "city", "town", "location", "المدينة", "مدينة"):
            found["city"] = raw
    if sector_col_hint and "sector" not in found:
        if sector_col_hint in headers:
            found["sector"] = sector_col_hint
    return found


def analyse(rows: list[dict], cols: dict) -> dict:
    report = {
        "total": len(rows),
        "valid": 0,
        "invalid_email": 0,
        "missing_email": 0,
        "missing_company": 0,
        "duplicates": 0,
        "missing_sector": 0,
        "matched_sectors": 0,
        "unknown_sectors": 0,
        "by_sector": Counter(),
        "unknown_labels": Counter(),
        "samples": {"invalid_email": [], "unknown_label": []},
    }
    seen_emails: set[str] = set()
    email_col = cols.get("email")
    company_col = cols.get("company_name")
    sector_col = cols.get("sector")

    for r in rows:
        company = (r.get(company_col, "") or "").strip() if company_col else ""
        email = (r.get(email_col, "") or "").strip().lower() if email_col else ""

        if not email:
            report["missing_email"] += 1
            continue
        if not company:
            report["missing_company"] += 1
            continue
        if not EMAIL_RE.match(email):
            report["invalid_email"] += 1
            if len(report["samples"]["invalid_email"]) < 5:
                report["samples"]["invalid_email"].append(email)
            continue
        if email in seen_emails:
            report["duplicates"] += 1
            continue
        seen_emails.add(email)
        report["valid"] += 1

        sector_raw = (r.get(sector_col, "") or "").strip() if sector_col else ""
        if not sector_raw:
            report["missing_sector"] += 1
        else:
            canon = normalise_sector(sector_raw)
            if canon:
                report["matched_sectors"] += 1
                report["by_sector"][canon] += 1
            else:
                report["unknown_sectors"] += 1
                report["unknown_labels"][sector_raw] += 1
                if len(report["samples"]["unknown_label"]) < 5:
                    report["samples"]["unknown_label"].append(sector_raw)
    return report


def print_report(path: str, headers: list[str], cols: dict, rep: dict) -> None:
    pct = lambda n: f"{(n / max(rep['total'], 1) * 100):5.1f}%"
    print(f"\n=== Import preview: {os.path.basename(path)} ===\n")
    print(f"Detected columns:")
    for k in ("company_name", "email", "language", "sector", "city"):
        v = cols.get(k)
        mark = "v" if v else "-"
        print(f"  [{mark}] {k:<14} -> {v!r}")
    missing = [k for k in ("company_name", "email") if k not in cols]
    if missing:
        print(f"\n  WARNING: required columns missing: {missing}")
        print(f"  Available headers: {headers}")
        return

    print(f"\nRow counts (out of {rep['total']:,}):")
    print(f"  Valid (will import)      : {rep['valid']:>7,}  {pct(rep['valid'])}")
    print(f"  Invalid email            : {rep['invalid_email']:>7,}  {pct(rep['invalid_email'])}")
    print(f"  Missing email            : {rep['missing_email']:>7,}  {pct(rep['missing_email'])}")
    print(f"  Missing company name     : {rep['missing_company']:>7,}  {pct(rep['missing_company'])}")
    print(f"  Duplicate emails         : {rep['duplicates']:>7,}  {pct(rep['duplicates'])}")

    if "sector" in cols:
        print(f"\nSector classification (of valid rows = {rep['valid']:,}):")
        print(f"  Auto-matched to canonical: {rep['matched_sectors']:>7,}")
        print(f"  Missing sector cell      : {rep['missing_sector']:>7,}")
        print(f"  Unknown labels           : {rep['unknown_sectors']:>7,}")

        if rep["by_sector"]:
            print("\nDistribution by canonical sector:")
            for code, n in sorted(rep["by_sector"].items(),
                                  key=lambda x: -x[1]):
                bar = "#" * int(40 * n / max(rep["by_sector"].values()))
                print(f"  {code:<14} {n:>5,}  {bar}")

        if rep["unknown_labels"]:
            print(f"\nTop unknown sector labels (need a rule or AI):")
            for label, n in rep["unknown_labels"].most_common(15):
                print(f"  {n:>5,}  {label!r}")
    else:
        print("\n(No sector column detected — companies will import without sectors.)")
        print("  Use --sector-col 'X' to point to one, or rely on AI fallback.")

    if rep["samples"]["invalid_email"]:
        print(f"\nSamples of invalid emails: {rep['samples']['invalid_email']}")
    print()


def main():
    ap = argparse.ArgumentParser(description="Preview a company import file.")
    ap.add_argument("path", help="Path to .xlsx or .csv file")
    ap.add_argument("--sector-col",
                    help="Hint: column name to use as the sector column",
                    default=None)
    args = ap.parse_args()

    if not os.path.exists(args.path):
        sys.exit(f"file not found: {args.path}")
    ext = os.path.splitext(args.path)[1].lower()
    if ext == ".xlsx":
        headers, rows = read_xlsx_rows(args.path)
    elif ext in (".csv", ".tsv"):
        headers, rows = read_csv_rows(args.path)
    else:
        sys.exit(f"unsupported extension: {ext}. Use .xlsx or .csv")

    cols = detect_columns(headers, args.sector_col)
    rep = analyse(rows, cols)
    print_report(args.path, headers, cols, rep)


if __name__ == "__main__":
    main()
