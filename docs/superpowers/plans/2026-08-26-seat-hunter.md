# 좌석 확보 통합(Seat Hunter) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 감시 앱이 예매 오픈·취소표를 감지하면 로그인된 크롬을 자동으로 조종해 좌석 선택까지 마치고 결제 직전에 멈춘 뒤 사람을 부른다.

**Architecture:** 노트북 단독 실행(`python run.py`). 기존 감시 스레드는 그대로 두고, Playwright를 소유하는 **헌트 매니저 스레드**를 추가한다. 두 스레드는 큐로만 통신한다. 좌석 판정은 DOM이 아니라 좌석 지도 API 결과로 하며, 이 계산은 순수 함수로 분리해 단위 테스트한다.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, requests, **playwright (sync API)**, pytest
**패키지 관리:** [uv](https://docs.astral.sh/uv/) — `pyproject.toml` + `uv.lock`

## Global Constraints

- 설계 문서: `docs/superpowers/specs/2026-08-26-seat-hunter-design.md` — CGV API·DOM 관찰 기록이 여기 있다. 막히면 먼저 읽는다.
- 자동 로그인을 만들지 않는다. 계정 정보(아이디/비밀번호)를 코드·설정·로그 어디에도 저장하지 않는다.
- 결제를 자동화하지 않는다. 결제 페이지 도달 즉시 모든 자동 동작을 중단한다.
- 좌석 폴링 간격 하한은 **1초**(`POLL_SEC = 1.0`). 429를 받으면 대기를 늘린다.
- 동시 헌팅은 **1개**. 활성 헌팅이 있으면 큐에서 꺼내지 않는다.
- CGV API 호출은 반드시 기존 `CGVClient`를 통한다(`Referer` 헤더가 거기 있다). 새로 `requests.get`을 직접 쓰지 않는다.
- 상태 문자열은 기존 `Status`(`대기중`/`열림`/`오류`)를 그대로 쓰고, 헌팅 상태는 별도 문자열로 둔다.
- 모든 DOM 셀렉터와 URL 경로는 `cgvwatch/hunt/selectors.py`에만 둔다. 다른 파일에 셀렉터 문자열을 쓰지 않는다.
- **의존성은 uv로 관리한다.** 패키지 추가는 `uv add <이름>`(`pyproject.toml`과 `uv.lock`이 함께 갱신된다).
  `pip install`을 직접 쓰지 않는다 — 전역 파이썬에 설치되어 잠금 파일과 어긋난다.
- **모든 파이썬 실행은 `uv run`을 앞에 붙인다** (`uv run pytest`, `uv run python -c "..."`).
  그냥 `python`을 쓰면 프로젝트 가상환경이 아니라 전역 파이썬이 잡힌다.
- `uv.lock`은 깃에 커밋한다(재현성). `.venv/`는 커밋하지 않는다.
- 테스트 실행: `uv run pytest tests/ -v` (저장소 루트). 시작 시점의 기존 테스트 **55개**는 계속 통과해야 한다.
- 커밋 메시지는 한국어 + `feat:`/`fix:`/`refactor:`/`docs:`/`build:` 접두.
- Windows 환경. 경로는 `pathlib` 사용, 셸 명령은 PowerShell 기준.

## File Structure

| 파일 | 책임 |
|---|---|
| `cgvwatch/cgv/seats.py` | 좌석 지도 API 조회·파싱 (신규) |
| `cgvwatch/cgv/showtimes.py` | 오픈 날짜 + 회차 조회 (수정: `scns_no`/`scn_sseq` 추가) |
| `cgvwatch/core/seatpick.py` | 좌석 후보 선정 알고리즘, 순수 함수 (신규) |
| `cgvwatch/core/showpick.py` | 회차 선택 로직, 순수 함수 (신규) |
| `cgvwatch/core/models.py` | `Watch`에 헌팅 옵션 필드 추가 (수정) |
| `cgvwatch/hunt/selectors.py` | DOM 셀렉터·URL 중앙화 (신규) |
| `cgvwatch/hunt/browser.py` | Playwright 전용 프로필 크롬 관리 (신규) |
| `cgvwatch/hunt/hunter.py` | 좌석 페이지 진입 + 좌석 확보 (신규) |
| `cgvwatch/hunt/manager.py` | 헌트 큐·스레드·상태 (신규) |
| `cgvwatch/notify/discord.py` | 좌석 확보/구조 변경/로그인 필요 알림 (수정) |
| `cgvwatch/notify/desktop.py` | 윈도우 알림 1회 (신규) |
| `cgvwatch/web/server.py` | 헌팅 API·상태 엔드포인트 (수정) |
| `cgvwatch/web/static/index.html` | 헌팅 옵션·상태 UI (수정) |
| `docs/reference/hunterH.js` | 원본 스크립트 보존 (신규) |

---

### Task 1: 좌석 지도 API 클라이언트

**Files:**
- Create: `cgvwatch/cgv/seats.py`
- Create: `tests/test_seats.py`
- Create: `tests/fixtures/seatmap.json`

**Interfaces:**
- Consumes: `CGVClient.get_json(endpoint, params)` (기존, `cgvwatch/cgv/client.py`)
- Produces: `get_seat_map(client, site_no: str, scn_ymd: str, scns_no: str, scn_sseq: str) -> list[dict]`
  각 좌석은 `{"name": "H12", "row": "H", "no": 12, "loc_no": "00100100230015", "x": 23, "y": 15, "free": True}`.
  Task 2·6이 이 형식을 사용한다.

- [ ] **Step 1: 픽스처 파일 생성**

`tests/fixtures/seatmap.json` — 실제 응답을 축약한 형태(3행 × 4석, 일부 판매완료/선점중):

```json
{
  "resultCode": "0",
  "items": [
    {
      "seats": [
        {"seatLocNo": "L001", "seatRowNm": "A", "seatNo": "1", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0001", "ycoordStartVal": "0001"},
        {"seatLocNo": "L002", "seatRowNm": "A", "seatNo": "2", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0003", "ycoordStartVal": "0001"},
        {"seatLocNo": "L003", "seatRowNm": "A", "seatNo": "3", "seatStusCd": "01", "seatSaleYn": "N", "xcoordStartVal": "0005", "ycoordStartVal": "0001"},
        {"seatLocNo": "L004", "seatRowNm": "A", "seatNo": "4", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0007", "ycoordStartVal": "0001"},
        {"seatLocNo": "L005", "seatRowNm": "B", "seatNo": "1", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0001", "ycoordStartVal": "0003"},
        {"seatLocNo": "L006", "seatRowNm": "B", "seatNo": "2", "seatStusCd": "04", "seatSaleYn": "Y", "xcoordStartVal": "0003", "ycoordStartVal": "0003"},
        {"seatLocNo": "L007", "seatRowNm": "B", "seatNo": "3", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0005", "ycoordStartVal": "0003"},
        {"seatLocNo": "L008", "seatRowNm": "B", "seatNo": "4", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0007", "ycoordStartVal": "0003"},
        {"seatLocNo": "L009", "seatRowNm": "C", "seatNo": "1", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0001", "ycoordStartVal": "0005"},
        {"seatLocNo": "L010", "seatRowNm": "C", "seatNo": "2", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0003", "ycoordStartVal": "0005"},
        {"seatLocNo": "L011", "seatRowNm": "C", "seatNo": "3", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0005", "ycoordStartVal": "0005"},
        {"seatLocNo": "L012", "seatRowNm": "C", "seatNo": "4", "seatStusCd": "00", "seatSaleYn": "Y", "xcoordStartVal": "0007", "ycoordStartVal": "0005"}
      ]
    }
  ]
}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_seats.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock

from cgvwatch.cgv.seats import get_seat_map

FIX = json.loads((Path(__file__).parent / "fixtures" / "seatmap.json").read_text(encoding="utf-8"))


def test_get_seat_map_parses_seats():
    client = MagicMock()
    client.get_json.return_value = FIX

    seats = get_seat_map(client, "0056", "20260827", "003", "2")

    assert len(seats) == 12
    a1 = next(s for s in seats if s["name"] == "A1")
    assert a1 == {"name": "A1", "row": "A", "no": 1, "loc_no": "L001",
                  "x": 1, "y": 1, "free": True}
    endpoint, params = client.get_json.call_args[0]
    assert endpoint == "searchIfSeatData"
    assert params == {"siteNo": "0056", "scnYmd": "20260827", "scnsNo": "003",
                      "scnSseq": "2", "seatAreaNo": "001", "cusgdCd": "01"}


def test_get_seat_map_marks_sold_and_holding_as_not_free():
    client = MagicMock()
    client.get_json.return_value = FIX

    seats = get_seat_map(client, "0056", "20260827", "003", "2")

    sold = next(s for s in seats if s["name"] == "A3")      # seatStusCd 01
    holding = next(s for s in seats if s["name"] == "B2")   # seatStusCd 04
    assert sold["free"] is False
    assert holding["free"] is False
    assert len([s for s in seats if s["free"]]) == 10


def test_get_seat_map_empty_when_no_items():
    client = MagicMock()
    client.get_json.return_value = {"resultCode": "0", "items": []}
    assert get_seat_map(client, "0056", "20260827", "003", "2") == []


def test_get_seat_map_empty_when_none():
    client = MagicMock()
    client.get_json.return_value = None
    assert get_seat_map(client, "0056", "20260827", "003", "2") == []
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_seats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cgvwatch.cgv.seats'`

- [ ] **Step 4: 구현**

`cgvwatch/cgv/seats.py`:

```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_seats.py -v`
Expected: 4 PASS

- [ ] **Step 6: 실제 CGV로 스모크 확인**

Run:
```bash
uv run python -c "
from cgvwatch.cgv.client import CGVClient
from cgvwatch.cgv.showtimes import get_open_dates
from cgvwatch.cgv.seats import get_seat_map
c = CGVClient()
d = sorted(get_open_dates(c, '0056', '30001192'))[0]
print('날짜', d)
"
```
Expected: 날짜가 출력된다. (좌석 조회는 `scnsNo`/`scnSseq`가 필요해 Task 3 이후 가능하다.)

- [ ] **Step 7: Commit**

```bash
git add cgvwatch/cgv/seats.py tests/test_seats.py tests/fixtures/seatmap.json
git commit -m "feat: 좌석 지도 API 조회 추가 (로그인 없이 좌석 상태·좌표 획득)"
```

---

### Task 2: 좌석 선택 알고리즘

**Files:**
- Create: `cgvwatch/core/seatpick.py`
- Create: `tests/test_seatpick.py`

**Interfaces:**
- Consumes: Task 1의 좌석 딕셔너리 형식 `{"name","row","no","loc_no","x","y","free"}`
- Produces:
  - `pick_seats(seats: list[dict], count: int, row_offset: int = 1, blacklist: set[str] | None = None) -> list[list[dict]]`
    점수가 좋은 순으로 정렬된 후보 그룹 목록. `count=1`이면 각 그룹의 길이가 1, `count=2`면 2.
  - `center_of(seats: list[dict], row_offset: int = 1) -> tuple[int, int]` — (중앙 행 인덱스, 중앙 번호)
  Task 6이 `pick_seats`를 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_seatpick.py`:

```python
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_seatpick.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cgvwatch.core.seatpick'`

- [ ] **Step 3: 구현**

`cgvwatch/core/seatpick.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_seatpick.py -v`
Expected: 9 PASS

- [ ] **Step 5: Commit**

```bash
git add cgvwatch/core/seatpick.py tests/test_seatpick.py
git commit -m "feat: 좌석 후보 선정 알고리즘 추가 (중앙 기준 점수·연석 판정)"
```

---

### Task 3: 회차 정보 확장 및 회차 선택 로직

**Files:**
- Modify: `cgvwatch/cgv/showtimes.py` (`get_showtimes` 반환에 `scns_no`/`scn_sseq` 추가)
- Modify: `tests/test_showtimes.py`
- Create: `cgvwatch/core/showpick.py`
- Create: `tests/test_showpick.py`

**Interfaces:**
- Consumes: `CGVClient`
- Produces:
  - `get_showtimes(client, site_no, mov_no, ymd) -> list[dict]` — 각 항목이
    `{"start": "1230", "screen": "3관 (Laser)", "free_seats": "158", "scns_no": "003", "scn_sseq": "2"}`
  - `pick_showtime(showtimes: list[dict], screen_filter: str, preferred_time: str) -> dict | None`
  Task 6·8이 둘 다 사용한다.

- [ ] **Step 1: showtimes 테스트를 새 형식으로 수정**

`tests/test_showtimes.py`의 `test_get_showtimes_parses_and_sorts`를 다음으로 교체:

```python
def test_get_showtimes_parses_and_sorts():
    from cgvwatch.cgv.showtimes import get_showtimes
    client = MagicMock()
    client.get_json.return_value = [
        {"scnsrtTm": "1550", "scnsNm": "1관 (Laser)", "frSeatCnt": "34",
         "scnsNo": "001", "scnSseq": "3"},
        {"scnsrtTm": "0900", "scnsNm": "IMAX관", "frSeatCnt": "28",
         "scnsNo": "018", "scnSseq": "1"},
    ]

    rows = get_showtimes(client, "0056", "30001192", "20260819")

    assert rows == [
        {"start": "0900", "screen": "IMAX관", "free_seats": "28",
         "scns_no": "018", "scn_sseq": "1"},
        {"start": "1550", "screen": "1관 (Laser)", "free_seats": "34",
         "scns_no": "001", "scn_sseq": "3"},
    ]
    endpoint, params = client.get_json.call_args[0]
    assert endpoint == "searchSchByMov"
    assert params == {"siteNo": "0056", "movNo": "30001192",
                      "scnYmd": "20260819", "rtctlScopCd": "08"}
```

- [ ] **Step 2: showpick 테스트 작성**

`tests/test_showpick.py`:

```python
from cgvwatch.core.showpick import pick_showtime


def _rows():
    return [
        {"start": "0900", "screen": "1관 (Laser)", "free_seats": "10", "scns_no": "001", "scn_sseq": "1"},
        {"start": "1400", "screen": "IMAX관", "free_seats": "50", "scns_no": "018", "scn_sseq": "2"},
        {"start": "1900", "screen": "IMAX관", "free_seats": "0", "scns_no": "018", "scn_sseq": "3"},
        {"start": "2200", "screen": "4DX관", "free_seats": "5", "scns_no": "004", "scn_sseq": "4"},
    ]


def test_pick_showtime_without_filter_returns_earliest():
    assert pick_showtime(_rows(), "", "")["start"] == "0900"


def test_pick_showtime_applies_screen_filter():
    assert pick_showtime(_rows(), "imax", "")["start"] == "1400"


def test_pick_showtime_picks_nearest_to_preferred_time():
    assert pick_showtime(_rows(), "", "2000")["start"] == "1900"


def test_pick_showtime_filter_and_preference_together():
    assert pick_showtime(_rows(), "IMAX", "2100")["scn_sseq"] == "3"


def test_pick_showtime_none_when_filter_matches_nothing():
    assert pick_showtime(_rows(), "돌비", "") is None


def test_pick_showtime_none_when_empty():
    assert pick_showtime([], "", "") is None
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_showtimes.py tests/test_showpick.py -v`
Expected: FAIL — showtimes는 `scns_no` 키가 없어서, showpick은 모듈이 없어서 실패

- [ ] **Step 4: showtimes 수정**

`cgvwatch/cgv/showtimes.py`의 `get_showtimes` 내부 리스트 컴프리헨션을 다음으로 교체:

```python
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
```

- [ ] **Step 5: showpick 구현**

`cgvwatch/core/showpick.py`:

```python
"""회차 선택. CGV·Playwright에 의존하지 않는 순수 로직."""
from __future__ import annotations

from typing import Optional


def pick_showtime(
    showtimes: list[dict],
    screen_filter: str,
    preferred_time: str,
) -> Optional[dict]:
    """관 필터에 맞는 회차 중 선호 시각에 가장 가까운 것. 선호 시각이 없으면 가장 이른 회차."""
    if not showtimes:
        return None
    candidates = showtimes
    if screen_filter:
        kw = screen_filter.strip().lower()
        candidates = [s for s in showtimes if kw in s.get("screen", "").lower()]
    if not candidates:
        return None
    if not preferred_time:
        return min(candidates, key=lambda s: s.get("start", ""))
    target = int(preferred_time)
    return min(candidates, key=lambda s: abs(int(s.get("start") or 0) - target))
```

- [ ] **Step 6: 전체 테스트 실행**

Run: `uv run pytest tests/ -v`
Expected: 전부 PASS (기존 관 필터 테스트도 그대로 통과해야 한다)

- [ ] **Step 7: 실제 CGV로 좌석 조회 스모크**

Run:
```bash
uv run python -c "
from cgvwatch.cgv.client import CGVClient
from cgvwatch.cgv.showtimes import get_open_dates, get_showtimes
from cgvwatch.cgv.seats import get_seat_map
from cgvwatch.core.showpick import pick_showtime
from cgvwatch.core.seatpick import pick_seats
c = CGVClient()
ymd = sorted(get_open_dates(c, '0056', '30001192'))[0]
st = get_showtimes(c, '0056', '30001192', ymd)
pick = pick_showtime(st, '', '1900')
print('회차:', pick['start'], pick['screen'], pick['scns_no'], pick['scn_sseq'])
seats = get_seat_map(c, '0056', ymd, pick['scns_no'], pick['scn_sseq'])
print('좌석 수:', len(seats), '빈자리:', sum(1 for s in seats if s['free']))
print('1인 후보 5개:', [g[0]['name'] for g in pick_seats(seats, 1)[:5]])
print('2인 후보 3개:', [[x['name'] for x in g] for g in pick_seats(seats, 2)[:3]])
"
```
Expected: 회차 정보와 좌석 수가 나오고, 후보 좌석 이름이 중앙 부근으로 출력된다.

- [ ] **Step 8: Commit**

```bash
git add cgvwatch/cgv/showtimes.py cgvwatch/core/showpick.py tests/test_showtimes.py tests/test_showpick.py
git commit -m "feat: 회차 식별자(scnsNo/scnSseq) 노출 및 회차 선택 로직 추가"
```

---

### Task 4: Watch 모델에 헌팅 옵션 추가

**Files:**
- Modify: `cgvwatch/core/models.py`
- Modify: `cgvwatch/web/server.py` (`WatchIn`)
- Modify: `cgvwatch/web/static/index.html` (추가 폼·목록 표시)
- Modify: `tests/test_server.py`

**Interfaces:**
- Produces: `Watch`에 다음 필드가 추가된다. Task 6·8이 읽는다.
  - `hunt_enabled: bool = False`
  - `seat_count: int = 1` (1 또는 2)
  - `row_offset: int = 1`
  - `preferred_time: str = ""` (HHMM, 빈 값이면 가장 이른 회차)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_server.py` 끝에 추가:

```python
def test_add_watch_with_hunt_options(api, monkeypatch):
    tc, store, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "send_created_alert", MagicMock())
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산아이파크몰",
            "target_ymd": "20260729", "screen_filter": "IMAX",
            "hunt_enabled": True, "seat_count": 2, "row_offset": 2,
            "preferred_time": "1900"}

    res = tc.post("/api/watches", json=body)

    assert res.status_code == 201
    assert res.json()["hunt_enabled"] is True
    _, saved = store.load()
    assert saved[0].seat_count == 2
    assert saved[0].row_offset == 2
    assert saved[0].preferred_time == "1900"


