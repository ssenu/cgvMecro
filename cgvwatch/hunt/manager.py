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
        self._want_diag = threading.Event()
        self._diag: dict = {}
        self._stop = threading.Event()

    # --- 외부 API ---

    def request_browser(self) -> None:
        self._want_browser.set()

    def request_diag(self) -> None:
        """지금 브라우저가 무엇을 보고 있는지 수집을 요청한다(셀렉터 진단용)."""
        self._want_diag.set()

    def _collect_diag(self) -> None:
        """매니저 스레드에서만 실행된다(Playwright 격리)."""
        info: dict = {}
        try:
            page = self._browser.page()
            info["url"] = page.url
            info["title"] = page.title()
            info["auth_buttons"] = [t.strip() for t in page.locator(sel.AUTH_BUTTON).all_inner_texts()][:5]
            modal = page.locator(sel.MODAL)
            info["modal_count"] = modal.count()
            info["modal_text"] = modal.first.inner_text(timeout=2000)[:200] if modal.count() else ""
            info["seat_buttons"] = page.locator(sel.SEAT_BUTTON).count()
            info["count_wrap"] = page.locator(sel.COUNT_WRAP).count()
            info["showtime_buttons"] = page.locator(sel.SHOWTIME_BUTTON).count()
            info["cta"] = page.get_by_role("button", name=sel.CTA_TEXT).count()
            for n in (1, 2):
                info[f"count_btn_{n}"] = page.locator(sel.COUNT_BUTTON_TMPL.format(count=n)).count()
            body = page.inner_text(sel.BODY, timeout=3000)
            info["has_logout_text"] = sel.LOGOUT_TEXT in body
            info["has_login_text"] = sel.LOGIN_TEXT in body
        except Exception as exc:
            info["error"] = f"{type(exc).__name__}: {exc}"
        with self._lock:
            self._diag = info
        logger.info("진단: %s", info)

    def request_hunt(self, watch: Watch) -> bool:
        with self._lock:
            if watch.id in self._queued_ids or watch.id == self._active:
                return False
            self._queued_ids.add(watch.id)
        self._queue.put(watch)
        return True

    def stop_hunt(self) -> None:
        with self._lock:
            hunter = self._hunter
        if hunter:
            hunter.stop()

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
                "diag": dict(self._diag),
            }

    # --- 내부 ---

    def _notify(self, fn, *args) -> None:
        """알림은 부가 기능이다. 실패해도 헌팅 결과를 바꾸지 않는다."""
        try:
            fn(*args)
        except Exception:
            logger.warning("알림 발송 실패 (무시하고 계속합니다)", exc_info=True)

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
            browser = BrowserManager(self._profile_dir)
            with self._lock:
                self._browser = browser
        if not self._browser.is_running():
            self._browser.start()
        return self._browser.is_running()

    def _dismiss_ads(self, page) -> None:
        """광고 팝업을 닫는다. 로그인 안내 모달은 건드리지 않는다."""
        import re as _re
        for _ in range(3):
            try:
                modal = page.locator(sel.MODAL)
                if not modal.count():
                    return
                text = modal.first.inner_text(timeout=2000)
                if sel.LOGIN_REQUIRED_TEXT in text:
                    return  # 로그인 안내는 호출부가 판정해야 한다
                modal.first.get_by_role(
                    "button", name=_re.compile(sel.AD_DISMISS_TEXT)
                ).first.click(timeout=2000)
                logger.info("광고 팝업을 닫았습니다: %s", " ".join(text.split())[:40])
                page.wait_for_timeout(400)
            except Exception:
                return

    def _open_seat_page(self, watch: Watch, showtime: dict) -> str:
        """예매 페이지 → 회차 클릭 → 좌석 화면. "ok" | "login" | "fail"."""
        page = self._browser.page()
        url = sel.BOOKING_URL_TMPL.format(
            mov_no=watch.mov_no,
            ymd=watch.target_ymd,
            site_no=watch.site_no,
            site_nm=quote(watch.site_nm),
        )
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)  # 광고 팝업이 뜰 시간을 준다
        self._dismiss_ads(page)
        start = showtime.get("start", "")
        label = f"{start[:2]}:{start[2:]}" if len(start) == 4 else start
        try:
            page.locator(sel.SHOWTIME_BUTTON, has_text=label).first.click(timeout=15000)
        except Exception as exc:
            logger.warning("회차 클릭 실패(%s): %s", label, exc)
            return "fail"

        # 로그인하지 않았으면 CGV가 안내 모달을 띄운다 (확인: 2026-08-26)
        try:
            modal = page.locator(sel.MODAL)
            if modal.count() and sel.LOGIN_REQUIRED_TEXT in modal.first.inner_text(timeout=3000):
                logger.info("CGV가 로그인을 요구했습니다: %s", watch.mov_nm)
                return "login"
        except Exception:
            logger.debug("모달 확인 실패(무시)", exc_info=True)
        for _ in range(60):
            if sel.SEAT_PATH in page.url:
                return "ok"
            page.wait_for_timeout(500)
        logger.warning("좌석 화면(%s)에 도달하지 못했습니다: %s", sel.SEAT_PATH, page.url)
        return "fail"

    def _process(self, watch: Watch) -> None:
        settings = self._get_settings()
        if not (self._browser and self._browser.is_running()):
            self._record(watch, "브라우저없음", "브라우저를 먼저 열어주세요.")
            return
        # 사전 로그인 검사는 하지 않는다. 첫 화면 푸터로 판정하는 방식은
        # 렌더 시점에 따라 틀리게 나와 헌팅을 막는 일이 잦았다.
        # 회차를 눌렀을 때 CGV가 띄우는 안내 모달이 유일하게 믿을 수 있는 신호다.

        showtimes = get_showtimes(
            self._client, watch.site_no, watch.mov_no, watch.target_ymd
        )
        showtime = pick_showtime(showtimes, watch.screen_filter, watch.preferred_time)
        if not showtime:
            self._record(watch, "회차없음", "조건에 맞는 회차를 찾지 못했습니다.")
            return

        entry = self._open_seat_page(watch, showtime)
        if entry == "login":
            self._notify(send_login_required, settings)
            self._record(watch, "로그인필요", "CGV가 로그인을 요구했습니다.")
            return
        if entry != "ok":
            self._notify(send_structure_warning, watch, settings, "좌석 화면까지 진입하지 못했습니다.")
            self._record(watch, "구조변경", "좌석 화면 진입 실패")
            return

        hunter = Hunter(
            self._browser.page(), self._client, watch, showtime,
            on_event=lambda msg: logger.info("[헌팅] %s", msg),
        )
        with self._lock:
            self._hunter = hunter
        result = hunter.run()
        with self._lock:
            self._hunter = None

        if result.status == "확보":
            try:
                self._browser.page().bring_to_front()
            except Exception:
                logger.warning("창을 앞으로 가져오지 못했습니다", exc_info=True)
            self._notify(send_seat_secured, watch, settings, result.seats, showtime)
            self._notify(notify_desktop, "좌석 확보", f"{watch.mov_nm} {', '.join(result.seats)} — 결제해 주세요")
        elif result.status == "구조변경":
            self._notify(send_structure_warning, watch, settings, result.detail)
        self._record(watch, result.status, result.detail, result.seats)

    def _cleanup_browser(self) -> None:
        """브라우저는 이 스레드에서만 다뤄야 하므로 run() 종료 시 여기서 정리한다."""
        if self._browser is not None:
            try:
                self._browser.stop()
            except Exception:
                logger.warning("브라우저 정리 실패", exc_info=True)
            self._browser = None

    def run(self) -> None:
        logger.info("헌트 매니저 시작")
        try:
            while not self._stop.is_set():
                if self._want_diag.is_set():
                    self._want_diag.clear()
                    if self._browser and self._browser.is_running():
                        self._collect_diag()
                    else:
                        with self._lock:
                            self._diag = {"error": "브라우저가 꺼져 있습니다."}
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
        finally:
            self._cleanup_browser()
            logger.info("헌트 매니저 종료")
