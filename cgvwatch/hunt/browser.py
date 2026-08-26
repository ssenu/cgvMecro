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
        if self.is_running():
            return
        if self._context or self._pw:
            # 상태는 남아 있는데 실제로는 죽어 있다(사용자가 창을 직접 닫은 경우 등).
            # 새로 띄우기 전에 낡은 상태를 정리한다.
            self._cleanup()
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
        self._context.on("close", self._on_context_closed)
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
            self._cleanup()
            logger.info("브라우저 종료")

    def _on_context_closed(self, *_args) -> None:
        """사용자가 크롬 창을 직접 닫는 등, 우리가 모르는 사이에 컨텍스트가 죽었을 때 불린다."""
        logger.info("브라우저 컨텍스트가 닫혔습니다(외부에서 종료됨)")

    def is_running(self) -> bool:
        """실제로 살아 있는지 확인한다. 죽어 있으면 내부 상태도 함께 정리한다.

        컨텍스트 객체가 남아 있어도(사용자가 창을 직접 닫은 경우) 실제로는
        죽어 있을 수 있으므로, 방어적으로 pages에 접근해 본다.
        지속 컨텍스트에 열린 탭이 하나도 없는 것도 "죽었다"로 취급한다 —
        우리 흐름은 항상 탭을 최소 하나 열어 두기 때문이다.
        """
        if self._context is None:
            return False
        try:
            alive = len(self._context.pages) > 0
        except Exception:
            alive = False
        if not alive:
            self._cleanup()
            return False
        return True

    def _cleanup(self) -> None:
        """죽었거나 낡은 상태를 정리한다. Playwright 드라이버가 살아 있으면 멈춘다."""
        self._context = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                logger.warning("Playwright 드라이버 정리 실패(무시)", exc_info=True)
            self._pw = None

    def page(self):
        """첫 번째 탭. 브라우저가 꺼져 있으면 RuntimeError."""
        if not self._context:
            raise RuntimeError("브라우저가 실행되지 않았습니다.")
        return self._context.pages[0] if self._context.pages else self._context.new_page()

    def login_state(self) -> Optional[bool]:
        """로그인 상태. True=로그인됨 / False=로그아웃됨 / None=판정 불가.

        CGV 첫 화면 푸터의 로그인·로그아웃 버튼 텍스트로 판정한다.
        (확인: 2026-08-26 — 로그아웃 상태에서 `sel.AUTH_BUTTON`이 정확히 하나,
        텍스트가 "로그인"이었다. 로그인 상태의 DOM은 아직 확인하지 못했다.)

        푸터는 스크립트로 늦게 그려지므로 버튼이 붙을 때까지 잠깐 기다린다.
        그래도 못 찾으면 None을 돌려주고, 판단은 호출부에 맡긴다.
        """
        if not self._context:
            return False
        page = self.page()
        try:
            page.goto(sel.HOME_URL, wait_until="domcontentloaded", timeout=20000)
            buttons = page.locator(sel.AUTH_BUTTON)
            try:
                buttons.first.wait_for(state="attached", timeout=10000)
            except Exception:
                logger.warning("로그인 버튼(%s)이 나타나지 않았습니다", sel.AUTH_BUTTON)
                return None
            texts = [t.strip() for t in buttons.all_inner_texts()]
        except Exception:
            logger.exception("로그인 상태 확인 실패")
            return None
        if any(t == sel.LOGOUT_TEXT for t in texts):
            return True
        if any(t == sel.LOGIN_TEXT for t in texts):
            return False
        logger.warning("로그인 상태를 판정할 수 없습니다 (버튼 텍스트: %s)", texts)
        return None

    def is_logged_in(self) -> bool:
        """확실히 로그인된 경우에만 True. 판정 불가는 False로 접는다."""
        return self.login_state() is True
