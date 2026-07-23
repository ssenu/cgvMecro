"""CGV 공개 JSON API 클라이언트. 외부 네트워크 접근은 이 모듈로만 한다."""
from __future__ import annotations

from typing import Any, Optional

import requests

BASE_URL = "https://cgv.co.kr/api/v1/booking/"
CO_CD = "A420"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class CGVError(Exception):
    """CGV API 호출 실패(HTTP 오류 또는 statusCode != 0)."""


class CGVClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        co_cd: str = CO_CD,
        timeout: int = 10,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url
        self.co_cd = co_cd
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    def get_json(self, endpoint: str, params: dict) -> Any:
        merged = {"coCd": self.co_cd, **params}
        try:
            resp = self.session.get(self.base_url + endpoint, params=merged, timeout=self.timeout)
        except requests.RequestException as exc:  # 네트워크 오류
            raise CGVError(f"요청 실패: {endpoint}: {exc}") from exc
        if resp.status_code != 200:
            raise CGVError(f"HTTP {resp.status_code}: {endpoint}")
        body = resp.json()
        if body.get("statusCode") not in (0, "0"):
            raise CGVError(f"API 오류: {body.get('statusMessage')} ({endpoint})")
        return body.get("data")
