from cgvwatch.core.models import Watch, Settings, Status
from cgvwatch.core.store import Store


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    store = Store(path)
    settings = Settings(interval_min=10)
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
