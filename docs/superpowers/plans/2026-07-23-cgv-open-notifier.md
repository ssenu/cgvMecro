# CGV 예매 오픈 알리미 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 지정한 (극장·날짜·영화) 조건의 CGV 예매가 열리는 순간을 감지해 이메일로 알려주는 PyQt6 Windows 데스크톱 앱을 만든다.

**Architecture:** PyQt6 단일 프로세스 앱. 메인 스레드는 GUI, `QThread` 워커가 N분마다 CGV 공개 JSON API(`cgv.co.kr/api/v1/booking/*`)를 `requests`로 조회한다. 감지 로직은 Qt에 의존하지 않는 순수 함수로 분리해 테스트한다. 상태는 로컬 JSON, Gmail 앱 비밀번호는 `keyring`에 저장한다.

**Tech Stack:** Python 3.11+, PyQt6, requests, keyring, pytest, pytest-mock

## Global Constraints

- Python 3.11 이상.
- 외부 네트워크 접근은 `cgv/client.py` 한 곳으로만. 나머지 모듈은 client를 통해서만 CGV에 접근.
- CGV 공통 파라미터 `coCd=A420`, base URL `https://cgv.co.kr/api/v1/booking/`.
- 성공 응답은 `statusCode == 0`. 그 외는 오류로 취급.
- User-Agent는 일반 브라우저 문자열 사용, 요청 타임아웃 10초.
- Gmail 앱 비밀번호는 절대 JSON/코드에 평문 저장 금지 → `keyring` 사용.
- 설정 디렉터리: `%USERPROFILE%\.cgv-watcher\` (`Path.home() / ".cgv-watcher"`).
- 모든 사용자 노출 문자열은 한국어.

---

## 파일 구조

```
cgvwatch/
  __init__.py
  cgv/
    __init__.py
    client.py        # CGVClient: 세션/요청 래퍼/statusCode 검증
    theaters.py      # get_regions()
    movies.py        # get_movies()
    showtimes.py     # get_open_dates(site_no, mov_no)
  core/
    __init__.py
    models.py        # Watch, Settings 데이터클래스 + 상태 상수
    detect.py        # 순수 감지 전이 함수 (Qt 비의존)
    store.py         # 설정/감시목록 JSON 로드·저장
    watcher.py       # WatcherWorker(QThread): 주기 조회 + 시그널
  notify/
    __init__.py
    mailer.py        # Gmail SMTP 발송 + keyring
  gui/
    __init__.py
    settings_dialog.py
    add_dialog.py
    main_window.py
  app.py             # 진입점
tests/
  __init__.py
  fixtures/
    regions.json
    movies.json
    open_dates.json
  test_client.py
  test_theaters.py
  test_movies.py
  test_showtimes.py
  test_detect.py
  test_store.py
  test_mailer.py
requirements.txt
README.md
```

---

### Task 1: 프로젝트 스캐폴드 + CGV API 클라이언트

**Files:**
- Create: `requirements.txt`, `cgvwatch/__init__.py`, `cgvwatch/cgv/__init__.py`, `tests/__init__.py`
- Create: `cgvwatch/cgv/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Produces:
  - `class CGVError(Exception)`
  - `class CGVClient(base_url: str = "https://cgv.co.kr/api/v1/booking/", co_cd: str = "A420", timeout: int = 10, session=None)`
  - `CGVClient.get_json(self, endpoint: str, params: dict) -> Any` — `coCd`를 자동 주입, HTTP·`statusCode` 검증 후 `data` 반환. 실패 시 `CGVError`.

- [ ] **Step 1: requirements.txt와 패키지 스캐폴드 작성**

`requirements.txt`:
```
PyQt6>=6.6
requests>=2.31
keyring>=24
pytest>=8.0
pytest-mock>=3.12
```

빈 파일 생성: `cgvwatch/__init__.py`, `cgvwatch/cgv/__init__.py`, `tests/__init__.py`.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_client.py`:
```python
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
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_client.py -v`
Expected: FAIL (`ModuleNotFoundError: cgvwatch.cgv.client`)

- [ ] **Step 4: 최소 구현 작성**

`cgvwatch/cgv/client.py`:
```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_client.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋**

```bash
git add requirements.txt cgvwatch tests
git commit -m "feat: CGV API 클라이언트(get_json) + 프로젝트 스캐폴드"
```

---

### Task 2: 극장 목록 (theaters)

**Files:**
- Create: `cgvwatch/cgv/theaters.py`, `tests/fixtures/regions.json`
- Test: `tests/test_theaters.py`

**Interfaces:**
- Consumes: `CGVClient.get_json`
- Produces:
  - `Region = namedtuple/dataclass` 아님 — 단순 dict 리스트 사용.
  - `get_regions(client: CGVClient) -> list[dict]` — `[{"name": str, "sites": [{"site_no": str, "site_nm": str}, ...]}, ...]`

