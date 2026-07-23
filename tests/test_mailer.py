from unittest.mock import MagicMock
import pytest
import cgvwatch.notify.mailer as mailer
from cgvwatch.core.models import Watch, Settings


def _watch():
    return Watch(id="1", mov_no="30001192", mov_nm="스파이더맨-브랜드 뉴 데이",
                 site_no="0056", site_nm="강남", target_ymd="20260725")


def test_build_message_contains_key_fields():
    subject, body = mailer.build_message(_watch(), Settings(recipient="me@gmail.com"))
    assert "스파이더맨-브랜드 뉴 데이" in subject
    assert "강남" in subject
    assert "07/25" in subject
    assert "강남" in body
    assert "2026" in body


def test_send_open_mail_uses_smtp(monkeypatch):
    smtp = MagicMock()
    smtp_ctx = MagicMock()
    smtp_ctx.__enter__.return_value = smtp
    factory = MagicMock(return_value=smtp_ctx)
    monkeypatch.setattr(mailer, "get_app_password", lambda user: "app-pw")

    settings = Settings(gmail_user="me@gmail.com", recipient="you@gmail.com")
    mailer.send_open_mail(_watch(), settings, smtp_factory=factory)

    smtp.login.assert_called_once_with("me@gmail.com", "app-pw")
    assert smtp.send_message.call_count == 1


def test_send_open_mail_raises_without_password(monkeypatch):
    monkeypatch.setattr(mailer, "get_app_password", lambda user: None)
    with pytest.raises(RuntimeError):
        mailer.send_open_mail(_watch(), Settings(gmail_user="me@gmail.com"), smtp_factory=MagicMock())
