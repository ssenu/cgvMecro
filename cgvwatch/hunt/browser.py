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
        try:
            self._context = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=False,
                viewport=None,
                args=["--start-maximized"],
            )
        except Exception:
            self._pw.stop()
            self._pw = None
            raise
        page = self._context.pages[0] if self._context.pages else self._context.new_page()
        try:
            # 빈 탭(about:blank)이 뜨면 사용자가 무엇을 해야 할지 알 수 없다.
            # 로그인할 수 있도록 CGV 첫 화면을 띄워준다.
            page.goto(sel.HOME_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            logger.warning("첫 화면을 여는 데 실패했습니다(브라우저는 사용 가능)", exc_info=True)
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
        """CGV 첫 화면의 로그인/로그아웃 버튼 텍스트로 로그인 상태를 판정한다.

        2026-08-26에 실제 DOM을 확인한 결과, 로그아웃 상태에서는
        `sel.AUTH_BUTTON`에 해당하는 버튼이 정확히 하나 있고 텍스트가
        "로그인"이었다. 로그인 상태의 DOM은 아직 확인하지 못했으므로,
        버튼 텍스트가 "로그아웃"이면 로그인된 것으로 간주한다.
        어느 쪽도 아니면(판정 불가) 보수적으로 로그인되지 않은 것으로 본다.
        """
        if not self._context:
            return False
        page = self.page()
        try:
            page.goto(sel.HOME_URL, wait_until="domcontentloaded", timeout=20000)
            texts = page.locator(sel.AUTH_BUTTON).all_inner_texts()
        except Exception:
            logger.exception("로그인 상태 확인 실패")
            return False
        texts = [t.strip() for t in texts]
        if any(t == sel.LOGOUT_TEXT for t in texts):
            return True
        if any(t == sel.LOGIN_TEXT for t in texts):
            return False
        logger.warning("로그인 상태를 판정할 수 없습니다 (버튼 텍스트: %s)", texts)
        return False
