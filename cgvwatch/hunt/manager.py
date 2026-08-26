"""헌트 큐와 스레드. Playwright는 이 스레드에서만 다룬다."""
from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

from cgvwatch.cgv.showtimes import get_showtimes
from cgvwatch.core.models import Watch
from cgvwatch.core.showpick import pick_showtime
from cgvwatch.hunt import selectors as sel
from cgvwatch.hunt.browser import BrowserManager
from cgvwatch.hunt.hunter import Hunter
from cgvwatch.notify.desktop import notify_desktop
from cgvwatch.notify.discord import (
    send_login_required,
    send_seat_secured,
    send_structure_warning,
)

logger = logging.getLogger(__name__)


class HuntManager(threading.Thread):
    """감시 스레드가 넣은 요청을 하나씩 처리한다. 동시 헌팅은 1개."""

    def __init__(self, client, profile_dir: Path, get_settings: Callable) -> None:
        super().__init__(daemon=True, name="cgvwatch-hunt")
        self._client = client
        self._profile_dir = Path(profile_dir)
        self._get_settings = get_settings
        self._queue: "queue.Queue[Watch]" = queue.Queue()
        self._lock = threading.Lock()
        self._queued_ids: set[str] = set()
        self._active: Optional[str] = None
        self._last: dict = {}
        self._hunter: Optional[Hunter] = None
        self._browser: Optional[BrowserManager] = None
        self._want_browser = threading.Event()
        self._stop = threading.Event()

    # --- 외부 API ---

    def request_browser(self) -> None:
        self._want_browser.set()

    def request_hunt(self, watch: Watch) -> bool:
        with self._lock:
            if watch.id in self._queued_ids or watch.id == self._active:
                return False
            self._queued_ids.add(watch.id)
        self._queue.put(watch)
        return True

    def stop_hunt(self) -> None:
        if self._hunter:
            self._hunter.stop()

    def stop(self) -> None:
        self._stop.set()
        self.stop_hunt()

    def status(self) -> dict:
        with self._lock:
            return {
                "browser": bool(self._browser and self._browser.is_running()),
                "active": self._active or "",
                "queued": len(self._queued_ids) - (1 if self._active else 0),
                "last": dict(self._last),
            }

    # --- 내부 ---

    def _record(self, watch: Watch, status: str, detail: str, seats=None) -> None:
        with self._lock:
            self._last = {
                "watch_id": watch.id,
                "mov_nm": watch.mov_nm,
                "status": status,
                "detail": detail,
                "seats": seats or [],
                "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    def _ensure_browser(self) -> bool:
        if self._browser is None:
            self._browser = BrowserManager(self._profile_dir)
        if not self._browser.is_running():
            self._browser.start()
        return self._browser.is_running()

    def _open_seat_page(self, watch: Watch, showtime: dict) -> bool:
        """예매 페이지로 이동해 회차를 클릭하고 좌석 화면까지 간다."""
        page = self._browser.page()
        url = sel.BOOKING_URL_TMPL.format(
            mov_no=watch.mov_no,
            ymd=watch.target_ymd,
            site_no=watch.site_no,
            site_nm=quote(watch.site_nm),
        )
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        start = showtime.get("start", "")
        label = f"{start[:2]}:{start[2:]}" if len(start) == 4 else start
        try:
            page.get_by_text(label, exact=False).first.click(timeout=15000)
        except Exception as exc:
            logger.warning("회차 클릭 실패(%s): %s", label, exc)
            return False
        for _ in range(60):
            if sel.SEAT_PATH in page.url:
                return True
            page.wait_for_timeout(500)
        return False

    def _process(self, watch: Watch) -> None:
        settings = self._get_settings()
        if not (self._browser and self._browser.is_running()):
            self._record(watch, "브라우저없음", "브라우저를 먼저 열어주세요.")
            return
        if not self._browser.is_logged_in():
            send_login_required(settings)
            self._record(watch, "로그인필요", "CGV 로그인 후 다시 시도합니다.")
            return

        showtimes = get_showtimes(
            self._client, watch.site_no, watch.mov_no, watch.target_ymd
        )
        showtime = pick_showtime(showtimes, watch.screen_filter, watch.preferred_time)
        if not showtime:
            self._record(watch, "회차없음", "조건에 맞는 회차를 찾지 못했습니다.")
            return

        if not self._open_seat_page(watch, showtime):
            send_structure_warning(watch, settings, "좌석 화면까지 진입하지 못했습니다.")
            self._record(watch, "구조변경", "좌석 화면 진입 실패")
            return

        self._hunter = Hunter(
            self._browser.page(), self._client, watch, showtime,
            on_event=lambda msg: logger.info("[헌팅] %s", msg),
        )
        result = self._hunter.run()
        self._hunter = None

        if result.status == "확보":
            try:
                self._browser.page().bring_to_front()
            except Exception:
                logger.warning("창을 앞으로 가져오지 못했습니다", exc_info=True)
            send_seat_secured(watch, settings, result.seats, showtime)
            notify_desktop("좌석 확보", f"{watch.mov_nm} {', '.join(result.seats)} — 결제해 주세요")
        elif result.status == "구조변경":
            send_structure_warning(watch, settings, result.detail)
        self._record(watch, result.status, result.detail, result.seats)

    def run(self) -> None:
        logger.info("헌트 매니저 시작")
        while not self._stop.is_set():
            if self._want_browser.is_set():
                self._want_browser.clear()
                try:
                    self._ensure_browser()
                except Exception:
                    logger.exception("브라우저 실행 실패")
            try:
                watch = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            with self._lock:
                self._active = watch.id
            try:
                self._process(watch)
            except Exception:
                logger.exception("헌팅 처리 실패: %s", watch.mov_nm)
                self._record(watch, "오류", "예기치 못한 오류. 로그를 확인하세요.")
            finally:
                with self._lock:
                    self._active = None
                    self._queued_ids.discard(watch.id)
        logger.info("헌트 매니저 종료")
