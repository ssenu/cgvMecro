from unittest.mock import MagicMock
from cgvwatch.core.models import Watch, Settings, Status
from cgvwatch.core.watcher import check_watch


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260729")
    base.update(kw)
    return Watch(**base)


def test_check_watch_sends_mail_and_marks_open(monkeypatch):
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})
    send = MagicMock()

    result = check_watch(MagicMock(), _watch(), Settings(), send_mail=send, now="2026-07-23 10:00")

    assert result.was_open is True
    assert result.status == Status.OPEN
    assert result.last_checked == "2026-07-23 10:00"
    send.assert_called_once()


def test_check_watch_waiting_when_not_open(monkeypatch):
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260801"})
    send = MagicMock()

    result = check_watch(MagicMock(), _watch(), Settings(), send_mail=send)

    assert result.was_open is False
    assert result.status == Status.WAITING
    send.assert_not_called()


def test_check_watch_error_sets_error_status(monkeypatch):
    import cgvwatch.core.watcher as w
    def boom(c, s, m):
        raise RuntimeError("네트워크")
    monkeypatch.setattr(w, "get_open_dates", boom)

    result = check_watch(MagicMock(), _watch(), Settings(), send_mail=MagicMock())

    assert result.status == Status.ERROR
