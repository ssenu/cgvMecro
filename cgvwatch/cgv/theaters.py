"""지역·극장 목록 조회."""
from __future__ import annotations

from .client import CGVClient


def get_regions(client: CGVClient) -> list[dict]:
    data = client.get_json("searchRegnList", {}) or []
    regions = []
    for r in data:
        sites = [
            {"site_no": s["siteNo"], "site_nm": s["siteNm"]}
            for s in r.get("siteList", [])
        ]
        regions.append({"name": r.get("regnGrpNm", ""), "sites": sites})
    return regions
