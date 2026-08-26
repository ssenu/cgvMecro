"""디스코드 웹훅 알림. 웹훅 URL은 DISCORD_WEBHOOK_URL 환경변수로 주입한다."""
from __future__ import annotations

import os
from typing import Callable
from urllib.parse import quote

import requests

from cgvwatch.core.models import Settings, Watch

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"


class WebhookNotConfigured(RuntimeError):
    """웹훅 URL이 아예 설정되지 않았다.

    '보내려다 실패한 것'이 아니라 '보낼 곳이 없는 것'이므로,
    호출부는 이 예외를 알림 건너뛰기로 처리해도 된다.
    """


def booking_url(watch: Watch) -> str:
    """영화·극장·날짜가 미리 선택된 CGV 예매 페이지 딥링크."""
    return (
        "https://cgv.co.kr/cnm/movieBook/movie"
        f"?movNo={watch.mov_no}&scnYmd={watch.target_ymd}"
        f"&siteNo={watch.site_no}&siteNm={quote(watch.site_nm)}"
    )


def build_message(watch: Watch) -> str:
    ymd = watch.target_ymd
    date = f"{ymd[4:6]}/{ymd[6:8]}"
    screen = f" {watch.screen_filter}" if watch.screen_filter else ""
    return (
        f"🎬 **{watch.mov_nm}**\n"
        f"{watch.site_nm} {date}{screen} 예매가 열렸습니다!\n"
        f"👉 바로 예매하기 (시간대만 고르면 좌석 선택으로 넘어갑니다)\n"
        f"{booking_url(watch)}"
    )


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
        raise WebhookNotConfigured(f"{WEBHOOK_ENV} 환경변수가 설정되지 않았습니다.")
    resp = post(url, json={"content": content}, timeout=10)
    resp.raise_for_status()


def send_open_alert(
    watch: Watch,
    settings: Settings,
    post: Callable = requests.post,
) -> None:
    """예매 오픈 알림 발송. 미설정/HTTP 오류 시 예외를 던진다(호출부에서 재시도 처리)."""
    _send(build_message(watch), post)


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


def send_seat_secured(
    watch: Watch,
    settings: Settings,
    seats: list[str],
    showtime: dict,
    post: Callable = requests.post,
) -> None:
    """좌석 확보 알림. 결제는 사람이 해야 한다는 것을 분명히 적는다."""
    ymd = watch.target_ymd
    date = f"{ymd[4:6]}/{ymd[6:8]}"
    start = showtime.get("start", "")
    hhmm = f"{start[:2]}:{start[2:]}" if len(start) == 4 else start
    content = (
        f"🎟️ **좌석 확보! {watch.mov_nm}**\n"
        f"{watch.site_nm} {date} {hhmm} {showtime.get('screen', '')}\n"
        f"좌석: {', '.join(seats)}\n"
        f"⏳ 브라우저에서 **결제를 직접 진행**해 주세요. 시간이 지나면 좌석이 풀립니다."
    )
    _send(content, post)


def send_structure_warning(
    watch: Watch,
    settings: Settings,
    detail: str,
    post: Callable = requests.post,
) -> None:
    """CGV 화면 구조가 바뀐 것으로 의심될 때."""
    content = (
        f"🔧 **화면 구조 변경 의심** ({watch.mov_nm} / {watch.site_nm})\n"
        f"{detail}\n"
        f"selectors.py를 최신 화면에 맞게 확인해야 합니다."
    )
    _send(content, post)


def send_login_required(
    settings: Settings,
    post: Callable = requests.post,
) -> None:
    """브라우저 세션이 없어 헌팅을 시작할 수 없을 때."""
    _send(
        "🔑 **CGV 로그인이 필요합니다**\n"
        "웹 UI에서 브라우저를 열고 로그인해 주세요. 좌석 확보가 대기 중입니다.",
        post,
    )
