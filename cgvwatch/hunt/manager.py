"""헌트 큐와 스레드. Playwright는 이 스레드에서만 다룬다."""
from __future__ import annotations

import logging
import queue
import threading
import time
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
        self._cancelled: set[str] = set()
        self._active: Optional[str] = None
        self._last: dict = {}
        self._hunter: Optional[Hunter] = None
        self._browser: Optional[BrowserManager] = None
        self._browser_alive: bool = False
        self._want_browser = threading.Event()
        self._want_diag = threading.Event()
        self._want_close = threading.Event()
        self._diag: dict = {}
        self._stop = threading.Event()
        self._last_ping_monotonic: float = 0.0

    # --- 외부 API ---

    def request_browser(self) -> None:
        self._want_browser.set()

    def request_close_browser(self) -> None:
        """브라우저를 정상적으로 닫는다. 강제 종료하면 로그인 쿠키가 저장되지 않는다."""
        self._want_close.set()

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

    def cancel_watch(self, watch_id: str) -> None:
        """감시가 삭제됐을 때 호출한다. 대기/진행 중인 헌팅을 모두 정리한다.

        `_cancelled`는 run()의 큐 소비 루프가 언젠가 pop해서 discard해 줄
        항목만 기록해야 한다 — 그렇지 않은 id(한 번도 큐에 들어간 적 없거나
        이미 처리가 끝난 watch)를 넣으면 아무도 지워주지 않아 무한히 쌓인다.
        활성 id는 run()의 finally에서 pop될 때까지 _queued_ids에 남아 있으므로,
        이 멤버십 검사 하나로 "대기 중" 과 "활성" 을 모두 커버한다.
        """
        with self._lock:
            will_be_popped = watch_id in self._queued_ids
            if will_be_popped:
                self._cancelled.add(watch_id)
                self._queued_ids.discard(watch_id)
            is_active = self._active == watch_id
            hunter = self._hunter if is_active else None
            if self._last.get("watch_id") == watch_id:
                self._last = {}
        if hunter:
            hunter.stop()

    def stop(self) -> None:
        self._stop.set()
        self.stop_hunt()

    def status(self) -> dict:
        with self._lock:
            # 활성 id를 명시적으로 제외해서 센다 (단순히 -1 하면, cancel_watch가
            # 활성 id를 먼저 _queued_ids에서 지워버린 순서에서 음수가 될 수 있다).
            queued = sum(1 for wid in self._queued_ids if wid != self._active)
            return {
                # 실제 Playwright 왕복(ping())은 이 요청 스레드에서 절대 호출하지
                # 않는다 — run() 루프가 캐시해 둔 값만 읽는다.
                "browser": self._browser_alive,
                "active": self._active or "",
                "queued": queued,
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

    def _goto(self, page, url: str, attempts: int = 3) -> bool:
        """페이지 이동. CGV가 도중에 다른 곳으로 보내면 중단되므로 몇 번 재시도한다."""
        for i in range(attempts):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return True
            except Exception as exc:
                logger.warning("페이지 이동 실패(%d/%d): %s", i + 1, attempts, exc)
                page.wait_for_timeout(1500)
        return False

    def _login_modal_shown(self, page) -> bool:
        """CGV가 '로그인이 필요한 서비스' 안내를 띄웠는지."""
        try:
            modal = page.locator(sel.MODAL)
            if not modal.count():
                return False
            return sel.LOGIN_REQUIRED_TEXT in modal.first.inner_text(timeout=2000)
        except Exception:
            return False

    def _open_seat_page(self, watch: Watch, showtime: dict) -> str:
        """예매 페이지 → 회차 클릭 → 좌석 화면. "ok" | "login" | "fail"."""
        page = self._browser.page()
        url = sel.BOOKING_URL_TMPL.format(
            mov_no=watch.mov_no,
            ymd=watch.target_ymd,
            site_no=watch.site_no,
            site_nm=quote(watch.site_nm),
        )
        if not self._goto(page, url):
            logger.warning("예매 페이지로 이동하지 못했습니다: %s", url)
            return "fail"
        page.wait_for_timeout(1500)  # 광고 팝업이 뜰 시간을 준다
        self._dismiss_ads(page)
        start = showtime.get("start", "")
        label = f"{start[:2]}:{start[2:]}" if len(start) == 4 else start
        try:
            page.locator(sel.SHOWTIME_BUTTON, has_text=label).first.click(timeout=15000)
        except Exception as exc:
            logger.warning("회차 클릭 실패(%s): %s", label, exc)
            return "fail"

        # 좌석 화면 도달과 로그인 요구를 함께 지켜본다.
        # 로그인 안내 모달은 클릭 직후가 아니라 잠시 뒤에 뜬다 (확인: 2026-08-26)
        for _ in range(60):
            if sel.SEAT_PATH in page.url:
                return "ok"
            if self._login_modal_shown(page):
                logger.info("CGV가 로그인을 요구했습니다: %s", watch.mov_nm)
                return "login"
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

        try:
            entry = self._open_seat_page(watch, showtime)
        except Exception as exc:
            logger.warning("좌석 화면 진입 중 오류: %s", exc)
            entry = "fail"
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

    def _refresh_browser_liveness(self) -> None:
        """매니저 스레드에서만 호출한다. 실제 왕복(ping())으로 생존을 확인해 캐시한다.

        status()는 이 캐시된 값만 읽는다 — Playwright 객체는 이 스레드에서만
        건드릴 수 있기 때문이다. 너무 자주 왕복하지 않도록 최소 1초 간격을 둔다.
        """
        now = time.monotonic()
        if now - self._last_ping_monotonic < 1.0:
            return
        self._last_ping_monotonic = now
        if self._browser is None:
            with self._lock:
                self._browser_alive = False
            return
        alive = self._browser.ping()
        with self._lock:
            self._browser_alive = alive
            if not alive:
                # 죽은 참조를 버려서 다음 브라우저 열기가 새로 띄우게 한다.
                self._browser = None

    def _cleanup_browser(self) -> None:
        """브라우저는 이 스레드에서만 다뤄야 하므로 run() 종료 시 여기서 정리한다."""
        if self._browser is not None:
            try:
                self._browser.stop()
            except Exception:
                logger.warning("브라우저 정리 실패", exc_info=True)
            self._browser = None
        with self._lock:
            self._browser_alive = False

    def run(self) -> None:
        logger.info("헌트 매니저 시작")
        try:
            while not self._stop.is_set():
                if self._want_close.is_set():
                    self._want_close.clear()
                    self._cleanup_browser()
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
                self._refresh_browser_liveness()
                try:
                    watch = self._queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                with self._lock:
                    if watch.id in self._cancelled:
                        # 대기 중이던 감시가 삭제됐다 — 처리하지 않고 넘어간다.
                        self._cancelled.discard(watch.id)
                        self._queued_ids.discard(watch.id)
                        continue
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
                        self._cancelled.discard(watch.id)
        finally:
            self._cleanup_browser()
            logger.info("헌트 매니저 종료")
