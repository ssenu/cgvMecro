import json
from pathlib import Path
from unittest.mock import MagicMock
from cgvwatch.cgv.theaters import get_regions

FIX = json.loads((Path(__file__).parent / "fixtures" / "regions.json").read_text(encoding="utf-8"))


def test_get_regions_parses_sites():
    client = MagicMock()
    client.get_json.return_value = FIX["data"]

    regions = get_regions(client)

    assert regions[0]["name"] == "서울"
    assert {s["site_nm"] for s in regions[0]["sites"]} == {"강남", "강변"}
    assert regions[0]["sites"][0]["site_no"] == "0056"
    client.get_json.assert_called_once_with("searchRegnList", {})
