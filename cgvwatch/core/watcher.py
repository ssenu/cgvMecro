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
        try:
            send_mail(watch, settings)
        except Exception:
            # 열렸지만 메일 발송 실패(미설정/SMTP 오류 등) → 앱을 죽이지 않는다.
            # was_open을 True로 올리지 않아 다음 주기에 재시도한다.
            return replace(watch, status=Status.ERROR, last_checked=now)
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

    def _run_once(self, settings: Settings, watches: list, set_watch: Callable) -> None:
        """감시 목록 1회 순회. 어떤 항목의 예외도 스레드/앱을 죽이지 않도록 방어한다."""
        for watch in list(watches):
            if not self._running:
                break
            try:
                updated = check_watch(self._client, watch, settings)
                set_watch(updated)
                self.updated.emit(updated.id, updated.status, updated.last_checked)
            except Exception:
                # 예기치 못한 오류(저장 실패 등)로 전체가 멈추지 않도록 무시하고 다음 항목으로.
                continue

    def run(self) -> None:
        while self._running:
            settings, watches, set_watch = self._get_state()
            self._run_once(settings, watches, set_watch)
            # interval 분 동안 1초 단위로 나눠 대기 (정지 응답성)
            for _ in range(max(1, settings.interval_min) * 60):
                if not self._running:
                    break
                time.sleep(1)
