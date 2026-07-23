"""Gmail SMTP 이메일 발송 + keyring 앱 비밀번호 관리."""
from __future__ import annotations

import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Callable, Optional

import keyring

from cgvwatch.core.models import Settings, Watch

KEYRING_SERVICE = "cgv-watcher"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
BOOK_URL = "https://cgv.co.kr/cnm/movieBook/cinema"


def save_app_password(user: str, password: str) -> None:
    keyring.set_password(KEYRING_SERVICE, user, password)


def get_app_password(user: str) -> Optional[str]:
    return keyring.get_password(KEYRING_SERVICE, user)


def _fmt_ymd(ymd: str) -> str:
    return f"{ymd[4:6]}/{ymd[6:8]}"  # MM/DD


def build_message(watch: Watch, settings: Settings) -> tuple[str, str]:
    subject = f'[CGV] "{watch.mov_nm}" {watch.site_nm} {_fmt_ymd(watch.target_ymd)} 예매 열렸습니다'
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = (
        f"CGV 예매가 열렸습니다.\n\n"
        f"영화: {watch.mov_nm}\n"
        f"상영관: {watch.site_nm}\n"
        f"날짜: {watch.target_ymd[:4]}-{watch.target_ymd[4:6]}-{watch.target_ymd[6:8]}\n"
        f"확인 시각: {now}\n\n"
        f"예매하기: {BOOK_URL}\n"
    )
    return subject, body


def send_open_mail(
    watch: Watch,
    settings: Settings,
    smtp_factory: Optional[Callable] = None,
) -> None:
    password = get_app_password(settings.gmail_user)
    if not password:
        raise RuntimeError("Gmail 앱 비밀번호가 설정되지 않았습니다.")
    subject, body = build_message(watch, settings)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.gmail_user
    msg["To"] = settings.recipient or settings.gmail_user
    msg.set_content(body)

    factory = smtp_factory or (lambda: smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15))
    with factory() as smtp:
        smtp.login(settings.gmail_user, password)
        smtp.send_message(msg)
