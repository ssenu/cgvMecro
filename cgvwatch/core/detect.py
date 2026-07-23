"""Qt에 의존하지 않는 순수 감지 전이 로직."""
from __future__ import annotations

from .models import Watch


def evaluate(watch: Watch, open_dates: set[str]) -> bool:
    """이번 조회에서 대상 날짜가 '새로' 열렸으면 True(메일 발송 대상)."""
    if watch.was_open:
        return False
    return watch.target_ymd in open_dates
