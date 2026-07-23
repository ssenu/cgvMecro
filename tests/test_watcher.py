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


def test_check_watch_open_but_mail_fails_does_not_raise(monkeypatch):
    """열렸지만 메일 발송이 실패해도 예외가 전파되면 안 된다(앱 크래시 원인)."""
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})

    def failing_send(watch, settings):
        raise RuntimeError("Gmail 주소가 설정되지 않았습니다.")

    result = check_watch(MagicMock(), _watch(was_open=False), Settings(), send_mail=failing_send)

    # 크래시 없이 ERROR로 표시, 다음 주기에 재시도하도록 was_open은 False 유지
    assert result.status == Status.ERROR
    assert result.was_open is False


def test_worker_run_survives_check_exception(monkeypatch):
    """방어적: 워커 루프는 한 항목의 예외로 스레드/앱이 죽으면 안 된다."""
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "check_watch", MagicMock(side_effect=RuntimeError("불의의 오류")))

    def get_state():
        return Settings(interval_min=1), [_watch()], lambda updated: None

    worker = w.WatcherWorker(MagicMock(), get_state)
    worker._running = True
    # run 루프 1회분을 직접 실행: 예외가 전파되지 않아야 함
    worker._run_once(*get_state())  # 예외 없이 반환되면 통과
