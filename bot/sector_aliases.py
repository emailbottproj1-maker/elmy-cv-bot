"""
Sector alias normaliser.

The client's company file may label sectors in Arabic, English, or a mix.
This module collapses any reasonable label to ONE of the 11 canonical codes
the UI/filter expect:

    Healthcare, Marketing, Technology, Finance, Engineering, Legal,
    Retail, Education, HR, Hospitality, Logistics

Usage:
    code = normalise_sector("صحة")          # -> "Healthcare"
    code = normalise_sector("IT")           # -> "Technology"
    code = normalise_sector("هندسه")        # -> "Engineering"  (typo-tolerant)
    code = normalise_sector("random junk")  # -> None  (caller decides what to do)

Matching strategy (in order):
    1. exact case-insensitive match in the alias table
    2. partial match: any alias appears as a substring of the input
    3. None  → caller can fall back to AI classification or "Unknown"
"""
from __future__ import annotations

import re
import unicodedata

# Canonical code -> list of accepted aliases (Arabic + English + variants).
# Keep lowercase + stripped of diacritics for matching.
ALIASES: dict[str, list[str]] = {
    "Healthcare": [
        "صحة", "صحه", "صحي", "صحيه", "الصحة", "الصحه",
        "healthcare", "health", "medical", "hospital", "clinic",
        "طبي", "طبيه", "مستشفى", "مستشفيات", "عيادات", "صيدلية", "صيدله",
        "pharma", "pharmacy", "biotech",
    ],
    "Marketing": [
        "تسويق", "اعلان", "إعلان", "اعلانات", "إعلانات", "تسويق واعلان",
        "تسويق وإعلان", "ديجيتال", "تسويق رقمي",
        "marketing", "advertising", "ads", "digital marketing", "branding",
        "agency", "media", "pr", "public relations",
    ],
    "Technology": [
        "تقنية", "تقنيه", "برمجة", "برمجه", "تكنولوجيا", "تقنية وبرمجة",
        "تقنيه وبرمجه", "معلوماتية", "معلوماتيه",
        "technology", "tech", "it", "software", "saas", "startup",
        "ai", "ml", "cyber", "cybersecurity", "data", "cloud", "platform",
    ],
    "Finance": [
        "مالية", "ماليه", "بنوك", "بنك", "مالية وبنوك", "بنوك ومالية",
        "محاسبة", "محاسبه", "تأمين", "تامين", "fintech", "استثمار",
        "finance", "financial", "bank", "banking", "accounting",
        "insurance", "investment", "wealth", "asset", "capital",
    ],
    "Engineering": [
        "هندسة", "هندسه", "مقاولات", "هندسة ومقاولات", "إنشاءات", "انشاءات",
        "بناء", "تشييد", "كهرباء", "ميكانيكا", "مدنية", "صناعية",
        "engineering", "construction", "contracting", "mep", "civil",
        "mechanical", "electrical", "industrial", "manufacturing",
        "petrochemical", "energy", "oil", "gas",
    ],
    "Legal": [
        "قانون", "قانونيه", "قانونية", "محاماة", "محاماه", "محامين",
        "استشارات قانونية", "استشاره قانونيه",
        "legal", "law", "attorney", "lawyer", "compliance",
    ],
    "Retail": [
        "تجزئة", "تجزئه", "تجارة", "تجاره", "تجارية", "تجاريه",
        "تجزئة وتجارة", "تسوق", "سوبرماركت", "هايبر", "متاجر",
        "retail", "trading", "commerce", "supermarket", "store",
        "shop", "mall", "wholesale", "fmcg", "ecommerce", "e-commerce",
    ],
    "Education": [
        "تعليم", "تعليمي", "تعليميه", "تعليمية", "مدارس", "مدرسة", "مدرسه",
        "جامعة", "جامعه", "جامعات", "تدريب", "كلية", "كليه",
        "education", "school", "university", "academy", "training",
        "edtech", "college", "institute", "k-12", "tutoring",
    ],
    "HR": [
        "موارد بشرية", "موارد بشريه", "الموارد البشرية", "توظيف", "استقطاب",
        "تطوير وظيفي", "hr", "human resources", "recruitment", "recruiting",
        "talent", "staffing", "headhunting", "people",
    ],
    "Hospitality": [
        "ضيافة", "ضيافه", "فنادق", "فندق", "ضيافة وفنادق", "سياحة", "سياحه",
        "مطاعم", "مطعم", "ترفيه",
        "hospitality", "hotel", "hotels", "tourism", "restaurant", "f&b",
        "food and beverage", "resort", "hostel", "catering", "entertainment",
    ],
    "Logistics": [
        "لوجستيك", "لوجستيات", "شحن", "نقل", "توصيل", "لوجستيك وشحن",
        "شحن ونقل", "مستودعات", "سلسلة توريد", "موانئ", "مطارات",
        "logistics", "shipping", "freight", "transport", "transportation",
        "delivery", "supply chain", "warehouse", "warehousing", "courier",
        "fulfillment", "trucking",
    ],
}

