from cgvwatch.core.models import Watch, Settings, Status
from cgvwatch.core.store import Store


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    store = Store(path)
    settings = Settings(interval_sec=90)
    watches = [Watch(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                     site_nm="강남", target_ymd="20260729", was_open=True, status=Status.OPEN)]

    store.save(settings, watches)
    loaded_settings, loaded_watches = store.load()

    assert loaded_settings == settings
    assert loaded_watches == watches


def test_load_missing_file_returns_defaults(tmp_path):
    store = Store(tmp_path / "nope.json")
    settings, watches = store.load()
    assert settings == Settings()
    assert watches == []


def test_default_path_uses_env_var(monkeypatch, tmp_path):
    from cgvwatch.core.store import default_path
    monkeypatch.setenv("CGVWATCH_DATA", str(tmp_path))
    assert default_path() == tmp_path / "config.json"


def test_default_path_falls_back_to_home(monkeypatch):
    from cgvwatch.core.store import default_path
    monkeypatch.delenv("CGVWATCH_DATA", raising=False)
    from pathlib import Path
    assert default_path() == Path.home() / ".cgv-watcher" / "config.json"


def test_load_ignores_legacy_keys(tmp_path):
    """GUI 시절 config.json(gmail 필드 잔존)을 읽어도 TypeError 없이 로드된다."""
    path = tmp_path / "config.json"
    path.write_text(
        '{"settings": {"gmail_user": "me@gmail.com", "recipient": "me@gmail.com", '
        '"interval_min": 10}, "watches": []}',
        encoding="utf-8",
    )
    settings, watches = Store(path).load()
    assert settings.interval_sec == 600  # 분 단위 구버전 → 초로 변환
    assert watches == []


def test_load_ignores_unknown_watch_keys(tmp_path):
    """다른 버전이 저장한 config의 낯선 watch 키(time_from 등)에도 로드가 죽으면 안 된다."""
    path = tmp_path / "config.json"
    path.write_text(
        '{"settings": {"interval_sec": 60}, "watches": [{'
        '"id": "1", "mov_no": "30001192", "mov_nm": "스파이더맨", "site_no": "0056", '
        '"site_nm": "강남", "target_ymd": "20260729", "time_from": "1700", "time_to": "2200"}]}',
        encoding="utf-8",
    )
    settings, watches = Store(path).load()
    assert watches[0].mov_nm == "스파이더맨"
    assert settings.interval_sec == 60
