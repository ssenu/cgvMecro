"""Qt에 의존하지 않는 순수 감지 전이 로직."""
from __future__ import annotations

from .models import Watch


def evaluate(watch: Watch, open_dates: set[str]) -> bool:
    """이번 조회에서 대상 날짜가 '새로' 열렸으면 True(알림 발송 대상)."""
    if watch.was_open:
        return False
    return watch.target_ymd in open_dates


def filter_showtimes(showtimes: list[dict], time_from: str, time_to: str) -> list[dict]:
    """시작시각(HHMM)이 [time_from, time_to] 범위(양끝 포함)인 회차만. 범위 미설정 시 전체."""
    if not time_from and not time_to:
        return showtimes
    lo = time_from or "0000"
    hi = time_to or "2959"  # 심야(24시 이후 표기) 포함
    return [s for s in showtimes if lo <= s.get("start", "") <= hi]
