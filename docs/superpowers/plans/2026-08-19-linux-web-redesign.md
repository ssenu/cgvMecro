# cgvwatch 리눅스 웹 버전 (Rpi + Docker) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PyQt6 GUI 앱을 FastAPI 웹 앱으로 개편해 Raspberry Pi의 Docker 컨테이너에서 24시간 상시 구동하고, 예매 오픈 시 디스코드 웹훅으로 알린다.

**Architecture:** 단일 컨테이너·단일 프로세스. FastAPI가 정적 HTML 한 장과 JSON API를 서빙하고, lifespan에서 시작한 백그라운드 스레드가 기존 순수 함수 `check_watch()` 루프를 돌린다. 상태는 메모리(락 보호) + `/data/config.json` 볼륨에 영속화. 알림은 `DISCORD_WEBHOOK_URL` 환경변수의 웹훅으로 POST.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, requests, pytest. (PyQt6·keyring 제거)

## Global Constraints

- 알림은 디스코드 웹훅만. 이메일/keyring 코드는 전부 제거한다.
- 웹 UI는 LAN 전용, 인증 없음.
- 데이터 경로는 환경변수 `CGVWATCH_DATA`(기본: `~/.cgv-watcher`) 하위 `config.json`.
- 감시 루프의 방어 로직 유지: 항목별 예외 무시, 알림 실패 시 `was_open=False` 유지(다음 주기 재시도).
- 상태 문자열은 기존 그대로: `대기중` / `열림` / `오류` (`core/models.py`의 `Status`).
- 다크 테마 팔레트는 `gui/theme.py`의 hex 값을 그대로 CSS로 옮긴다: BG_BASE `#17130F`, BG_SURFACE `#211B16`, BG_ELEVATED `#2C241D`, LINE `#3A2F27`, TEXT `#F4EEE4`, TEXT_MUTED `#A99C8D`, ACCENT `#E23744`, ACCENT_HOVER `#F04654`, GOLD `#F5B841`.
- 테스트 실행 명령: `python -m pytest tests/ -v` (저장소 루트에서).
- 커밋 메시지는 기존 관례(한국어, `feat:`/`fix:`/`docs:`/`build:` 접두)로 쓴다.

---

### Task 1: Settings 모델에서 이메일 필드 제거

**Files:**
- Modify: `cgvwatch/core/models.py`
- Modify: `tests/test_store.py`

**Interfaces:**
- Produces: `Settings(interval_min: int = 5)` — gmail_user/recipient 필드 없음. 이후 모든 태스크가 이 형태를 사용한다.

- [ ] **Step 1: test_store.py에서 gmail 필드 제거**

`tests/test_store.py`의 `test_save_then_load_roundtrip`에서 Settings 생성부를 수정:

```python
    settings = Settings(interval_min=10)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_store.py -v`
Expected: 아직 통과함(필드가 남아 있어도 동작) — 이 태스크는 삭제 리팩터링이므로 Step 3 후 전체 테스트로 검증한다.

- [ ] **Step 3: models.py에서 필드 삭제**

`cgvwatch/core/models.py`의 `Settings`를 다음으로 교체:

```python
@dataclass
class Settings:
    interval_min: int = 5
```

- [ ] **Step 4: 전체 테스트 실행**

Run: `python -m pytest tests/ -v`
Expected: `test_mailer.py`, `test_watcher.py` 일부가 gmail 필드 참조로 FAIL — 이는 Task 2·3에서 해소된다. `test_store.py`, `test_detect.py`, `test_client.py` 등은 PASS.
(주의: 이 시점의 실패는 예상된 중간 상태다. Task 3 종료 시 전체 GREEN이 된다.)

- [ ] **Step 5: Commit**

```bash
git add cgvwatch/core/models.py tests/test_store.py
git commit -m "refactor: Settings에서 이메일 필드 제거 (디스코드 전환 준비)"
```

---

### Task 2: 디스코드 웹훅 알림 모듈 신설, mailer 제거

**Files:**
- Create: `cgvwatch/notify/discord.py`
- Create: `tests/test_discord.py`
- Delete: `cgvwatch/notify/mailer.py`, `tests/test_mailer.py`

