# CGV 예매 오픈 알리미

지정한 (상영관·날짜·영화)의 CGV 예매가 열리면 이메일로 알려주는 Windows 데스크톱 앱.

- 예매 오픈을 **알림**만 하는 도구입니다. 자동 예매/결제 기능은 없습니다.
- CGV 공개 조회 API(`cgv.co.kr/api/v1/booking/*`)를 예의 있게(기본 5분 간격) 사용합니다.

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

## 사용법

1. **[설정]** 에서 Gmail 주소, 앱 비밀번호(2단계 인증 후 발급), 수신 메일, 확인 간격을 입력합니다.
   - 앱 비밀번호는 Windows 자격 증명 관리자(`keyring`)에 저장되며 설정 파일에 평문으로 남지 않습니다.
2. **[추가]** 로 지역 → 상영관, 영화, 날짜를 선택합니다.
3. 창을 켜두면 설정한 간격마다 자동으로 확인하고, 해당 날짜의 예매가 열리면 메일을 보냅니다.
   - 팁: Windows 작업 스케줄러에 등록하면 부팅 시 자동 실행됩니다.

## 동작 원리

CGV의 공개 조회 API `searchSiteScnscYmdListByMov(siteNo, movNo)` 는 해당 영화가 그
상영관에서 **예매 가능한 날짜 목록**을 반환합니다. 이 목록에 감시 대상 날짜가
처음 나타나는 순간을 "예매 오픈"으로 감지해 알림을 보냅니다.

## 테스트

```
python -m pytest -v
```

## 설정/데이터 위치

- 설정·감시목록: `%USERPROFILE%\.cgv-watcher\config.json`
- Gmail 앱 비밀번호: Windows 자격 증명 관리자 (서비스명 `cgv-watcher`)
