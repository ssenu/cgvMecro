"""디스코드 웹훅 알림. 웹훅 URL은 DISCORD_WEBHOOK_URL 환경변수로 주입한다."""
from __future__ import annotations

import os
from typing import Callable
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


def build_message(watch: Watch) -> str:
    ymd = watch.target_ymd
    date = f"{ymd[4:6]}/{ymd[6:8]}"
    return (
        f"🎬 **{watch.mov_nm}**\n"
        f"{watch.site_nm} {date} 예매가 열렸습니다!\n"
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
        raise RuntimeError(f"{WEBHOOK_ENV} 환경변수가 설정되지 않았습니다.")
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
