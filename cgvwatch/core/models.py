"""도메인 모델과 상태 상수."""
from __future__ import annotations

from dataclasses import dataclass


class Status:
    WAITING = "대기중"
    OPEN = "열림"
    ERROR = "오류"


@dataclass
class Watch:
    id: str
    mov_no: str
    mov_nm: str
    site_no: str
    site_nm: str
    target_ymd: str  # YYYYMMDD
    status: str = Status.WAITING
    was_open: bool = False
    last_checked: str = ""


@dataclass
class Settings:
    gmail_user: str = ""
    recipient: str = ""
    interval_min: int = 5
