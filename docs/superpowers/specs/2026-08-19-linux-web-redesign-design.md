# cgvwatch 리눅스 웹 버전 설계 (Rpi + Docker 상시 구동)

- 날짜: 2026-08-19
- 상태: 사용자 승인됨

## 목표

Windows용 PyQt6 GUI 앱(CGV 예매 오픈 알리미)을 Raspberry Pi 위 Docker 컨테이너에서
24시간 상시 구동하는 웹 앱으로 개편한다. PyQt GUI는 완전 대체(제거)하고,
알림은 이메일 대신 디스코드 웹훅으로 보낸다. 웹 UI는 집 LAN 전용(로그인 없음).

## 결정 사항 요약

| 항목 | 결정 |
|---|---|
| 운영 방식 | 웹 UI (FastAPI + 바닐라 HTML 한 장) |
| PyQt GUI | 완전 제거 |
| 알림 | 디스코드 웹훅만 (이메일/keyring 제거) |
| 배포 | Rpi에서 `git clone` 후 직접 빌드 (`docker compose up -d --build`) |
| 접속 범위 | 집 LAN 전용, 인증 없음 |

## 아키텍처

단일 컨테이너, 단일 프로세스(uvicorn). FastAPI 앱이 두 역할을 한다.

1. 웹 UI(정적 HTML)와 JSON API 제공
2. 앱 lifespan 시작 시 백그라운드 감시 스레드를 띄워 기존 `check_watch()` 루프 상시 실행

영속화는 기존 `Store`(JSON 파일)를 그대로 쓰되 경로를 `/data/config.json`으로 변경,
도커 볼륨(`./data:/data`)으로 컨테이너 재생성에도 유지한다.
비밀값(디스코드 웹훅 URL)은 `.env` → 환경변수로 주입한다.

## 코드 변경

### 제거
- `cgvwatch/gui/` 전체 (main_window, add_dialog, settings_dialog, theme)
- `cgvwatch/notify/mailer.py` (keyring 의존 포함)
- PyInstaller 관련: `cgv_notifier.spec`, `build/`, `dist/`, `requirements-dev.txt`의 관련 항목
- `Settings`의 `gmail_user`, `recipient` 필드
- GUI 관련 테스트

### 수정
- `core/watcher.py`: `WatcherWorker(QThread)` → 표준 `threading.Thread` + `threading.Event` 기반
  `WatcherThread`로 교체. 순수 함수 `check_watch()`는 유지하되 기본 알림 함수를
  디스코드 발송으로 교체. 방어 로직(항목별 예외 무시, 알림 실패 시 `was_open` 미상승으로
  다음 주기 재시도)은 그대로 승계.
- `core/store.py`: 기본 경로를 환경변수 `CGVWATCH_DATA`(기본 `/data`) 하위 `config.json`으로.
- `run.py`: uvicorn으로 웹 서버를 띄우는 진입점으로 교체.

### 신설
- `cgvwatch/notify/discord.py`
  - `send_open_alert(watch)`: `DISCORD_WEBHOOK_URL` 환경변수로 웹훅 POST.
    임베드 형식: "🎬 <영화명> — <극장명> <날짜> 예매가 열렸습니다!"
  - URL 미설정 시 예외 발생 → watcher의 기존 실패 처리 경로(ERROR + 재시도)를 탄다.
- `cgvwatch/web/server.py` — FastAPI 앱
  - `GET /api/watches` — 감시 목록(상태·마지막 확인 시각 포함)
  - `POST /api/watches` — 감시 추가 (mov_no, mov_nm, site_no, site_nm, target_ymd)
  - `DELETE /api/watches/{id}` — 감시 삭제
  - `GET /api/movies` — 상영예정작 목록 (기존 `cgv/movies.py` 재사용)
  - `GET /api/theaters` — 극장 목록 (기존 `cgv/theaters.py` 재사용)
  - `GET /api/settings` / `PUT /api/settings` — 감시 주기(interval_min)
  - `GET /healthz` — 도커 헬스체크용, 200 반환
  - `GET /` — `static/index.html` 서빙
- `cgvwatch/web/static/index.html` — 파일 한 장(HTML+CSS+JS)
  - 기존 '어두운 상영관' 다크 테마를 CSS로 재현
  - 감시 목록 테이블 + 상태 뱃지(대기중/열림/오류)
  - 추가 폼: 영화 검색 → 극장 선택 → 날짜 선택 (기존 add_dialog 흐름)
  - 설정: 감시 주기 변경
  - 5초 주기 폴링(`GET /api/watches`)으로 상태 자동 갱신

## Docker

- `Dockerfile`: `python:3.12-slim` 기반. 의존성: fastapi, uvicorn, requests.
  (PyQt6·keyring 제거로 이미지 경량화. Pi에서 직접 빌드하므로 네이티브 arch로 빌드됨)
- `docker-compose.yml`:
  - `restart: unless-stopped` (Pi 재부팅 시 자동 기동)
  - `./data:/data` 볼륨
  - `env_file: .env` (`DISCORD_WEBHOOK_URL`)
  - 포트 `8080:8080`
  - `TZ=Asia/Seoul`
  - `/healthz` 헬스체크
- `.env.example` 제공, `.env`·`data/`는 `.gitignore`에 추가
- 로그는 stdout(`logging` 표준 설정) → `docker logs cgvwatch`

## 운영 흐름

1. Pi에 SSH 접속 → `git clone` → `.env` 작성(`DISCORD_WEBHOOK_URL=...`)
2. `docker compose up -d --build`
3. 브라우저에서 `http://<Pi주소>:8080` 접속해 감시 등록
4. 업데이트: `git pull && docker compose up -d --build`

## 에러 처리

- 감시 루프: 항목별 try/except로 한 항목의 오류가 전체를 멈추지 않음 (기존 유지)
- 디스코드 발송 실패: `was_open`을 올리지 않아 다음 주기에 재발송 시도 (기존 메일 로직 승계)
- CGV API 오류: 해당 watch를 ERROR 상태로 표시, 다음 주기 재시도 (기존 유지)
- API 입력 검증: FastAPI/Pydantic 기본 검증 사용

## 테스트

- 유지: `core/detect.py`, `check_watch()` 등 순수 로직 테스트
- 추가: `notify/discord.py` (requests mock), API 엔드포인트 (FastAPI TestClient, CGV 클라이언트 mock)
- 제거: GUI 테스트
