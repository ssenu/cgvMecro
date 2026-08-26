from unittest.mock import MagicMock

import pytest

from cgvwatch.core.models import Watch
from cgvwatch.hunt.hunter import HuntResult, Hunter


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260827", seat_count=1, row_offset=1)
    base.update(kw)
    return Watch(**base)


def _showtime():
    return {"start": "1900", "screen": "3관", "free_seats": "10",
            "scns_no": "003", "scn_sseq": "2"}


def _seats(free_names):
    seats = []
    for ri, r in enumerate("ABCDE"):
        for c in range(1, 6):
            name = f"{r}{c}"
            seats.append({"name": name, "row": r, "no": c, "loc_no": f"L{name}",
                          "x": c * 2 - 1, "y": ri * 2 + 1, "free": name in free_names})
    return seats


def _page(url="https://cgv.co.kr/cnm/selectVisitorCnt", body="",
          seat_buttons=125, modals=0):
    """셀렉터별로 다른 개수를 돌려주는 페이지 목."""
    page = MagicMock()
    page.url = url
    page.inner_text.return_value = body

    def locator(selector):
        loc = MagicMock()
        loc.count.return_value = modals if "cgv-modal" in selector else seat_buttons
        return loc

    page.locator.side_effect = locator
    return page


def test_hunter_secures_seat_when_free(monkeypatch):
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats({"D3"}))
    page = _page()
    hunter = Hunter(page, MagicMock(), _watch(), _showtime(), poll_sec=0)

    # 좌석을 클릭하면 결제 페이지로 넘어간 것처럼 URL을 바꾼다
    def click_seat(seat):
        page.url = "https://cgv.co.kr/cnm/payment"

    monkeypatch.setattr(hunter, "_click_seat", click_seat)
    monkeypatch.setattr(hunter, "_click_cta", lambda: None)
    monkeypatch.setattr(hunter, "_set_count", lambda: None)

    result = hunter.run(max_cycles=1)

    assert result.status == "확보"
    assert result.seats == ["D3"]


def test_hunter_retries_next_seat_when_modal_blocks(monkeypatch):
    """모달이 뜨면 그 좌석을 포기하고 다음 후보로 넘어간다."""
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats({"D3", "D2"}))
    page = _page(modals=1)  # 항상 모달이 뜬다
    hunter = Hunter(page, MagicMock(), _watch(), _showtime(), poll_sec=0)
    tried = []
    monkeypatch.setattr(hunter, "_click_seat", lambda seat: tried.append(seat["name"]))
    monkeypatch.setattr(hunter, "_set_count", lambda: None)

    result = hunter.run(max_cycles=1)

    assert result.status == "실패"
    assert len(tried) >= 2  # 첫 후보가 막히면 다음 후보도 시도했다


def test_hunter_reports_structure_change_when_no_seat_buttons(monkeypatch):
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats({"D3"}))
    page = _page(seat_buttons=0)  # 좌석 버튼이 사라짐

    result = Hunter(page, MagicMock(), _watch(), _showtime(), poll_sec=0).run(max_cycles=1)

    assert result.status == "구조변경"


def test_hunter_returns_failed_when_no_free_seats(monkeypatch):
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats(set()))
    hunter = Hunter(_page(), MagicMock(), _watch(), _showtime(), poll_sec=0)
    monkeypatch.setattr(hunter, "_set_count", lambda: None)

    result = hunter.run(max_cycles=2)

    assert result.status == "실패"
    assert result.seats == []


def test_hunter_stops_when_asked(monkeypatch):
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats(set()))
    hunter = Hunter(_page(), MagicMock(), _watch(), _showtime(), poll_sec=0)
    monkeypatch.setattr(hunter, "_set_count", lambda: None)
    hunter.stop()

    result = hunter.run(max_cycles=5)

    assert result.status == "중단"


def test_hunter_refuses_when_seat_already_held(monkeypatch):
    """이미 좌석을 잡아둔 화면이면 건드리지 않는다."""
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats({"D3"}))
    page = _page(body="선택하신 좌석 D3")

    result = Hunter(page, MagicMock(), _watch(), _showtime()).run(max_cycles=1)

    assert result.status == "중단"
    assert "이미" in result.detail
