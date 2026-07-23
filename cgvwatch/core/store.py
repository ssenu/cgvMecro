"""설정·감시목록의 로컬 JSON 영속화."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Settings, Watch

DEFAULT_PATH = Path.home() / ".cgv-watcher" / "config.json"


class Store:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = Path(path)

    def load(self) -> tuple[Settings, list[Watch]]:
        if not self.path.exists():
            return Settings(), []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        settings = Settings(**raw.get("settings", {}))
        watches = [Watch(**w) for w in raw.get("watches", [])]
        return settings, watches

    def save(self, settings: Settings, watches: list[Watch]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"settings": asdict(settings), "watches": [asdict(w) for w in watches]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
