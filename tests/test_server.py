from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from cgvwatch.core.models import Settings, Status, Watch
from cgvwatch.core.store import Store
from cgvwatch.web.server import create_app


@pytest.fixture()
def api(tmp_path):
    store = Store(tmp_path / "config.json")
    client = MagicMock()
    app = create_app(store=store, client=client, start_watcher=False)
    return TestClient(app), store, client


def test_healthz(api):
    tc, _, _ = api
    assert tc.get("/healthz").json() == {"status": "ok"}


def test_add_list_delete_watch(api):
    tc, store, _ = api
    body = {"mov_no": "30001192", "mov_nm": "스파이더맨", "site_no": "0056",
            "site_nm": "강남", "target_ymd": "20260729"}

    created = tc.post("/api/watches", json=body)
    assert created.status_code == 201
    wid = created.json()["id"]
    assert created.json()["status"] == Status.WAITING

    listed = tc.get("/api/watches").json()
    assert len(listed) == 1 and listed[0]["id"] == wid

    # 영속화 확인
    _, saved = store.load()
    assert saved[0].mov_nm == "스파이더맨"

    assert tc.delete(f"/api/watches/{wid}").status_code == 204
    assert tc.get("/api/watches").json() == []


def test_delete_unknown_watch_404(api):
    tc, _, _ = api
    assert tc.delete("/api/watches/nope").status_code == 404


def test_settings_roundtrip(api):
    tc, store, _ = api
    assert tc.get("/api/settings").json() == {"interval_sec": 300}
    assert tc.put("/api/settings", json={"interval_sec": 30}).json() == {"interval_sec": 30}
    settings, _ = store.load()
    assert settings.interval_sec == 30


def test_movies_proxies_cgv(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "get_movies", lambda c: [{"mov_no": "1", "mov_nm": "영화"}])
    assert tc.get("/api/movies").json() == [{"mov_no": "1", "mov_nm": "영화"}]


def test_theaters_proxies_cgv(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "get_regions",
                        lambda c: [{"name": "서울", "sites": [{"site_no": "0056", "site_nm": "강남"}]}])
    assert tc.get("/api/theaters").json()[0]["name"] == "서울"


def test_cgv_error_returns_502(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    from cgvwatch.cgv.client import CGVError
    def boom(c):
        raise CGVError("down")
    monkeypatch.setattr(srv, "get_movies", boom)
    assert tc.get("/api/movies").status_code == 502

def test_add_watch_sends_created_alert(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    sent = MagicMock()
    monkeypatch.setattr(srv, "send_created_alert", sent)
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0056",
            "site_nm": "강남", "target_ymd": "20260729"}

    assert tc.post("/api/watches", json=body).status_code == 201

    sent.assert_called_once()
    assert sent.call_args[0][0].mov_nm == "영화"


def test_add_watch_succeeds_even_if_alert_fails(api, monkeypatch):
    """웹훅 미설정 등으로 등록 알림이 실패해도 등록 자체는 성공해야 한다."""
    tc, _, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "send_created_alert",
                        MagicMock(side_effect=RuntimeError("웹훅 미설정")))
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0056",
            "site_nm": "강남", "target_ymd": "20260729"}

    res = tc.post("/api/watches", json=body)

    assert res.status_code == 201
    assert len(tc.get("/api/watches").json()) == 1

def test_add_watch_with_screen_filter(api, monkeypatch):
    tc, store, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "send_created_alert", MagicMock())
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산아이파크몰",
            "target_ymd": "20260729", "screen_filter": "IMAX"}

    res = tc.post("/api/watches", json=body)

    assert res.status_code == 201
    assert res.json()["screen_filter"] == "IMAX"
    _, saved = store.load()
    assert saved[0].screen_filter == "IMAX"


def test_add_watch_with_hunt_options(api, monkeypatch):
    tc, store, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "send_created_alert", MagicMock())
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산아이파크몰",
            "target_ymd": "20260729", "screen_filter": "IMAX",
            "hunt_enabled": True, "seat_count": 2, "row_offset": 2,
            "preferred_time": "1900"}

    res = tc.post("/api/watches", json=body)

    assert res.status_code == 201
    assert res.json()["hunt_enabled"] is True
    _, saved = store.load()
    assert saved[0].seat_count == 2
    assert saved[0].row_offset == 2
    assert saved[0].preferred_time == "1900"


def test_add_watch_rejects_bad_seat_count(api):
    tc, _, _ = api
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산",
            "target_ymd": "20260729", "seat_count": 5}
    assert tc.post("/api/watches", json=body).status_code == 422


def test_add_watch_rejects_bad_preferred_time(api):
    tc, _, _ = api
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산",
            "target_ymd": "20260729", "preferred_time": "7pm"}
    assert tc.post("/api/watches", json=body).status_code == 422


def test_hunt_now_404_for_unknown_watch(api):
    tc, _, _ = api
    assert tc.post("/api/hunt/nope").status_code == 404


def test_hunt_status_endpoint(api):
    tc, _, _ = api
    body = tc.get("/api/hunt").json()
    assert body["browser"] is False
    assert body["queued"] == 0


def test_add_watch_mode_now_enqueues_hunt(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "send_created_alert", MagicMock())
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산",
            "target_ymd": "20260729", "mode": "now"}

    res = tc.post("/api/watches", json=body)

    assert res.status_code == 201
    assert res.json()["mode"] == "now"
    # start_watcher=False라 헌트 매니저 스레드는 돌지 않지만, 큐에는 들어가야 한다.
    hunt_body = tc.get("/api/hunt").json()
    assert hunt_body["queued"] == 1


def test_add_watch_mode_onopen_does_not_enqueue_hunt(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "send_created_alert", MagicMock())
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산",
            "target_ymd": "20260729", "mode": "onopen"}

    res = tc.post("/api/watches", json=body)

    assert res.status_code == 201
    assert res.json()["mode"] == "onopen"
    hunt_body = tc.get("/api/hunt").json()
    assert hunt_body["queued"] == 0


def test_add_watch_default_mode_is_onopen_and_no_hunt(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "send_created_alert", MagicMock())
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산",
            "target_ymd": "20260729"}

    res = tc.post("/api/watches", json=body)

    assert res.status_code == 201
    assert res.json()["mode"] == "onopen"
    hunt_body = tc.get("/api/hunt").json()
    assert hunt_body["queued"] == 0


def test_add_watch_rejects_bad_mode(api):
    tc, _, _ = api
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산",
            "target_ymd": "20260729", "mode": "asap"}
    assert tc.post("/api/watches", json=body).status_code == 422
