"""좌석 후보 선정. CGV·Playwright에 의존하지 않는 순수 로직."""
from __future__ import annotations

FRONT_EXCLUDE_RATIO = 0.2  # 스크린에 가까운 앞줄 20%는 후보에서 제외
ROW_WEIGHT = 2  # 행 차이를 번호 차이보다 무겁게 본다
ADJACENT_X_GAP = 2  # 같은 행의 옆자리는 x가 2 차이 (2026-08-26 확인)


def _rows(seats: list[dict]) -> list[str]:
    return sorted({s["row"] for s in seats})


def center_of(seats: list[dict], row_offset: int = 1) -> tuple[int, int]:
    """(중앙 행 인덱스, 중앙 번호). row_offset만큼 뒤쪽 행으로 민다."""
    rows = _rows(seats)
    if not rows:
        return (0, 0)
    row_idx = min(len(rows) - 1, max(0, len(rows) // 2 + row_offset))
    numbers = sorted(s["no"] for s in seats)
    return (row_idx, numbers[len(numbers) // 2])


def _score(seat: dict, rows: list[str], center_row: int, center_no: int) -> int:
    return abs(rows.index(seat["row"]) - center_row) * ROW_WEIGHT + abs(
        seat["no"] - center_no
    )


def pick_seats(
    seats: list[dict],
    count: int,
    row_offset: int = 1,
    blacklist: set[str] | None = None,
) -> list[list[dict]]:
    """점수가 좋은 순으로 정렬된 좌석 후보 그룹 목록."""
    if not seats or count not in (1, 2):
        return []
    black = blacklist or set()
    rows = _rows(seats)
    center_row, center_no = center_of(seats, row_offset)
    excluded = set(rows[: int(len(rows) * FRONT_EXCLUDE_RATIO)])

    usable = [
        s
        for s in seats
        if s["free"] and s["name"] not in black and s["row"] not in excluded
    ]
    if count == 1:
        scored = [([s], _score(s, rows, center_row, center_no)) for s in usable]
    else:
        by_pos = {(s["y"], s["x"]): s for s in usable}
        scored = []
        for s in usable:
            right = by_pos.get((s["y"], s["x"] + ADJACENT_X_GAP))
            if not right:
                continue
            pair_score = (
                _score(s, rows, center_row, center_no)
                + _score(right, rows, center_row, center_no)
            ) / 2
            scored.append(([s, right], pair_score))

    scored.sort(key=lambda item: (item[1], item[0][0]["name"]))
    return [group for group, _ in scored]
