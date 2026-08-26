from cgvwatch.core.seatpick import center_of, pick_seats


def _grid(rows="ABCDE", cols=9, free=None):
    """rows × cols 격자. free=None이면 전부 빈자리."""
    seats = []
    for ri, r in enumerate(rows):
        for c in range(1, cols + 1):
            name = f"{r}{c}"
            seats.append({
                "name": name, "row": r, "no": c, "loc_no": f"L{name}",
                "x": c * 2 - 1, "y": ri * 2 + 1,
                "free": True if free is None else name in free,
            })
    return seats


def test_center_of_returns_middle_row_and_number():
    # 5행(A~E) × 9열 → 중앙 행 인덱스 2(C), 오프셋 +1이면 3(D), 중앙 번호 5
    assert center_of(_grid(), row_offset=1) == (3, 5)


def test_center_of_without_offset():
    assert center_of(_grid(), row_offset=0) == (2, 5)


def test_pick_seats_prefers_center_after_offset():
    groups = pick_seats(_grid(), count=1, row_offset=1)
    assert groups[0][0]["name"] == "D5"


def test_pick_seats_excludes_front_rows():
    """전체 5행이면 앞 20%(=1행, A열)는 후보에서 빠진다."""
    groups = pick_seats(_grid(), count=1, row_offset=1)
    names = {g[0]["name"] for g in groups}
    assert not any(n.startswith("A") for n in names)
    assert any(n.startswith("B") for n in names)


def test_pick_seats_only_free_seats():
    groups = pick_seats(_grid(free={"B3", "D5"}), count=1, row_offset=1)
    assert [g[0]["name"] for g in groups] == ["D5", "B3"]


def test_pick_seats_respects_blacklist():
    groups = pick_seats(_grid(free={"B3", "D5"}), count=1, row_offset=1,
                        blacklist={"D5"})
    assert [g[0]["name"] for g in groups] == ["B3"]


def test_pick_seats_pairs_are_adjacent():
    groups = pick_seats(_grid(), count=2, row_offset=1)
    first = groups[0]
    assert len(first) == 2
    assert first[0]["y"] == first[1]["y"]
    assert abs(first[0]["x"] - first[1]["x"]) == 2


def test_pick_seats_pair_skips_gap():
    """통로(x 간격이 2가 아닌 곳)를 사이에 둔 좌석은 연석이 아니다."""
    seats = _grid(rows="BCD", cols=2)
    for s in seats:
        if s["no"] == 2:
            s["x"] += 4  # 통로를 만든다
    assert pick_seats(seats, count=2, row_offset=0) == []


def test_pick_seats_empty_when_nothing_free():
    assert pick_seats(_grid(free=set()), count=1) == []
