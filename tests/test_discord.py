from unittest.mock import MagicMock

import pytest

import cgvwatch.notify.discord as discord
from cgvwatch.core.models import Settings, Watch


def _watch():
    return Watch(id="1", mov_no="30001192", mov_nm="스파이더맨-브랜드 뉴 데이",
                 site_no="0056", site_nm="강남", target_ymd="20260725")


def test_build_message_contains_key_fields():
    msg = discord.build_message(_watch())
    assert "스파이더맨-브랜드 뉴 데이" in msg
    assert "강남" in msg
    assert "07/25" in msg


def test_send_open_alert_posts_to_webhook(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    resp = MagicMock(status_code=204)
    post = MagicMock(return_value=resp)

    discord.send_open_alert(_watch(), Settings(), post=post)

    url = post.call_args[0][0]
    payload = post.call_args[1]["json"]
    assert url == "https://discord.test/hook"
    assert "스파이더맨-브랜드 뉴 데이" in payload["content"]


def test_send_open_alert_raises_without_webhook_url(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError):
        discord.send_open_alert(_watch(), Settings(), post=MagicMock())


def test_send_open_alert_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    resp = MagicMock()
    resp.raise_for_status.side_effect = RuntimeError("HTTP 400")
    post = MagicMock(return_value=resp)
    with pytest.raises(RuntimeError):
        discord.send_open_alert(_watch(), Settings(), post=post)

def test_build_created_message_contains_key_fields():
    msg = discord.build_created_message(_watch())
    assert "스파이더맨-브랜드 뉴 데이" in msg
    assert "강남" in msg
    assert "07/25" in msg
    assert "등록" in msg


def test_send_created_alert_posts_to_webhook(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    resp = MagicMock(status_code=204)
    post = MagicMock(return_value=resp)

    discord.send_created_alert(_watch(), Settings(), post=post)

    payload = post.call_args[1]["json"]
    assert "등록" in payload["content"]


def test_send_created_alert_raises_without_webhook_url(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError):
        discord.send_created_alert(_watch(), Settings(), post=MagicMock())


def test_send_error_alert_posts_reason(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    resp = MagicMock(status_code=204)
    post = MagicMock(return_value=resp)

    discord.send_error_alert(_watch(), Settings(), "CGV 조회 실패: HTTP 403", post=post)

    payload = post.call_args[1]["json"]
    assert "오류" in payload["content"]
    assert "HTTP 403" in payload["content"]
    assert "강남" in payload["content"]