def test_add_watch_rejects_bad_seat_count(api):
    tc, _, _ = api
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산",
            "target_ymd": "20260729", "seat_count": 5}
    assert tc.post("/api/watches", json=body).status_code == 422


def test_add_watch_rejects_bad_preferred_time(api):
    tc, _, _ = api
    body = {"mov_no": "1", "mov_nm": "영화", "site_no": "0013", "site_nm": "용산",
            "target_ymd": "20260729", "preferred_time": "7pm"}
    assert tc.post("/api/watches", json=body).status_code == 422
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL — `hunt_enabled` 키가 응답에 없음

- [ ] **Step 3: 모델 수정**

`cgvwatch/core/models.py`의 `Watch`에서 `screen_filter` 아래에 추가:

```python
    hunt_enabled: bool = False  # 좌석 확보까지 자동으로 진행할지
    seat_count: int = 1  # 1 또는 2
    row_offset: int = 1  # 중앙 기준 뒤쪽으로 몇 열
    preferred_time: str = ""  # HHMM, 빈 값이면 가장 이른 회차
```

- [ ] **Step 4: 서버 입력 모델 수정**

`cgvwatch/web/server.py`의 `WatchIn`에서 `screen_filter` 아래에 추가:

```python
    hunt_enabled: bool = False
    seat_count: int = Field(default=1, ge=1, le=2)
    row_offset: int = Field(default=1, ge=-5, le=5)
    preferred_time: str = Field(default="", pattern=r"^(\d{4})?$")
```

