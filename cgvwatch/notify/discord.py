"""디스코드 웹훅 알림. 웹훅 URL은 DISCORD_WEBHOOK_URL 환경변수로 주입한다."""
from __future__ import annotations

import os
from typing import Callable

import requests

from cgvwatch.core.models import Settings, Watch

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"


def build_message(watch: Watch) -> str:
    ymd = watch.target_ymd
    date = f"{ymd[4:6]}/{ymd[6:8]}"
    return (
        f"🎬 **{watch.mov_nm}**\n"
        f"{watch.site_nm} {date} 예매가 열렸습니다!\n"
        f"https://cgv.co.kr"
    )


def send_open_alert(
    watch: Watch,
    settings: Settings,
    post: Callable = requests.post,
) -> None:
    """예매 오픈 알림 발송. 미설정/HTTP 오류 시 예외를 던진다(호출부에서 재시도 처리)."""
    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if not url:
        raise RuntimeError(f"{WEBHOOK_ENV} 환경변수가 설정되지 않았습니다.")
    resp = post(url, json={"content": build_message(watch)}, timeout=10)
    resp.raise_for_status()
