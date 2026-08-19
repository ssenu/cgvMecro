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
    last_error: str = ""  # 오류 상태일 때의 실패 원인 (정상 복귀 시 빈 문자열)


@dataclass
class Settings:
    interval_sec: int = 300