- [ ] **Step 5: 웹 UI에 입력 추가**

`cgvwatch/web/static/index.html`의 관 필터 `div.field` 바로 뒤에 추가:

```html
        <div class="field">
          <label for="hunt-check">좌석 자동 확보</label>
          <label class="check-row">
            <input id="hunt-check" type="checkbox">
            <span>켜기</span>
          </label>
        </div>
        <div class="field">
          <label for="seat-count-input">인원</label>
          <select id="seat-count-input">
            <option value="1">1명</option>
            <option value="2">2명</option>
          </select>
        </div>
        <div class="field">
          <label for="row-offset-input">중앙 기준 열 오프셋</label>
          <input id="row-offset-input" type="number" min="-5" max="5" value="1">
        </div>
        <div class="field">
          <label for="pref-time-input">선호 시각 (선택)</label>
          <input id="pref-time-input" type="time">
        </div>
```

`.error-reason` CSS 규칙 바로 앞에 추가:

```css
  .check-row {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text);
    font-size: 0.9rem;
    padding: 8px 0;
  }

  .hunt-mark {
    margin-top: 4px;
    font-size: 0.74rem;
    color: var(--accent-hover);
  }
```

`var(--gold)` 를 쓰는 `.screen-filter` 규칙은 그대로 둔다.

`var screenInput = ...` 아래에 참조를 추가:

```javascript
  var huntCheck = document.getElementById("hunt-check");
  var seatCountInput = document.getElementById("seat-count-input");
  var rowOffsetInput = document.getElementById("row-offset-input");
  var prefTimeInput = document.getElementById("pref-time-input");
```

`screen_filter: screenInput.value.trim()` 다음 줄에 이어서:

```javascript
      hunt_enabled: huntCheck.checked,
      seat_count: parseInt(seatCountInput.value, 10),
      row_offset: parseInt(rowOffsetInput.value, 10) || 0,
      preferred_time: prefTimeInput.value.replace(":", "")
```

목록의 극장 칸에 관 필터를 붙이는 블록(`if (w.screen_filter) { ... }`) 바로 뒤에 추가:

```javascript
      if (w.hunt_enabled) {
        var hm = document.createElement("div");
        hm.className = "hunt-mark";
        hm.textContent = "자동 확보 " + w.seat_count + "명";
        siteTd.appendChild(hm);
      }
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 7: 화면 확인**

Run: `uv run python -c "from fastapi.testclient import TestClient; from cgvwatch.web.server import create_app; from cgvwatch.core.store import Store; import tempfile, pathlib; tc = TestClient(create_app(store=Store(pathlib.Path(tempfile.mkdtemp())/'c.json'), start_watcher=False)); r = tc.get('/'); print(r.status_code, 'hunt-check' in r.text)"`
Expected: `200 True`

- [ ] **Step 8: Commit**

```bash
git add cgvwatch/core/models.py cgvwatch/web/server.py cgvwatch/web/static/index.html tests/test_server.py
git commit -m "feat: 감시 항목에 좌석 자동 확보 옵션(인원·오프셋·선호 시각) 추가"
```

---

### Task 5: 셀렉터 중앙화와 브라우저 매니저

**Files:**
- Create: `cgvwatch/hunt/__init__.py` (빈 파일)
- Create: `cgvwatch/hunt/selectors.py`
- Create: `cgvwatch/hunt/browser.py`
- Create: `docs/reference/hunterH.js` (원본 복사)
- Modify: `pyproject.toml` (playwright 의존성 추가)
- Create: `tests/test_selectors.py`

**Interfaces:**
- Produces:
  - `cgvwatch/hunt/selectors.py` 상수들: `BOOKING_URL_TMPL`, `SEAT_PATH`, `SEAT_BUTTON`, `COUNT_WRAP`, `COUNT_BUTTON_TMPL`, `MODAL`, `MODAL_CLOSE_TEXT`, `WHEELCHAIR_TEXT`, `SEAT_HELD_TEXT`, `CTA_TEXT`, `LOGIN_MARK`
  - `BrowserManager(profile_dir: Path)` — `start()`, `stop()`, `is_running() -> bool`, `page()`, `is_logged_in() -> bool`
  Task 6·8이 사용한다.

- [ ] **Step 1: Playwright 설치**

Run:
```bash
uv add playwright
uv run playwright install chromium
```
Expected: `uv add`가 `pyproject.toml`의 dependencies에 playwright를 넣고 `uv.lock`을 갱신한다.
그 다음 `uv run playwright install chromium`이 브라우저 바이너리를 받는다(수백 MB, 수 분 소요).

- [ ] **Step 2: 원본 스크립트 보존**

Run:
```bash
mkdir -p docs/reference
cp "/c/Users/cwhap/바탕 화면/예매/.hunt/hunterH.js" docs/reference/hunterH.js
```
Expected: 파일이 복사된다. (원본 폴더가 사라져도 참조할 수 있도록 레포에 남긴다.)

- [ ] **Step 3: 셀렉터 상수 테스트 작성**

`tests/test_selectors.py`:

```python
from cgvwatch.hunt import selectors as sel


def test_booking_url_has_all_params():
    url = sel.BOOKING_URL_TMPL.format(
        mov_no="30001192", ymd="20260827", site_no="0056", site_nm="%EA%B0%95%EB%82%A8"
    )
    assert url.startswith("https://cgv.co.kr/cnm/movieBook/movie?")
    for part in ("movNo=30001192", "scnYmd=20260827", "siteNo=0056", "siteNm="):
        assert part in url


def test_count_button_template_renders():
    assert sel.COUNT_BUTTON_TMPL.format(count=2) == 'button[aria-label="2 선택"]'


def test_seat_button_by_loc_template_renders():
    assert sel.SEAT_BUTTON_BY_LOC_TMPL.format(loc_no="00100100230015") == (
        'button[data-seatlocno="00100100230015"]'
    )


def test_required_selectors_are_non_empty_strings():
    for name in ("SEAT_PATH", "SEAT_BUTTON", "SEAT_BUTTON_BY_LOC_TMPL", "COUNT_WRAP",
                 "MODAL", "MODAL_CLOSE_TEXT", "WHEELCHAIR_TEXT", "SEAT_HELD_TEXT", "CTA_TEXT",
                 "SHOWTIME_BUTTON", "LOGIN_REQUIRED_TEXT"):
        value = getattr(sel, name)
        assert isinstance(value, str) and value
```

- [ ] **Step 4: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_selectors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cgvwatch.hunt'`

- [ ] **Step 5: 셀렉터 모듈 구현**

`cgvwatch/hunt/__init__.py`: 빈 파일 생성.

`cgvwatch/hunt/selectors.py`:

