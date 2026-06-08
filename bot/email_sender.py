"""
Email sender (Gmail SMTP).

Builds a personalized multipart email (plain-text + HTML), attaches the CV PDF,
injects the tracking pixel, and sends via Gmail's SMTP server using an App
Password. Designed to be created once and reused across many sends (one
connection reused, reconnect on failure).
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from typing import Any, Optional

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 587  # STARTTLS


class EmailConfigError(Exception):
    """Raised for bad/missing configuration (caught by the GUI)."""


class EmailSender:
    def __init__(
        self,
        gmail_address: str,
        app_password: str,
        sender_name: str,
        cv_path: str,
        subject_ar: str = "طلب توظيف - سيرة ذاتية",
        subject_en: str = "Job Application - CV",
    ):
        if not gmail_address or "@" not in gmail_address:
            raise EmailConfigError("عنوان Gmail غير صالح.")
        if not app_password:
            raise EmailConfigError("App Password مفقود.")

        self.gmail_address = gmail_address.strip()
        # Gmail app passwords are shown with spaces; strip them.
        self.app_password = app_password.replace(" ", "").strip()
        self.sender_name = sender_name or gmail_address
        self.cv_path = cv_path
        self.subject_ar = subject_ar
        self.subject_en = subject_en

        self._cv_bytes: Optional[bytes] = None
        self._cv_filename: str = "CV.pdf"
        self._server: Optional[smtplib.SMTP] = None
        self._load_cv()

    # ---------- setup ----------
    def _load_cv(self) -> None:
        import os

        if not self.cv_path or not os.path.exists(self.cv_path):
            raise EmailConfigError(f"ملف الـ CV غير موجود: {self.cv_path}")
        with open(self.cv_path, "rb") as f:
            self._cv_bytes = f.read()
        if not self._cv_bytes:
            raise EmailConfigError("ملف الـ CV فارغ.")
        self._cv_filename = os.path.basename(self.cv_path) or "CV.pdf"

    # ---------- connection ----------
    def connect(self) -> None:
        """Open (or reopen) an authenticated SMTP connection."""
        context = ssl.create_default_context()
        server = smtplib.SMTP(GMAIL_HOST, GMAIL_PORT, timeout=30)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        try:
            server.login(self.gmail_address, self.app_password)
        except smtplib.SMTPAuthenticationError as exc:
            server.close()
            raise EmailConfigError(
                "فشل تسجيل الدخول إلى Gmail. تأكد من صحة الإيميل و App Password "
                "وأن خاصية 2-Step Verification مفعّلة."
            ) from exc
        self._server = server

    def _ensure_connection(self) -> None:
        if self._server is None:
            self.connect()
            return
        # NOOP to check liveness; reconnect if dropped.
        try:
            status = self._server.noop()[0]
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPException, OSError):
            status = -1
        if status != 250:
            try:
                self._server.close()
            except Exception:
                pass
            self.connect()

    def verify_login(self) -> None:
        """Connect + login only, to validate credentials from the GUI."""
        self.connect()
        self.close()

    # ---------- message building ----------
    def _build_message(
        self,
        recipient: dict[str, Any],
        html_body: str,
        text_body: str,
    ) -> MIMEMultipart:
        lang = recipient.get("language", "en")
        subject_tpl = self.subject_ar if lang == "ar" else self.subject_en
        # Subject can also use {company_name}
        subject = subject_tpl.replace("{company_name}", recipient.get("company_name", ""))

        # 'mixed' wraps the alternative (text/html) body + the PDF attachment.
        msg = MIMEMultipart("mixed")
        msg["From"] = formataddr((str(self.sender_name), self.gmail_address))
        msg["To"] = recipient["email"]
        msg["Reply-To"] = formataddr((str(self.sender_name), self.gmail_address))
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=self.gmail_address.split("@")[-1])
        msg["X-Mailer"] = "Elmy CV Bot"
        msg["Importance"] = "Normal"
        msg["X-Priority"] = "3"

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(text_body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        msg.attach(alt)

        pdf = MIMEApplication(self._cv_bytes, _subtype="pdf")
        pdf.add_header("Content-Disposition", "attachment", filename=self._cv_filename)
        msg.attach(pdf)
        return msg

    @staticmethod
    def text_to_html(text_body: str, is_rtl: bool, pixel_html: str = "") -> str:
        """Wrap a plain-text cover letter into a clean HTML email."""
        # Escape minimal HTML special chars, preserve line breaks.
        escaped = (
            text_body.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>\n")
        )
        direction = "rtl" if is_rtl else "ltr"
        align = "right" if is_rtl else "left"
        return (
            f'<!DOCTYPE html><html dir="{direction}"><head>'
            f'<meta charset="utf-8"></head>'
            f'<body style="margin:0;padding:0;">'
            f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
            f'line-height:1.7;color:#222;direction:{direction};text-align:{align};'
            f'max-width:600px;">'
            f"{escaped}"
            f"</div>{pixel_html}</body></html>"
        )

    # ---------- send ----------
    def send(
        self,
        recipient: dict[str, Any],
        text_body: str,
        is_rtl: bool,
        pixel_html: str = "",
    ) -> None:
        """Send to a single recipient. Raises on failure (caller decides retry)."""
        html_body = self.text_to_html(text_body, is_rtl, pixel_html)
        msg = self._build_message(recipient, html_body, text_body)

        self._ensure_connection()
        assert self._server is not None
        try:
            self._server.send_message(msg)
        except smtplib.SMTPServerDisconnected:
            # one transparent retry after reconnect
            self.connect()
            assert self._server is not None
            self._server.send_message(msg)

    def close(self) -> None:
        if self._server is not None:
            try:
                self._server.quit()
            except Exception:
                try:
                    self._server.close()
                except Exception:
                    pass
            self._server = None


if __name__ == "__main__":
    # Build-only test (no network): verify message assembly works.
    import os

    # create a tiny fake PDF
    os.makedirs("data", exist_ok=True)
    fake = "data/_fake_cv.pdf"
    with open(fake, "wb") as f:
        f.write(b"%PDF-1.4 fake cv for test")

    sender = EmailSender(
        gmail_address="test@gmail.com",
        app_password="abcd efgh ijkl mnop",
        sender_name="Youssef Dagher",
        cv_path=fake,
    )
    html = EmailSender.text_to_html("Dear Acme,\nHello.", is_rtl=False,
                                    pixel_html='<img src="x">')
    msg = sender._build_message(
        {"company_name": "Acme", "email": "to@x.com", "language": "en"},
        html, "Dear Acme,\nHello.",
    )
    print("Subject:", msg["Subject"])
    print("From:", msg["From"])
    print("To:", msg["To"])
    print("Parts:", [p.get_content_type() for p in msg.walk()])
    print("App password stripped:", sender.app_password)
    os.remove(fake)
    print("OK - message build test passed")
