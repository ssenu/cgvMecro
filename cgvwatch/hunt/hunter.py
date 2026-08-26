"""좌석 페이지에서 자리를 확보한다. 결제 페이지에 닿으면 즉시 멈춘다."""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from cgvwatch.cgv.seats import get_seat_map
from cgvwatch.core.models import Watch
from cgvwatch.core.seatpick import pick_seats
from cgvwatch.hunt import selectors as sel

logger = logging.getLogger(__name__)

POLL_SEC = 1.0  # 좌석 폴링 하한. 더 짧게 하지 않는다.
BACKOFF_SEC = 5.0  # 429를 받았을 때 추가로 쉬는 시간


@dataclass
class HuntResult:
    status: str  # "확보" | "실패" | "구조변경" | "중단"
    seats: list[str] = field(default_factory=list)
    detail: str = ""


class Hunter:
    """한 회차의 좌석을 확보한다. 페이지는 이미 좌석 화면에 있다고 가정한다."""

    def __init__(
        self,
        page,
        client,
        watch: Watch,
        showtime: dict,
        on_event: Optional[Callable[[str], None]] = None,
        poll_sec: float = POLL_SEC,
    ) -> None:
        self.page = page
        self.client = client
        self.watch = watch
        self.showtime = showtime
        self.on_event = on_event or (lambda msg: None)
        self.poll_sec = poll_sec
        self._stop = threading.Event()
        self._blacklist: set[str] = set()

    def stop(self) -> None:
        self._stop.set()

    # --- 페이지 조작 (셀렉터를 쓰는 유일한 지점) ---

    def _seat_button_count(self) -> int:
        return self.page.locator(sel.SEAT_BUTTON).count()

    def _seat_held(self) -> bool:
        try:
            return sel.SEAT_HELD_TEXT in self.page.inner_text("body", timeout=5000)
        except Exception:
            return False

    def _left_seat_page(self) -> bool:
        return sel.SEAT_PATH not in self.page.url

    def _set_count(self) -> None:
        selector = sel.COUNT_BUTTON_TMPL.format(count=self.watch.seat_count)
        self.page.locator(selector).first.click(timeout=5000)

    def _click_seat(self, seat: dict) -> None:
        self.page.locator(
            sel.SEAT_BUTTON_BY_LOC_TMPL.format(loc_no=seat["loc_no"])
        ).first.click(timeout=5000)

    def _click_cta(self) -> None:
        self.page.get_by_role("button", name=sel.CTA_TEXT).first.click(timeout=5000)

    def _handle_modal(self, seat_name: str) -> bool:
        """모달이 떠 있으면 닫고 True. 휠체어석 경고면 블랙리스트에 넣는다."""
        modal = self.page.locator(sel.MODAL)
        if modal.count() == 0:
            return False
        try:
            text = modal.first.inner_text(timeout=2000)
        except Exception:
            text = ""
        if re.search(sel.WHEELCHAIR_TEXT, text):
            self._blacklist.add(seat_name)
        try:
            modal.first.get_by_role(
                "button", name=re.compile(sel.MODAL_CLOSE_TEXT)
            ).first.click(timeout=2000)
        except Exception:
            logger.warning("모달을 닫지 못했습니다: %s", text[:60])
        return True

    # --- 본 흐름 ---

    def _try_group(self, group: list[dict]) -> bool:
        """좌석 그룹을 클릭하고 선택완료까지. 결제 페이지로 넘어가면 True."""
        for seat in group:
            self._click_seat(seat)
            time.sleep(0.15)
            if self._handle_modal(seat["name"]):
                return False
        self._click_cta()
        for _ in range(50):
            time.sleep(0.2)
            if self._left_seat_page():
                return True
        return False

    def run(self, max_cycles: int = 3600) -> HuntResult:
        if self._stop.is_set():
            return HuntResult("중단", detail="시작 전 중단 요청")
        if self._seat_held():
            return HuntResult("중단", detail="이미 선택된 좌석이 있어 건드리지 않았습니다.")
        if self._seat_button_count() == 0:
            return HuntResult("구조변경", detail=f"좌석 버튼({sel.SEAT_BUTTON})을 찾지 못했습니다.")

        try:
            self._set_count()
        except Exception as exc:
            return HuntResult("구조변경", detail=f"인원 선택 실패: {exc}")

        backoff = 0.0
        for _ in range(max_cycles):
            if self._stop.is_set():
                return HuntResult("중단", detail="사용자 중단")
            try:
                seats = get_seat_map(
                    self.client,
                    self.watch.site_no,
                    self.watch.target_ymd,
                    self.showtime["scns_no"],
                    self.showtime["scn_sseq"],
                )
                backoff = 0.0
            except Exception as exc:
                if "429" in str(exc):
                    backoff += BACKOFF_SEC
                    self.on_event(f"요청이 제한되어 {backoff:.0f}초 쉽니다")
                logger.warning("좌석 조회 실패: %s", exc)
                time.sleep(self.poll_sec + backoff)
                continue

            for group in pick_seats(
                seats, self.watch.seat_count, self.watch.row_offset, self._blacklist
            ):
                if self._stop.is_set():
                    return HuntResult("중단", detail="사용자 중단")
                names = [s["name"] for s in group]
                self.on_event(f"좌석 시도: {', '.join(names)}")
                try:
                    if self._try_group(group):
                        return HuntResult("확보", seats=names, detail="결제 페이지 도달")
                except Exception as exc:
                    logger.warning("좌석 클릭 실패 %s: %s", names, exc)
                if self._seat_held():
                    return HuntResult("확보", seats=names, detail="좌석 선점 확인")

            time.sleep(self.poll_sec + backoff)

        return HuntResult("실패", detail="제한 시간 안에 좌석을 확보하지 못했습니다.")
