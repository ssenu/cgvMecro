from unittest.mock import MagicMock

from cgvwatch.core.models import Settings, Watch
from cgvwatch.hunt.manager import HuntManager


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


def test_process_one_requires_login(tmp_path, monkeypatch):
    """로그인이 안 돼 있으면 헌팅을 시작하지 않고 알림만 보낸다."""
    import cgvwatch.hunt.manager as hm
    alert = MagicMock()
    monkeypatch.setattr(hm, "send_login_required", alert)
    m = _manager(tmp_path)
    m._browser = MagicMock(is_running=lambda: True, is_logged_in=lambda: False)

    m._process(_watch())

    alert.assert_called_once()
    assert m.status()["last"]["status"] == "로그인필요"


def test_process_one_reports_no_showtime(tmp_path, monkeypatch):
    import cgvwatch.hunt.manager as hm
    monkeypatch.setattr(hm, "get_showtimes", lambda *a, **k: [])
    m = _manager(tmp_path)
    m._browser = MagicMock(is_running=lambda: True, is_logged_in=lambda: True)

    m._process(_watch(screen_filter="IMAX"))

    assert m.status()["last"]["status"] == "회차없음"


def test_process_one_reports_missing_browser(tmp_path):
    m = _manager(tmp_path)
    m._process(_watch())
    assert m.status()["last"]["status"] == "브라우저없음"
