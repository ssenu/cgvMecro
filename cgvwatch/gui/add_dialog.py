"""감시 조건 추가 다이얼로그."""
from __future__ import annotations

import uuid

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor, QTextCharFormat
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QCalendarWidget, QDialogButtonBox,
    QVBoxLayout, QLabel,
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

        # 달력: 오늘 이후만 선택 가능, 클릭으로 날짜 선택
        self.calendar = QCalendarWidget()
        self.calendar.setObjectName("datePicker")
        self.calendar.setGridVisible(True)
        self.calendar.setMinimumDate(QDate.currentDate())
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self.calendar.selectionChanged.connect(self._update_date_label)
        self.calendar.currentPageChanged.connect(lambda *_: self._dim_past_dates())
        self._dim_past_dates()

        self.date_label = QLabel()
        self.date_label.setObjectName("dateLabel")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        form = QFormLayout()
        form.addRow("지역", self.region_combo)
        form.addRow("상영관", self.site_combo)
        form.addRow("영화", self.movie_combo)

        date_header = QLabel("날짜 선택")
        date_header.setObjectName("sectionLabel")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("추가")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(date_header)
        layout.addWidget(self.calendar)
        layout.addWidget(self.date_label)
        layout.addWidget(buttons)

        self._reload_sites()
        self._update_date_label()

    def _reload_sites(self) -> None:
        self.site_combo.clear()
        idx = self.region_combo.currentIndex()
        if 0 <= idx < len(self._regions):
            for s in self._regions[idx]["sites"]:
                self.site_combo.addItem(s["site_nm"], s["site_no"])

    def _dim_past_dates(self) -> None:
        """현재 표시된 달에서 오늘 이전 날짜를 흐리게 표시(선택 불가임을 명확히)."""
        dim = QTextCharFormat()
        dim.setForeground(QColor("#5A4E44"))
        today = QDate.currentDate()
        d = QDate(self.calendar.yearShown(), self.calendar.monthShown(), 1)
        while d.isValid() and d.month() == self.calendar.monthShown():
            if d < today:
                self.calendar.setDateTextFormat(d, dim)
            d = d.addDays(1)

    def _update_date_label(self) -> None:
        d = self.calendar.selectedDate()
        weekday = ["월", "화", "수", "목", "금", "토", "일"][d.dayOfWeek() - 1]
        self.date_label.setText(f"선택한 날짜:  {d.toString('yyyy-MM-dd')} ({weekday})")

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
            target_ymd=self.calendar.selectedDate().toString("yyyyMMdd"),
        )
        self.accept()

    def result_watch(self) -> Watch | None:
        return self._watch
