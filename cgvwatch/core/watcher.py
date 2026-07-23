"""주기적 감시 워커. 순수 로직(check_watch)과 QThread 래퍼를 분리한다."""
from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from cgvwatch.cgv.showtimes import get_open_dates
from cgvwatch.core.detect import evaluate
from cgvwatch.core.models import Settings, Status, Watch
from cgvwatch.notify.mailer import send_open_mail


def check_watch(
    client,
    watch: Watch,
    settings: Settings,
    send_mail: Callable = send_open_mail,
    now: Optional[str] = None,
) -> Watch:
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        open_dates = get_open_dates(client, watch.site_no, watch.mov_no)
    except Exception:
        return replace(watch, status=Status.ERROR, last_checked=now)

    if evaluate(watch, open_dates):
        send_mail(watch, settings)
        return replace(watch, was_open=True, status=Status.OPEN, last_checked=now)

    status = Status.OPEN if watch.was_open else Status.WAITING
    return replace(watch, status=status, last_checked=now)


class WatcherWorker(QThread):
    updated = pyqtSignal(str, str, str)  # watch_id, status, last_checked

    def __init__(self, client, get_state: Callable, parent=None) -> None:
        super().__init__(parent)
        self._client = client
        self._get_state = get_state  # () -> tuple[Settings, list[Watch], set_watch_fn]
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            settings, watches, set_watch = self._get_state()
            for watch in list(watches):
                if not self._running:
                    break
                updated = check_watch(self._client, watch, settings)
                set_watch(updated)
                self.updated.emit(updated.id, updated.status, updated.last_checked)
            # interval 분 동안 1초 단위로 나눠 대기 (정지 응답성)
            for _ in range(max(1, settings.interval_min) * 60):
                if not self._running:
                    break
                time.sleep(1)
