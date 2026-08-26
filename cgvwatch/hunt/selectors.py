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

# CGV 첫 화면. 로그인 상태 확인에 쓴다 (확인: 2026-08-26)
HOME_URL = "https://cgv.co.kr/"

# 로그인/로그아웃 버튼. 로그아웃 상태에서 텍스트가 "로그인" (확인: 2026-08-26)
AUTH_BUTTON = "button.cgv-footer-link"
LOGIN_TEXT = "로그인"
LOGOUT_TEXT = "로그아웃"