- [ ] **Step 1: 픽스처 저장**

`tests/fixtures/regions.json` (실제 응답 축약):
```json
{
  "statusCode": 0,
  "statusMessage": "조회 되었습니다.",
  "data": [
    {"regnGrpNm": "서울", "siteList": [
      {"siteNo": "0056", "siteNm": "강남"},
      {"siteNo": "0001", "siteNm": "강변"}
    ]},
    {"regnGrpNm": "경기", "siteList": [
      {"siteNo": "0112", "siteNm": "수원"}
    ]}
  ]
}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_theaters.py`:
```python
import json
from pathlib import Path
from unittest.mock import MagicMock
from cgvwatch.cgv.theaters import get_regions

FIX = json.loads((Path(__file__).parent / "fixtures" / "regions.json").read_text(encoding="utf-8"))


def test_get_regions_parses_sites():
    client = MagicMock()
    client.get_json.return_value = FIX["data"]

    regions = get_regions(client)

    assert regions[0]["name"] == "서울"
    assert {s["site_nm"] for s in regions[0]["sites"]} == {"강남", "강변"}
    assert regions[0]["sites"][0]["site_no"] == "0056"
    client.get_json.assert_called_once_with("searchRegnList", {})
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_theaters.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 4: 최소 구현 작성**

`cgvwatch/cgv/theaters.py`:
```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_theaters.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add cgvwatch/cgv/theaters.py tests/test_theaters.py tests/fixtures/regions.json
git commit -m "feat: 지역·극장 목록 조회(get_regions)"
```

---

### Task 3: 영화 목록 (movies)

**Files:**
- Create: `cgvwatch/cgv/movies.py`, `tests/fixtures/movies.json`
- Test: `tests/test_movies.py`

**Interfaces:**
- Consumes: `CGVClient.get_json`
- Produces:
  - `get_movies(client: CGVClient) -> list[dict]` — `[{"mov_no": str, "mov_nm": str}, ...]`

- [ ] **Step 1: 픽스처 저장**

`tests/fixtures/movies.json`:
```json
{
  "statusCode": 0,
  "data": [
    {"movNo": "30001192", "movNm": "스파이더맨-브랜드 뉴 데이"},
    {"movNo": "30001323", "movNm": "오디세이"}
  ]
}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_movies.py`:
```python
import json
from pathlib import Path
from unittest.mock import MagicMock
from cgvwatch.cgv.movies import get_movies

FIX = json.loads((Path(__file__).parent / "fixtures" / "movies.json").read_text(encoding="utf-8"))


def test_get_movies_parses_list():
    client = MagicMock()
    client.get_json.return_value = FIX["data"]

    movies = get_movies(client)

    assert {"mov_no": "30001192", "mov_nm": "스파이더맨-브랜드 뉴 데이"} in movies
    endpoint, params = client.get_json.call_args[0]
    assert endpoint == "searchAtktTopPostrList"
    assert params == {"movNm": "", "div": "", "attrCd": ""}
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_movies.py -v`
Expected: FAIL

- [ ] **Step 4: 최소 구현 작성**

`cgvwatch/cgv/movies.py`:
```python
"""영화 목록 조회 (제목 → movNo 매핑용)."""
from __future__ import annotations

from .client import CGVClient


def get_movies(client: CGVClient) -> list[dict]:
    data = client.get_json("searchAtktTopPostrList", {"movNm": "", "div": "", "attrCd": ""}) or []
    return [{"mov_no": m["movNo"], "mov_nm": m["movNm"]} for m in data]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_movies.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add cgvwatch/cgv/movies.py tests/test_movies.py tests/fixtures/movies.json
git commit -m "feat: 영화 목록 조회(get_movies)"
```

---

### Task 4: 예매 오픈 날짜 조회 (showtimes) — 감지 핵심

**Files:**
- Create: `cgvwatch/cgv/showtimes.py`, `tests/fixtures/open_dates.json`
- Test: `tests/test_showtimes.py`

**Interfaces:**
- Consumes: `CGVClient.get_json`
- Produces:
  - `get_open_dates(client: CGVClient, site_no: str, mov_no: str) -> set[str]` — 예매 가능한 `YYYYMMDD` 집합.

- [ ] **Step 1: 픽스처 저장**

`tests/fixtures/open_dates.json`:
```json
{
  "statusCode": 0,
  "data": [
    {"scnYmd": "20260729", "hldyYn": null},
    {"scnYmd": "20260730", "hldyYn": null}
  ]
}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_showtimes.py`:
```python
import json
from pathlib import Path
from unittest.mock import MagicMock
from cgvwatch.cgv.showtimes import get_open_dates

FIX = json.loads((Path(__file__).parent / "fixtures" / "open_dates.json").read_text(encoding="utf-8"))