**Interfaces:**
- Consumes: `Watch` (core/models), `Settings` (Task 1 형태)
- Produces: `send_open_alert(watch: Watch, settings: Settings) -> None` (실패 시 예외), `build_message(watch: Watch) -> str`. Task 3의 watcher가 기본 알림 함수로 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_discord.py`:

```python
from unittest.mock import MagicMock

import pytest

import cgvwatch.notify.discord as discord
from cgvwatch.core.models import Settings, Watch


def _watch():
    return Watch(id="1", mov_no="30001192", mov_nm="스파이더맨-브랜드 뉴 데이",
                 site_no="0056", site_nm="강남", target_ymd="20260725")


def test_build_message_contains_key_fields():
    msg = discord.build_message(_watch())
    assert "스파이더맨-브랜드 뉴 데이" in msg
    assert "강남" in msg
    assert "07/25" in msg


def test_send_open_alert_posts_to_webhook(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    resp = MagicMock(status_code=204)
    post = MagicMock(return_value=resp)

    discord.send_open_alert(_watch(), Settings(), post=post)

    url = post.call_args[0][0]
    payload = post.call_args[1]["json"]
    assert url == "https://discord.test/hook"
    assert "스파이더맨-브랜드 뉴 데이" in payload["content"]


def test_send_open_alert_raises_without_webhook_url(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError):
        discord.send_open_alert(_watch(), Settings(), post=MagicMock())


def test_send_open_alert_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    resp = MagicMock()
    resp.raise_for_status.side_effect = RuntimeError("HTTP 400")
    post = MagicMock(return_value=resp)
    with pytest.raises(RuntimeError):
        discord.send_open_alert(_watch(), Settings(), post=post)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_discord.py -v`
Expected: FAIL — `ModuleNotFoundError: cgvwatch.notify.discord`

- [ ] **Step 3: 구현**

`cgvwatch/notify/discord.py`:

```python
"""디스코드 웹훅 알림. 웹훅 URL은 DISCORD_WEBHOOK_URL 환경변수로 주입한다."""
from __future__ import annotations

import os
from typing import Callable

import requests

from cgvwatch.core.models import Settings, Watch

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"


def build_message(watch: Watch) -> str:
    ymd = watch.target_ymd
    date = f"{ymd[4:6]}/{ymd[6:8]}"
    return (
        f"🎬 **{watch.mov_nm}**\n"
        f"{watch.site_nm} {date} 예매가 열렸습니다!\n"
        f"https://cgv.co.kr"
    )


def send_open_alert(
    watch: Watch,
    settings: Settings,
    post: Callable = requests.post,
) -> None:
    """예매 오픈 알림 발송. 미설정/HTTP 오류 시 예외를 던진다(호출부에서 재시도 처리)."""
    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if not url:
        raise RuntimeError(f"{WEBHOOK_ENV} 환경변수가 설정되지 않았습니다.")
    resp = post(url, json={"content": build_message(watch)}, timeout=10)
    resp.raise_for_status()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_discord.py -v`
Expected: 4 PASS

- [ ] **Step 5: mailer 삭제**

```bash
git rm cgvwatch/notify/mailer.py tests/test_mailer.py
```

- [ ] **Step 6: Commit**

```bash
git add cgvwatch/notify/discord.py tests/test_discord.py
git commit -m "feat: 디스코드 웹훅 알림 추가, 이메일(mailer/keyring) 제거"
```

---

### Task 3: watcher를 QThread → 표준 threading으로 교체

**Files:**
- Modify: `cgvwatch/core/watcher.py` (전면 재작성)
- Modify: `tests/test_watcher.py`

**Interfaces:**
- Consumes: `send_open_alert(watch, settings)` (Task 2), `check_watch` 기존 순수 로직, `get_open_dates(client, site_no, mov_no)`
- Produces:
  - `check_watch(client, watch: Watch, settings: Settings, notify: Callable = send_open_alert, now: str | None = None) -> Watch` (파라미터명 `send_mail` → `notify`)
  - `WatcherThread(client, get_state: Callable[[], tuple[Settings, list[Watch], Callable]], on_update: Callable[[Watch], None] | None = None)` — `threading.Thread` 서브클래스(daemon), `.stop()` 메서드. Task 5의 서버가 사용.

- [ ] **Step 1: 테스트를 새 인터페이스로 수정**

`tests/test_watcher.py` 전체를 다음으로 교체:

```python
from unittest.mock import MagicMock
from cgvwatch.core.models import Watch, Settings, Status
from cgvwatch.core.watcher import check_watch


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260729")
    base.update(kw)
    return Watch(**base)


def test_check_watch_notifies_and_marks_open(monkeypatch):
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})
    notify = MagicMock()

    result = check_watch(MagicMock(), _watch(), Settings(), notify=notify, now="2026-07-23 10:00")

    assert result.was_open is True
    assert result.status == Status.OPEN
    assert result.last_checked == "2026-07-23 10:00"
    notify.assert_called_once()


