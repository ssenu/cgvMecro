"""회차 선택. CGV·Playwright에 의존하지 않는 순수 로직."""
from __future__ import annotations

from typing import Optional


def pick_showtime(
    showtimes: list[dict],
    screen_filter: str,
    preferred_time: str,
) -> Optional[dict]:
    """관 필터에 맞는 회차 중 선호 시각에 가장 가까운 것. 선호 시각이 없으면 가장 이른 회차."""
    if not showtimes:
        return None
    candidates = showtimes
    if screen_filter:
        kw = screen_filter.strip().lower()
        candidates = [s for s in showtimes if kw in s.get("screen", "").lower()]
    if not candidates:
        return None
    if not preferred_time:
        return min(candidates, key=lambda s: s.get("start", ""))
    try:
        target = int(preferred_time)
    except ValueError:
        # 형식이 잘못된 값은 '선호 시각 없음'과 같게 취급한다.
        return min(candidates, key=lambda s: s.get("start", ""))
    return min(candidates, key=lambda s: abs(int(s.get("start") or 0) - target))