def test_get_open_dates_returns_set():
    client = MagicMock()
    client.get_json.return_value = FIX["data"]

    dates = get_open_dates(client, "0056", "30001192")

    assert dates == {"20260729", "20260730"}
    endpoint, params = client.get_json.call_args[0]
    assert endpoint == "searchSiteScnscYmdListByMov"
    assert params == {"siteNo": "0056", "movNo": "30001192"}


def test_get_open_dates_empty_when_no_data():
    client = MagicMock()
    client.get_json.return_value = None
    assert get_open_dates(client, "0056", "30001192") == set()
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/test_showtimes.py -v`
Expected: FAIL

- [ ] **Step 4: 최소 구현 작성**

`cgvwatch/cgv/showtimes.py`:
```python
"""예매 오픈 날짜 조회. 시나리오 A 감지의 핵심."""
from __future__ import annotations

from .client import CGVClient


def get_open_dates(client: CGVClient, site_no: str, mov_no: str) -> set[str]:
    data = client.get_json(
        "searchSiteScnscYmdListByMov", {"siteNo": site_no, "movNo": mov_no}
    ) or []
    return {row["scnYmd"] for row in data if row.get("scnYmd")}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_showtimes.py -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add cgvwatch/cgv/showtimes.py tests/test_showtimes.py tests/fixtures/open_dates.json
git commit -m "feat: 예매 오픈 날짜 조회(get_open_dates)"
```

---

### Task 5: 데이터 모델 + 순수 감지 로직

**Files:**
- Create: `cgvwatch/core/__init__.py`, `cgvwatch/core/models.py`, `cgvwatch/core/detect.py`
- Test: `tests/test_detect.py`

**Interfaces:**
- Produces:
  - `models.Status`: 상수 `WAITING="대기중"`, `OPEN="열림"`, `ERROR="오류"`.
  - `models.Watch` 데이터클래스: `id: str, mov_no: str, mov_nm: str, site_no: str, site_nm: str, target_ymd: str, status: str = WAITING, was_open: bool = False, last_checked: str = ""`.
  - `models.Settings` 데이터클래스: `gmail_user: str = "", recipient: str = "", interval_min: int = 5`.
  - `detect.evaluate(watch: Watch, open_dates: set[str]) -> bool` — 이번 조회에서 **새로 열렸으면** True(=메일 대상). `watch.was_open`이 False이고 `target_ymd in open_dates`일 때만 True.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_detect.py`:
```python
from cgvwatch.core.models import Watch, Status
from cgvwatch.core.detect import evaluate


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260729")
    base.update(kw)
    return Watch(**base)


def test_evaluate_true_on_first_open():
    w = _watch(was_open=False)
    assert evaluate(w, {"20260729", "20260730"}) is True


def test_evaluate_false_when_target_not_open_yet():
    w = _watch(was_open=False)
    assert evaluate(w, {"20260801"}) is False


def test_evaluate_false_when_already_open_no_duplicate():
    w = _watch(was_open=True)
    assert evaluate(w, {"20260729"}) is False


def test_default_status_is_waiting():
    assert _watch().status == Status.WAITING
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_detect.py -v`
Expected: FAIL

- [ ] **Step 3: 최소 구현 작성**

`cgvwatch/core/__init__.py`: (빈 파일)

`cgvwatch/core/models.py`:
```python
"""도메인 모델과 상태 상수."""
from __future__ import annotations

from dataclasses import dataclass


class Status:
    WAITING = "대기중"
    OPEN = "열림"
    ERROR = "오류"


@dataclass
class Watch:
    id: str
    mov_no: str
    mov_nm: str
    site_no: str
    site_nm: str
    target_ymd: str  # YYYYMMDD
    status: str = Status.WAITING
    was_open: bool = False
    last_checked: str = ""


@dataclass
class Settings:
    gmail_user: str = ""
    recipient: str = ""
    interval_min: int = 5
```

`cgvwatch/core/detect.py`:
```python
"""Qt에 의존하지 않는 순수 감지 전이 로직."""
from __future__ import annotations

from .models import Watch


def evaluate(watch: Watch, open_dates: set[str]) -> bool:
    """이번 조회에서 대상 날짜가 '새로' 열렸으면 True(메일 발송 대상)."""
    if watch.was_open:
        return False
    return watch.target_ymd in open_dates
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_detect.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add cgvwatch/core/__init__.py cgvwatch/core/models.py cgvwatch/core/detect.py tests/test_detect.py
git commit -m "feat: 도메인 모델 + 순수 감지 전이 로직(evaluate)"
```

---

### Task 6: 설정/감시목록 저장소 (store)