def test_check_watch_waiting_when_not_open(monkeypatch):
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260801"})
    notify = MagicMock()

    result = check_watch(MagicMock(), _watch(), Settings(), notify=notify)

    assert result.was_open is False
    assert result.status == Status.WAITING
    notify.assert_not_called()


def test_check_watch_error_sets_error_status(monkeypatch):
    import cgvwatch.core.watcher as w
    def boom(c, s, m):
        raise RuntimeError("네트워크")
    monkeypatch.setattr(w, "get_open_dates", boom)

    result = check_watch(MagicMock(), _watch(), Settings(), notify=MagicMock())

    assert result.status == Status.ERROR


def test_check_watch_open_but_notify_fails_does_not_raise(monkeypatch):
    """열렸지만 알림 발송 실패 시 예외 전파 없이 ERROR, was_open 유지(재시도)."""
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "get_open_dates", lambda c, s, m: {"20260729"})

    def failing_notify(watch, settings):
        raise RuntimeError("웹훅 미설정")

    result = check_watch(MagicMock(), _watch(was_open=False), Settings(), notify=failing_notify)

    assert result.status == Status.ERROR
    assert result.was_open is False


def test_thread_run_once_survives_check_exception(monkeypatch):
    """워커 루프는 한 항목의 예외로 죽으면 안 된다."""
    import cgvwatch.core.watcher as w
    monkeypatch.setattr(w, "check_watch", MagicMock(side_effect=RuntimeError("불의의 오류")))

    def get_state():
        return Settings(interval_min=1), [_watch()], lambda updated: None

    thread = w.WatcherThread(MagicMock(), get_state)
    thread._run_once(*get_state())  # 예외 없이 반환되면 통과


def test_thread_stop_interrupts_wait():
    import cgvwatch.core.watcher as w
    thread = w.WatcherThread(MagicMock(), lambda: (Settings(), [], lambda u: None))
    thread.stop()
    assert thread._stop.is_set()
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_watcher.py -v`
Expected: FAIL — `notify` 키워드 없음 / `WatcherThread` 없음

- [ ] **Step 3: watcher.py 재작성**

`cgvwatch/core/watcher.py` 전체를 다음으로 교체:

```python
"""주기적 감시 워커. 순수 로직(check_watch)과 스레드 래퍼를 분리한다."""
from __future__ import annotations

import logging
import threading
from dataclasses import replace
from datetime import datetime
from typing import Callable, Optional

from cgvwatch.cgv.showtimes import get_open_dates
from cgvwatch.core.detect import evaluate
from cgvwatch.core.models import Settings, Status, Watch
from cgvwatch.notify.discord import send_open_alert

logger = logging.getLogger(__name__)


