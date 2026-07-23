from unittest.mock import MagicMock
import pytest
from cgvwatch.cgv.client import CGVClient, CGVError


def _resp(status_code=200, json_body=None):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_body or {}
    return r


def test_get_json_injects_cocd_and_returns_data():
    session = MagicMock()
    session.get.return_value = _resp(json_body={"statusCode": 0, "data": [{"x": 1}]})
    client = CGVClient(session=session)

    data = client.get_json("searchRegnList", {"siteNo": "0056"})

    assert data == [{"x": 1}]
    called_url = session.get.call_args[0][0]
    called_params = session.get.call_args[1]["params"]
    assert called_url == "https://cgv.co.kr/api/v1/booking/searchRegnList"
    assert called_params["coCd"] == "A420"
    assert called_params["siteNo"] == "0056"


def test_get_json_raises_on_nonzero_status_code():
    session = MagicMock()
    session.get.return_value = _resp(json_body={"statusCode": 400, "statusMessage": "필수값", "data": None})
    client = CGVClient(session=session)
    with pytest.raises(CGVError):
        client.get_json("searchSiteScnscYmdListByMov", {})


def test_get_json_raises_on_http_error():
    session = MagicMock()
    session.get.return_value = _resp(status_code=500, json_body={})
    client = CGVClient(session=session)
    with pytest.raises(CGVError):
        client.get_json("searchRegnList", {})
