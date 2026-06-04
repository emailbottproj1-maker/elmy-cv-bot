"""
Cover-letter language selection + placeholder rendering.

Loads the AR and EN cover-letter templates once, then renders the correct one
per recipient based on their `language` field. Placeholders use {name} syntax
and unknown placeholders are left intact (never crashes on a typo).
"""
from __future__ import annotations

import os
import re
from typing import Any

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class LanguageHandler:
    def __init__(self, ar_path: str, en_path: str, default_lang: str = "en"):
        self.default_lang = default_lang if default_lang in ("ar", "en") else "en"
        self._templates: dict[str, str] = {}

        # English is required; Arabic is optional (falls back to English).
        self._templates["en"] = self._load(en_path, required=True, label="English")
        ar = self._load(ar_path, required=False, label="Arabic")
        self._templates["ar"] = ar if ar is not None else self._templates["en"]

    @staticmethod
    def _load(path: str, required: bool, label: str) -> str | None:
        if not path or not os.path.exists(path):
            if required:
                raise FileNotFoundError(f"{label} cover letter not found: {path}")
            return None
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if not text:
            if required:
                raise ValueError(f"{label} cover letter is empty: {path}")
            return None
        return text

    def is_rtl(self, lang: str) -> bool:
        return lang == "ar"

    def render(self, recipient: dict[str, Any], sender_name: str) -> tuple[str, bool]:
        """Return (rendered_body, is_rtl) for a recipient.

        Substitutes {company_name}, {sender_name}, and any extra columns.
        Unknown placeholders are left as-is.
        """
        lang = recipient.get("language", self.default_lang)
        if lang not in self._templates:
            lang = self.default_lang
        template = self._templates[lang]

        values = dict(recipient)
        values["sender_name"] = sender_name

        def repl(match: re.Match) -> str:
            key = match.group(1)
            val = values.get(key)
            return str(val) if val is not None else match.group(0)

        body = PLACEHOLDER_RE.sub(repl, template)
        return body, self.is_rtl(lang)


if __name__ == "__main__":
    lh = LanguageHandler("data/cover_letter_ar.txt", "data/cover_letter_en.txt")
    en_body, en_rtl = lh.render(
        {"company_name": "Acme Corp", "language": "en"}, "Youssef Dagher"
    )
    ar_body, ar_rtl = lh.render(
        {"company_name": "شركة النور", "language": "ar"}, "يوسف"
    )
    print("=== EN (rtl:", en_rtl, ") ===")
    print(en_body)
    print("\n=== AR (rtl:", ar_rtl, ") ===")
    print(ar_body)
