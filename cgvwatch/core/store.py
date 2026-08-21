"""설정·감시목록의 로컬 JSON 영속화."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from pathlib import Path

from .models import Settings, Watch


def default_path() -> Path:
    base = os.environ.get("CGVWATCH_DATA", "").strip()
    root = Path(base) if base else Path.home() / ".cgv-watcher"
    return root / "config.json"


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else default_path()

    def load(self) -> tuple[Settings, list[Watch]]:
        if not self.path.exists():
            return Settings(), []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw_settings = dict(raw.get("settings", {}))
        # 분 단위(interval_min)를 쓰던 구버전 설정을 초 단위로 변환한다.
        if "interval_sec" not in raw_settings and "interval_min" in raw_settings:
            raw_settings["interval_sec"] = int(raw_settings["interval_min"]) * 60
        allowed = {f.name for f in fields(Settings)}
        known = {k: v for k, v in raw_settings.items() if k in allowed}
        settings = Settings(**known)
        # 다른 버전이 남긴 낯선 watch 키(time_from 등)는 무시하고 로드한다.
        watch_fields = {f.name for f in fields(Watch)}
        watches = [
            Watch(**{k: v for k, v in w.items() if k in watch_fields})
            for w in raw.get("watches", [])
        ]
        return settings, watches

    def save(self, settings: Settings, watches: list[Watch]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"settings": asdict(settings), "watches": [asdict(w) for w in watches]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
