"""
Settings persistence for the GUI.

Stores user settings (paths, Gmail creds, subjects, delays) in a local JSON file
next to the data dir. This file is gitignored — it lives only on the client's
machine. The app password is stored here too (local-only, never committed).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

CONFIG_PATH = "data/config.json"


@dataclass
class Settings:
    gmail_address: str = ""
    app_password: str = ""
    sender_name: str = ""
    subject_ar: str = "طلب توظيف - سيرة ذاتية"
    subject_en: str = "Job Application - CV"

    cv_path: str = ""
    cover_letter_ar: str = "data/cover_letter_ar.txt"
    cover_letter_en: str = "data/cover_letter_en.txt"
    companies_xlsx: str = ""

    pixel_base_url: str = ""
    stats_token: str = ""

    daily_cap: int = 50
    min_delay: int = 60
    max_delay: int = 180
    default_lang: str = "en"

    def save(self, path: str = CONFIG_PATH) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "Settings":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            return cls()
        # only keep known fields (forward/backward compatible)
        known = {f for f in cls().__dict__}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)


if __name__ == "__main__":
    s = Settings(gmail_address="a@gmail.com", sender_name="يوسف")
    s.save("data/_cfg_test.json")
    s2 = Settings.load("data/_cfg_test.json")
    assert s2.gmail_address == "a@gmail.com"
    assert s2.sender_name == "يوسف"
    assert s2.daily_cap == 50
    os.remove("data/_cfg_test.json")
    print("OK - config save/load test passed")