# Build a flat lookup table once at import.
_FLAT_LOOKUP: dict[str, str] = {}


def _strip_diacritics(text: str) -> str:
    """Remove Arabic tashkeel + general unicode diacritics."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if not unicodedata.combining(c))


def _normalise_key(text: str) -> str:
    """Lowercase, strip diacritics, collapse spaces, drop punctuation."""
    if text is None:
        return ""
    s = _strip_diacritics(str(text)).lower().strip()
    # collapse separators (slashes, dashes, &, +, multiple spaces)
    s = re.sub(r"[\s/\-+&,؛]+", " ", s)
    # drop leading "ال" article variations are tricky — leave them; matching
    # the bare form already covers the common case.
    return s.strip()


for canonical, words in ALIASES.items():
    # canonical itself is an alias of itself
    for w in [canonical] + words:
        _FLAT_LOOKUP[_normalise_key(w)] = canonical


def normalise_sector(value: str | None) -> str | None:
    """Return the canonical code for a sector label, or None if unrecognised."""
    if value is None:
        return None
    key = _normalise_key(value)
    if not key:
        return None

    # 1) exact match
    if key in _FLAT_LOOKUP:
        return _FLAT_LOOKUP[key]

    # 2) substring match (handles e.g. "Tech & SaaS" -> Technology;
    #    or "شركة هندسة مدنية" -> Engineering). We check the LONGEST
    #    known aliases first so "marketing agency" matches Marketing rather
    #    than a generic "agency" (which isn't in the table anyway).
    for alias in sorted(_FLAT_LOOKUP.keys(), key=len, reverse=True):
        if len(alias) >= 3 and alias in key:
            return _FLAT_LOOKUP[alias]

    return None


def categorize_rows(rows: list[dict], sector_field: str = "sector") -> dict:
    """Apply normalise_sector across a list of recipients.

    Returns:
        {
          "matched":   int,  # rows whose sector matched a canonical code
          "missing":   int,  # rows with an empty sector cell
          "unknown":   int,  # rows whose sector did NOT match (kept verbatim)
          "by_sector": {code: count, ...},   # canonical distribution
          "unknown_labels": {label: count},  # for the user to review
        }

    Mutates each row by setting `row[sector_field]` to the canonical code when
    matched. Leaves it as-is when unknown (caller decides AI / manual).
    """
    out = {
        "matched": 0,
        "missing": 0,
        "unknown": 0,
        "by_sector": {},
        "unknown_labels": {},
    }
    for r in rows:
        raw = r.get(sector_field)
        if raw is None or str(raw).strip() == "":
            out["missing"] += 1
            continue
        canon = normalise_sector(raw)
        if canon:
            r[sector_field] = canon
            out["matched"] += 1
            out["by_sector"][canon] = out["by_sector"].get(canon, 0) + 1
        else:
            out["unknown"] += 1
            label = str(raw).strip()
            out["unknown_labels"][label] = (
                out["unknown_labels"].get(label, 0) + 1
            )
    return out


if __name__ == "__main__":
    # quick smoke test
    cases = {
        "صحة": "Healthcare",
        "الصحة": "Healthcare",
        "Marketing & Advertising": "Marketing",
        "تسويق رقمي": "Marketing",
        "IT": "Technology",
        "Software / SaaS": "Technology",
        "Banking": "Finance",
        "هندسة مدنية": "Engineering",
        "Law Firm": "Legal",
        "E-commerce": "Retail",
        "K-12 School": "Education",
        "Human Resources": "HR",
        "Hotel": "Hospitality",
        "Freight & Shipping": "Logistics",
        "random nonsense": None,
        "": None,
        None: None,
    }
    failed = []
    for inp, expected in cases.items():
        got = normalise_sector(inp)
        ok = got == expected
        mark = "ok" if ok else "FAIL"
        print(f"  [{mark}] {inp!r} -> {got!r}  (expected {expected!r})")
        if not ok:
            failed.append((inp, got, expected))
    print()
    rows = [
        {"company_name": "A", "sector": "صحة"},
        {"company_name": "B", "sector": "IT"},
        {"company_name": "C", "sector": "random"},
        {"company_name": "D", "sector": ""},
    ]
    rep = categorize_rows(rows)
    print("categorize_rows report:", rep)
    print("rows after:", [(r["company_name"], r["sector"]) for r in rows])
    if failed:
        raise SystemExit(f"{len(failed)} alias test(s) failed")
    print("\nOK - sector alias map passes all smoke tests")