**Files:**
- Create: `cgvwatch/core/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `models.Watch`, `models.Settings`
- Produces:
  - `store.Store(path: Path)` — 기본 경로 `Path.home()/".cgv-watcher"/"config.json"`.
  - `Store.load() -> tuple[Settings, list[Watch]]`
  - `Store.save(settings: Settings, watches: list[Watch]) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_store.py`:
```python
from cgvwatch.core.models import Watch, Settings, Status
from cgvwatch.core.store import Store


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    store = Store(path)
    settings = Settings(gmail_user="me@gmail.com", recipient="me@gmail.com", interval_min=10)
    watches = [Watch(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                     site_nm="강남", target_ymd="20260729", was_open=True, status=Status.OPEN)]

    store.save(settings, watches)
    loaded_settings, loaded_watches = store.load()

    assert loaded_settings == settings
    assert loaded_watches == watches


def test_load_missing_file_returns_defaults(tmp_path):
    store = Store(tmp_path / "nope.json")
    settings, watches = store.load()
    assert settings == Settings()
    assert watches == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL

- [ ] **Step 3: 최소 구현 작성**

`cgvwatch/core/store.py`:
```python
"""설정·감시목록의 로컬 JSON 영속화."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Settings, Watch

DEFAULT_PATH = Path.home() / ".cgv-watcher" / "config.json"


class Store:
    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = Path(path)

    def load(self) -> tuple[Settings, list[Watch]]:
        if not self.path.exists():
            return Settings(), []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        settings = Settings(**raw.get("settings", {}))
        watches = [Watch(**w) for w in raw.get("watches", [])]
        return settings, watches

    def save(self, settings: Settings, watches: list[Watch]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"settings": asdict(settings), "watches": [asdict(w) for w in watches]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_store.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add cgvwatch/core/store.py tests/test_store.py
git commit -m "feat: 설정·감시목록 JSON 저장소(Store)"
```

---

### Task 7: 이메일 발송 (mailer)

**Files:**
- Create: `cgvwatch/notify/__init__.py`, `cgvwatch/notify/mailer.py`
- Test: `tests/test_mailer.py`

**Interfaces:**
- Consumes: `models.Watch`, `models.Settings`
- Produces:
  - `mailer.KEYRING_SERVICE = "cgv-watcher"`
  - `mailer.save_app_password(user: str, password: str) -> None` (keyring 저장)
  - `mailer.get_app_password(user: str) -> str | None`
  - `mailer.build_message(watch: Watch, settings: Settings) -> tuple[str, str]` — `(subject, body)` 순수 함수.
  - `mailer.send_open_mail(watch: Watch, settings: Settings, smtp_factory=None) -> None` — 앱 비밀번호를 keyring에서 읽어 Gmail SMTP(SSL)로 발송. `smtp_factory`는 테스트 주입용(기본 `smtplib.SMTP_SSL`).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_mailer.py`:
```python
from unittest.mock import MagicMock
import cgvwatch.notify.mailer as mailer
from cgvwatch.core.models import Watch, Settings


def _watch():
    return Watch(id="1", mov_no="30001192", mov_nm="스파이더맨-브랜드 뉴 데이",
                 site_no="0056", site_nm="강남", target_ymd="20260725")


def test_build_message_contains_key_fields():
    subject, body = mailer.build_message(_watch(), Settings(recipient="me@gmail.com"))
    assert "스파이더맨-브랜드 뉴 데이" in subject
    assert "강남" in subject
    assert "07/25" in subject
    assert "강남" in body
    assert "2026" in body


def test_send_open_mail_uses_smtp(monkeypatch):
    smtp = MagicMock()
    smtp_ctx = MagicMock()
    smtp_ctx.__enter__.return_value = smtp
    factory = MagicMock(return_value=smtp_ctx)
    monkeypatch.setattr(mailer, "get_app_password", lambda user: "app-pw")

    settings = Settings(gmail_user="me@gmail.com", recipient="you@gmail.com")
    mailer.send_open_mail(_watch(), settings, smtp_factory=factory)

    smtp.login.assert_called_once_with("me@gmail.com", "app-pw")
    assert smtp.send_message.call_count == 1


def test_send_open_mail_raises_without_password(monkeypatch):
    monkeypatch.setattr(mailer, "get_app_password", lambda user: None)
    import pytest
    with pytest.raises(RuntimeError):
        mailer.send_open_mail(_watch(), Settings(gmail_user="me@gmail.com"), smtp_factory=MagicMock())
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_mailer.py -v`
Expected: FAIL

- [ ] **Step 3: 최소 구현 작성**

`cgvwatch/notify/__init__.py`: (빈 파일)

`cgvwatch/notify/mailer.py`:
```python
"""Gmail SMTP 이메일 발송 + keyring 앱 비밀번호 관리."""
from __future__ import annotations

import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Callable, Optional

import keyring

from cgvwatch.core.models import Settings, Watch

KEYRING_SERVICE = "cgv-watcher"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
BOOK_URL = "https://cgv.co.kr/cnm/movieBook/cinema"


def save_app_password(user: str, password: str) -> None:
    keyring.set_password(KEYRING_SERVICE, user, password)