```python
"""CGV 예매 화면의 DOM 셀렉터와 경로. 화면이 바뀌면 여기만 고친다.

각 항목의 (확인: YYYY-MM-DD)는 마지막으로 실제 페이지에서 확인한 날짜다.
오래됐다면 Playwright로 좌석 페이지를 열어 다시 확인할 것.
복구 절차는 CLAUDE.md 참고.
"""
from __future__ import annotations

# 영화·날짜·극장이 미리 선택된 예매 페이지 (확인: 2026-08-26)
BOOKING_URL_TMPL = (
    "https://cgv.co.kr/cnm/movieBook/movie"
    "?movNo={mov_no}&scnYmd={ymd}&siteNo={site_no}&siteNm={site_nm}"
)

# 인원 선택과 좌석 선택이 함께 있는 페이지 (확인: 2026-08-23)
SEAT_PATH = "/cnm/selectVisitorCnt"

# 좌석 버튼. 텍스트가 좌석명("H12"), disabled면 선택 불가 (확인: 2026-08-23)
SEAT_BUTTON = "button[data-seatlocno]"
# 특정 좌석 하나를 고르는 셀렉터. loc_no는 좌석 지도 API의 seatLocNo (확인: 2026-08-26)
SEAT_BUTTON_BY_LOC_TMPL = 'button[data-seatlocno="{loc_no}"]' 

# 회차(상영 시각) 버튼 — 자동 생성 클래스명이라 배포 시 바뀔 수 있다 (확인: 2026-08-26)
# 버튼 텍스트 예: "15:40-18:15 47/123석 2관 (Laser)". 시각은 안쪽 span에 들어있다.
SHOWTIME_BUTTON = "button.screenInfo_timeLink__45VfR"

# 로그인 없이 회차를 누르면 뜨는 안내 모달의 문구 (확인: 2026-08-26)
LOGIN_REQUIRED_TEXT = "로그인이 필요한"

# 인원 선택 박스 — 자동 생성 클래스명이라 배포 시 바뀔 수 있다 (확인: 2026-08-23)
COUNT_WRAP = "div.numberChoice_NumberWrap__JKTv1"
COUNT_BUTTON_TMPL = 'button[aria-label="{count} 선택"]'

# 모달과 닫기 버튼 (확인: 2026-08-23)
MODAL = ".cgv-modal.active"
MODAL_CLOSE_TEXT = "확인|닫기"

# 모달 본문에 이 단어가 있으면 그 좌석은 블랙리스트 (확인: 2026-08-23)
WHEELCHAIR_TEXT = "휠체어|장애인"

# 좌석 확보 성공 시 본문에 나타나는 문구 (확인: 2026-08-23)
SEAT_HELD_TEXT = "선택하신 좌석"

# 다음 단계로 가는 버튼 텍스트 (공백 제거 후 비교) (확인: 2026-08-23)
CTA_TEXT = "선택완료"

# 로그인 상태 판정: 이 텍스트가 보이면 로그아웃 상태 (확인: 2026-08-26)
LOGIN_MARK = "로그인"
```

- [ ] **Step 6: 브라우저 매니저 구현**

`cgvwatch/hunt/browser.py`:

```python
"""로그인된 크롬을 전용 프로필로 관리한다. 계정 정보는 다루지 않는다."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

from cgvwatch.hunt import selectors as sel

logger = logging.getLogger(__name__)


class BrowserManager:
    """Playwright 전용 프로필 크롬. 반드시 한 스레드에서만 사용한다."""

    def __init__(self, profile_dir: Path) -> None:
        self.profile_dir = Path(profile_dir)
        self._pw = None
        self._context = None

    def start(self) -> None:
        if self._context:
            return
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=False,
            viewport=None,
            args=["--start-maximized"],
        )
        if not self._context.pages:
            self._context.new_page()
        logger.info("브라우저 시작: %s", self.profile_dir)

    def stop(self) -> None:
        try:
            if self._context:
                self._context.close()
        finally:
            self._context = None
            if self._pw:
                self._pw.stop()
                self._pw = None
            logger.info("브라우저 종료")

    def is_running(self) -> bool:
        return self._context is not None

    def page(self):
        """첫 번째 탭. 브라우저가 꺼져 있으면 RuntimeError."""
        if not self._context:
            raise RuntimeError("브라우저가 실행되지 않았습니다.")
        return self._context.pages[0] if self._context.pages else self._context.new_page()

    def is_logged_in(self) -> bool:
        """CGV 첫 화면에서 로그인 문구가 안 보이면 로그인된 것으로 본다."""
        if not self._context:
            return False
        page = self.page()
        try:
            page.goto("https://cgv.co.kr/", wait_until="domcontentloaded", timeout=20000)
            body = page.inner_text("body", timeout=5000)
        except Exception:
            logger.exception("로그인 상태 확인 실패")
            return False
        return sel.LOGIN_MARK not in body
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `uv run pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 8: 실제 브라우저로 셀렉터 재확인 (중요)**

셀렉터는 2026-08-23 관찰값이라 오래됐을 수 있다. 실제로 열어서 확인한다.

Run:
```bash
uv run python -c "
from pathlib import Path
from cgvwatch.hunt.browser import BrowserManager
b = BrowserManager(Path.home()/'.cgv-watcher'/'chrome-profile')
b.start()
p = b.page()
p.goto('https://cgv.co.kr/cnm/movieBook/movie?movNo=30001192&scnYmd=20260827&siteNo=0056&siteNm=%EA%B0%95%EB%82%A8')
input('브라우저에서 로그인하고 회차를 눌러 좌석 화면까지 간 뒤 Enter: ')
print('경로:', p.url)
print('좌석 버튼 수:', p.locator('button[data-seatlocno]').count())
print('인원 박스:', p.locator('div.numberChoice_NumberWrap__JKTv1').count())
print('선택완료 버튼:', p.get_by_role('button', name='선택완료').count())
b.stop()
"
```
Expected: 좌석 버튼이 100개 이상, 인원 박스 1개가 나온다.
**하나라도 0이면** 그 셀렉터가 바뀐 것이다. 브라우저 개발자도구로 새 셀렉터를 찾아
`selectors.py`를 고치고 확인 날짜를 오늘로 갱신한 뒤, 이 단계를 다시 수행한다.

- [ ] **Step 9: Commit**

```bash
git add cgvwatch/hunt/ docs/reference/hunterH.js pyproject.toml uv.lock tests/test_selectors.py
git commit -m "feat: Playwright 브라우저 매니저와 셀렉터 중앙화 모듈 추가"
```

---

### Task 6: 좌석 확보 헌터

**Files:**
- Create: `cgvwatch/hunt/hunter.py`
- Create: `tests/test_hunter.py`

**Interfaces:**
- Consumes: `get_seat_map` (Task 1), `pick_seats` (Task 2), `BrowserManager`·`selectors` (Task 5), `Watch` (Task 4)
- Produces:
  - `HuntResult` 데이터클래스: `status: str`, `seats: list[str]`, `detail: str`
    `status`는 `"확보"` / `"실패"` / `"구조변경"` / `"중단"` 중 하나
  - `Hunter(page, client, watch, showtime, on_event=None, poll_sec=POLL_SEC)` — `run(max_cycles=3600) -> HuntResult`
    (`poll_sec`는 테스트에서 0으로 낮추기 위한 것. 운영 코드는 기본값을 쓴다.)
  Task 8이 사용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

브라우저 없이 검증할 수 있도록 페이지를 목으로 만든다.

`tests/test_hunter.py`:

