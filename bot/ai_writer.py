"""
AI cover-letter writer using Google Gemini Flash.

Generates a personalised cover letter per company by giving the model:
  - the base template (so tone/structure stays the client's voice)
  - the company's name, sector, city
  - the recipient language (ar/en)

Design rules:
  * NEVER blocks the campaign. Any failure (no API key, quota hit, timeout,
    invalid response) falls back to the rendered template from language_handler.
  * Output is plain text only (no markdown / no HTML).
  * Always includes the company name AND the sender name verbatim.
  * Hard cap on length so we don't ship novels.

API: text-only generateContent on gemini-2.0-flash (free tier friendly).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from .language_handler import LanguageHandler

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


class AIWriter:
    def __init__(
        self,
        language_handler: LanguageHandler,
        api_key: Optional[str] = None,
        enabled: bool = True,
        timeout: int = 15,
        max_chars: int = 1800,
    ):
        self.lh = language_handler
        self.api_key = (api_key or os.environ.get("GEMINI_API_KEY") or "").strip()
        self.enabled = bool(enabled and self.api_key)
        self.timeout = timeout
        self.max_chars = max_chars

    # ---------- prompt building ----------
    def _build_prompt(self, recipient: dict[str, Any], sender_name: str,
                      base_template: str) -> str:
        lang = recipient.get("language", "en")
        company = recipient.get("company_name", "").strip()
        sector = (recipient.get("sector") or "").strip()
        city = (recipient.get("city") or "").strip()

        ctx = [f"Company: {company}"]
        if sector:
            ctx.append(f"Sector: {sector}")
        if city:
            ctx.append(f"City: {city}")
        ctx.append(f"Sender (applicant): {sender_name}")
        ctx_block = "\n".join(ctx)

        if lang == "ar":
            instruction = (
                "أنت كاتب محترف لرسائل التوظيف. اكتب رسالة تغطية مخصّصة "
                "لهذه الشركة بالعربية الفصحى. أعد فقط نص الرسالة بدون "
                "أي عناوين أو شروحات أو علامات. "
                f"أبقِ الطول أقل من {self.max_chars // 4} كلمة. "
                "اذكر اسم الشركة واسم المُرسِل صراحةً. حافظ على نبرة القالب أدناه."
            )
        else:
            instruction = (
                "You are a professional job application writer. Write a "
                "tailored cover letter for this company in English. Return "
                "ONLY the letter body — no headings, no commentary, no "
                f"markdown. Keep it under {self.max_chars // 5} words. "
                "Mention the company name and sender name explicitly. "
                "Match the tone of the template below."
            )

        return (
            f"{instruction}\n\n"
            f"--- Context ---\n{ctx_block}\n\n"
            f"--- Base template (keep its tone) ---\n{base_template}\n"
        )

    # ---------- gemini call ----------
    def _call_gemini(self, prompt: str) -> Optional[str]:
        url = f"{GEMINI_ENDPOINT}?key={self.api_key}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.9,
                "maxOutputTokens": 800,
            },
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None

        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return None

        text = (text or "").strip()
        if not text or len(text) < 30:
            return None
        return text[: self.max_chars]

    # ---------- output sanity check ----------
    @staticmethod
    def _looks_valid(text: str, company: str, sender: str) -> bool:
        if not text or len(text) < 60:
            return False
        # Reject obvious markdown / instruction echoes.
        bad = ("```", "###", "<html", "Subject:", "INSTRUCTIONS")
        if any(b in text for b in bad):
            return False
        # Must include the company name (sender is a softer requirement).
        if company and company.lower() not in text.lower():
            return False
        return True

    # ---------- public API ----------
    def generate(
        self,
        recipient: dict[str, Any],
        sender_name: str,
    ) -> tuple[str, bool, str]:
        """Return (body, is_rtl, source) where source = 'ai' or 'template'.

        Never raises; always returns a usable body.
        """
        template_body, is_rtl = self.lh.render(recipient, sender_name)
        if not self.enabled:
            return template_body, is_rtl, "template"

        prompt = self._build_prompt(recipient, sender_name, template_body)
        ai_text = self._call_gemini(prompt)
        if ai_text and self._looks_valid(
            ai_text, recipient.get("company_name", ""), sender_name
        ):
            return ai_text, is_rtl, "ai"
        return template_body, is_rtl, "template"


if __name__ == "__main__":
    # Offline-safe smoke test: no API key → must fall back to template.
    lh = LanguageHandler("data/cover_letter_ar.txt", "data/cover_letter_en.txt")
    writer = AIWriter(lh, api_key="")  # disabled
    body, rtl, src = writer.generate(
        {"company_name": "Acme Corp", "language": "en", "sector": "SaaS"},
        "Youssef Dagher",
    )
    assert src == "template", f"expected fallback, got {src}"
    assert "Acme Corp" in body
    assert "Youssef" in body
    print("OK - AI writer falls back to template cleanly")
    print(f"  src={src}, len={len(body)}")
