"""디스코드 웹훅 알림. 웹훅 URL은 DISCORD_WEBHOOK_URL 환경변수로 주입한다."""
from __future__ import annotations

import os
from typing import Callable, Optional
from urllib.parse import quote

import requests

from cgvwatch.core.models import Settings, Watch

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"


def booking_url(watch: Watch) -> str:
    """영화·극장·날짜가 미리 선택된 CGV 예매 페이지 딥링크."""
    return (
        "https://cgv.co.kr/cnm/movieBook/movie"
        f"?movNo={watch.mov_no}&scnYmd={watch.target_ymd}"
        f"&siteNo={watch.site_no}&siteNm={quote(watch.site_nm)}"
    )


def build_message(watch: Watch, showtimes: Optional[list[dict]] = None) -> str:
    ymd = watch.target_ymd
    date = f"{ymd[4:6]}/{ymd[6:8]}"
    lines = [
        f"🎬 **{watch.mov_nm}**",
        f"{watch.site_nm} {date} 예매가 열렸습니다!",
    ]
    for s in (showtimes or [])[:10]:
        t = s.get("start", "")
        hhmm = f"{t[:2]}:{t[2:]}" if len(t) == 4 else t
        seats = f" · 잔여 {s['free_seats']}석" if s.get("free_seats") else ""
        lines.append(f"🕒 {hhmm} {s.get('screen', '')}{seats}")
    lines += [
        "👉 바로 예매하기 (시간대만 고르면 좌석 선택으로 넘어갑니다)",
        booking_url(watch),
    ]
    return "\n".join(lines)


def build_created_message(watch: Watch) -> str:
    ymd = watch.target_ymd
    date = f"{ymd[4:6]}/{ymd[6:8]}"
    return (
        f"📝 **{watch.mov_nm}**\n"
        f"{watch.site_nm} {date} 감시가 등록되었습니다. 예매가 열리면 알려드릴게요."
    )


def _send(content: str, post: Callable) -> None:
    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if not url:
        raise RuntimeError(f"{WEBHOOK_ENV} 환경변수가 설정되지 않았습니다.")
    resp = post(url, json={"content": content}, timeout=10)
    resp.raise_for_status()


def build_showtime_buttons(watch: Watch, showtimes: list[dict]) -> list[dict]:
    """회차별 링크 버튼(action row 목록). 한 줄 최대 5개, 최대 2줄(10개)."""
    url = booking_url(watch)
    buttons = []
    for s in showtimes[:10]:
        t = s.get("start", "")
        hhmm = f"{t[:2]}:{t[2:]}" if len(t) == 4 else t
        seats = f" · {s['free_seats']}석" if s.get("free_seats") else ""
        label = f"{hhmm} {s.get('screen', '')}{seats}"[:80]
        buttons.append({"type": 2, "style": 5, "label": label, "url": url})
    return [
        {"type": 1, "components": buttons[i:i + 5]}
        for i in range(0, len(buttons), 5)
    ]


def send_open_alert(
    watch: Watch,
    settings: Settings,
    showtimes: Optional[list[dict]] = None,
    post: Callable = requests.post,
) -> None:
    """예매 오픈 알림 발송. 미설정/HTTP 오류 시 예외를 던진다(호출부에서 재시도 처리)."""
    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if not url:
        raise RuntimeError(f"{WEBHOOK_ENV} 환경변수가 설정되지 않았습니다.")
    if showtimes:
        # 일반 웹훅도 링크 버튼은 with_components=true 로 전송 가능.
        # 버튼이 회차 목록을 대신하므로 본문에는 🕒 줄을 넣지 않는다.
        sep = "&" if "?" in url else "?"
        payload = {
            "content": build_message(watch, None),
            "components": build_showtime_buttons(watch, showtimes),
        }
        resp = post(f"{url}{sep}with_components=true", json=payload, timeout=10)
        if resp.status_code < 400:
            return
        # 버튼이 거부되면(정책 변경 등) 회차를 텍스트로 담아 재시도해 알림 자체는 보장한다.
    resp = post(url, json={"content": build_message(watch, showtimes)}, timeout=10)
    resp.raise_for_status()


def send_error_alert(
    watch: Watch,
    settings: Settings,
    reason: str,
    post: Callable = requests.post,
) -> None:
    """감시가 정상 작동하다 오류로 멈췄을 때의 경고. 실패 시 예외(호출부에서 무시)."""
    ymd = watch.target_ymd
    date = f"{ymd[4:6]}/{ymd[6:8]}"
    content = (
        f"⚠️ **{watch.mov_nm}**\n"
        f"{watch.site_nm} {date} 감시가 오류로 멈췄습니다.\n"
        f"원인: {reason}\n"
        f"자동으로 재시도하며, 복구되면 감시가 계속됩니다."
    )
    _send(content, post)


def send_created_alert(
    watch: Watch,
    settings: Settings,
    post: Callable = requests.post,
) -> None:
    """감시 등록 알림 발송. 미설정/HTTP 오류 시 예외를 던진다(호출부에서 무시 가능)."""
    _send(build_created_message(watch), post)