```python
from unittest.mock import MagicMock

import pytest

from cgvwatch.core.models import Watch
from cgvwatch.hunt.hunter import HuntResult, Hunter


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260827", seat_count=1, row_offset=1)
    base.update(kw)
    return Watch(**base)


def _showtime():
    return {"start": "1900", "screen": "3관", "free_seats": "10",
            "scns_no": "003", "scn_sseq": "2"}


def _seats(free_names):
    seats = []
    for ri, r in enumerate("ABCDE"):
        for c in range(1, 6):
            name = f"{r}{c}"
            seats.append({"name": name, "row": r, "no": c, "loc_no": f"L{name}",
                          "x": c * 2 - 1, "y": ri * 2 + 1, "free": name in free_names})
    return seats


def _page(url="https://cgv.co.kr/cnm/selectVisitorCnt", body="",
          seat_buttons=125, modals=0):
    """셀렉터별로 다른 개수를 돌려주는 페이지 목."""
    page = MagicMock()
    page.url = url
    page.inner_text.return_value = body

    def locator(selector):
        loc = MagicMock()
        loc.count.return_value = modals if "cgv-modal" in selector else seat_buttons
        return loc

    page.locator.side_effect = locator
    return page


def test_hunter_secures_seat_when_free(monkeypatch):
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats({"D3"}))
    page = _page()
    hunter = Hunter(page, MagicMock(), _watch(), _showtime(), poll_sec=0)

    # 좌석을 클릭하면 결제 페이지로 넘어간 것처럼 URL을 바꾼다
    def click_seat(seat):
        page.url = "https://cgv.co.kr/cnm/payment"

    monkeypatch.setattr(hunter, "_click_seat", click_seat)
    monkeypatch.setattr(hunter, "_click_cta", lambda: None)
    monkeypatch.setattr(hunter, "_set_count", lambda: None)

    result = hunter.run(max_cycles=1)

    assert result.status == "확보"
    assert result.seats == ["D3"]


def test_hunter_retries_next_seat_when_modal_blocks(monkeypatch):
    """모달이 뜨면 그 좌석을 포기하고 다음 후보로 넘어간다."""
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats({"D3", "D2"}))
    page = _page(modals=1)  # 항상 모달이 뜬다
    hunter = Hunter(page, MagicMock(), _watch(), _showtime(), poll_sec=0)
    tried = []
    monkeypatch.setattr(hunter, "_click_seat", lambda seat: tried.append(seat["name"]))
    monkeypatch.setattr(hunter, "_set_count", lambda: None)

    result = hunter.run(max_cycles=1)

    assert result.status == "실패"
    assert len(tried) >= 2  # 첫 후보가 막히면 다음 후보도 시도했다


def test_hunter_reports_structure_change_when_no_seat_buttons(monkeypatch):
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats({"D3"}))
    page = _page(seat_buttons=0)  # 좌석 버튼이 사라짐

    result = Hunter(page, MagicMock(), _watch(), _showtime(), poll_sec=0).run(max_cycles=1)

    assert result.status == "구조변경"


def test_hunter_returns_failed_when_no_free_seats(monkeypatch):
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats(set()))
    hunter = Hunter(_page(), MagicMock(), _watch(), _showtime(), poll_sec=0)
    monkeypatch.setattr(hunter, "_set_count", lambda: None)

    result = hunter.run(max_cycles=2)

    assert result.status == "실패"
    assert result.seats == []


def test_hunter_stops_when_asked(monkeypatch):
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats(set()))
    hunter = Hunter(_page(), MagicMock(), _watch(), _showtime(), poll_sec=0)
    monkeypatch.setattr(hunter, "_set_count", lambda: None)
    hunter.stop()

    result = hunter.run(max_cycles=5)

    assert result.status == "중단"


def test_hunter_refuses_when_seat_already_held(monkeypatch):
    """이미 좌석을 잡아둔 화면이면 건드리지 않는다."""
    import cgvwatch.hunt.hunter as h
    monkeypatch.setattr(h, "get_seat_map", lambda *a, **k: _seats({"D3"}))
    page = _page(body="선택하신 좌석 D3")

    result = Hunter(page, MagicMock(), _watch(), _showtime()).run(max_cycles=1)

    assert result.status == "중단"
    assert "이미" in result.detail
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_hunter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cgvwatch.hunt.hunter'`

- [ ] **Step 3: 구현**

`cgvwatch/hunt/hunter.py`:

```python
"""좌석 페이지에서 자리를 확보한다. 결제 페이지에 닿으면 즉시 멈춘다."""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from cgvwatch.cgv.seats import get_seat_map
from cgvwatch.core.models import Watch
from cgvwatch.core.seatpick import pick_seats
from cgvwatch.hunt import selectors as sel

logger = logging.getLogger(__name__)

POLL_SEC = 1.0  # 좌석 폴링 하한. 더 짧게 하지 않는다.
BACKOFF_SEC = 5.0  # 429를 받았을 때 추가로 쉬는 시간


@dataclass
class HuntResult:
    status: str  # "확보" | "실패" | "구조변경" | "중단"
    seats: list[str] = field(default_factory=list)
    detail: str = ""


class Hunter:
    """한 회차의 좌석을 확보한다. 페이지는 이미 좌석 화면에 있다고 가정한다."""

    def __init__(
        self,
        page,
        client,
        watch: Watch,
        showtime: dict,
        on_event: Optional[Callable[[str], None]] = None,
        poll_sec: float = POLL_SEC,
    ) -> None:
        self.page = page
        self.client = client
        self.watch = watch
        self.showtime = showtime
        self.on_event = on_event or (lambda msg: None)
        self.poll_sec = poll_sec
        self._stop = threading.Event()
        self._blacklist: set[str] = set()

    def stop(self) -> None:
        self._stop.set()

    # --- 페이지 조작 (셀렉터를 쓰는 유일한 지점) ---

    def _seat_button_count(self) -> int:
        return self.page.locator(sel.SEAT_BUTTON).count()

    def _seat_held(self) -> bool:
        try:
            return sel.SEAT_HELD_TEXT in self.page.inner_text("body", timeout=5000)
        except Exception:
            return False

    def _left_seat_page(self) -> bool:
        return sel.SEAT_PATH not in self.page.url

    def _set_count(self) -> None:
        selector = sel.COUNT_BUTTON_TMPL.format(count=self.watch.seat_count)
        self.page.locator(selector).first.click(timeout=5000)

    def _click_seat(self, seat: dict) -> None:
        self.page.locator(
            sel.SEAT_BUTTON_BY_LOC_TMPL.format(loc_no=seat["loc_no"])
        ).first.click(timeout=5000)

    def _click_cta(self) -> None:
        self.page.get_by_role("button", name=sel.CTA_TEXT).first.click(timeout=5000)

    def _handle_modal(self, seat_name: str) -> bool:
        """모달이 떠 있으면 닫고 True. 휠체어석 경고면 블랙리스트에 넣는다."""
        modal = self.page.locator(sel.MODAL)
        if modal.count() == 0:
            return False
        try:
            text = modal.first.inner_text(timeout=2000)
        except Exception:
            text = ""
        if re.search(sel.WHEELCHAIR_TEXT, text):
            self._blacklist.add(seat_name)
        try:
            modal.first.get_by_role(
                "button", name=re.compile(sel.MODAL_CLOSE_TEXT)
            ).first.click(timeout=2000)
        except Exception:
            logger.warning("모달을 닫지 못했습니다: %s", text[:60])
        return True

    # --- 본 흐름 ---

    def _try_group(self, group: list[dict]) -> bool:
        """좌석 그룹을 클릭하고 선택완료까지. 결제 페이지로 넘어가면 True."""
        for seat in group:
            self._click_seat(seat)
            time.sleep(0.15)
            if self._handle_modal(seat["name"]):
                return False
        self._click_cta()
        for _ in range(50):
            time.sleep(0.2)
            if self._left_seat_page():
                return True
        return False

    def run(self, max_cycles: int = 3600) -> HuntResult:
        if self._stop.is_set():
            return HuntResult("중단", detail="시작 전 중단 요청")
        if self._seat_held():
            return HuntResult("중단", detail="이미 선택된 좌석이 있어 건드리지 않았습니다.")
        if self._seat_button_count() == 0:
            return HuntResult("구조변경", detail=f"좌석 버튼({sel.SEAT_BUTTON})을 찾지 못했습니다.")

        try:
            self._set_count()
        except Exception as exc:
            return HuntResult("구조변경", detail=f"인원 선택 실패: {exc}")

        backoff = 0.0
        for _ in range(max_cycles):
            if self._stop.is_set():
                return HuntResult("중단", detail="사용자 중단")
            try:
                seats = get_seat_map(
                    self.client,
                    self.watch.site_no,
                    self.watch.target_ymd,
                    self.showtime["scns_no"],
                    self.showtime["scn_sseq"],
                )
                backoff = 0.0
            except Exception as exc:
                if "429" in str(exc):
                    backoff += BACKOFF_SEC
                    self.on_event(f"요청이 제한되어 {backoff:.0f}초 쉽니다")
                logger.warning("좌석 조회 실패: %s", exc)
                time.sleep(self.poll_sec + backoff)
                continue

            for group in pick_seats(
                seats, self.watch.seat_count, self.watch.row_offset, self._blacklist
            ):
                if self._stop.is_set():
                    return HuntResult("중단", detail="사용자 중단")
                names = [s["name"] for s in group]
                self.on_event(f"좌석 시도: {', '.join(names)}")
                try:
                    if self._try_group(group):
                        return HuntResult("확보", seats=names, detail="결제 페이지 도달")
                except Exception as exc:
                    logger.warning("좌석 클릭 실패 %s: %s", names, exc)
                if self._seat_held():
                    return HuntResult("확보", seats=names, detail="좌석 선점 확인")

            time.sleep(self.poll_sec + backoff)

        return HuntResult("실패", detail="제한 시간 안에 좌석을 확보하지 못했습니다.")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_hunter.py -v`
Expected: 6 PASS

- [ ] **Step 5: 전체 테스트 실행**

Run: `uv run pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 6: Commit**

```bash
git add cgvwatch/hunt/hunter.py tests/test_hunter.py
git commit -m "feat: 좌석 확보 헌터 추가 (좌석 지도 폴링·후보 클릭·결제 직전 정지)"
```

---

### Task 7: 좌석 확보·이상 상황 알림

**Files:**
- Modify: `cgvwatch/notify/discord.py`
- Create: `cgvwatch/notify/desktop.py`
- Modify: `tests/test_discord.py`
- Create: `tests/test_desktop.py`

**Interfaces:**
- Produces:
  - `send_seat_secured(watch, settings, seats: list[str], showtime: dict, post=requests.post) -> None`
  - `send_structure_warning(watch, settings, detail: str, post=requests.post) -> None`
  - `send_login_required(settings, post=requests.post) -> None`
  - `notify_desktop(title: str, message: str, runner=subprocess.run) -> None`
  Task 8이 모두 사용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_discord.py` 끝에 추가:

