# CGV 예매 오픈 알리미

지정한 (상영관·날짜·영화)의 CGV 예매가 열리면 즉시 알려주는 웹 앱. Raspberry Pi 등 상시
켜져 있는 서버에 Docker로 올려두고, 브라우저로 감시 목록을 관리합니다.

- 예매 오픈을 **알림**만 하는 도구입니다. 자동 예매/결제 기능은 없습니다.
- CGV 공개 조회 API(`cgv.co.kr/api/v1/booking/*`)를 예의 있게(기본 5분 간격) 사용합니다.
- 백그라운드 감시 스레드가 등록된 (상영관·영화·날짜) 조합을 주기적으로 확인하고,
  예매 가능 날짜 목록에 감시 대상 날짜가 처음 나타나는 순간 "예매 오픈"으로 판단해
  Discord 웹훅으로 알립니다.

## 동작 원리

CGV의 공개 조회 API `searchSiteScnscYmdListByMov(siteNo, movNo)` 는 해당 영화가 그
상영관에서 **예매 가능한 날짜 목록**을 반환합니다. 이 목록에 감시 대상 날짜가
처음 나타나는 순간을 "예매 오픈"으로 감지해 Discord 채널로 알림을 보냅니다.

## 요구사항

- Docker / Docker Compose
- 알림을 받을 Discord 웹훅 URL

## 빠른 시작 (Docker)

```bash
# Raspberry Pi에서
git clone https://github.com/ssenu/cgvMecro.git && cd cgvMecro
cp .env.example .env && nano .env   # DISCORD_WEBHOOK_URL 기입
docker compose up -d --build
# 접속: http://<Pi주소>:8080  /  로그: docker logs -f cgvwatch
# 업데이트: git pull && docker compose up -d --build
```

브라우저에서 `http://<raspberry-pi-주소>:8080` 으로 접속하면 웹 UI가 열립니다.
감시 목록·상영관·영화 검색, 추가/삭제가 모두 웹 화면에서 이루어집니다.

## 개발자용 로컬 실행

의존성은 [uv](https://docs.astral.sh/uv/)로 관리합니다. `uv run`이 가상환경을 자동으로
만들고 `uv.lock`에 잠긴 버전 그대로 설치하므로, 가상환경을 직접 켤 필요가 없습니다.

```
uv sync --extra dev
uv run python run.py
```

기본적으로 `http://0.0.0.0:8080` 에서 서버가 뜹니다.

### 테스트

```
uv run pytest tests/
```

## 환경 변수

| 변수 | 설명 | 기본값 |
| --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | 예매 오픈 알림을 보낼 Discord 웹훅 URL. 미설정 시 알림 전송을 시도하면 오류가 발생합니다. | (없음, 필수) |
| `CGVWATCH_DATA` | 설정·감시목록을 저장할 디렉터리 (`config.json` 위치). | 사용자 홈 디렉터리 |
| `HOST_PORT` | Docker 사용 시 호스트에서 접속할 포트 (`.env`에서 변경). 컨테이너 내부 포트는 8080 고정. | `8080` |
| `PORT` | 웹 서버가 바인딩할 포트 (로컬 직접 실행 시). | `8080` |
| `TZ` | 컨테이너/프로세스의 타임존 (예매 오픈 판단·표시 시각에 영향). | 시스템 기본값 |

## API

- `GET /healthz` — 헬스체크
- `GET/POST/DELETE /api/watches` — 감시 목록 조회/추가/삭제
- `GET/PUT /api/settings` — 설정 조회/변경
- `GET /api/movies`, `GET /api/theaters` — CGV 상영관/영화 목록 조회
- `GET /` — 웹 UI
