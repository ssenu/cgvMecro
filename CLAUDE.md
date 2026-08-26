# CLAUDE.md — 유지보수 매뉴얼

이 문서는 **다음 세션의 코딩 에이전트**를 위한 것이다. 파일 목록이나 함수 시그니처는
싣지 않는다 — 코드를 읽으면 알 수 있고, 여기 적으면 금방 낡아서 거짓말을 하게 된다.
대신 코드만 읽어서는 알 수 없는 것 — **외부 세계(CGV)에 대한 관찰, 그 관찰의 날짜,
안전선이 왜 있는지, 깨졌을 때 무엇을 확인해야 하는지, 이미 시도했다가 버린 것** — 을 담는다.

**규칙: 외부 세계에 대한 사실에는 항상 `(확인: YYYY-MM-DD)`를 붙인다.** CGV는 예고 없이
화면과 API를 바꾼다. 날짜 없는 관찰은 신뢰할 수 없는 관찰이다.

## 이 프로젝트가 무엇이고, 무엇을 하지 않는지

CGV 예매 오픈·취소표를 감시해 Discord로 알리고, 원하면 로그인된 크롬을 직접 조종해
좌석 선택까지 자동으로 마친다. 노트북에서 `python run.py`로 실행하는 단일 프로세스다
(Raspberry Pi/Docker 운영은 2026-08-26에 중단했다 — 실제 크롬을 띄워야 해서 컨테이너에
맞지 않는다).

**하지 않는 것 (안전선)** — 코드에도 상수/구조로 박혀 있지만, 이유는 코드에 없으므로 여기 적는다.

- **자동 로그인을 만들지 않는다.** 계정 정보(아이디/비밀번호)를 코드·설정·로그 어디에도
  저장하거나 다루지 않는다. 로그인은 사람이 뜬 크롬 창에서 직접 한다. 이 선을 넘으면
  계정 탈취/차단 위험을 프로그램이 직접 떠안게 된다.
- **결제를 자동화하지 않는다.** 결제 페이지 도달 즉시 모든 자동 동작을 멈춘다. 결제는
  금전이 오가는 동작이라 사람의 최종 확인 없이는 절대 진행하지 않는다.
- **좌석 폴링 간격 하한 1초.** 이보다 짧게 하지 않는다. CGV가 429(과도한 요청)를 반환하기
  시작하면 계정/IP가 차단될 위험이 있다.
- **동시 헌팅 1개.** 여러 헌팅을 동시에 돌리면 요청량이 늘어 차단 위험이 커진다.
- **좌석 확보 후 추가 시도 중단.** 이미 잡은 좌석 위에 또 시도하면 중복 선점·꼬임이 생긴다.

이 안전선을 코드에서 완화하는 변경(폴링 주기를 낮추거나, 자동 로그인/결제를 추가하는 등)은
**절대 사람의 명시적 지시 없이 하지 않는다.**

## CGV API 관찰 기록

설계 문서 `docs/superpowers/specs/2026-08-26-seat-hunter-design.md`의 "CGV API 관찰 기록"
절을 옮긴 것이다. 감시·헌팅이 오류를 내면 여기부터 확인한다.

**공통 (확인: 2026-08-26)**
- Base URL: `https://cgv.co.kr/api/v1/booking/`
- 모든 요청에 `coCd=A420` 필요
- **`Referer: https://cgv.co.kr/` 헤더가 없으면 일부 엔드포인트가 403을 반환한다**
  (`searchSiteScnscYmdListByMov`에서 실제로 겪었다. 2026-08-19 수정). CGV API는 반드시
  `CGVClient`를 통해 호출한다 — 이 헤더가 거기 있다. 새로 `requests.get`을 직접 쓰지 않는다.
- 응답은 `statusCode`가 0이면 성공, `data`에 본문. 단 `searchIfSeatData`는 형식이 다르다(아래).
- 과도한 폴링 시 429가 반환된다.