```python
def _showtime():
    return {"start": "1900", "screen": "IMAX관", "free_seats": "3",
            "scns_no": "018", "scn_sseq": "2"}


def test_send_seat_secured_includes_seats_and_time(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    post = MagicMock(return_value=MagicMock(status_code=204))

    discord.send_seat_secured(_watch(), Settings(), ["H12", "H13"], _showtime(), post=post)

    content = post.call_args[1]["json"]["content"]
    assert "H12" in content and "H13" in content
    assert "19:00" in content
    assert "IMAX관" in content
    assert "결제" in content


def test_send_structure_warning_includes_detail(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    post = MagicMock(return_value=MagicMock(status_code=204))

    discord.send_structure_warning(_watch(), Settings(), "좌석 버튼을 찾지 못했습니다.", post=post)

    content = post.call_args[1]["json"]["content"]
    assert "구조" in content
    assert "좌석 버튼" in content


def test_send_login_required(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    post = MagicMock(return_value=MagicMock(status_code=204))

    discord.send_login_required(Settings(), post=post)

    assert "로그인" in post.call_args[1]["json"]["content"]
```

`tests/test_desktop.py`:

```python
from unittest.mock import MagicMock

from cgvwatch.notify.desktop import notify_desktop


def test_notify_desktop_runs_powershell():
    runner = MagicMock()
    notify_desktop("좌석 확보", "H12 잡았습니다", runner=runner)
    args = runner.call_args[0][0]
    assert args[0] == "powershell"
    joined = " ".join(args)
    assert "좌석 확보" in joined
    assert "H12" in joined


def test_notify_desktop_swallows_errors():
    runner = MagicMock(side_effect=OSError("powershell 없음"))
    notify_desktop("제목", "내용", runner=runner)  # 예외가 나면 안 된다
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_discord.py tests/test_desktop.py -v`
Expected: FAIL — `send_seat_secured` 없음, `cgvwatch.notify.desktop` 없음

- [ ] **Step 3: 디스코드 알림 추가**

`cgvwatch/notify/discord.py`의 `send_created_alert` 아래에 추가:

```python
def send_seat_secured(
    watch: Watch,
    settings: Settings,
    seats: list[str],
    showtime: dict,
    post: Callable = requests.post,
) -> None:
    """좌석 확보 알림. 결제는 사람이 해야 한다는 것을 분명히 적는다."""
    ymd = watch.target_ymd
    date = f"{ymd[4:6]}/{ymd[6:8]}"
    start = showtime.get("start", "")
    hhmm = f"{start[:2]}:{start[2:]}" if len(start) == 4 else start
    content = (
        f"🎟️ **좌석 확보! {watch.mov_nm}**\n"
        f"{watch.site_nm} {date} {hhmm} {showtime.get('screen', '')}\n"
        f"좌석: {', '.join(seats)}\n"
        f"⏳ 브라우저에서 **결제를 직접 진행**해 주세요. 시간이 지나면 좌석이 풀립니다."
    )
    _send(content, post)


def send_structure_warning(
    watch: Watch,
    settings: Settings,
    detail: str,
    post: Callable = requests.post,
) -> None:
    """CGV 화면 구조가 바뀐 것으로 의심될 때."""
    content = (
        f"🔧 **화면 구조 변경 의심** ({watch.mov_nm} / {watch.site_nm})\n"
        f"{detail}\n"
        f"selectors.py를 최신 화면에 맞게 확인해야 합니다."
    )
    _send(content, post)


def send_login_required(
    settings: Settings,
    post: Callable = requests.post,
) -> None:
    """브라우저 세션이 없어 헌팅을 시작할 수 없을 때."""
    _send(
        "🔑 **CGV 로그인이 필요합니다**\n"
        "웹 UI에서 브라우저를 열고 로그인해 주세요. 좌석 확보가 대기 중입니다.",
        post,
    )
```

- [ ] **Step 4: 데스크톱 알림 구현**

`cgvwatch/notify/desktop.py`:

```python
"""윈도우 알림 1회. 추가 설치 없이 PowerShell 내장 기능만 쓴다."""
from __future__ import annotations

import logging
import subprocess
from typing import Callable

logger = logging.getLogger(__name__)

_PS_TEMPLATE = (
    "[reflection.assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
    "$n = New-Object System.Windows.Forms.NotifyIcon; "
    "$n.Icon = [System.Drawing.SystemIcons]::Information; "
    "$n.BalloonTipTitle = '{title}'; "
    "$n.BalloonTipText = '{message}'; "
    "$n.Visible = $true; "
    "$n.ShowBalloonTip(10000); "
    "Start-Sleep -Seconds 10; "
    "$n.Dispose()"
)


def _escape(text: str) -> str:
    return text.replace("'", "''").replace("\n", " ")


def notify_desktop(title: str, message: str, runner: Callable = subprocess.run) -> None:
    """알림을 한 번 띄운다. 실패해도 예외를 밖으로 내보내지 않는다."""
    script = _PS_TEMPLATE.format(title=_escape(title), message=_escape(message))
    try:
        runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=15,
        )
    except Exception:
        logger.warning("윈도우 알림 실패 (무시하고 계속합니다)", exc_info=True)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 6: 실제 알림 확인**

Run: `uv run python -c "from cgvwatch.notify.desktop import notify_desktop; notify_desktop('테스트', '알림이 보이면 성공')"`
Expected: 윈도우 우측 하단에 알림이 뜬다.

- [ ] **Step 7: Commit**

```bash
git add cgvwatch/notify/discord.py cgvwatch/notify/desktop.py tests/test_discord.py tests/test_desktop.py
git commit -m "feat: 좌석 확보·구조 변경·로그인 필요 알림 추가 (디스코드 + 윈도우 알림)"
```

---

### Task 8: 헌트 매니저와 감시 연동

**Files:**
- Create: `cgvwatch/hunt/manager.py`
- Modify: `cgvwatch/core/watcher.py` (알림 후 헌트 요청)
- Modify: `cgvwatch/web/server.py` (헌팅 상태·브라우저 열기 API)
- Modify: `cgvwatch/web/static/index.html` (상태 표시·버튼)
- Create: `tests/test_hunt_manager.py`

**Interfaces:**
- Consumes: `BrowserManager` (Task 5), `Hunter`/`HuntResult` (Task 6), 알림 함수 (Task 7),
  `get_showtimes`/`pick_showtime` (Task 3), `Watch` (Task 4)
- Produces:
  - `HuntManager(client, profile_dir, get_settings)` — `threading.Thread` 서브클래스(daemon)
    - `request_browser() -> None` — 브라우저 열기 요청
    - `request_hunt(watch: Watch) -> bool` — 큐에 넣음. 이미 같은 watch가 대기/진행 중이면 False
    - `stop_hunt() -> None` — 진행 중인 헌팅 중단
    - `status() -> dict` — `{"browser": bool, "active": str, "queued": int, "last": dict}`
    - `stop() -> None`
  - `cgvwatch/core/watcher.py`의 `check_watch`에 `on_open: Callable[[Watch], None] | None = None` 인자 추가.
    오픈을 감지해 알림까지 성공했을 때 호출한다.

**동작 규칙 (구현자가 알아야 할 것):**
- 감시는 날짜가 **새로 열리는 순간에만** 헌팅을 요청한다(`evaluate()`가 True일 때). 새로 등록한
  감시 항목은 이미 열린 날짜여도 첫 확인에서 한 번 요청이 나가므로 취소표 시나리오도 자동으로 걸린다.
- 헌터는 최대 1시간(`max_cycles=3600`, 1초 간격) 좌석 페이지에 머물며 빈자리를 기다린다.
  그 뒤에는 `실패`로 끝난다. 더 오래 노리려면 UI의 "지금 헌팅" 버튼으로 다시 시작한다.
- 이 규칙은 의도된 것이다. 무한정 폴링하지 않는 이유는 차단 위험과 방치된 자동화를 피하기 위해서다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_hunt_manager.py`:

```python
from unittest.mock import MagicMock

from cgvwatch.core.models import Settings, Watch
from cgvwatch.hunt.manager import HuntManager


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260827", hunt_enabled=True)
    base.update(kw)
    return Watch(**base)


def _manager(tmp_path):
    return HuntManager(MagicMock(), tmp_path / "profile", lambda: Settings())


def test_request_hunt_queues_watch(tmp_path):
    m = _manager(tmp_path)
    assert m.request_hunt(_watch()) is True
    assert m.status()["queued"] == 1


def test_request_hunt_rejects_duplicate(tmp_path):
    m = _manager(tmp_path)
    m.request_hunt(_watch())
    assert m.request_hunt(_watch()) is False
    assert m.status()["queued"] == 1


def test_status_reports_browser_off_initially(tmp_path):
    assert _manager(tmp_path).status()["browser"] is False


def test_process_one_requires_login(tmp_path, monkeypatch):
    """로그인이 안 돼 있으면 헌팅을 시작하지 않고 알림만 보낸다."""
    import cgvwatch.hunt.manager as hm
    alert = MagicMock()
    monkeypatch.setattr(hm, "send_login_required", alert)
    m = _manager(tmp_path)
    m._browser = MagicMock(is_running=lambda: True, is_logged_in=lambda: False)

    m._process(_watch())

    alert.assert_called_once()
    assert m.status()["last"]["status"] == "로그인필요"


def test_process_one_reports_no_showtime(tmp_path, monkeypatch):
    import cgvwatch.hunt.manager as hm
    monkeypatch.setattr(hm, "get_showtimes", lambda *a, **k: [])
    m = _manager(tmp_path)
    m._browser = MagicMock(is_running=lambda: True, is_logged_in=lambda: True)

    m._process(_watch(screen_filter="IMAX"))

    assert m.status()["last"]["status"] == "회차없음"


def test_process_one_reports_missing_browser(tmp_path):
    m = _manager(tmp_path)
    m._process(_watch())
    assert m.status()["last"]["status"] == "브라우저없음"
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `uv run pytest tests/test_hunt_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cgvwatch.hunt.manager'`

