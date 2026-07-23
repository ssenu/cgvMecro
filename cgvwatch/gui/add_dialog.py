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
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("추가")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
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
