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
    assert tc.get("/api/settings").json() == {"interval_min": 5}
    assert tc.put("/api/settings", json={"interval_min": 10}).json() == {"interval_min": 10}
    settings, _ = store.load()
    assert settings.interval_min == 10


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