- [ ] **Step 3: 매니저 구현**

`cgvwatch/hunt/manager.py`:

```python
"""헌트 큐와 스레드. Playwright는 이 스레드에서만 다룬다."""
from __future__ import annotations

import logging
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

from cgvwatch.cgv.showtimes import get_showtimes
from cgvwatch.core.models import Watch
from cgvwatch.core.showpick import pick_showtime
from cgvwatch.hunt import selectors as sel
from cgvwatch.hunt.browser import BrowserManager
from cgvwatch.hunt.hunter import Hunter
from cgvwatch.notify.desktop import notify_desktop
from cgvwatch.notify.discord import (
    send_login_required,
    send_seat_secured,
    send_structure_warning,
)

logger = logging.getLogger(__name__)


class HuntManager(threading.Thread):
    """감시 스레드가 넣은 요청을 하나씩 처리한다. 동시 헌팅은 1개."""

    def __init__(self, client, profile_dir: Path, get_settings: Callable) -> None:
        super().__init__(daemon=True, name="cgvwatch-hunt")
        self._client = client
        self._profile_dir = Path(profile_dir)
        self._get_settings = get_settings
        self._queue: "queue.Queue[Watch]" = queue.Queue()
        self._lock = threading.Lock()
        self._queued_ids: set[str] = set()
        self._active: Optional[str] = None
        self._last: dict = {}
        self._hunter: Optional[Hunter] = None
        self._browser: Optional[BrowserManager] = None
        self._want_browser = threading.Event()
        self._stop = threading.Event()

    # --- 외부 API ---

    def request_browser(self) -> None:
        self._want_browser.set()

    def request_hunt(self, watch: Watch) -> bool:
        with self._lock:
            if watch.id in self._queued_ids or watch.id == self._active:
                return False
            self._queued_ids.add(watch.id)
        self._queue.put(watch)
        return True

    def stop_hunt(self) -> None:
        if self._hunter:
            self._hunter.stop()

    def stop(self) -> None:
        self._stop.set()
        self.stop_hunt()

    def status(self) -> dict:
        with self._lock:
            return {
                "browser": bool(self._browser and self._browser.is_running()),
                "active": self._active or "",
                "queued": len(self._queued_ids) - (1 if self._active else 0),
                "last": dict(self._last),
            }

    # --- 내부 ---

    def _record(self, watch: Watch, status: str, detail: str, seats=None) -> None:
        with self._lock:
            self._last = {
                "watch_id": watch.id,
                "mov_nm": watch.mov_nm,
                "status": status,
                "detail": detail,
                "seats": seats or [],
                "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    def _ensure_browser(self) -> bool:
        if self._browser is None:
            self._browser = BrowserManager(self._profile_dir)
        if not self._browser.is_running():
            self._browser.start()
        return self._browser.is_running()

    def _open_seat_page(self, watch: Watch, showtime: dict) -> bool:
        """예매 페이지로 이동해 회차를 클릭하고 좌석 화면까지 간다."""
        page = self._browser.page()
        url = sel.BOOKING_URL_TMPL.format(
            mov_no=watch.mov_no,
            ymd=watch.target_ymd,
            site_no=watch.site_no,
            site_nm=quote(watch.site_nm),
        )
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        start = showtime.get("start", "")
        label = f"{start[:2]}:{start[2:]}" if len(start) == 4 else start
        try:
            page.get_by_text(label, exact=False).first.click(timeout=15000)
        except Exception as exc:
            logger.warning("회차 클릭 실패(%s): %s", label, exc)
            return False
        for _ in range(60):
            if sel.SEAT_PATH in page.url:
                return True
            page.wait_for_timeout(500)
        return False

    def _process(self, watch: Watch) -> None:
        settings = self._get_settings()
        if not (self._browser and self._browser.is_running()):
            self._record(watch, "브라우저없음", "브라우저를 먼저 열어주세요.")
            return
        if not self._browser.is_logged_in():
            send_login_required(settings)
            self._record(watch, "로그인필요", "CGV 로그인 후 다시 시도합니다.")
            return

        showtimes = get_showtimes(
            self._client, watch.site_no, watch.mov_no, watch.target_ymd
        )
        showtime = pick_showtime(showtimes, watch.screen_filter, watch.preferred_time)
        if not showtime:
            self._record(watch, "회차없음", "조건에 맞는 회차를 찾지 못했습니다.")
            return

        if not self._open_seat_page(watch, showtime):
            send_structure_warning(watch, settings, "좌석 화면까지 진입하지 못했습니다.")
            self._record(watch, "구조변경", "좌석 화면 진입 실패")
            return

        self._hunter = Hunter(
            self._browser.page(), self._client, watch, showtime,
            on_event=lambda msg: logger.info("[헌팅] %s", msg),
        )
        result = self._hunter.run()
        self._hunter = None

        if result.status == "확보":
            try:
                self._browser.page().bring_to_front()
            except Exception:
                logger.warning("창을 앞으로 가져오지 못했습니다", exc_info=True)
            send_seat_secured(watch, settings, result.seats, showtime)
            notify_desktop("좌석 확보", f"{watch.mov_nm} {', '.join(result.seats)} — 결제해 주세요")
        elif result.status == "구조변경":
            send_structure_warning(watch, settings, result.detail)
        self._record(watch, result.status, result.detail, result.seats)

    def run(self) -> None:
        logger.info("헌트 매니저 시작")
        while not self._stop.is_set():
            if self._want_browser.is_set():
                self._want_browser.clear()
                try:
                    self._ensure_browser()
                except Exception:
                    logger.exception("브라우저 실행 실패")
            try:
                watch = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            with self._lock:
                self._active = watch.id
            try:
                self._process(watch)
            except Exception:
                logger.exception("헌팅 처리 실패: %s", watch.mov_nm)
                self._record(watch, "오류", "예기치 못한 오류. 로그를 확인하세요.")
            finally:
                with self._lock:
                    self._active = None
                    self._queued_ids.discard(watch.id)
        logger.info("헌트 매니저 종료")
```

- [ ] **Step 4: 감시 스레드에서 헌트 요청**

`cgvwatch/core/watcher.py`의 `check_watch` 시그니처에 인자를 추가한다:

```python
def check_watch(
    client,
    watch: Watch,
    settings: Settings,
    notify: Callable = send_open_alert,
    notify_error: Callable = send_error_alert,
    now: Optional[str] = None,
    on_open: Optional[Callable] = None,
) -> Watch:
```

오픈 알림이 성공한 직후(`logger.info("예매 오픈 감지·알림 발송", ...)` 다음 줄) 다음을 추가:

```python
        if on_open and watch.hunt_enabled:
            try:
                on_open(watch)
            except Exception:
                logger.exception("헌트 요청 실패: %s", watch.mov_nm)
```

`WatcherThread.__init__`에 `on_open: Optional[Callable] = None`을 받아 `self._on_open`에 저장하고,
`_run_once`의 `check_watch(...)` 호출에 `on_open=self._on_open`을 넘긴다.

- [ ] **Step 5: 서버에 매니저 연결**

`cgvwatch/web/server.py`의 `create_app`에서 `AppState` 생성 뒤에 추가:

```python
    hunt = HuntManager(
        client,
        Path.home() / ".cgv-watcher" / "chrome-profile",
        lambda: state.settings,
    )
```

`lifespan`에서 `watcher.start()` 앞에 `hunt.start()`를, `watcher.stop()` 뒤에 `hunt.stop()`을 넣는다.
`WatcherThread(client, state.get_state)` 를 `WatcherThread(client, state.get_state, on_open=hunt.request_hunt)` 로 바꾼다.

엔드포인트를 추가한다:

```python
    @app.get("/api/hunt")
    def hunt_status():
        return hunt.status()

    @app.post("/api/hunt/browser", status_code=202)
    def open_browser():
        hunt.request_browser()
        return {"ok": True}

    @app.post("/api/hunt/stop", status_code=202)
    def stop_hunt():
        hunt.stop_hunt()
        return {"ok": True}

    @app.post("/api/hunt/{watch_id}", status_code=202)
    def hunt_now(watch_id: str):
        """이미 등록된 감시 항목으로 지금 바로 헌팅을 시작한다.

        감시는 '새로 열린' 순간에만 헌팅을 요청하므로, 이미 열린 회차의 취소표를
        노리거나 실패한 헌팅을 다시 시도할 때 이 엔드포인트를 쓴다.
        """
        with state.lock:
            watch = next((w for w in state.watches if w.id == watch_id), None)
        if not watch:
            raise HTTPException(404, "해당 감시 항목이 없습니다.")
        if not hunt.request_hunt(watch):
            raise HTTPException(409, "이미 대기 중이거나 진행 중입니다.")
        return {"ok": True}
```