def check_watch(
    client,
    watch: Watch,
    settings: Settings,
    notify: Callable = send_open_alert,
    now: Optional[str] = None,
) -> Watch:
    now = now or datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        open_dates = get_open_dates(client, watch.site_no, watch.mov_no)
    except Exception:
        return replace(watch, status=Status.ERROR, last_checked=now)

    if evaluate(watch, open_dates):
        try:
            notify(watch, settings)
        except Exception:
            # 열렸지만 알림 실패(웹훅 미설정 등) → 앱을 죽이지 않는다.
            # was_open을 True로 올리지 않아 다음 주기에 재시도한다.
            logger.exception("알림 발송 실패: %s", watch.mov_nm)
            return replace(watch, status=Status.ERROR, last_checked=now)
        logger.info("예매 오픈 감지·알림 발송: %s %s %s", watch.mov_nm, watch.site_nm, watch.target_ymd)
        return replace(watch, was_open=True, status=Status.OPEN, last_checked=now)

    status = Status.OPEN if watch.was_open else Status.WAITING
    return replace(watch, status=status, last_checked=now)


class WatcherThread(threading.Thread):
    """백그라운드 감시 스레드. get_state()로 매 주기 최신 상태를 받아온다."""

    def __init__(
        self,
        client,
        get_state: Callable,  # () -> tuple[Settings, list[Watch], set_watch_fn]
        on_update: Optional[Callable[[Watch], None]] = None,
    ) -> None:
        super().__init__(daemon=True, name="cgvwatch-watcher")
        self._client = client
        self._get_state = get_state
        self._on_update = on_update
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _run_once(self, settings: Settings, watches: list, set_watch: Callable) -> None:
        """감시 목록 1회 순회. 어떤 항목의 예외도 스레드를 죽이지 않는다."""
        for watch in list(watches):
            if self._stop.is_set():
                break
            try:
                updated = check_watch(self._client, watch, settings)
                set_watch(updated)
                if self._on_update:
                    self._on_update(updated)
            except Exception:
                logger.exception("감시 항목 처리 실패: %s", getattr(watch, "id", "?"))
                continue

    def run(self) -> None:
        logger.info("감시 스레드 시작")
        while not self._stop.is_set():
            settings, watches, set_watch = self._get_state()
            self._run_once(settings, watches, set_watch)
            self._stop.wait(max(1, settings.interval_min) * 60)
        logger.info("감시 스레드 종료")
```

- [ ] **Step 4: 전체 테스트 실행 → 전부 통과 확인**

Run: `python -m pytest tests/ -v`
Expected: 전체 PASS (Task 1에서 실패하던 것들 해소)

- [ ] **Step 5: Commit**

```bash
git add cgvwatch/core/watcher.py tests/test_watcher.py
git commit -m "refactor: 감시 워커를 QThread에서 표준 threading으로 교체, 알림을 디스코드로 전환"
```

---

### Task 4: Store 기본 경로를 환경변수 기반으로

**Files:**
- Modify: `cgvwatch/core/store.py`
- Modify: `tests/test_store.py`

**Interfaces:**
- Produces: `default_path() -> Path` — `$CGVWATCH_DATA/config.json`, 미설정 시 `~/.cgv-watcher/config.json`. `Store()` 무인자 생성 시 이 경로 사용.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_store.py` 끝에 추가:

```python
def test_default_path_uses_env_var(monkeypatch, tmp_path):
    from cgvwatch.core.store import default_path
    monkeypatch.setenv("CGVWATCH_DATA", str(tmp_path))
    assert default_path() == tmp_path / "config.json"


def test_default_path_falls_back_to_home(monkeypatch):
    from cgvwatch.core.store import default_path
    monkeypatch.delenv("CGVWATCH_DATA", raising=False)
    from pathlib import Path
    assert default_path() == Path.home() / ".cgv-watcher" / "config.json"
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `default_path` 없음

- [ ] **Step 3: store.py 수정**

`cgvwatch/core/store.py`에서 `DEFAULT_PATH` 상수를 함수로 교체:

```python
"""설정·감시목록의 로컬 JSON 영속화."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from .models import Settings, Watch


def default_path() -> Path:
    base = os.environ.get("CGVWATCH_DATA", "").strip()
    root = Path(base) if base else Path.home() / ".cgv-watcher"
    return root / "config.json"


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else default_path()

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

주의: 기존 사용자 config.json에 `settings.gmail_user`가 남아 있으면 `Settings(**raw…)`가 TypeError를 낸다. `load()`의 settings 파싱을 방어적으로 바꾼다:

```python
        known = {k: v for k, v in raw.get("settings", {}).items() if k in {"interval_min"}}
        settings = Settings(**known)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_store.py -v`
Expected: 전부 PASS

- [ ] **Step 5: Commit**

```bash
git add cgvwatch/core/store.py tests/test_store.py
git commit -m "feat: 데이터 경로를 CGVWATCH_DATA 환경변수로 지정 가능하게 변경"
```

---

### Task 5: FastAPI 서버 (API + 감시 스레드 통합)

**Files:**
- Create: `cgvwatch/web/__init__.py` (빈 파일)
- Create: `cgvwatch/web/server.py`
- Create: `tests/test_server.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `Store` (Task 4), `WatcherThread`/`check_watch` (Task 3), `CGVClient`, `get_movies(client)`, `get_regions(client)`
- Produces: `create_app(store: Store | None = None, client: CGVClient | None = None, start_watcher: bool = True) -> FastAPI`. Task 6의 HTML이 아래 API를 호출, Task 7의 run.py가 `create_app()` 사용.
  - `GET /api/watches` → `[{id, mov_no, mov_nm, site_no, site_nm, target_ymd, status, was_open, last_checked}]`
  - `POST /api/watches` body `{mov_no, mov_nm, site_no, site_nm, target_ymd}` → 생성된 watch (201)
  - `DELETE /api/watches/{id}` → 204
  - `GET /api/movies` → `[{mov_no, mov_nm}]`
  - `GET /api/theaters` → `[{name, sites: [{site_no, site_nm}]}]`
  - `GET /api/settings` / `PUT /api/settings` body `{interval_min}` → `{interval_min}`
  - `GET /healthz` → `{"status": "ok"}`
  - `GET /` → `web/static/index.html`

- [ ] **Step 1: requirements.txt 갱신**

`requirements.txt` 전체를 다음으로 교체:

```
fastapi>=0.110
uvicorn>=0.29
requests>=2.31
```

설치: `pip install -r requirements.txt`

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_server.py`:

```python
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from cgvwatch.core.models import Settings, Status, Watch
from cgvwatch.core.store import Store
from cgvwatch.web.server import create_app


@pytest.fixture()
def api(tmp_path):
    store = Store(tmp_path / "config.json")
    client = MagicMock()
    app = create_app(store=store, client=client, start_watcher=False)
    return TestClient(app), store, client


def test_healthz(api):
    tc, _, _ = api
    assert tc.get("/healthz").json() == {"status": "ok"}


def test_add_list_delete_watch(api):
    tc, store, _ = api
    body = {"mov_no": "30001192", "mov_nm": "스파이더맨", "site_no": "0056",
            "site_nm": "강남", "target_ymd": "20260729"}

    created = tc.post("/api/watches", json=body)
    assert created.status_code == 201
    wid = created.json()["id"]
    assert created.json()["status"] == Status.WAITING

    listed = tc.get("/api/watches").json()
    assert len(listed) == 1 and listed[0]["id"] == wid

    # 영속화 확인
    _, saved = store.load()
    assert saved[0].mov_nm == "스파이더맨"

    assert tc.delete(f"/api/watches/{wid}").status_code == 204
    assert tc.get("/api/watches").json() == []


def test_delete_unknown_watch_404(api):
    tc, _, _ = api
    assert tc.delete("/api/watches/nope").status_code == 404


def test_settings_roundtrip(api):
    tc, store, _ = api
    assert tc.get("/api/settings").json() == {"interval_min": 5}
    assert tc.put("/api/settings", json={"interval_min": 10}).json() == {"interval_min": 10}
    settings, _ = store.load()
    assert settings.interval_min == 10


def test_movies_proxies_cgv(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "get_movies", lambda c: [{"mov_no": "1", "mov_nm": "영화"}])
    assert tc.get("/api/movies").json() == [{"mov_no": "1", "mov_nm": "영화"}]


def test_theaters_proxies_cgv(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    monkeypatch.setattr(srv, "get_regions",
                        lambda c: [{"name": "서울", "sites": [{"site_no": "0056", "site_nm": "강남"}]}])
    assert tc.get("/api/theaters").json()[0]["name"] == "서울"


def test_cgv_error_returns_502(api, monkeypatch):
    tc, _, _ = api
    import cgvwatch.web.server as srv
    from cgvwatch.cgv.client import CGVError
    def boom(c):
        raise CGVError("down")
    monkeypatch.setattr(srv, "get_movies", boom)
    assert tc.get("/api/movies").status_code == 502
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL — `cgvwatch.web.server` 없음

- [ ] **Step 4: 구현**

`cgvwatch/web/__init__.py`: 빈 파일 생성.

`cgvwatch/web/server.py`:

```python
"""FastAPI 웹 서버: JSON API + 정적 UI + 백그라운드 감시 스레드."""
from __future__ import annotations

import logging
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from cgvwatch.cgv.client import CGVClient, CGVError
from cgvwatch.cgv.movies import get_movies
from cgvwatch.cgv.theaters import get_regions
from cgvwatch.core.models import Settings, Watch
from cgvwatch.core.store import Store
from cgvwatch.core.watcher import WatcherThread

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


class WatchIn(BaseModel):
    mov_no: str
    mov_nm: str
    site_no: str
    site_nm: str
    target_ymd: str = Field(pattern=r"^\d{8}$")


class SettingsIn(BaseModel):
    interval_min: int = Field(ge=1, le=1440)


class AppState:
    """메모리 상태 + 영속화. 감시 스레드와 API 핸들러가 락으로 공유한다."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.lock = threading.Lock()
        self.settings, self.watches = store.load()

    def get_state(self):
        with self.lock:
            return self.settings, list(self.watches), self.set_watch

    def set_watch(self, updated: Watch) -> None:
        with self.lock:
            self.watches = [updated if w.id == updated.id else w for w in self.watches]
            self.store.save(self.settings, self.watches)

    def add_watch(self, watch: Watch) -> None:
        with self.lock:
            self.watches.append(watch)
            self.store.save(self.settings, self.watches)

    def remove_watch(self, watch_id: str) -> bool:
        with self.lock:
            before = len(self.watches)
            self.watches = [w for w in self.watches if w.id != watch_id]
            if len(self.watches) == before:
                return False
            self.store.save(self.settings, self.watches)
            return True

    def update_settings(self, interval_min: int) -> Settings:
        with self.lock:
            self.settings = Settings(interval_min=interval_min)
            self.store.save(self.settings, self.watches)
            return self.settings


