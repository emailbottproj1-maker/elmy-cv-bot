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
    "company_name": "company_name",
    "company": "company_name",
    "company name": "company_name",
    "الشركة": "company_name",
    "اسم الشركة": "company_name",
    "email": "email",
    "e-mail": "email",
    "mail": "email",
    "الايميل": "email",
    "الإيميل": "email",
    "البريد": "email",
    "language": "language",
    "lang": "language",
    "اللغة": "language",
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


def read_companies(path: str, default_lang: str = "en") -> ReadResult:
    """Read and validate an Excel file. Never raises on bad rows; collects them."""
    result = ReadResult()

    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except FileNotFoundError:
        result.errors.append(f"الملف غير موجود: {path}")
        return result
    except Exception as exc:  # corrupt file, wrong format, etc.
        result.errors.append(f"تعذّر فتح ملف Excel: {exc}")
        return result

    ws = wb.active
    rows = ws.iter_rows(values_only=True)

    # --- header row ---
    try:
        header = next(rows)
    except StopIteration:
        result.errors.append("الملف فارغ.")
        wb.close()
        return result

    col_index: dict[str, int] = {}
    for idx, cell in enumerate(header):
        canon = _normalize_header(cell)
        if canon and canon not in col_index:
            col_index[canon] = idx

    missing = [c for c in REQUIRED if c not in col_index]
    if missing:
        result.errors.append(
            "الأعمدة المطلوبة مفقودة: " + ", ".join(missing)
            + ". يجب أن يحتوي الملف على عمودي company_name و email."
        )
        wb.close()
        return result

    seen_emails: set[str] = set()

    # --- data rows ---
    for row_num, row in enumerate(rows, start=2):
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue  # skip fully empty rows silently

        result.total_rows += 1

        def get(col: str) -> str:
            i = col_index.get(col)
            if i is None or i >= len(row) or row[i] is None:
                return ""
            return str(row[i]).strip()

        company = get("company_name")
        email = get("email").lower()
        lang = get("language").lower() or default_lang

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
            if canon in ("company_name", "email", "language"):
                continue
            if i < len(row) and row[i] is not None:
                extra[canon] = str(row[i]).strip()

        recipient = {
            "company_name": company,
            "email": email,
            "language": lang,
            **extra,
        }
        result.recipients.append(recipient)

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
