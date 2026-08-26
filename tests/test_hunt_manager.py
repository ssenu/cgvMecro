import time
from unittest.mock import MagicMock

from cgvwatch.core.models import Settings, Watch
from cgvwatch.hunt.manager import HuntManager


def _wait_until(predicate, timeout=2.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260827", hunt_enabled=True)
    base.update(kw)
    return Watch(**base)


def _manager(tmp_path):
    return HuntManager(MagicMock(), tmp_path / "profile", lambda: Settings())


def test_request_hunt_queues_watch(tmp_path):
    m = _manager(tmp_path)
    assert m.request_hunt(_watch()) is True
    assert m.status()["queued"] == 1


def test_request_hunt_rejects_duplicate(tmp_path):
    m = _manager(tmp_path)
    m.request_hunt(_watch())
    assert m.request_hunt(_watch()) is False
    assert m.status()["queued"] == 1


def test_status_reports_browser_off_initially(tmp_path):
    assert _manager(tmp_path).status()["browser"] is False


def test_process_no_longer_blocks_on_preflight_login(tmp_path, monkeypatch):
    """사전 로그인 검사로 헌팅을 막지 않는다. 판정은 CGV 모달이 한다."""
    import cgvwatch.hunt.manager as hm
    alert = MagicMock()
    monkeypatch.setattr(hm, "send_login_required", alert)
    monkeypatch.setattr(hm, "get_showtimes", lambda *a, **k: [])
    m = _manager(tmp_path)
    # 로그아웃 상태로 보이더라도 회차 조회까지는 진행해야 한다
    m._browser = MagicMock(is_running=lambda: True, login_state=lambda: False,
                           is_logged_in=lambda: False)

    m._process(_watch())

    alert.assert_not_called()
    assert m.status()["last"]["status"] == "회차없음"


def test_process_one_reports_no_showtime(tmp_path, monkeypatch):
    import cgvwatch.hunt.manager as hm
    monkeypatch.setattr(hm, "get_showtimes", lambda *a, **k: [])
    m = _manager(tmp_path)
    m._browser = MagicMock(is_running=lambda: True, is_logged_in=lambda: True, login_state=lambda: True)

    m._process(_watch(screen_filter="IMAX"))

    assert m.status()["last"]["status"] == "회차없음"


def test_process_one_reports_missing_browser(tmp_path):
    m = _manager(tmp_path)
    m._process(_watch())
    assert m.status()["last"]["status"] == "브라우저없음"


def test_run_processes_watch_and_cleans_up(tmp_path):
    """run() 루프가 큐를 소비하고 active/queued_ids를 정리한다."""
    m = _manager(tmp_path)
    processed = []
    m._process = lambda watch: processed.append(watch.id)
    m.start()
    try:
        m.request_hunt(_watch())
        assert _wait_until(lambda: len(processed) == 1)
        assert _wait_until(lambda: m.status()["active"] == "" and m.status()["queued"] == 0)
        # 같은 id를 다시 큐에 넣을 수 있어야 한다 (queued_ids가 비워졌다는 증거)
        assert m.request_hunt(_watch()) is True
    finally:
        m.stop()
        m.join(timeout=3.0)
    assert not m.is_alive()


def test_run_survives_process_exception(tmp_path):
    """_process에서 예외가 나도 정리되고 스레드는 살아있어야 한다."""
    m = _manager(tmp_path)
    calls = []

    def boom(watch):
        calls.append(watch.id)
        raise RuntimeError("boom")

    m._process = boom
    m.start()
    try:
        m.request_hunt(_watch())
        assert _wait_until(lambda: len(calls) == 1)
        assert _wait_until(lambda: m.status()["active"] == "" and m.status()["queued"] == 0)
        assert m.is_alive()
    finally:
        m.stop()
        m.join(timeout=3.0)


def test_run_stops_browser_on_shutdown(tmp_path):
    """종료 시 run()이 브라우저를 정리한다 (stop()이 아니라 run() 스레드에서)."""
    m = _manager(tmp_path)
    m._process = lambda watch: None
    browser_mock = MagicMock()
    m._browser = browser_mock
    m.start()
    try:
        assert _wait_until(lambda: m.is_alive())
    finally:
        m.stop()
        m.join(timeout=3.0)
    browser_mock.stop.assert_called_once()
    assert m._browser is None


def test_stop_and_join_completes(tmp_path):
    """stop() 후 join으로 스레드가 실제로 끝나야 한다(크롬 정리 보장)."""
    m = _manager(tmp_path)
    browser = MagicMock()
    m._browser = browser
    m.start()
    m.stop()
    m.join(timeout=5.0)
    assert not m.is_alive()
    browser.stop.assert_called_once()


def test_notify_failure_does_not_change_hunt_outcome(tmp_path, monkeypatch):
    """웹훅이 없어 알림이 실패해도 헌팅 결과 기록은 정상이어야 한다."""
    import cgvwatch.hunt.manager as hm
    from cgvwatch.hunt.hunter import HuntResult

    m = _manager(tmp_path)
    m._browser = MagicMock(is_running=lambda: True, is_logged_in=lambda: True, login_state=lambda: True)
    monkeypatch.setattr(hm, "get_showtimes", lambda *a, **k: [
        {"start": "1900", "screen": "3관", "free_seats": "5",
         "scns_no": "003", "scn_sseq": "2"}])
    monkeypatch.setattr(m, "_open_seat_page", lambda w, s: "ok")
    monkeypatch.setattr(hm, "Hunter", lambda *a, **k: MagicMock(
        run=lambda: HuntResult("확보", seats=["H12"], detail="결제 페이지 도달")))
    # 알림 두 종류 모두 실패시킨다
    monkeypatch.setattr(hm, "send_seat_secured", MagicMock(side_effect=RuntimeError("웹훅 없음")))
    monkeypatch.setattr(hm, "notify_desktop", MagicMock(side_effect=RuntimeError("알림 실패")))

    m._process(_watch())

    last = m.status()["last"]
    assert last["status"] == "확보"
    assert last["seats"] == ["H12"]


def test_process_proceeds_when_login_state_unknown(tmp_path, monkeypatch):
    """로그인 상태를 판정할 수 없으면 막지 말고 진행해야 한다."""
    import cgvwatch.hunt.manager as hm
    m = _manager(tmp_path)
    m._browser = MagicMock(is_running=lambda: True, login_state=lambda: None)
    monkeypatch.setattr(hm, "get_showtimes", lambda *a, **k: [])

    m._process(_watch())

    # 로그인에서 멈추지 않고 회차 조회까지 갔다
    assert m.status()["last"]["status"] == "회차없음"


def test_process_reports_login_when_cgv_demands_it(tmp_path, monkeypatch):
    """회차를 눌렀을 때 CGV가 로그인을 요구하면 '로그인필요'로 기록한다."""
    import cgvwatch.hunt.manager as hm
    m = _manager(tmp_path)
    m._browser = MagicMock(is_running=lambda: True, login_state=lambda: None)
    monkeypatch.setattr(hm, "get_showtimes", lambda *a, **k: [
        {"start": "1900", "screen": "3관", "free_seats": "5",
         "scns_no": "003", "scn_sseq": "2"}])
    monkeypatch.setattr(m, "_open_seat_page", lambda w, s: "login")

    m._process(_watch())

    assert m.status()["last"]["status"] == "로그인필요"
