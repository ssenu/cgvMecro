import json
from pathlib import Path
from unittest.mock import MagicMock

from cgvwatch.cgv.seats import get_seat_map

FIX = json.loads((Path(__file__).parent / "fixtures" / "seatmap.json").read_text(encoding="utf-8"))


def test_get_seat_map_parses_seats():
    client = MagicMock()
    client.get_json.return_value = FIX

    seats = get_seat_map(client, "0056", "20260827", "003", "2")

    assert len(seats) == 12
    a1 = next(s for s in seats if s["name"] == "A1")
    assert a1 == {"name": "A1", "row": "A", "no": 1, "loc_no": "L001",
                  "x": 1, "y": 1, "free": True}
    endpoint, params = client.get_json.call_args[0]
    assert endpoint == "searchIfSeatData"
    assert params == {"siteNo": "0056", "scnYmd": "20260827", "scnsNo": "003",
                      "scnSseq": "2", "seatAreaNo": "001", "cusgdCd": "01"}


def test_get_seat_map_marks_sold_and_holding_as_not_free():
    client = MagicMock()
    client.get_json.return_value = FIX

    seats = get_seat_map(client, "0056", "20260827", "003", "2")

    sold = next(s for s in seats if s["name"] == "A3")      # seatStusCd 01
    holding = next(s for s in seats if s["name"] == "B2")   # seatStusCd 04
    assert sold["free"] is False
    assert holding["free"] is False
    assert len([s for s in seats if s["free"]]) == 10


def test_get_seat_map_empty_when_no_items():
    client = MagicMock()
    client.get_json.return_value = {"resultCode": "0", "items": []}
    assert get_seat_map(client, "0056", "20260827", "003", "2") == []


def test_get_seat_map_empty_when_none():
    client = MagicMock()
    client.get_json.return_value = None
    assert get_seat_map(client, "0056", "20260827", "003", "2") == []
