"""주기적 감시 워커. 순수 로직(check_watch)과 스레드 래퍼를 분리한다."""
from __future__ import annotations

import logging
import threading
from dataclasses import replace
from datetime import datetime
from typing import Callable, Optional

from cgvwatch.cgv.showtimes import get_open_dates
from cgvwatch.core.detect import evaluate
from cgvwatch.core.models import Settings, Status, Watch
from cgvwatch.notify.discord import send_open_alert

logger = logging.getLogger(__name__)


def check_watch(
    client,
    watch: Watch,
    settings: Settings,
    notify: Callable = send_open_alert,
    now: Optional[str] = None,
) -> Watch:
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        open_dates = get_open_dates(client, watch.site_no, watch.mov_no)
    except Exception as exc:
        logger.warning("CGV 조회 실패: %s %s → %s", watch.mov_nm, watch.site_nm, exc)
        return replace(watch, status=Status.ERROR, last_checked=now)

    if evaluate(watch, open_dates):
        try:
            notify(watch, settings)
        except Exception:
            # 열렸지만 알림 실패(웹훅 미설정 등) → 앱을 죽이지 않는다.
            # was_open을 True로 올리지 않아 다음 주기에 재시도한다.
            logger.exception("알림 발송 실패: %s", watch.mov_nm)
            return replace(watch, status=Status.ERROR, last_checked=now)
        logger.info("예매 오픈 감지·알림 발송: %s %s %s", watch.mov_nm, watch.site_nm, watch.target_ymd)
        return replace(watch, was_open=True, status=Status.OPEN, last_checked=now)

    status = Status.OPEN if watch.was_open else Status.WAITING
    return replace(watch, status=status, last_checked=now)


class WatcherThread(threading.Thread):
    """백그라운드 감시 스레드. get_state()로 매 주기 최신 상태를 받아온다."""

    def __init__(
        self,
        client,
        get_state: Callable,  # () -> tuple[Settings, list[Watch], set_watch_fn]
        on_update: Optional[Callable[[Watch], None]] = None,
    ) -> None:
        super().__init__(daemon=True, name="cgvwatch-watcher")
        self._client = client
        self._get_state = get_state
        self._on_update = on_update
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _run_once(self, settings: Settings, watches: list, set_watch: Callable) -> None:
        """감시 목록 1회 순회. 어떤 항목의 예외도 스레드를 죽이지 않는다."""
        for watch in list(watches):
            if self._stop.is_set():
                break
            try:
                updated = check_watch(self._client, watch, settings)
                set_watch(updated)
                if self._on_update:
                    self._on_update(updated)
            except Exception:
                logger.exception("감시 항목 처리 실패: %s", getattr(watch, "id", "?"))
                continue

    def run(self) -> None:
        logger.info("감시 스레드 시작")
        while not self._stop.is_set():
            settings, watches, set_watch = self._get_state()
            self._run_once(settings, watches, set_watch)
            self._stop.wait(max(1, settings.interval_min) * 60)
        logger.info("감시 스레드 종료")