def get_app_password(user: str) -> Optional[str]:
    return keyring.get_password(KEYRING_SERVICE, user)


def _fmt_ymd(ymd: str) -> str:
    return f"{ymd[4:6]}/{ymd[6:8]}"  # MM/DD


def build_message(watch: Watch, settings: Settings) -> tuple[str, str]:
    subject = f'[CGV] "{watch.mov_nm}" {watch.site_nm} {_fmt_ymd(watch.target_ymd)} 예매 열렸습니다'
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = (
        f"CGV 예매가 열렸습니다.\n\n"
        f"영화: {watch.mov_nm}\n"
        f"상영관: {watch.site_nm}\n"
        f"날짜: {watch.target_ymd[:4]}-{watch.target_ymd[4:6]}-{watch.target_ymd[6:8]}\n"
        f"확인 시각: {now}\n\n"
        f"예매하기: {BOOK_URL}\n"
    )
    return subject, body


def send_open_mail(
    watch: Watch,
    settings: Settings,
    smtp_factory: Optional[Callable] = None,
) -> None:
    password = get_app_password(settings.gmail_user)
    if not password:
        raise RuntimeError("Gmail 앱 비밀번호가 설정되지 않았습니다.")
    subject, body = build_message(watch, settings)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.gmail_user
    msg["To"] = settings.recipient or settings.gmail_user
    msg.set_content(body)

    factory = smtp_factory or (lambda: smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15))
    with factory() as smtp:
        smtp.login(settings.gmail_user, password)
        smtp.send_message(msg)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_mailer.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add cgvwatch/notify tests/test_mailer.py
git commit -m "feat: Gmail SMTP 발송 + keyring 앱 비밀번호(mailer)"
```

---

### Task 8: 감시 워커 (watcher, QThread)

**Files:**
- Create: `cgvwatch/core/watcher.py`
- Test: `tests/test_watcher.py`

**Interfaces:**
- Consumes: `CGVClient`, `showtimes.get_open_dates`, `detect.evaluate`, `mailer.send_open_mail`, `models.Watch/Settings`
- Produces:
  - `watcher.check_watch(client, watch, settings, send_mail=send_open_mail, now=None) -> Watch` — 순수 로직: 한 조건을 조회·판정하고 **갱신된 새 Watch**를 반환(상태/was_open/last_checked 갱신). 새로 열리면 `send_mail` 호출. 예외 시 status=ERROR.
  - `watcher.WatcherWorker(QThread)` — `__init__(client, get_state, set_state)`; `run()`에서 `interval` 간격 루프. 시그널 `updated = pyqtSignal(str, str, str)` (watch_id, status, last_checked). `stop()`.

  > 참고: QThread 부분은 `check_watch`를 호출만 하는 얇은 래퍼다. 로직 테스트는 `check_watch`로 한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_watcher.py`:
```python
from unittest.mock import MagicMock
from cgvwatch.core.models import Watch, Settings, Status
from cgvwatch.core.watcher import check_watch


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260729")
    base.update(kw)
    return Watch(**base)


def test_check_watch_sends_mail_and_marks_open(monkeypatch):
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})
    send = MagicMock()

    result = check_watch(MagicMock(), _watch(), Settings(), send_mail=send, now="2026-07-23 10:00")

    assert result.was_open is True
    assert result.status == Status.OPEN
    assert result.last_checked == "2026-07-23 10:00"
    send.assert_called_once()


def test_check_watch_waiting_when_not_open(monkeypatch):
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260801"})
    send = MagicMock()

    result = check_watch(MagicMock(), _watch(), Settings(), send_mail=send)

    assert result.was_open is False
    assert result.status == Status.WAITING
    send.assert_not_called()


def test_check_watch_error_sets_error_status(monkeypatch):
    import cgvwatch.core.watcher as w
    def boom(c, s, m):
        raise RuntimeError("네트워크")
    monkeypatch.setattr(w, "get_open_dates", boom)

    result = check_watch(MagicMock(), _watch(), Settings(), send_mail=MagicMock())

    assert result.status == Status.ERROR
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/test_watcher.py -v`
Expected: FAIL

- [ ] **Step 3: 최소 구현 작성**

