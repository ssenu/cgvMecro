# CGV 예매 오픈 알리미 — 설계 문서

작성일: 2026-07-23 (API 실측 검증 반영)

## 1. 목적

CGV에서 사용자가 지정한 **(상영관, 날짜, 영화)** 조건에 대해, 아직 예매가 열리지 않은 영화의 **상영시간표가 처음 뜨는 순간(예매 오픈)** 을 감지하여 **이메일로 알림**을 보낸다.

- 이것은 **알림 도구**다. 좌석을 자동으로 선점/결제하는 **자동 예매 봇이 아니다.**
- 로그인·결제 없이 공개된 조회용 JSON API만 예의 있게(polite) 주기 조회한다.

## 2. 사용 결정 사항 (브레인스토밍 확정)

| 항목 | 결정 |
| --- | --- |
| 감지 대상 | 시나리오 A: 상영시간표가 그 상영관에 처음 뜨는 순간 |
| 실행 위치 | 사용자의 Windows PC (창을 열어두고 상시 실행) |
| 입력 방식 | PyQt6 GUI (감시 목록을 여러 개 추가/삭제) |
| 알림 방식 | Gmail SMTP + 앱 비밀번호, 수신 주소는 설정에서 지정 |
| 데이터 수집 | **CGV 공개 JSON API + `requests`** (실측 검증 완료) |
| 폴링 간격 | 기본 5분 (설정 가능) |
| 앱 비밀번호 저장 | `keyring` (Windows 자격 증명 관리자) |

## 3. 데이터 소스 실측 결과 (2026-07-23 검증)

> **중요:** CGV는 사이트를 Next.js(React) + Cloudflare 구조로 전면 개편했다. 구 `iframeTheater.aspx`(ASP.NET) endpoint는 폐기되었다. 브레인스토밍에서 가정한 "HTML 파싱 + Playwright 폴백"은 **불필요**하며, 대신 아래 **공개 JSON API**를 사용한다.

CGV 웹 프런트는 `https://cgv.co.kr/api/v1/booking/*` 프록시(BFF)를 통해 백엔드(`api.cgv.co.kr`)를 호출한다. 이 프록시 endpoint들은 **쿠키·로그인·브라우저 없이 일반 User-Agent의 단순 GET 요청(curl / Python `requests`)으로 HTTP 200 + JSON을 반환함을 실측 확인**했다. 즉 헤드리스 브라우저가 전혀 필요 없다.

공통 파라미터: `coCd=A420` (CGV 회사 코드).

| 용도 | Endpoint (base: `https://cgv.co.kr/api/v1/booking/`) | 핵심 파라미터 | 응답 요지 |
| --- | --- | --- | --- |
| 지역·극장 목록 | `searchRegnList` | `coCd` | `data[].regnGrpNm`, `data[].siteList[].{siteNo, siteNm}` |
| 영화 목록 | `searchAtktTopPostrList` | `coCd, movNm, div, attrCd` | `data[].{movNo, movNm}` (현재/상영예정 약 50편) |
| **예매 오픈 날짜(감지 핵심)** | `searchSiteScnscYmdListByMov` | `coCd, siteNo, movNo` | `data[].{scnYmd}` = 그 영화가 그 극장에서 **예매 가능한 날짜 목록** |

실측 예: `searchSiteScnscYmdListByMov?coCd=A420&siteNo=0056&movNo=30001192` (강남·스파이더맨) →
`[{"scnYmd":"20260729"},{"scnYmd":"20260730"},...]` — 7/29부터 예매 오픈, 그 이전 날짜는 목록에 없음.

응답 공통 래퍼: `{ "statusCode": 0, "statusMessage": "...", "data": ... }` (성공 시 `statusCode == 0`).

## 4. 핵심 감지 로직 (시나리오 A)

- 감시조건 = `(siteNo, siteNm, movNo, movNm, 대상 날짜 targetYmd)`
- 매 주기마다 `searchSiteScnscYmdListByMov(siteNo, movNo)` 호출 → 반환된 `scnYmd` 집합을 얻음
- **대상 날짜 `targetYmd`가 이전엔 집합에 없었는데 이번에 등장** = 예매 오픈 → 메일 발송
  - 단순화: 한 번도 열린 적 없던 조건에서 `targetYmd ∈ scnYmd 집합`이 되는 최초 시점에 발송
- 발송 후 해당 조건은 `열림(opened)` 상태로 전이하여 중복 메일 방지
- GUI 상태 표시: `대기중` / `열림🔔` / `오류`

장점: HTML 파싱·브라우저 불필요. 조건당 GET 1회. 응답이 작고 명확(날짜 배열).

**제목 → `movNo` 변환:** 사용자는 영화 제목을 (드롭다운/검색으로) 고르고, 내부적으로 `searchAtktTopPostrList`의 `movNm`↔`movNo` 매핑으로 `movNo`를 확정한다. 목록에 없는 영화(아주 이른 개봉예정작)는 추가 시 경고하고, 매핑되는 영화만 감시 등록한다.

## 5. 컴포넌트 상세

