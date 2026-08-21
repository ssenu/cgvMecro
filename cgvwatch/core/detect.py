"""Qt에 의존하지 않는 순수 감지 전이 로직."""
from __future__ import annotations

from .models import Watch


def evaluate(watch: Watch, open_dates: set[str]) -> bool:
    """이번 조회에서 대상 날짜가 '새로' 열렸으면 True(알림 발송 대상)."""
    if watch.was_open:
        return False
    return watch.target_ymd in open_dates


def has_screen(showtimes: list[dict], keyword: str) -> bool:
    """관 이름에 키워드가 포함된 회차가 있는지 (대소문자 무시). 키워드 없으면 항상 True."""
    if not keyword:
        return True
    kw = keyword.strip().lower()
    return any(kw in s.get("screen", "").lower() for s in showtimes)