**엔드포인트 (확인: 2026-08-26)**

| 엔드포인트 | 파라미터 | 반환 |
|---|---|---|
| `searchAtktTopPostrList` | `movNm=&div=&attrCd=` | 상영예정작 목록 (`movNo`, `movNm`) |
| `searchRegnList` | 없음 | 지역별 극장 (`regnGrpNm`, `siteList[].siteNo/siteNm`) |
| `searchSiteScnscYmdListByMov` | `siteNo`, `movNo` | 예매 오픈된 날짜 목록 (`scnYmd`) |
| `searchSchByMov` | `siteNo`, `movNo`, `scnYmd`, `rtctlScopCd=08` | 회차 목록 |
| `searchIfSeatData` | `siteNo`, `scnYmd`, `scnsNo`, `scnSseq`, `seatAreaNo=001`, `cusgdCd=01` | 좌석 지도 전체 |

**회차 (`searchSchByMov`) 주요 필드 (확인: 2026-08-26)**
- `scnsNo` (상영관 번호, 예 `"003"`), `scnSseq` (회차 순번, 예 `"2"`) — 좌석 조회에 필요
- `scnsNm` (관 이름, 예 `"3관 (Laser)"`, `"IMAX관"`) — 관 필터 판정에 사용
- `scnsrtTm` (시작 시각 `"1230"`), `frSeatCnt` (잔여석), `stcnt` (총 좌석)

**좌석 지도 (`searchIfSeatData`) — 로그인 불필요 (확인: 2026-08-26, 실제 CGV API로 검증)**
- 최상위에 `resultCode`, `items[]`. `items[0].seats[]`에 좌석 전체가 들어있다.
- 좌석 필드:
  - `seatRowNm` (행, `"A"`~), `seatNo` (번호, `"12"`), `seatLocNo` (고유 ID)
  - `seatStusCd`: `"00"` 빈자리 / `"01"` 판매완료 / `"04"` 선점중(결제 진행)
  - `seatSaleYn`: `"Y"`면 판매 가능
  - `xcoordStartVal`, `ycoordStartVal`: 좌표 문자열(`"0023"` 등)
- **좌표 규칙**: 같은 행은 `ycoordStartVal`이 같고, 옆자리는 `xcoordStartVal`이 2 차이난다.
  통로가 있으면 간격이 더 벌어진다. → **2인 연석 판정을 DOM 없이 좌표만으로** 할 수 있다
  (`cgvwatch/core/seatpick.py`).
- 검증 예 (2026-08-26, 강남 3관): 172석 중 빈자리 158, 행 A~M.
- 이 API는 **로그인 세션 없이도** 전체 좌석 상태·좌표를 정상 반환한다. 로그인이 필요한 것은
  실제 좌석을 클릭해 확보하는 동작(Playwright로 화면을 조작하는 부분)뿐이다.

**예매 화면 회차 버튼 (확인: 2026-08-26)**
- 셀렉터: `button.screenInfo_timeLink__45VfR`
- 버튼 텍스트 예: `"15:40-18:15 47/123석 2관 (Laser)"`
- **로그아웃 상태에서 회차 버튼을 누르면** `.cgv-modal.active`에 "로그인이 필요한" 문구가 든
  모달이 뜬다. 모달 버튼은 취소/확인.

**로그인 상태 판정 (확인: 2026-08-26)**
- CGV 첫 화면(`https://cgv.co.kr/`)에서, 로그아웃 상태일 때 정확히 텍스트가 "로그인"인
  요소가 하나 있다 — `button.cgv-footer-link`. 로그인 상태에서는 "로그아웃"이라는 텍스트는
  **아예 나타나지 않는다.** 그래서 판정은 "로그아웃 문구가 있는지"가 아니라
  "'로그인' 문구가 사라졌는지"로 한다 (`BrowserManager.is_logged_in`).

