"""좌석 지도 조회. 로그인 없이도 응답한다(2026-08-26 확인)."""
from __future__ import annotations

from .client import CGVClient

FREE_STATUS = "00"  # 00=빈자리, 01=판매완료, 04=선점중


def get_seat_map(
    client: CGVClient,
    site_no: str,
    scn_ymd: str,
    scns_no: str,
    scn_sseq: str,
) -> list[dict]:
    """회차의 전체 좌석 목록. 각 좌석은 name/row/no/loc_no/x/y/free를 갖는다."""
    data = client.get_json(
        "searchIfSeatData",
        {
            "siteNo": site_no,
            "scnYmd": scn_ymd,
            "scnsNo": scns_no,
            "scnSseq": scn_sseq,
            "seatAreaNo": "001",
            "cusgdCd": "01",
        },
    )
    items = (data or {}).get("items") or []
    if not items:
        return []
    seats = []
    for raw in items[0].get("seats") or []:
        row = raw.get("seatRowNm") or ""
        no_txt = raw.get("seatNo") or ""
        if not row or not no_txt.isdigit():
            continue
        seats.append(
            {
                "name": f"{row}{int(no_txt)}",
                "row": row,
                "no": int(no_txt),
                "loc_no": raw.get("seatLocNo") or "",
                "x": int(raw.get("xcoordStartVal") or 0),
                "y": int(raw.get("ycoordStartVal") or 0),
                "free": raw.get("seatStusCd") == FREE_STATUS
                and raw.get("seatSaleYn") == "Y",
            }
        )
    return seats
