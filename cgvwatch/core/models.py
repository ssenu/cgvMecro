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
    screen_filter: str = ""  # 관 이름 키워드 (예: IMAX). 빈 값이면 아무 관이나 열리면 알림
    mode: str = "onopen"  # "now": 이미 열린 회차를 지금부터 노림 / "onopen": 열리면 그때 헌팅
    hunt_enabled: bool = False  # 좌석 확보까지 자동으로 진행할지
    seat_count: int = 1  # 1 또는 2
    row_offset: int = 1  # 중앙 기준 뒤쪽으로 몇 열
    preferred_time: str = ""  # HHMM, 빈 값이면 가장 이른 회차
    status: str = Status.WAITING
    was_open: bool = False
    last_checked: str = ""
    last_error: str = ""  # 오류 상태일 때의 실패 원인 (정상 복귀 시 빈 문자열)


@dataclass
class Settings:
    interval_sec: int = 300