**예매 페이지 / DOM 관찰 기록 (확인: 2026-08-23, hunterH.js 기준 — 아직 재확인 필요, 아래 "미해결 항목" 참고)**
- 예매 페이지: `https://cgv.co.kr/cnm/movieBook/movie?movNo=&scnYmd=&siteNo=&siteNm=`
  (영화·날짜·극장이 미리 선택된 상태로 열린다)
- 좌석 페이지: `/cnm/selectVisitorCnt` — 인원 선택과 좌석 선택이 한 화면에 있다
- 셀렉터 (자동 생성 클래스명이 섞여 있어 CGV 배포 시 깨질 수 있음):
  - 인원 선택 박스: `div.numberChoice_NumberWrap__JKTv1`
  - 인원 버튼: `button[aria-label="1 선택"]` / `"2 선택"` (`aria-pressed="true"`면 선택됨)
  - 좌석 버튼: `button[data-seatlocno]` — 텍스트가 좌석명(`"H12"`), `disabled`면 선택 불가
  - 모달: `.cgv-modal.active` — 안의 `확인|닫기` 버튼으로 닫는다
  - 휠체어석 경고: 모달 텍스트에 `휠체어|장애인` 포함 → 그 좌석은 세션 동안 블랙리스트
  - 좌석 확보 완료 신호: 본문에 `선택하신 좌석` 문구
  - 다음 단계 버튼: 텍스트가 `선택완료`인 `button` (공백 제거 후 비교)
- 결제 페이지 도달 판정: `location.pathname`이 `/cnm/selectVisitorCnt`가 아니게 되는 순간

**미해결 항목: 좌석 페이지는 로그인 없이 접근할 수 없다.** 위 좌석 페이지 셀렉터들
(`button[data-seatlocno]`, `div.numberChoice_NumberWrap__JKTv1`, `선택완료` 등)은
2026-08-23 관찰값 그대로 남아 있고, 이후 자동으로 재확인하지 못했다. **사람이 CGV에
로그인하고 실제로 좌석 화면까지 들어가야 재확인할 수 있는 대화형 단계**다. 다음 세션에서
좌석 확보가 이상하게 동작하면 가장 먼저 의심할 곳이 여기다. 재확인 절차는 아래
"깨졌을 때 진단 절차"를 따른다.

## 깨졌을 때 진단 절차

**감시가 오류 상태로 표시될 때**
1. Docker를 쓰지 않으므로 `docker logs` 대신 `uv run python run.py`를 띄운 콘솔의 로그를
   본다 (`%(asctime)s %(levelname)s %(name)s: %(message)s` 형식).
2. `CGV 조회 실패` 로그를 찾는다.
3. HTTP 상태코드를 확인한다.
   - **403**이면 `Referer: https://cgv.co.kr/` 헤더가 살아있는지 `cgvwatch/cgv/client.py`의
     `CGVClient`를 확인한다. CGV가 헤더 검증 방식을 바꿨을 수 있다.
   - **429**면 폴링 간격이 실제로 지켜지고 있는지, 백오프가 동작하는지 확인한다. 간격을
     더 줄이는 방향으로 "고치지" 않는다 (안전선 참고).
   - 그 외 코드/응답 형식 변경이면 CGV API 관찰 기록(위 절)의 파라미터·필드명이 아직
     맞는지 실제 요청으로 확인하고, 바뀐 부분을 이 문서와 코드에 함께 반영한다.

**좌석을 못 잡을 때 / "⚠️ 화면 구조 변경 의심" 알림이 왔을 때**
1. `cgvwatch/hunt/selectors.py`를 열어 문제된 셀렉터의 확인 날짜를 본다. 오래됐으면
   1순위 용의자다.
