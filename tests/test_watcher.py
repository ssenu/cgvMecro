from unittest.mock import MagicMock
from cgvwatch.core.models import Watch, Settings, Status
from cgvwatch.core.watcher import check_watch


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260729")
    base.update(kw)
    return Watch(**base)


def test_check_watch_notifies_and_marks_open(monkeypatch):
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})
    notify = MagicMock()

    result = check_watch(MagicMock(), _watch(), Settings(), notify=notify, now="2026-07-23 10:00")

    assert result.was_open is True
    assert result.status == Status.OPEN
    assert result.last_checked == "2026-07-23 10:00"
    notify.assert_called_once()


def test_check_watch_waiting_when_not_open(monkeypatch):
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260801"})
    notify = MagicMock()

    result = check_watch(MagicMock(), _watch(), Settings(), notify=notify)

    assert result.was_open is False
    assert result.status == Status.WAITING
    notify.assert_not_called()


def test_check_watch_error_sets_error_status(monkeypatch):
    import cgvwatch.core.watcher as w
    def boom(c, s, m):
        raise RuntimeError("네트워크")
    monkeypatch.setattr(w, "get_open_dates", boom)

    result = check_watch(MagicMock(), _watch(), Settings(), notify=MagicMock())

    assert result.status == Status.ERROR


def test_check_watch_open_but_notify_fails_does_not_raise(monkeypatch):
    """열렸지만 알림 발송 실패 시 예외 전파 없이 ERROR, was_open 유지(재시도)."""
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})

    def failing_notify(watch, settings):
        raise RuntimeError("웹훅 미설정")

    result = check_watch(MagicMock(), _watch(was_open=False), Settings(), notify=failing_notify)

    assert result.status == Status.ERROR
    assert result.was_open is False


def test_thread_run_once_survives_check_exception(monkeypatch):
    """워커 루프는 한 항목의 예외로 죽으면 안 된다."""
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "check_watch", MagicMock(side_effect=RuntimeError("불의의 오류")))

    def get_state():
        return Settings(interval_min=1), [_watch()], lambda updated: None

    thread = w.WatcherThread(MagicMock(), get_state)
    thread._run_once(*get_state())  # 예외 없이 반환되면 통과


def test_thread_stop_interrupts_wait():
    import cgvwatch.core.watcher as w
    thread = w.WatcherThread(MagicMock(), lambda: (Settings(), [], lambda u: None))
    thread.stop()
    assert thread._stop.is_set()


def test_check_watch_error_logs_cause(monkeypatch, caplog):
    """CGV 조회 실패가 조용히 삼켜지지 않고 원인이 로그에 남아야 한다."""
    import logging
    import cgvwatch.core.watcher as w

    def boom(c, s, m):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(w, "get_open_dates", boom)

    with caplog.at_level(logging.WARNING):
        result = check_watch(MagicMock(), _watch(), Settings(), notify=MagicMock())

    assert result.status == Status.ERROR
    assert "connection refused" in caplog.text
    assert "스파이더맨" in caplog.text
