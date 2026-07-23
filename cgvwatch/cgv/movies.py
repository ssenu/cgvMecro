"""영화 목록 조회 (제목 → movNo 매핑용)."""
from __future__ import annotations

from .client import CGVClient


def get_movies(client: CGVClient) -> list[dict]:
    data = client.get_json("searchAtktTopPostrList", {"movNm": "", "div": "", "attrCd": ""}) or []
    return [{"mov_no": m["movNo"], "mov_nm": m["movNm"]} for m in data]
