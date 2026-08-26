from cgvwatch.hunt import selectors as sel


def test_booking_url_has_all_params():
    url = sel.BOOKING_URL_TMPL.format(
        mov_no="30001192", ymd="20260827", site_no="0056", site_nm="%EA%B0%95%EB%82%A8"
    )
    assert url.startswith("https://cgv.co.kr/cnm/movieBook/movie?")
    for part in ("movNo=30001192", "scnYmd=20260827", "siteNo=0056", "siteNm="):
        assert part in url


def test_count_button_template_renders():
    assert sel.COUNT_BUTTON_TMPL.format(count=2) == 'button[aria-label="2 선택"]'


def test_seat_button_by_loc_template_renders():
    assert sel.SEAT_BUTTON_BY_LOC_TMPL.format(loc_no="00100100230015") == (
        'button[data-seatlocno="00100100230015"]'
    )


def test_required_selectors_are_non_empty_strings():
    for name in ("SEAT_PATH", "SEAT_BUTTON", "SEAT_BUTTON_BY_LOC_TMPL", "COUNT_WRAP",
                 "MODAL", "MODAL_CLOSE_TEXT", "WHEELCHAIR_TEXT", "SEAT_HELD_TEXT", "CTA_TEXT",
                 "SHOWTIME_BUTTON", "LOGIN_REQUIRED_TEXT",
                 "AUTH_BUTTON", "LOGIN_TEXT", "LOGOUT_TEXT", "HOME_URL"):
        value = getattr(sel, name)
        assert isinstance(value, str) and value


def test_home_url_is_cgv():
    assert sel.HOME_URL.startswith("https://cgv.co.kr")
