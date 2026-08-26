"""로그인된 크롬을 전용 프로필로 관리한다. 계정 정보는 다루지 않는다."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

from cgvwatch.hunt import selectors as sel

logger = logging.getLogger(__name__)


class BrowserManager:
    """Playwright 전용 프로필 크롬. 반드시 한 스레드에서만 사용한다."""

    def __init__(self, profile_dir: Path) -> None:
        self.profile_dir = Path(profile_dir)
        self._pw = None
        self._context = None

    def start(self) -> None:
        if self._context:
            return
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=False,
            viewport=None,
            args=["--start-maximized"],
        )
        if not self._context.pages:
            self._context.new_page()
        logger.info("브라우저 시작: %s", self.profile_dir)

    def stop(self) -> None:
        try:
            if self._context:
                self._context.close()
        finally:
            self._context = None
            if self._pw:
                self._pw.stop()
                self._pw = None
            logger.info("브라우저 종료")

    def is_running(self) -> bool:
        return self._context is not None

    def page(self):
        """첫 번째 탭. 브라우저가 꺼져 있으면 RuntimeError."""
        if not self._context:
            raise RuntimeError("브라우저가 실행되지 않았습니다.")
        return self._context.pages[0] if self._context.pages else self._context.new_page()

    def is_logged_in(self) -> bool:
        """CGV 첫 화면에서 로그인 문구가 안 보이면 로그인된 것으로 본다."""
        if not self._context:
            return False
        page = self.page()
        try:
            page.goto("https://cgv.co.kr/", wait_until="domcontentloaded", timeout=20000)
            body = page.inner_text("body", timeout=5000)
        except Exception:
            logger.exception("로그인 상태 확인 실패")
            return False
        return sel.LOGIN_MARK not in body
