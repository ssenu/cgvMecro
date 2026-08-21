"""FastAPI 웹 서버: JSON API + 정적 UI + 백그라운드 감시 스레드."""
from __future__ import annotations

import logging
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from cgvwatch.cgv.client import CGVClient, CGVError
from cgvwatch.cgv.movies import get_movies
from cgvwatch.cgv.theaters import get_regions
from cgvwatch.core.models import Settings, Watch
from cgvwatch.core.store import Store
from cgvwatch.core.watcher import WatcherThread
from cgvwatch.notify.discord import send_created_alert

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


class WatchIn(BaseModel):
    mov_no: str
    mov_nm: str
    site_no: str
    site_nm: str
    target_ymd: str = Field(pattern=r"^\d{8}$")


class SettingsIn(BaseModel):
    interval_sec: int = Field(ge=5, le=86400)


class AppState:
    """메모리 상태 + 영속화. 감시 스레드와 API 핸들러가 락으로 공유한다."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.lock = threading.Lock()
        self.settings, self.watches = store.load()

    def get_state(self):
        with self.lock:
            return self.settings, list(self.watches), self.set_watch

    def set_watch(self, updated: Watch) -> None:
        with self.lock:
            self.watches = [updated if w.id == updated.id else w for w in self.watches]
            self.store.save(self.settings, self.watches)

    def add_watch(self, watch: Watch) -> None:
        with self.lock:
            self.watches.append(watch)
            self.store.save(self.settings, self.watches)

    def remove_watch(self, watch_id: str) -> bool:
        with self.lock:
            before = len(self.watches)
            self.watches = [w for w in self.watches if w.id != watch_id]
            if len(self.watches) == before:
                return False
            self.store.save(self.settings, self.watches)
            return True

    def update_settings(self, interval_sec: int) -> Settings:
        with self.lock:
            self.settings = Settings(interval_sec=interval_sec)
            self.store.save(self.settings, self.watches)
            return self.settings


def create_app(
    store: Optional[Store] = None,
    client: Optional[CGVClient] = None,
    start_watcher: bool = True,
) -> FastAPI:
    store = store or Store()
    client = client or CGVClient()
    state = AppState(store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        watcher = None
        if start_watcher:
            watcher = WatcherThread(client, state.get_state)
            watcher.start()
        yield
        if watcher:
            watcher.stop()

    app = FastAPI(title="CGV 예매 오픈 알리미", lifespan=lifespan)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/watches")
    def list_watches():
        with state.lock:
            return [asdict(w) for w in state.watches]

    @app.post("/api/watches", status_code=201)
    def add_watch(body: WatchIn):
        watch = Watch(id=uuid.uuid4().hex[:8], **body.model_dump())
        state.add_watch(watch)
        try:
            send_created_alert(watch, state.settings)
        except Exception:
            # 등록 알림 실패(웹훅 미설정 등)가 등록 자체를 막으면 안 된다.
            logger.exception("등록 알림 발송 실패: %s", watch.mov_nm)
        return asdict(watch)

    @app.delete("/api/watches/{watch_id}", status_code=204)
    def delete_watch(watch_id: str):
        if not state.remove_watch(watch_id):
            raise HTTPException(404, "해당 감시 항목이 없습니다.")

    @app.get("/api/settings")
    def get_settings():
        with state.lock:
            return asdict(state.settings)

    @app.put("/api/settings")
    def put_settings(body: SettingsIn):
        return asdict(state.update_settings(body.interval_sec))

    @app.get("/api/movies")
    def movies():
        try:
            return get_movies(client)
        except CGVError as exc:
            raise HTTPException(502, str(exc))

    @app.get("/api/theaters")
    def theaters():
        try:
            return get_regions(client)
        except CGVError as exc:
            raise HTTPException(502, str(exc))

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
