"""주기적 감시 워커. 순수 로직(check_watch)과 스레드 래퍼를 분리한다."""
from __future__ import annotations

import logging
import threading
from dataclasses import replace
from datetime import datetime
from typing import Callable, Optional

from cgvwatch.cgv.showtimes import get_open_dates, get_showtimes
from cgvwatch.core.detect import evaluate, has_screen
from cgvwatch.core.models import Settings, Status, Watch
from cgvwatch.notify.discord import (
    WebhookNotConfigured,
    send_error_alert,
    send_open_alert,
)

logger = logging.getLogger(__name__)


def _to_error(
    watch: Watch,
    settings: Settings,
    reason: str,
    now: str,
    notify_error: Callable,
) -> Watch:
    """오류 상태로 전이. 정상→오류 '전환'일 때만 디스코드 경고를 1회 시도한다."""
    if watch.status != Status.ERROR:
        try:
            notify_error(watch, settings, reason)
        except Exception:
            # 경고 발송 실패(디코 장애 등)가 감시를 막으면 안 된다.
            logger.exception("오류 경고 발송 실패: %s", watch.mov_nm)
    return replace(watch, status=Status.ERROR, last_checked=now, last_error=reason)


def check_watch(
    client,
    watch: Watch,
    settings: Settings,
    notify: Callable = send_open_alert,
    notify_error: Callable = send_error_alert,
    now: Optional[str] = None,
    on_open: Optional[Callable] = None,
) -> Watch:
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        open_dates = get_open_dates(client, watch.site_no, watch.mov_no)
    except Exception as exc:
        logger.warning("CGV 조회 실패: %s %s → %s", watch.mov_nm, watch.site_nm, exc)
        return _to_error(watch, settings, f"CGV 조회 실패: {exc}", now, notify_error)

    if evaluate(watch, open_dates):
        if watch.screen_filter:
            try:
                showtimes = get_showtimes(client, watch.site_no, watch.mov_no, watch.target_ymd)
            except Exception as exc:
                # 관 조건을 판정할 수 없으면 오류로 표시하고 다음 주기 재시도.
                logger.warning("회차 조회 실패: %s %s → %s", watch.mov_nm, watch.site_nm, exc)
                return _to_error(watch, settings, f"회차 조회 실패: {exc}", now, notify_error)
            if not has_screen(showtimes, watch.screen_filter):
                # 날짜는 열렸지만 원하는 관 회차가 아직 없다 → 계속 대기.
                return replace(watch, status=Status.WAITING, last_checked=now, last_error="")
        try:
            notify(watch, settings)
        except WebhookNotConfigured:
            # 보낼 곳이 아예 없는 것은 '실패'가 아니다. 오픈 처리를 계속해서
            # 좌석 확보(헌팅)까지 이어지게 한다. 웹훅은 나중에 넣어도 된다.
            logger.info("웹훅 미설정 — 오픈 알림을 건너뜁니다: %s", watch.mov_nm)
        except Exception as exc:
            # 보낼 곳은 있는데 실패했다(디코 장애 등) → 알림을 놓치지 않도록
            # was_open을 올리지 않고 다음 주기에 재시도한다.
            logger.exception("알림 발송 실패: %s", watch.mov_nm)
            return _to_error(watch, settings, f"알림 발송 실패: {exc}", now, notify_error)
        logger.info("예매 오픈 감지·알림 발송: %s %s %s", watch.mov_nm, watch.site_nm, watch.target_ymd)
        if on_open and watch.hunt_enabled:
            try:
                on_open(watch)
            except Exception:
                logger.exception("헌트 요청 실패: %s", watch.mov_nm)
        return replace(watch, was_open=True, status=Status.OPEN, last_checked=now, last_error="")

    status = Status.OPEN if watch.was_open else Status.WAITING
    return replace(watch, status=status, last_checked=now, last_error="")


class WatcherThread(threading.Thread):
    """백그라운드 감시 스레드. get_state()로 매 주기 최신 상태를 받아온다."""

    def __init__(
        self,
        client,
        get_state: Callable,  # () -> tuple[Settings, list[Watch], set_watch_fn]
        on_update: Optional[Callable[[Watch], None]] = None,
        on_open: Optional[Callable] = None,
    ) -> None:
        super().__init__(daemon=True, name="cgvwatch-watcher")
        self._client = client
        self._get_state = get_state
        self._on_update = on_update
        self._on_open = on_open
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _run_once(self, settings: Settings, watches: list, set_watch: Callable) -> None:
        """감시 목록 1회 순회. 어떤 항목의 예외도 스레드를 죽이지 않는다."""
        for watch in list(watches):
            if self._stop.is_set():
                break
            try:
                updated = check_watch(self._client, watch, settings, on_open=self._on_open)
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
            self._stop.wait(max(5, settings.interval_sec))
        logger.info("감시 스레드 종료")
