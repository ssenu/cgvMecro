"""예매 오픈 날짜 조회. 시나리오 A 감지의 핵심."""
from __future__ import annotations

from .client import CGVClient


def get_open_dates(client: CGVClient, site_no: str, mov_no: str) -> set[str]:
    data = client.get_json(
        "searchSiteScnscYmdListByMov", {"siteNo": site_no, "movNo": mov_no}
    ) or []
    return {row["scnYmd"] for row in data if row.get("scnYmd")}


def get_showtimes(client: CGVClient, site_no: str, mov_no: str, ymd: str) -> list[dict]:
    """특정 날짜의 상영 회차 목록 (시작시각 HHMM 오름차순). 관 필터 판정에 사용."""
    data = client.get_json(
        "searchSchByMov",
        {"siteNo": site_no, "movNo": mov_no, "scnYmd": ymd, "rtctlScopCd": "08"},
    ) or []
    rows = [
        {
            "start": row.get("scnsrtTm", ""),
            "screen": row.get("scnsNm", ""),
            "free_seats": row.get("frSeatCnt", ""),
            "scns_no": row.get("scnsNo", ""),
            "scn_sseq": row.get("scnSseq", ""),
        }
        for row in data
        if row.get("scnsrtTm")
    ]
    return sorted(rows, key=lambda r: r["start"])