임포트에 다음을 추가한다:

```python
from cgvwatch.hunt.manager import HuntManager
```

- [ ] **Step 6: 웹 UI에 상태 표시**

`index.html`의 헤더 `interval-box` 뒤에 추가:

```html
    <div class="interval-box">
      <button id="browser-btn" class="primary" type="button">브라우저 열기</button>
      <span id="hunt-status">헌팅 대기</span>
    </div>
```

스크립트에 추가:

```javascript
  var browserBtn = document.getElementById("browser-btn");
  var huntStatus = document.getElementById("hunt-status");

  function loadHunt() {
    fetch("/api/hunt")
      .then(function (res) {
        if (!res.ok) throw new Error("헌팅 상태를 불러오지 못했습니다.");
        return res.json();
      })
      .then(function (h) {
        var parts = [h.browser ? "브라우저 켜짐" : "브라우저 꺼짐"];
        if (h.active) parts.push("헌팅 중");
        if (h.queued > 0) parts.push("대기 " + h.queued);
        if (h.last && h.last.status) {
          parts.push("최근: " + h.last.status +
            (h.last.seats && h.last.seats.length ? " " + h.last.seats.join(",") : ""));
        }
        huntStatus.textContent = parts.join(" · ");
      })
      .catch(function (err) { showError(err.message); });
  }

  browserBtn.addEventListener("click", function () {
    browserBtn.disabled = true;
    fetch("/api/hunt/browser", { method: "POST" })
      .then(function (res) {
        if (!res.ok) throw new Error("브라우저를 열지 못했습니다.");
        huntStatus.textContent = "브라우저 여는 중…";
      })
      .catch(function (err) { showError(err.message); })
      .finally(function () { browserBtn.disabled = false; });
  });
```

`setInterval(loadWatches, 5000);` 아래에 `setInterval(loadHunt, 5000);` 와 초기 `loadHunt();` 를 추가한다.

목록의 삭제 버튼을 만드는 곳에서, 삭제 버튼을 붙이기 **전에** "지금 헌팅" 버튼을 추가한다
(헌팅이 켜진 항목에만 보인다). 이미 열린 회차의 취소표를 노리거나 실패한 헌팅을 다시 시도할 때 쓴다:

```javascript
      if (w.hunt_enabled) {
        var huntBtn = document.createElement("button");
        huntBtn.className = "delete-btn";
        huntBtn.textContent = "지금 헌팅";
        huntBtn.addEventListener("click", function () {
          huntBtn.disabled = true;
          fetch("/api/hunt/" + w.id, { method: "POST" })
            .then(function (res) {
              if (!res.ok) throw new Error("헌팅을 시작하지 못했습니다.");
              loadHunt();
            })
            .catch(function (err) { showError(err.message); })
            .finally(function () { huntBtn.disabled = false; });
        });
        actionTd.appendChild(huntBtn);
      }
```

(`actionTd`는 삭제 버튼이 들어가는 마지막 `<td>`의 변수명이다. 실제 코드의 변수명에 맞춘다.)

- [ ] **Step 7: 수동 헌팅 엔드포인트 테스트 추가**

`tests/test_server.py` 끝에 추가:

```python
def test_hunt_now_404_for_unknown_watch(api):
    tc, _, _ = api
    assert tc.post("/api/hunt/nope").status_code == 404


def test_hunt_status_endpoint(api):
    tc, _, _ = api
    body = tc.get("/api/hunt").json()
    assert body["browser"] is False
    assert body["queued"] == 0
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `uv run pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 9: 서버 기동 스모크**

Run:
```bash
uv run python -c "
from fastapi.testclient import TestClient
from cgvwatch.web.server import create_app
from cgvwatch.core.store import Store
import tempfile, pathlib
tc = TestClient(create_app(store=Store(pathlib.Path(tempfile.mkdtemp())/'c.json'), start_watcher=False))
print('GET /api/hunt:', tc.get('/api/hunt').json())
print('GET /:', tc.get('/').status_code)
"
```
Expected: 상태 딕셔너리가 출력되고 `200`이 뜬다.

- [ ] **Step 10: Commit**

```bash
git add cgvwatch/hunt/manager.py cgvwatch/core/watcher.py cgvwatch/web/server.py cgvwatch/web/static/index.html tests/test_hunt_manager.py
git commit -m "feat: 헌트 매니저 추가 및 감시-헌팅 연동 (큐·브라우저 제어·상태 API)"
```

---

### Task 9: 정리와 유지보수 문서

**Files:**
- Delete: `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- Modify: `README.md`
- Modify: `.env.example`
- Create: `CLAUDE.md`

**Interfaces:**
- Consumes: 앞선 모든 태스크의 결과
- Produces: `CLAUDE.md` — 다음 세션의 클로드코드가 자동으로 읽는 유지보수 매뉴얼

- [ ] **Step 1: Docker 파일 제거**

Run:
```bash
git rm Dockerfile docker-compose.yml .dockerignore
```
`.env.example`에서 `HOST_PORT` 줄을 지우고 `DISCORD_WEBHOOK_URL`만 남긴다.

- [ ] **Step 2: 전체 테스트 실행**

Run: `uv run pytest tests/ -v`
Expected: 전부 PASS (도커 제거는 테스트에 영향이 없어야 한다)

- [ ] **Step 3: README 재작성**

`README.md`를 노트북 실행 기준으로 다시 쓴다. 포함할 내용:
- 무엇을 하는 프로그램인지 (감시·알림 + 좌석 자동 확보, 결제는 사람이)
- 준비: `uv sync --extra dev`, `uv run playwright install chromium`,
  `.env`에 `DISCORD_WEBHOOK_URL` 기입
- 실행: `python run.py` → 브라우저로 `http://localhost:8080`
- 첫 사용: 웹 UI에서 "브라우저 열기" → 뜬 크롬에서 CGV 로그인 → 감시 등록
- 환경 변수 표: `DISCORD_WEBHOOK_URL`, `CGVWATCH_DATA`, `PORT`
- 안전 정책: 자동 로그인 없음, 결제 자동화 없음, 폴링 1초 하한, 동시 헌팅 1개

- [ ] **Step 4: CLAUDE.md 작성**

`CLAUDE.md`를 저장소 루트에 만든다. **파일 목록이나 함수 시그니처를 나열하지 않는다**(코드를 읽으면 알 수 있고 금방 낡는다).
대신 다음을 담는다:

1. **이 프로젝트가 무엇이고 무엇을 하지 않는지** — 안전선(자동 로그인·결제 자동화 금지)과 그 이유
2. **CGV API 관찰 기록** — 설계 문서(`docs/superpowers/specs/2026-08-26-seat-hunter-design.md`)의
   "CGV API 관찰 기록" 절을 옮기고, 각 항목에 확인 날짜를 붙인다
3. **깨졌을 때 진단 절차** — 아래 내용을 구체적 수순으로:
   - 감시가 오류 상태 → `docker logs` 대신 콘솔 로그에서 `CGV 조회 실패` 확인 →
     `Referer` 헤더가 살아있는지, 403/429인지 확인
   - 좌석을 못 잡음 → `selectors.py`의 확인 날짜를 보고, Playwright로 좌석 페이지를 열어
     `button[data-seatlocno]` 개수를 센다 → 0이면 새 셀렉터를 찾아 `selectors.py`만 고친다
   - "화면 구조 변경 의심" 알림이 왔을 때도 같은 절차
4. **시도했다 버린 것들** — 회차별 딥링크는 CGV에 없음, 디스코드 회차 버튼은 실효가 없어 제거,
   시간대 범위 필터는 관 필터로 대체
5. **관찰 날짜를 반드시 적는 규칙** — 외부 세계에 대한 사실에는 항상 확인 날짜를 붙일 것

- [ ] **Step 5: 문서 정확성 확인**

Run: `grep -rn "docker\|Docker" README.md CLAUDE.md`
Expected: 매치 없음 (도커 운영을 중단했으므로 문서에 남아 있으면 안 된다)

- [ ] **Step 6: 전체 테스트 최종 실행**

Run: `uv run pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 7: Commit & Push**

```bash
git add -A
git commit -m "docs: 노트북 실행 기준 README와 유지보수 매뉴얼(CLAUDE.md) 작성, Docker 제거"
git push
```

---

## 실행 전 확인 사항

이 계획을 시작하기 전에 다음을 확인한다.

- `uv run playwright install chromium`이 완료되어야 Task 5부터 진행할 수 있다.
- Task 5 Step 8(실제 브라우저로 셀렉터 재확인)은 **사람이 로그인하고 좌석 화면까지 이동해야 하는
  대화형 단계**다. 자동으로 넘길 수 없다.
- 셀렉터가 2026-08-23 관찰값이므로, Task 5~6에서 실제 화면과 다를 가능성이 높다.
  다르면 `selectors.py`만 고치고 확인 날짜를 갱신한다. 다른 파일에는 셀렉터가 없어야 한다.
- 실전 테스트(실제 예매 오픈 시각에 헌팅)는 계획 밖이다. 사람이 지켜보는 상태에서 시도한다.