### 5.1 CGV Client (`cgv/`)
- `client.py` — `requests.Session` 래퍼: base URL, `coCd`, User-Agent, 타임아웃, `statusCode` 검증, 재시도
- `theaters.py` — `get_regions()` → 지역·극장 목록 (드롭다운용)
- `movies.py` — `get_movies()` → `{movNm: movNo}` 매핑
- `showtimes.py` — `get_open_dates(site_no, mov_no) -> set[str]` (예매 오픈 날짜 집합)
- 순수 `requests` 기반. HTML 파싱·헤드리스 브라우저 없음.

### 5.2 Watcher (`core/`)
- `models.py` — `Watch` 데이터클래스: `id, mov_no, mov_nm, site_no, site_nm, target_ymd, status, last_checked, was_open`
- `watcher.py` — QThread에서 QTimer로 N분마다 전체 감시 목록 순회
  - 각 Watch: `get_open_dates` 조회 → `target_ymd` 등장 여부 판정 → 미개봉→개봉 전이 감지 시 Notifier 호출
  - Qt 시그널로 GUI 상태 갱신(스레드 안전)
- `store.py` — 감시 목록/설정/상태를 로컬 JSON에 저장·로드

### 5.3 Notifier (`notify/`)
- `mailer.py` — Gmail SMTP(SSL 465) + 앱 비밀번호로 발송
  - 제목 예: `[CGV] "스파이더맨-브랜드 뉴 데이" 강남 07/25 예매 열렸습니다`
  - 본문: 상영관/날짜/확인시각 + CGV 예매 페이지 링크(`https://cgv.co.kr/cnm/movieBook/cinema`)
  - 앱 비밀번호는 `keyring`에서 조회(평문 저장 안 함)

### 5.4 GUI (`gui/`)
- `main_window.py` — 감시 목록 테이블(영화 | 상영관 | 날짜 | 상태 | 마지막확인), [추가][삭제][지금 확인] 버튼
- `add_dialog.py` — 지역 드롭다운 → 상영관 드롭다운(`searchRegnList`), 영화 선택(`searchAtktTopPostrList`), 날짜 선택(QDateEdit)
- `settings_dialog.py` — Gmail 주소/앱 비밀번호, 수신 주소, 폴링 간격

## 6. 데이터 흐름

1. 사용자가 추가 다이얼로그에서 지역→극장, 영화, 날짜 선택 → `(siteNo, movNo, targetYmd)`로 저장, 테이블에 표시
2. Watcher가 N분마다 각 조건에 대해 `get_open_dates(siteNo, movNo)` 조회
3. `was_open`(이전 상태)이 False인데 이번에 `targetYmd`가 오픈 날짜 집합에 포함되면
4. `Notifier`가 메일 발송 → Watch 상태 `열림`으로 전이, `Store` 갱신
5. GUI 상태 컬럼 실시간 갱신

## 7. 저장 위치 및 보안

- 설정/목록/상태: `%USERPROFILE%\.cgv-watcher\config.json`
- Gmail 앱 비밀번호: `keyring`(Windows 자격 증명 관리자)에 저장, config.json에는 저장하지 않음

## 8. 에러 처리

- 네트워크/HTTP/`statusCode!=0` 오류: 크래시 없이 로그 기록 후 다음 주기 재시도, GUI 상태 `오류` 표시
- SMTP 실패: 상태에 오류 표시 + 로그, 다음 주기 재시도
- 과도한 요청 방지: 기본 5분 간격 + 소량 지터, 정상 User-Agent 사용(예의 있는 폴링)
- CGV API 구조 변경 대비: `client.py`에 endpoint/파라미터를 상수로 모아 한 곳에서 수정 가능하게 함

## 9. 테스트 전략

- `showtimes.get_open_dates`: 저장한 실제 JSON 응답 픽스처로 파싱 단위 테스트
- 감지 전이 로직(미개봉→개봉 1회 발송, 개봉 유지 시 재발송 없음): 상태 mock 테스트
- `mailer`: SMTP mock으로 발송 포맷/호출 검증
- `client`: `requests` mock으로 `statusCode` 검증·재시도 테스트

## 10. 기술 스택

Python 3.11+, PyQt6, requests, keyring, pytest

(브레인스토밍 초안의 beautifulsoup4·playwright는 API 실측 결과 **불필요**하여 제외.)

## 11. 범위 밖 (YAGNI)

- 자동 좌석 선점/결제
- 취소표(재오픈) 감지 (시나리오 B)
- 클라우드 배포, 다중 사용자
- 카카오톡/텔레그램/윈도우 팝업 알림 (추후 확장 여지)
- 아주 이른 개봉예정작(영화 목록 API에 아직 없는 영화) 감시

## 부록 A. 재현용 원시 요청 예시

```bash
# 지역·극장 목록
curl -H "Accept: application/json" -A "Mozilla/5.0 Chrome/120" \
  "https://cgv.co.kr/api/v1/booking/searchRegnList?coCd=A420"

# 영화 목록 (movNo 확보)
curl -H "Accept: application/json" -A "Mozilla/5.0 Chrome/120" \
  "https://cgv.co.kr/api/v1/booking/searchAtktTopPostrList?coCd=A420&movNm=&div=&attrCd="

# 예매 오픈 날짜 (감지 핵심): 강남(0056) · 스파이더맨(30001192)
curl -H "Accept: application/json" -A "Mozilla/5.0 Chrome/120" \
  "https://cgv.co.kr/api/v1/booking/searchSiteScnscYmdListByMov?coCd=A420&siteNo=0056&movNo=30001192"
```