2. Playwright로 직접 좌석 페이지를 열어 확인한다 (사람이 로그인해야 하는 대화형 단계):
   ```python
   from pathlib import Path
   from cgvwatch.hunt.browser import BrowserManager
   b = BrowserManager(Path.home() / ".cgv-watcher" / "chrome-profile")
   b.start()
   p = b.page()
   p.goto("https://cgv.co.kr/cnm/movieBook/movie?movNo=<movNo>&scnYmd=<ymd>&siteNo=<siteNo>&siteNm=<인코딩된 이름>")
   input("로그인하고 회차를 눌러 좌석 화면까지 이동한 뒤 Enter: ")
   print(p.url)
   print("좌석 버튼 수:", p.locator("button[data-seatlocno]").count())
   ```
3. 좌석 버튼 개수가 **0**이면 셀렉터가 바뀐 것이다. 브라우저 개발자도구로 새 셀렉터를
   찾아 **`cgvwatch/hunt/selectors.py`만** 고치고, 그 항목의 확인 날짜를 오늘로 갱신한다.
   (다른 파일에 셀렉터 문자열을 직접 쓰지 않는다 — 셀렉터는 이 파일에만 둔다는 것이
   프로젝트 규칙이다.)
4. 개수가 0이 아니면 셀렉터는 살아있는 것이니, 헌터 로직(`cgvwatch/hunt/hunter.py`)의
   흐름 자체(클릭 순서, 대기 시간, 모달 처리)를 의심한다.
5. "화면 구조 변경 의심" 알림이 왔을 때도 같은 절차를 따른다 — 알림과 함께 저장된
   `data/snapshots/`의 페이지 스냅샷을 먼저 보고 무엇이 비어 있는지 확인한 뒤 2~4단계로
   간다.

## 시도했다 버린 것들

- **회차별 딥링크**: CGV에는 특정 회차로 바로 들어가는 URL이 존재하지 않는다. 예매
  페이지는 영화·날짜·극장까지만 미리 채워지고, 회차는 화면에서 사람(또는 자동화)이
  버튼을 눌러 골라야 한다.
- **디스코드 회차별 버튼**: 회차마다 버튼을 만들어 디스코드 메시지에 붙였던 적이 있으나,
  위의 딥링크 부재로 버튼이 결국 같은 예매 페이지로만 갈 뿐 실효가 없어 제거했다. 지금은
  오픈 알림을 단순 메시지 + 예매 페이지 딥링크로 되돌렸다.
- **시간대 범위 입력**: 감시 항목에 시간대 범위(예: 저녁 시간대만)를 입력받던 방식은
  관 필터(예: IMAX만)로 대체했다. 관 필터가 사용자가 실제로 원하는 조건을 더 직접적으로
  표현한다고 판단했다.

## 개발 환경 규칙

- **의존성은 uv로 관리한다.** 패키지 추가는 `uv add <이름>` (`pyproject.toml`과 `uv.lock`이
  함께 갱신된다). `pip install`을 직접 쓰지 않는다 — 전역 파이썬에 설치되어 잠금 파일과
  어긋난다.
- **모든 파이썬 실행에 `uv run`을 앞에 붙인다** (`uv run python run.py`, `uv run pytest`,
  `uv run python -c "..."`). 맨 `python`을 쓰면 프로젝트 가상환경이 아니라 전역 파이썬이
  잡힌다.
- 테스트: `uv run pytest tests/ -v` (저장소 루트에서). 브라우저 제어(Playwright로 실제
  CGV 화면 조작)는 실제 CGV에 의존하므로 자동 테스트하지 않는다 — 대신 셀렉터를
  `cgvwatch/hunt/selectors.py` 한 곳에 모아 변경 지점을 좁히고, 위 진단 절차로 수동 확인한다.
- 코드 변경 시 이 문서(CLAUDE.md)의 안전선·관찰 기록과 어긋나지 않는지 확인한다. 특히
  CGV API/DOM에 대해 새로 알게 된 사실은 **날짜를 붙여** 이 문서에 반영한다.
