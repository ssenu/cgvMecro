import json
from pathlib import Path
from unittest.mock import MagicMock
from cgvwatch.cgv.movies import get_movies

FIX = json.loads((Path(__file__).parent / "fixtures" / "movies.json").read_text(encoding="utf-8"))


def test_get_movies_parses_list():
    client = MagicMock()
    client.get_json.return_value = FIX["data"]

    movies = get_movies(client)

    assert {"mov_no": "30001192", "mov_nm": "스파이더맨-브랜드 뉴 데이"} in movies
    endpoint, params = client.get_json.call_args[0]
    assert endpoint == "searchAtktTopPostrList"
    assert params == {"movNm": "", "div": "", "attrCd": ""}
