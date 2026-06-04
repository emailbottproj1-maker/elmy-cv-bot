"""
Rate limiting helpers (pure logic, no I/O).

Kept separate so it can be unit-tested deterministically. The campaign engine
calls these to decide how long to wait and whether the daily cap is hit.
"""
from __future__ import annotations

import random


class RateLimiter:
    def __init__(self, min_delay: float, max_delay: float, daily_cap: int):
        if min_delay < 0 or max_delay < 0:
            raise ValueError("delays must be >= 0")
        if min_delay > max_delay:
            min_delay, max_delay = max_delay, min_delay
        self.min_delay = float(min_delay)
        self.max_delay = float(max_delay)
        self.daily_cap = int(daily_cap)

    def next_delay(self) -> float:
        """Random seconds to wait before the next email (anti-spam jitter)."""
        return random.uniform(self.min_delay, self.max_delay)

    def cap_reached(self, sent_today: int) -> bool:
        return self.daily_cap > 0 and sent_today >= self.daily_cap

    def remaining_today(self, sent_today: int) -> int:
        if self.daily_cap <= 0:
            return 1_000_000  # effectively unlimited
        return max(0, self.daily_cap - sent_today)

    @staticmethod
    def backoff_delay(attempt: int, base: float = 300.0, cap: float = 1800.0) -> float:
        """Exponential backoff for SMTP failures: 5min, 10min, ... capped 30min."""
        return min(cap, base * (2 ** max(0, attempt - 1)))


if __name__ == "__main__":
    rl = RateLimiter(60, 180, 50)
    print("sample delays:", [round(rl.next_delay(), 1) for _ in range(5)])
    print("cap reached at 50?", rl.cap_reached(50))
    print("cap reached at 49?", rl.cap_reached(49))
    print("remaining at 30:", rl.remaining_today(30))
    print("backoff:", [rl.backoff_delay(a) for a in (1, 2, 3, 4)])
    print("OK - rate limiter test passed")
