"""'어두운 상영관' 테마: 색 팔레트, 다크 QPalette, QSS, 상태 뱃지 델리게이트.

컨셉: 불 꺼진 CGV 상영관. 따뜻한 near-black 배경에 스크린처럼 은은한 빛.
CGV 버밀리언 레드는 주 액션에만, 골드 글로우는 오직 '열림' 순간에만 켜진다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette, QBrush, QPen
from PyQt6.QtWidgets import QStyledItemDelegate

from cgvwatch.core.models import Status

# --- 팔레트 (4~6개 이름있는 hex) ---
BG_BASE = "#17130F"      # 상영관의 따뜻한 near-black
BG_SURFACE = "#211B16"   # 패널/테이블 표면
BG_ELEVATED = "#2C241D"  # 헤더/호버
LINE = "#3A2F27"         # 따뜻한 헤어라인
TEXT = "#F4EEE4"         # 따뜻한 오프화이트
TEXT_MUTED = "#A99C8D"   # 캡션/서브

ACCENT = "#E23744"       # CGV 버밀리언 레드 (주 액션)
ACCENT_HOVER = "#F04654"
GOLD = "#F5B841"         # 스크린 글로우 — 오직 '열림'에만

# 상태별 뱃지 색 (배경틴트, 글자)
STATUS_COLORS = {
    Status.WAITING: ("#2E3A44", "#9FB3C4"),  # 슬레이트, 차분
    Status.OPEN: ("#4A3A16", GOLD),          # 골드 글로우 — 보상의 순간
    Status.ERROR: ("#4A2420", "#F0857C"),    # 레드, 경고
}


def apply_theme(app) -> None:
    """앱 전역에 Fusion + 다크 팔레트 + QSS + 기본 폰트를 적용한다."""
    app.setStyle("Fusion")

    font = QFont("Malgun Gothic", 10)  # 한글 또렷한 Windows UI 폰트
    app.setFont(font)

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG_BASE))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(BG_SURFACE))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1B1611"))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(BG_SURFACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_ELEVATED))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_MUTED))
    app.setPalette(pal)

    app.setStyleSheet(STYLESHEET)


STYLESHEET = f"""
* {{
    outline: none;
}}

QMainWindow, QDialog {{
    background-color: {BG_BASE};
}}

QWidget {{
    color: {TEXT};
    font-size: 14px;
}}

/* ---- 메뉴 바 ---- */
QMenuBar {{
    background-color: {BG_BASE};
    color: {TEXT_MUTED};
    padding: 4px 6px;
    border-bottom: 1px solid {LINE};
}}
QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background-color: {BG_ELEVATED};
    color: {TEXT};
}}
QMenu {{
    background-color: {BG_SURFACE};
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 18px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: #FFFFFF;
}}
QMenu::separator {{
    height: 1px;
    background: {LINE};
    margin: 6px 8px;
}}

/* ---- 헤더 ---- */
#header {{
    background-color: {BG_BASE};
}}
#appTitle {{
    color: {TEXT};
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 1px;
}}
#appSubtitle {{
    color: {TEXT_MUTED};
    font-size: 13px;
}}
#accentRule {{
    background-color: {ACCENT};
    max-height: 3px;
    min-height: 3px;
    border-radius: 2px;
}}

/* ---- 버튼: 보조(고스트) ---- */
QPushButton {{
    background-color: transparent;
    color: {TEXT};
    border: 1px solid {LINE};
    border-radius: 9px;
    padding: 9px 16px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {BG_ELEVATED};
    border-color: #4C4038;
}}
QPushButton:pressed {{
    background-color: {BG_SURFACE};
}}

/* ---- 버튼: 주 액션(추가) ---- */
QPushButton#primaryButton {{
    background-color: {ACCENT};
    color: #FFFFFF;
    border: none;
    padding: 9px 20px;
}}
QPushButton#primaryButton:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton#primaryButton:pressed {{
    background-color: {ACCENT};
}}

