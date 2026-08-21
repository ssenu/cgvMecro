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
        return Settings(interval_sec=60), [_watch()], lambda updated: None

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


def test_check_watch_records_and_clears_last_error(monkeypatch):
    import cgvwatch.core.watcher as w

    def boom(c, s, m):
        raise RuntimeError("HTTP 403")
    monkeypatch.setattr(w, "get_open_dates", boom)
    failed = check_watch(MagicMock(), _watch(), Settings(), notify=MagicMock(),
                         notify_error=MagicMock())
    assert failed.status == Status.ERROR
    assert "HTTP 403" in failed.last_error

    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: set())
    recovered = check_watch(MagicMock(), failed, Settings(), notify=MagicMock(),
                            notify_error=MagicMock())
    assert recovered.status == Status.WAITING
    assert recovered.last_error == ""


def test_check_watch_sends_error_alert_only_on_transition(monkeypatch):
    """정상→오류 전환 때만 디스코드 경고 1회, 오류 지속 중엔 반복 발송 없음."""
    import cgvwatch.core.watcher as w

    def boom(c, s, m):
        raise RuntimeError("HTTP 403")
    monkeypatch.setattr(w, "get_open_dates", boom)
    alert = MagicMock()

    first = check_watch(MagicMock(), _watch(), Settings(), notify=MagicMock(),
                        notify_error=alert)
    alert.assert_called_once()

    check_watch(MagicMock(), first, Settings(), notify=MagicMock(), notify_error=alert)
    alert.assert_called_once()  # 여전히 1회


def test_check_watch_error_alert_failure_is_swallowed(monkeypatch):
    """오류 경고 발송 자체가 실패해도(디코 장애 등) 감시는 계속된다."""
    import cgvwatch.core.watcher as w

    def boom(c, s, m):
        raise RuntimeError("HTTP 403")
    monkeypatch.setattr(w, "get_open_dates", boom)

    result = check_watch(MagicMock(), _watch(), Settings(), notify=MagicMock(),
                         notify_error=MagicMock(side_effect=RuntimeError("디코 장애")))
    assert result.status == Status.ERROR


def _imax_watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0013",
                site_nm="용산아이파크몰", target_ymd="20260729", screen_filter="IMAX")
    base.update(kw)
    return Watch(**base)


def test_check_watch_screen_filter_match_alerts(monkeypatch):
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})
    monkeypatch.setattr(w, "get_showtimes", lambda c, s, m, y: [
        {"start": "1800", "screen": "IMAX관 (Laser)", "free_seats": "100"},
    ])
    notify = MagicMock()

    result = check_watch(MagicMock(), _imax_watch(), Settings(), notify=notify,
                         notify_error=MagicMock())

    assert result.was_open is True and result.status == Status.OPEN
    notify.assert_called_once()


def test_check_watch_screen_filter_no_match_keeps_waiting(monkeypatch):
    """날짜는 열렸어도 원하는 관 회차가 없으면 알림 없이 대기(다음 주기 재확인)."""
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})
    monkeypatch.setattr(w, "get_showtimes", lambda c, s, m, y: [
        {"start": "1800", "screen": "4관 (2D)", "free_seats": "100"},
    ])
    notify = MagicMock()

    result = check_watch(MagicMock(), _imax_watch(), Settings(), notify=notify,
                         notify_error=MagicMock())

    assert result.was_open is False and result.status == Status.WAITING
    notify.assert_not_called()


def test_check_watch_screen_filter_showtimes_fail_is_error(monkeypatch):
    """관 조건을 판정할 수 없으면 ERROR로 표시하고 다음 주기 재시도."""
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})
    def boom(c, s, m, y):
        raise RuntimeError("회차 API 오류")
    monkeypatch.setattr(w, "get_showtimes", boom)
    notify = MagicMock()

    result = check_watch(MagicMock(), _imax_watch(), Settings(), notify=notify,
                         notify_error=MagicMock())

    assert result.status == Status.ERROR and result.was_open is False
    notify.assert_not_called()


def test_check_watch_no_screen_filter_skips_showtimes_fetch(monkeypatch):
    """관 필터가 없으면 회차 조회 없이 기존대로 즉시 알린다."""
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})
    fetch = MagicMock()
    monkeypatch.setattr(w, "get_showtimes", fetch)
    notify = MagicMock()

    result = check_watch(MagicMock(), _watch(), Settings(), notify=notify,
                         notify_error=MagicMock())

    assert result.status == Status.OPEN
    fetch.assert_not_called()
