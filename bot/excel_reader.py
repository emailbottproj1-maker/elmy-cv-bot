"""
Excel reader + validation.

Reads a companies Excel file and returns a clean list of recipients plus a
report of any rows that were skipped (invalid email, missing company name...).

Expected columns (header row, case-insensitive, order-independent):
    company_name   (required)
    email          (required, must be valid)
    language       (optional: ar / en ; defaults to en)

Anything else is ignored. Extra columns are preserved in the row dict so the
cover letter can use them as {placeholders} later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from openpyxl import load_workbook

# Reasonable, permissive email regex (RFC-lite). Good enough for outreach lists.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Column name aliases -> canonical name. Lets the client use Arabic headers too.
COLUMN_ALIASES = {
    # company name
    "company_name": "company_name",
    "company": "company_name",
    "company name": "company_name",
    "name": "company_name",
    "name_ar": "company_name",
    "الشركة": "company_name",
    "اسم الشركة": "company_name",
    "اسم": "company_name",
    "الاسم": "company_name",
    # email
    "email": "email",
    "e-mail": "email",
    "mail": "email",
    "الايميل": "email",
    "الإيميل": "email",
    "البريد": "email",
    "البريد الالكتروني": "email",
    "البريد الإلكتروني": "email",
    # language
    "language": "language",
    "lang": "language",
    "اللغة": "language",
    # sector
    "sector": "sector",
    "القطاع": "sector",
    "التخصص": "sector",
    "المجال": "sector",
    # city
    "city": "city",
    "المدينة": "city",
    "المدينه": "city",
}

REQUIRED = ("company_name", "email")
VALID_LANGS = {"ar", "en"}


@dataclass
class ReadResult:
    recipients: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_rows: int = 0

    @property
    def valid_count(self) -> int:
        return len(self.recipients)

    @property
    def error_count(self) -> int:
        return len(self.errors)


def _normalize_header(value: Any) -> str | None:
    if value is None:
        return None
    key = str(value).strip().lower()
    return COLUMN_ALIASES.get(key, key)


def _read_sheet(ws, result: ReadResult, default_lang: str,
                default_sector: str | None, seen_emails: set) -> None:
    """Parse one worksheet into result (modifies in-place)."""
    rows = ws.iter_rows(values_only=True)

    # --- header row ---
    try:
        header = next(rows)
    except StopIteration:
        return  # empty sheet, skip silently

    col_index: dict[str, int] = {}
    for idx, cell in enumerate(header):
        canon = _normalize_header(cell)
        if canon and canon not in col_index:
            col_index[canon] = idx

    # --- auto-detect missing required columns by scanning data rows ---
    missing = [c for c in REQUIRED if c not in col_index]
    if missing:
        # Read all data rows once to scan for email/name columns automatically
        data_rows = list(rows)
        if not data_rows:
            return  # nothing to scan

        if "email" in missing:
            # Find column with the most valid email addresses
            best_col, best_count = -1, 0
            for ci in range(len(header)):
                cnt = sum(1 for r in data_rows
                          if ci < len(r) and r[ci] and EMAIL_RE.match(str(r[ci]).strip()))
                if cnt > best_count:
                    best_count, best_col = cnt, ci
            if best_col >= 0 and best_count > 0:
                col_index["email"] = best_col
                missing = [c for c in missing if c != "email"]

        if "company_name" in missing:
            # Find the first text column that isn't the email column
            email_ci = col_index.get("email", -1)
            for ci in range(len(header)):
                if ci == email_ci:
                    continue
                non_empty = sum(1 for r in data_rows
                                if ci < len(r) and r[ci] and str(r[ci]).strip())
                if non_empty > len(data_rows) // 2:  # at least half non-empty
                    col_index["company_name"] = ci
                    missing = [c for c in missing if c != "company_name"]
                    break

        if missing:
            result.errors.append(
                f"ورقة '{ws.title}': لم يُعثر على أعمدة ({', '.join(missing)}) — تم تخطي الورقة."
            )
            return

        # Re-attach the iterator from our pre-read data
        rows = iter(data_rows)

    # --- data rows ---
    for row_num, row in enumerate(rows, start=2):
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue

        result.total_rows += 1

        def get(col: str) -> str:
            i = col_index.get(col)
            if i is None or i >= len(row) or row[i] is None:
                return ""
            return str(row[i]).strip()

        company = get("company_name")
        email = get("email").lower()
        lang = get("language").lower() or default_lang
        sector = get("sector") or default_sector
        city = get("city") or None

        if not company:
            result.errors.append(f"صف {row_num}: اسم الشركة فارغ — تم التخطي.")
            continue
        if not email:
            result.errors.append(f"صف {row_num} ({company}): الإيميل فارغ — تم التخطي.")
            continue
        if not EMAIL_RE.match(email):
            result.errors.append(f"صف {row_num} ({company}): إيميل غير صالح '{email}' — تم التخطي.")
            continue
        if lang not in VALID_LANGS:
            result.errors.append(
                f"صف {row_num} ({company}): لغة غير معروفة '{lang}'، تم استخدام '{default_lang}'."
            )
            lang = default_lang
        if email in seen_emails:
            result.errors.append(f"صف {row_num} ({company}): إيميل مكرر '{email}' — تم التخطي.")
            continue

        seen_emails.add(email)

        # Preserve any extra columns as placeholders
        extra: dict[str, Any] = {}
        for canon, i in col_index.items():
            if canon in ("company_name", "email", "language", "sector", "city"):
                continue
            if i < len(row) and row[i] is not None:
                extra[canon] = str(row[i]).strip()

        result.recipients.append({
            "company_name": company,
            "email": email,
            "language": lang,
            "sector": sector,
            "city": city,
            **extra,
        })


def read_companies(path: str, default_lang: str = "en",
                   default_sector: str | None = None) -> ReadResult:
    """Read and validate an Excel file (all sheets). Never raises on bad rows."""
    result = ReadResult()

    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except FileNotFoundError:
        result.errors.append(f"الملف غير موجود: {path}")
        return result
    except Exception as exc:
        result.errors.append(f"تعذّر فتح ملف Excel: {exc}")
        return result

    seen_emails: set[str] = set()
    for ws in wb.worksheets:
        _read_sheet(ws, result, default_lang, default_sector, seen_emails)

    wb.close()
    return result



if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "data/companies_sample.xlsx"
    res = read_companies(target)
    print(f"Total data rows: {res.total_rows}")
    print(f"Valid recipients: {res.valid_count}")
    print(f"Errors/skipped:  {res.error_count}")
    print("\n-- Recipients --")
    for r in res.recipients:
        print(f"  {r['company_name']:<20} {r['email']:<35} [{r['language']}]")
    print("\n-- Report --")
    for e in res.errors:
        print(f"  ! {e}")