def create_app(
    store: Optional[Store] = None,
    client: Optional[CGVClient] = None,
    start_watcher: bool = True,
) -> FastAPI:
    store = store or Store()
    client = client or CGVClient()
    state = AppState(store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        watcher = None
        if start_watcher:
            watcher = WatcherThread(client, state.get_state)
            watcher.start()
        yield
        if watcher:
            watcher.stop()

    app = FastAPI(title="CGV 예매 오픈 알리미", lifespan=lifespan)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/watches")
    def list_watches():
        with state.lock:
            return [asdict(w) for w in state.watches]

    @app.post("/api/watches", status_code=201)
    def add_watch(body: WatchIn):
        watch = Watch(id=uuid.uuid4().hex[:8], **body.model_dump())
        state.add_watch(watch)
        return asdict(watch)

    @app.delete("/api/watches/{watch_id}", status_code=204)
    def delete_watch(watch_id: str):
        if not state.remove_watch(watch_id):
            raise HTTPException(404, "해당 감시 항목이 없습니다.")

    @app.get("/api/settings")
    def get_settings():
        with state.lock:
            return asdict(state.settings)

    @app.put("/api/settings")
    def put_settings(body: SettingsIn):
        return asdict(state.update_settings(body.interval_min))

    @app.get("/api/movies")
    def movies():
        try:
            return get_movies(client)
        except CGVError as exc:
            raise HTTPException(502, str(exc))

    @app.get("/api/theaters")
    def theaters():
        try:
            return get_regions(client)
        except CGVError as exc:
            raise HTTPException(502, str(exc))

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_server.py -v` 이어서 `python -m pytest tests/ -v`
Expected: 전부 PASS
(참고: TestClient 사용에 `httpx` 필요 — `pip install httpx` 후 `requirements-dev.txt`에 `httpx>=0.27` 추가)

- [ ] **Step 6: Commit**

```bash
git add cgvwatch/web/ tests/test_server.py requirements.txt requirements-dev.txt
git commit -m "feat: FastAPI 웹 서버 추가 (감시 API·설정 API·헬스체크·감시 스레드 통합)"
```

---

### Task 6: 웹 UI (index.html 한 장, 다크 테마)

**Files:**
- Create: `cgvwatch/web/static/index.html`

**Interfaces:**
- Consumes: Task 5의 모든 `/api/*` 엔드포인트

- [ ] **Step 1: index.html 작성**

`cgvwatch/web/static/index.html` — 아래 요구사항으로 작성 (HTML+CSS+JS 단일 파일, 외부 리소스 없음):

- `<html lang="ko">`, `<title>CGV 예매 오픈 알리미</title>`
- CSS 변수로 Global Constraints의 팔레트 hex를 정의하고 전체에 적용. 시스템 한글 폰트 스택: `"Malgun Gothic", "Apple SD Gothic Neo", sans-serif`
- 레이아웃: 상단 헤더(제목 + 감시 주기 표시·수정), 본문에 감시 목록 테이블, 하단에 "감시 추가" 폼
- 감시 목록 테이블 컬럼: 영화 / 극장 / 날짜 / 상태 / 마지막 확인 / 삭제 버튼
  - 상태 뱃지 색: 대기중 `#2E3A44`배경·`#9FB3C4`글자, 열림 `#4A3A16`배경·`#F5B841`글자, 오류 `#4A2420`배경·`#F0857C`글자 (기존 STATUS_COLORS와 동일)
- 감시 추가 폼: ① `GET /api/movies`로 채우는 영화 `<select>` ② `GET /api/theaters`로 채우는 지역별 `<optgroup>` 극장 `<select>` ③ `<input type="date">` (min=오늘) ④ 추가 버튼 → `POST /api/watches` (date 값 `YYYY-MM-DD` → `YYYYMMDD` 변환)
- 설정: 헤더의 주기 숫자 클릭 시 `<input type="number" min="1">`로 변경, blur/Enter에 `PUT /api/settings`
- `setInterval(loadWatches, 5000)`으로 `GET /api/watches` 폴링해 테이블 갱신
- 오류 처리: fetch 실패·502 시 헤더 아래 경고 배너 표시(닫기 가능)
- JS는 프레임워크 없이 `fetch` + DOM API만 사용

- [ ] **Step 2: 수동 스모크 테스트**

Run: `uvicorn --factory cgvwatch.web.server:create_app --port 8080` 후 브라우저(또는 `curl http://localhost:8080/`)로 확인
Expected: HTML 200 응답, `/api/watches` 빈 배열, 페이지에 빈 목록 렌더
(참고: `--factory`는 `create_app`을 호출해 앱을 만든다. CGV API 접근이 없는 환경이면 영화/극장 select가 비고 배너가 뜨는 것까지가 정상)

- [ ] **Step 3: Commit**

```bash
git add cgvwatch/web/static/index.html
git commit -m "feat: 웹 UI 추가 ('어두운 상영관' 다크 테마, 감시 목록·추가·설정)"
```

---

### Task 7: 진입점 교체 및 PyQt 잔재 제거

**Files:**
- Modify: `run.py` (전면 재작성)
- Modify: `cgvwatch/app.py` 삭제
- Delete: `cgvwatch/gui/` 전체, `cgv_notifier.spec`, `build/`, `dist/`, `=6.6`
- Modify: `requirements-dev.txt`, `README.md`

**Interfaces:**
- Consumes: `create_app` (Task 5)
- Produces: `python run.py`로 서버 기동 (호스트 `0.0.0.0`, 포트 `PORT` 환경변수, 기본 8080). Task 8의 Dockerfile이 사용.

- [ ] **Step 1: run.py 재작성**

```python
"""CGV 예매 오픈 알리미 — 웹 서버 진입점."""
from __future__ import annotations

import logging
import os

import uvicorn

from cgvwatch.web.server import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: PyQt 잔재 삭제**

```bash
git rm -r cgvwatch/gui cgvwatch/app.py cgv_notifier.spec
git rm -r --cached build dist 2>/dev/null; rm -rf build dist "=6.6"
```

`requirements-dev.txt`를 다음으로 교체:

```
pytest>=8.0
pytest-mock>=3.12
httpx>=0.27
```

- [ ] **Step 3: PyQt import가 남았는지 전수 확인**

Run: `grep -rn "PyQt6\|keyring\|pyinstaller" cgvwatch/ tests/ run.py requirements*.txt`
Expected: 매치 없음

- [ ] **Step 4: 전체 테스트 실행**

Run: `python -m pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 5: README 갱신**

`README.md`를 웹 버전 기준으로 재작성: 프로젝트 소개(무엇을 감시하고 어떻게 알리는지), 요구사항(Docker), 빠른 시작(Task 8의 compose 절차 참조), 개발자용 로컬 실행(`pip install -r requirements.txt -r requirements-dev.txt`, `python run.py`, `python -m pytest tests/`), 환경변수 표(`DISCORD_WEBHOOK_URL`, `CGVWATCH_DATA`, `PORT`, `TZ`). 기존 스크린샷 중 PyQt GUI 이미지는 제거.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: PyQt GUI 제거, 웹 서버 진입점으로 교체"
```

---

### Task 8: Docker 패키징 및 배포 문서

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.dockerignore`
- Modify: `.gitignore` (없으면 생성)

**Interfaces:**
- Consumes: `run.py` (Task 7), `/healthz` (Task 5)
- Produces: `docker compose up -d --build`로 Rpi에서 상시 구동되는 컨테이너

- [ ] **Step 1: Dockerfile 작성**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cgvwatch/ cgvwatch/
COPY run.py .

ENV CGVWATCH_DATA=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"

CMD ["python", "run.py"]
```

- [ ] **Step 2: docker-compose.yml 작성**

```yaml
services:
  cgvwatch:
    build: .
    container_name: cgvwatch
    restart: unless-stopped
    ports:
      - "8080:8080"
    env_file: .env
    environment:
      TZ: Asia/Seoul
    volumes:
      - ./data:/data
```

- [ ] **Step 3: 부속 파일 작성**

`.env.example`:

```
# 디스코드 채널 설정 → 연동 → 웹후크에서 발급한 URL
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

`.dockerignore`:

```
.git
docs
tests
data
.env
__pycache__
*.pyc
```

`.gitignore`에 추가(없으면 생성):

```
.env
data/
__pycache__/
*.pyc
```

- [ ] **Step 4: 로컬(Windows) 도커 스모크 테스트**

Run: `cp .env.example .env && docker compose up -d --build && sleep 5 && curl -s http://localhost:8080/healthz && docker compose ps`
Expected: `{"status":"ok"}`, 컨테이너 상태 `Up ... (healthy)` (healthy 표시는 최초 60초 후)
확인 후: `docker compose down`

- [ ] **Step 5: README에 Rpi 배포 절차 추가**

README의 "빠른 시작" 절에 다음 절차를 기재:

```bash
# Raspberry Pi에서
git clone https://github.com/ssenu/cgvMecro.git && cd cgvMecro
cp .env.example .env && nano .env   # DISCORD_WEBHOOK_URL 기입
docker compose up -d --build
# 접속: http://<Pi주소>:8080  /  로그: docker logs -f cgvwatch
# 업데이트: git pull && docker compose up -d --build
```

- [ ] **Step 6: Commit & Push**

```bash
git add Dockerfile docker-compose.yml .env.example .dockerignore .gitignore README.md
git commit -m "build: Docker 패키징 추가 (compose, 헬스체크, 자동 재시작, Rpi 배포 문서)"
git push
```
