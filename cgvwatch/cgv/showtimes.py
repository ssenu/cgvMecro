"""예매 오픈 날짜 조회. 시나리오 A 감지의 핵심."""
from __future__ import annotations

from .client import CGVClient


def get_open_dates(client: CGVClient, site_no: str, mov_no: str) -> set[str]:
    data = client.get_json(
        "searchSiteScnscYmdListByMov", {"siteNo": site_no, "movNo": mov_no}
    ) or []
    return {row["scnYmd"] for row in data if row.get("scnYmd")}
