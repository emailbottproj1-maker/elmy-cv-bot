"""
Tracking pixel helpers.

Builds the 1x1 pixel <img> tag pointing at the Vercel service, and fetches
aggregated open stats back from that service for the dashboard.
"""
from __future__ import annotations

from typing import Any

import requests


class Tracker:
    def __init__(self, base_url: str, stats_token: str = ""):
        self.base_url = (base_url or "").rstrip("/")
        self.stats_token = stats_token

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def pixel_html(self, tracking_uuid: str) -> str:
        """Return an <img> tag to embed at the end of the email HTML body."""
        if not self.enabled:
            return ""
        url = f"{self.base_url}/api/pixel?id={tracking_uuid}"
        # Hidden, no border, fixed 1x1. alt empty so screen readers ignore it.
        return (
            f'<img src="{url}" width="1" height="1" alt="" '
            f'style="display:none;width:1px;height:1px;border:0;" />'
        )

    def fetch_opens(self, timeout: int = 15) -> list[dict[str, Any]]:
        """Fetch opens from the Vercel /api/stats endpoint.

        Expected JSON: {"opens": [{tracking_uuid, first_open_at, open_count,
        last_seen_at}, ...]}. Returns [] on any failure (never raises).
        """
        if not self.enabled:
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/api/stats",
                params={"token": self.stats_token},
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("opens", [])
        except (requests.RequestException, ValueError):
            return []


if __name__ == "__main__":
    t = Tracker("https://elmy-pixel.vercel.app", "secret")
    print(t.pixel_html("abc123"))
    t2 = Tracker("")  # disabled
    print("disabled pixel ->", repr(t2.pixel_html("abc123")))
