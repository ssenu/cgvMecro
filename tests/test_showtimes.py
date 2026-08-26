import json
from pathlib import Path
from unittest.mock import MagicMock
from cgvwatch.cgv.showtimes import get_open_dates

FIX = json.loads((Path(__file__).parent / "fixtures" / "open_dates.json").read_text(encoding="utf-8"))


def test_get_open_dates_returns_set():
    client = MagicMock()
    client.get_json.return_value = FIX["data"]

    dates = get_open_dates(client, "0056", "30001192")

    assert dates == {"20260729", "20260730"}
    endpoint, params = client.get_json.call_args[0]
    assert endpoint == "searchSiteScnscYmdListByMov"
    assert params == {"siteNo": "0056", "movNo": "30001192"}


def test_get_open_dates_empty_when_no_data():
    client = MagicMock()
    client.get_json.return_value = None
    assert get_open_dates(client, "0056", "30001192") == set()


def test_get_showtimes_parses_and_sorts():
    from cgvwatch.cgv.showtimes import get_showtimes
    client = MagicMock()
    client.get_json.return_value = [
        {"scnsrtTm": "1550", "scnsNm": "1관 (Laser)", "frSeatCnt": "34",
         "scnsNo": "001", "scnSseq": "3"},
        {"scnsrtTm": "0900", "scnsNm": "IMAX관", "frSeatCnt": "28",
         "scnsNo": "018", "scnSseq": "1"},
    ]

    rows = get_showtimes(client, "0056", "30001192", "20260819")

    assert rows == [
        {"start": "0900", "screen": "IMAX관", "free_seats": "28",
         "scns_no": "018", "scn_sseq": "1"},
        {"start": "1550", "screen": "1관 (Laser)", "free_seats": "34",
         "scns_no": "001", "scn_sseq": "3"},
    ]
    endpoint, params = client.get_json.call_args[0]
    assert endpoint == "searchSchByMov"
    assert params == {"siteNo": "0056", "movNo": "30001192",
                      "scnYmd": "20260819", "rtctlScopCd": "08"}
