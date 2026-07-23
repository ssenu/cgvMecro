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


def _send(
    gmail_user: str,
    password: str,
    recipient: str,
    subject: str,
    body: str,
    smtp_factory: Optional[Callable] = None,
) -> None:
    """실제 SMTP 발송 코어. 상위 함수들이 제목/본문/자격증명을 준비해 호출한다."""
    if not gmail_user:
        raise RuntimeError("Gmail 주소가 설정되지 않았습니다.")
    if not password:
        raise RuntimeError("Gmail 앱 비밀번호가 설정되지 않았습니다.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient or gmail_user
    msg.set_content(body)

    factory = smtp_factory or (lambda: smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15))
    with factory() as smtp:
        smtp.login(gmail_user, password)
        smtp.send_message(msg)


def send_open_mail(
    watch: Watch,
    settings: Settings,
    smtp_factory: Optional[Callable] = None,
) -> None:
    password = get_app_password(settings.gmail_user)
    subject, body = build_message(watch, settings)
    _send(settings.gmail_user, password, settings.recipient, subject, body, smtp_factory)


def send_test_mail(
    gmail_user: str,
    password: str,
    recipient: str,
    smtp_factory: Optional[Callable] = None,
) -> None:
    """설정 화면에서 입력한 값으로 실제 발송이 되는지 확인하는 테스트 메일."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = "[CGV 알리미] 테스트 메일"
    body = (
        "CGV 예매 오픈 알리미 설정이 정상입니다.\n\n"
        f"이 메일이 보이면 알림 발송이 잘 동작합니다.\n"
        f"발송 시각: {now}\n"
    )
    _send(gmail_user, password, recipient, subject, body, smtp_factory)