`cgvwatch/core/watcher.py`:
```python
"""주기적 감시 워커. 순수 로직(check_watch)과 QThread 래퍼를 분리한다."""
from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from cgvwatch.cgv.showtimes import get_open_dates
from cgvwatch.core.detect import evaluate
from cgvwatch.core.models import Settings, Status, Watch
from cgvwatch.notify.mailer import send_open_mail


def check_watch(
    client,
    watch: Watch,
    settings: Settings,
    send_mail: Callable = send_open_mail,
    now: Optional[str] = None,
) -> Watch:
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        open_dates = get_open_dates(client, watch.site_no, watch.mov_no)
    except Exception:
        return replace(watch, status=Status.ERROR, last_checked=now)

    if evaluate(watch, open_dates):
        send_mail(watch, settings)
        return replace(watch, was_open=True, status=Status.OPEN, last_checked=now)

    status = Status.OPEN if watch.was_open else Status.WAITING
    return replace(watch, status=status, last_checked=now)


class WatcherWorker(QThread):
    updated = pyqtSignal(str, str, str)  # watch_id, status, last_checked

    def __init__(self, client, get_state: Callable, parent=None) -> None:
        super().__init__(parent)
        self._client = client
        self._get_state = get_state  # () -> tuple[Settings, list[Watch], set_watch_fn]
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            settings, watches, set_watch = self._get_state()
            for watch in list(watches):
                if not self._running:
                    break
                updated = check_watch(self._client, watch, settings)
                set_watch(updated)
                self.updated.emit(updated.id, updated.status, updated.last_checked)
            # interval 분 동안 1초 단위로 나눠 대기 (정지 응답성)
            for _ in range(max(1, settings.interval_min) * 60):
                if not self._running:
                    break
                time.sleep(1)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_watcher.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 전체 테스트 확인**

Run: `python -m pytest -v`
Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add cgvwatch/core/watcher.py tests/test_watcher.py
git commit -m "feat: 감시 워커 check_watch + WatcherWorker(QThread)"
```

---

### Task 9: 설정 다이얼로그 (GUI)

**Files:**
- Create: `cgvwatch/gui/__init__.py`, `cgvwatch/gui/settings_dialog.py`

**Interfaces:**
- Consumes: `models.Settings`, `mailer.save_app_password`
- Produces:
  - `SettingsDialog(settings: Settings, parent=None)` — Gmail 주소/앱 비밀번호/수신 주소/폴링 간격 입력.
  - `SettingsDialog.result_settings() -> Settings`
  - 저장(수락) 시 앱 비밀번호가 입력돼 있으면 `save_app_password(gmail_user, pw)` 호출.

- [ ] **Step 1: 구현 작성**

`cgvwatch/gui/__init__.py`: (빈 파일)

`cgvwatch/gui/settings_dialog.py`:
```python
"""Gmail·알림 설정 다이얼로그."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox, QVBoxLayout, QLabel,
)

from cgvwatch.core.models import Settings
from cgvwatch.notify.mailer import save_app_password, get_app_password


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("설정")
        self._settings = settings

        self.gmail_edit = QLineEdit(settings.gmail_user)
        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_edit.setPlaceholderText("변경 시에만 입력 (Google 앱 비밀번호 16자리)")
        if settings.gmail_user and get_app_password(settings.gmail_user):
            self.pw_edit.setPlaceholderText("저장됨 — 변경 시에만 입력")
        self.recipient_edit = QLineEdit(settings.recipient)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 180)
        self.interval_spin.setValue(settings.interval_min)
        self.interval_spin.setSuffix(" 분")

        form = QFormLayout()
        form.addRow("Gmail 주소", self.gmail_edit)
        form.addRow("앱 비밀번호", self.pw_edit)
        form.addRow("수신 메일", self.recipient_edit)
        form.addRow("확인 간격", self.interval_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Gmail 2단계 인증 후 '앱 비밀번호'를 발급해 입력하세요."))
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        user = self.gmail_edit.text().strip()
        pw = self.pw_edit.text().strip()
        if user and pw:
            save_app_password(user, pw)
        self._settings = Settings(
            gmail_user=user,
            recipient=self.recipient_edit.text().strip(),
            interval_min=self.interval_spin.value(),
        )
        self.accept()

    def result_settings(self) -> Settings:
        return self._settings
```

- [ ] **Step 2: import 스모크 확인**

Run: `python -c "from cgvwatch.gui.settings_dialog import SettingsDialog; print('ok')"`
Expected: `ok` (import 오류 없음)

- [ ] **Step 3: 커밋**

```bash
git add cgvwatch/gui/__init__.py cgvwatch/gui/settings_dialog.py
git commit -m "feat: 설정 다이얼로그(SettingsDialog)"
```

---

### Task 10: 감시 추가 다이얼로그 (GUI)

**Files:**
- Create: `cgvwatch/gui/add_dialog.py`

**Interfaces:**
- Consumes: `theaters.get_regions`, `movies.get_movies`, `models.Watch`
- Produces:
  - `AddDialog(regions: list[dict], movies: list[dict], parent=None)`
  - `AddDialog.result_watch() -> Watch | None` — 지역→극장 연동 콤보, 영화 콤보, 날짜(QDateEdit)에서 `Watch` 생성(`id`는 uuid4 hex).

- [ ] **Step 1: 구현 작성**

