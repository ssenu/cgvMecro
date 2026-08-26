from cgvwatch.core.showpick import pick_showtime


def _rows():
    return [
        {"start": "0900", "screen": "1관 (Laser)", "free_seats": "10", "scns_no": "001", "scn_sseq": "1"},
        {"start": "1400", "screen": "IMAX관", "free_seats": "50", "scns_no": "018", "scn_sseq": "2"},
        {"start": "1900", "screen": "IMAX관", "free_seats": "0", "scns_no": "018", "scn_sseq": "3"},
        {"start": "2200", "screen": "4DX관", "free_seats": "5", "scns_no": "004", "scn_sseq": "4"},
    ]


def test_pick_showtime_without_filter_returns_earliest():
    assert pick_showtime(_rows(), "", "")["start"] == "0900"


def test_pick_showtime_applies_screen_filter():
    assert pick_showtime(_rows(), "imax", "")["start"] == "1400"


def test_pick_showtime_picks_nearest_to_preferred_time():
    assert pick_showtime(_rows(), "", "2000")["start"] == "1900"


def test_pick_showtime_filter_and_preference_together():
    assert pick_showtime(_rows(), "IMAX", "2100")["scn_sseq"] == "3"


def test_pick_showtime_none_when_filter_matches_nothing():
    assert pick_showtime(_rows(), "돌비", "") is None


def test_pick_showtime_none_when_empty():
    assert pick_showtime([], "", "") is None


def test_pick_showtime_falls_back_when_preferred_time_malformed():
    """잘못된 형식의 선호 시각은 '선호 없음'과 같게 취급해 가장 이른 회차를 고른다."""
    assert pick_showtime(_rows(), "", "7pm")["start"] == "0900"