/* ---- 테이블 ---- */
QTableWidget {{
    background-color: {BG_SURFACE};
    alternate-background-color: #1B1611;
    border: 1px solid {LINE};
    border-radius: 12px;
    gridline-color: transparent;
    padding: 4px;
    selection-background-color: rgba(226, 55, 68, 0.18);
    selection-color: {TEXT};
}}
QTableWidget::item {{
    padding: 10px 8px;
    border-bottom: 1px solid {LINE};
}}
QTableWidget::item:selected {{
    background-color: rgba(226, 55, 68, 0.18);
    color: {TEXT};
}}
QHeaderView::section {{
    background-color: {BG_SURFACE};
    color: {TEXT_MUTED};
    padding: 10px 8px;
    border: none;
    border-bottom: 1px solid {LINE};
    font-size: 12px;
    font-weight: 700;
}}
QTableCornerButton::section {{
    background-color: {BG_SURFACE};
    border: none;
}}

/* ---- 입력 위젯 (다이얼로그) ---- */
QLineEdit, QComboBox, QSpinBox, QDateEdit {{
    background-color: {BG_BASE};
    color: {TEXT};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down, QDateEdit::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_SURFACE};
    border: 1px solid {LINE};
    border-radius: 8px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
    padding: 4px;
}}

/* ---- 라벨 (설정 안내) ---- */
QLabel {{
    color: {TEXT};
}}
#hintLabel {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
#sectionLabel {{
    color: {TEXT_MUTED};
    font-size: 12px;
    font-weight: 700;
    padding-top: 4px;
}}
#dateLabel {{
    color: {GOLD};
    font-size: 13px;
    font-weight: 700;
    padding: 2px;
}}

/* ---- 달력 (날짜 선택) ---- */
QCalendarWidget {{
    background-color: {BG_SURFACE};
    border: 1px solid {LINE};
    border-radius: 10px;
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {BG_ELEVATED};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}}
QCalendarWidget QToolButton {{
    color: {TEXT};
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    margin: 3px;
    font-weight: 700;
    icon-size: 18px;
}}
QCalendarWidget QToolButton:hover {{
    background-color: {ACCENT};
    color: #FFFFFF;
}}
QCalendarWidget QMenu {{
    background-color: {BG_SURFACE};
    border: 1px solid {LINE};
    border-radius: 8px;
}}
QCalendarWidget QSpinBox {{
    background-color: {BG_BASE};
    color: {TEXT};
    border: 1px solid {LINE};
    border-radius: 6px;
    padding: 2px 6px;
}}
/* 날짜 그리드 */
QCalendarWidget QAbstractItemView:enabled {{
    background-color: {BG_SURFACE};
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
    outline: none;
    font-size: 14px;
}}
/* 지난 날짜(선택 불가)는 흐리게 */
QCalendarWidget QAbstractItemView:disabled {{
    color: #5A4E44;
}}

/* ---- 상태 바 ---- */
QStatusBar {{
    background-color: {BG_BASE};
    color: {TEXT_MUTED};
    border-top: 1px solid {LINE};
}}
QStatusBar::item {{ border: none; }}

/* ---- 스크롤바 ---- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px;
}}
QScrollBar::handle:vertical {{
    background: {LINE};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #4C4038; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

/* ---- 메시지 박스 ---- */
QMessageBox {{
    background-color: {BG_SURFACE};
}}
"""


class StatusDelegate(QStyledItemDelegate):
    """상태 열을 둥근 뱃지(pill)로 그린다. '열림'은 골드로 은은히 빛난다."""

    def paint(self, painter: QPainter, option, index) -> None:
        status = index.data(Qt.ItemDataRole.DisplayRole) or ""
        bg_hex, fg_hex = STATUS_COLORS.get(status, (BG_ELEVATED, TEXT_MUTED))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 선택 시 셀 배경 살짝
        if option.state & option.state.__class__.State_Selected:
            painter.fillRect(option.rect, QColor(226, 55, 68, 46))

        rect = QRectF(option.rect)
        label = f"● {status}"
        metrics = painter.fontMetrics()
        text_w = metrics.horizontalAdvance(label)
        pad_x, pill_h = 14, 26
        pill_w = min(text_w + pad_x * 2, rect.width() - 12)
        pill = QRectF(
            rect.left() + (rect.width() - pill_w) / 2,
            rect.top() + (rect.height() - pill_h) / 2,
            pill_w,
            pill_h,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(bg_hex)))
        painter.drawRoundedRect(pill, pill_h / 2, pill_h / 2)

        painter.setPen(QPen(QColor(fg_hex)))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()