`cgvwatch/gui/add_dialog.py`:
```python
"""감시 조건 추가 다이얼로그."""
from __future__ import annotations

import uuid

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QDateEdit, QDialogButtonBox, QVBoxLayout,
)

from cgvwatch.core.models import Watch


class AddDialog(QDialog):
    def __init__(self, regions: list[dict], movies: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("감시 추가")
        self._regions = regions
        self._movies = movies
        self._watch: Watch | None = None

        self.region_combo = QComboBox()
        for r in regions:
            self.region_combo.addItem(r["name"])
        self.region_combo.currentIndexChanged.connect(self._reload_sites)

        self.site_combo = QComboBox()
        self.movie_combo = QComboBox()
        for m in movies:
            self.movie_combo.addItem(m["mov_nm"], m["mov_no"])

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())

        form = QFormLayout()
        form.addRow("지역", self.region_combo)
        form.addRow("상영관", self.site_combo)
        form.addRow("영화", self.movie_combo)
        form.addRow("날짜", self.date_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._reload_sites()

    def _reload_sites(self) -> None:
        self.site_combo.clear()
        idx = self.region_combo.currentIndex()
        if 0 <= idx < len(self._regions):
            for s in self._regions[idx]["sites"]:
                self.site_combo.addItem(s["site_nm"], s["site_no"])

    def _on_accept(self) -> None:
        if self.site_combo.count() == 0 or self.movie_combo.count() == 0:
            self.reject()
            return
        self._watch = Watch(
            id=uuid.uuid4().hex,
            mov_no=self.movie_combo.currentData(),
            mov_nm=self.movie_combo.currentText(),
            site_no=self.site_combo.currentData(),
            site_nm=self.site_combo.currentText(),
            target_ymd=self.date_edit.date().toString("yyyyMMdd"),
        )
        self.accept()

    def result_watch(self) -> Watch | None:
        return self._watch
```

- [ ] **Step 2: import 스모크 확인**

Run: `python -c "from cgvwatch.gui.add_dialog import AddDialog; print('ok')"`
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add cgvwatch/gui/add_dialog.py
git commit -m "feat: 감시 추가 다이얼로그(AddDialog)"
```

---

### Task 11: 메인 윈도우 + 앱 진입점 (GUI)

**Files:**
- Create: `cgvwatch/gui/main_window.py`, `cgvwatch/app.py`, `README.md`

**Interfaces:**
- Consumes: 전 모듈. `Store`, `CGVClient`, `WatcherWorker`, `AddDialog`, `SettingsDialog`, `get_regions`, `get_movies`.
- Produces:
  - `MainWindow(store: Store, client: CGVClient)` — 테이블 + [추가][삭제][지금 확인][설정] 버튼, 워커 구동.
  - `app.main()` — QApplication 부팅.

- [ ] **Step 1: 메인 윈도우 구현**

`cgvwatch/gui/main_window.py`:
```python
"""메인 윈도우: 감시 목록 관리 + 워커 구동."""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout,
    QVBoxLayout, QWidget, QMessageBox, QHeaderView,
)

from cgvwatch.cgv.theaters import get_regions
from cgvwatch.cgv.movies import get_movies
from cgvwatch.core.models import Settings, Status, Watch
from cgvwatch.core.store import Store
from cgvwatch.core.watcher import WatcherWorker, check_watch
from cgvwatch.gui.add_dialog import AddDialog
from cgvwatch.gui.settings_dialog import SettingsDialog

HEADERS = ["영화", "상영관", "날짜", "상태", "마지막 확인"]


class MainWindow(QMainWindow):
    def __init__(self, store: Store, client) -> None:
        super().__init__()
        self.setWindowTitle("CGV 예매 오픈 알리미")
        self.resize(720, 400)
        self._store = store
        self._client = client
        self._settings, self._watches = store.load()

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        add_btn = QPushButton("추가")
        del_btn = QPushButton("삭제")
        check_btn = QPushButton("지금 확인")
        settings_btn = QPushButton("설정")
        add_btn.clicked.connect(self.on_add)
        del_btn.clicked.connect(self.on_delete)
        check_btn.clicked.connect(self.on_check_now)
        settings_btn.clicked.connect(self.on_settings)

        btn_row = QHBoxLayout()
        for b in (add_btn, del_btn, check_btn, settings_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(btn_row)
        layout.addWidget(self.table)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._refresh_table()
        self._start_worker()

    # --- 워커 상태 접근자 ---
    def _get_state(self):
        def set_watch(updated: Watch):
            for i, w in enumerate(self._watches):
                if w.id == updated.id:
                    self._watches[i] = updated
                    break
            self._store.save(self._settings, self._watches)
        return self._settings, self._watches, set_watch

    def _start_worker(self) -> None:
        self.worker = WatcherWorker(self._client, self._get_state)
        self.worker.updated.connect(self._on_worker_update)
        self.worker.start()

    def _on_worker_update(self, watch_id: str, status: str, last_checked: str) -> None:
        self._refresh_table()

    # --- 테이블 ---
    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._watches))
        for row, w in enumerate(self._watches):
            ymd = f"{w.target_ymd[:4]}-{w.target_ymd[4:6]}-{w.target_ymd[6:8]}"
            values = [w.mov_nm, w.site_nm, ymd, w.status, w.last_checked]
            for col, val in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(val))

    # --- 버튼 핸들러 ---
    def on_add(self) -> None:
        try:
            regions = get_regions(self._client)
            movies = get_movies(self._client)
        except Exception as exc:
            QMessageBox.warning(self, "오류", f"CGV 목록을 불러오지 못했습니다:\n{exc}")
            return
        dlg = AddDialog(regions, movies, self)
        if dlg.exec() and dlg.result_watch():
            self._watches.append(dlg.result_watch())
            self._store.save(self._settings, self._watches)
            self._refresh_table()

    def on_delete(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._watches):
            del self._watches[row]
            self._store.save(self._settings, self._watches)
            self._refresh_table()

    def on_check_now(self) -> None:
        _, watches, set_watch = self._get_state()
        for w in list(watches):
            set_watch(check_watch(self._client, w, self._settings))
        self._refresh_table()

    def on_settings(self) -> None:
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec():
            self._settings = dlg.result_settings()
            self._store.save(self._settings, self._watches)

    def closeEvent(self, event) -> None:
        if hasattr(self, "worker"):
            self.worker.stop()
            self.worker.wait(2000)
        super().closeEvent(event)
```

- [ ] **Step 2: 앱 진입점 작성**

`cgvwatch/app.py`:
```python
"""CGV 예매 오픈 알리미 진입점."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from cgvwatch.cgv.client import CGVClient
from cgvwatch.core.store import Store
from cgvwatch.gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow(Store(), CGVClient())
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: import 스모크 확인**

Run: `python -c "from cgvwatch.gui.main_window import MainWindow; from cgvwatch import app; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 전체 테스트 재확인**

Run: `python -m pytest -v`
Expected: 모든 테스트 PASS

- [ ] **Step 5: README 작성**

`README.md`:
```markdown
# CGV 예매 오픈 알리미

지정한 (상영관·날짜·영화)의 CGV 예매가 열리면 이메일로 알려주는 Windows 데스크톱 앱.

## 설치
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 실행
```
python -m cgvwatch.app
```

## 사용
1. [설정]에서 Gmail 주소·앱 비밀번호(2단계 인증 후 발급)·수신 메일·확인 간격 입력
2. [추가]로 지역→상영관, 영화, 날짜 선택
3. 창을 켜두면 설정한 간격마다 자동 확인, 예매가 열리면 메일 발송

## 주의
- 예매 오픈을 **알림**만 하는 도구입니다. 자동 예매/결제 기능은 없습니다.
- CGV 공개 조회 API를 예의 있게(기본 5분 간격) 사용합니다.
```

- [ ] **Step 6: 수동 스모크 실행 (선택, 사람 확인)**

Run: `python -m cgvwatch.app`
Expected: 창이 뜨고, [추가] 클릭 시 지역·상영관·영화 콤보가 실제 CGV 데이터로 채워짐. [지금 확인] 시 상태가 갱신됨.

- [ ] **Step 7: 커밋**

```bash
git add cgvwatch/gui/main_window.py cgvwatch/app.py README.md
git commit -m "feat: 메인 윈도우 + 앱 진입점 + README"
```

---

## Self-Review

**Spec coverage:**
- 감지(시나리오 A) → Task 4(get_open_dates) + Task 5(evaluate) + Task 8(check_watch) ✓
- PyQt6 GUI(목록/추가/설정) → Task 9,10,11 ✓
- Gmail SMTP + 앱 비밀번호 keyring → Task 7 ✓
- JSON API + requests (Playwright/BS4 없음) → Task 1~4 ✓
- 로컬 JSON 저장 → Task 6 ✓
- 폴링 기본 5분 → Settings.interval_min 기본 5 (Task 5), 워커 대기 루프(Task 8) ✓
- 에러 처리(크래시 없이 상태 ERROR) → Task 8 check_watch, Task 11 on_add try/except ✓
- 중복 메일 방지(was_open) → Task 5 evaluate, Task 8 ✓

**Placeholder scan:** 각 단계에 실제 코드/명령/기대출력 포함. 플레이스홀더 없음.

**Type consistency:** `Watch`/`Settings` 필드, `get_open_dates(client, site_no, mov_no)`, `check_watch(...)`, `send_open_mail(watch, settings, smtp_factory)`, `get_regions`/`get_movies` 반환 형태가 태스크 간 일치.

## 실행 참고

- GUI 태스크(9~11)는 순수 로직이 아니라 pytest strict TDD 대신 **import 스모크 + 수동 실행 확인**으로 검증한다(핵심 로직은 Task 1~8에서 이미 TDD 커버).
- Windows에서 `keyring`은 자격 증명 관리자를 자동 사용한다(추가 설정 불필요).
