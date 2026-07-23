"""메인 윈도우: 감시 목록 관리 + 워커 구동."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout,
    QVBoxLayout, QWidget, QMessageBox, QHeaderView,
)

from cgvwatch.cgv.theaters import get_regions
from cgvwatch.cgv.movies import get_movies
from cgvwatch.core.models import Watch
from cgvwatch.core.store import Store
from cgvwatch.core.watcher import WatcherWorker, check_watch
from cgvwatch.gui.add_dialog import AddDialog
from cgvwatch.gui.settings_dialog import SettingsDialog

HEADERS = ["영화", "상영관", "날짜", "상태", "마지막 확인"]


class MainWindow(QMainWindow):
    def __init__(self, store: Store, client) -> None:
        super().__init__()
        self.setWindowTitle("CGV 예매 오픈 알리미")
        self.resize(720, 400)
        self._store = store
        self._client = client
        self._settings, self._watches = store.load()

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        add_btn = QPushButton("추가")
        del_btn = QPushButton("삭제")
        check_btn = QPushButton("지금 확인")
        settings_btn = QPushButton("설정")
        add_btn.clicked.connect(self.on_add)
        del_btn.clicked.connect(self.on_delete)
        check_btn.clicked.connect(self.on_check_now)
        settings_btn.clicked.connect(self.on_settings)

        btn_row = QHBoxLayout()
        for b in (add_btn, del_btn, check_btn, settings_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(btn_row)
        layout.addWidget(self.table)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._refresh_table()
        self._start_worker()

    # --- 워커 상태 접근자 ---
    def _get_state(self):
        def set_watch(updated: Watch):
            for i, w in enumerate(self._watches):
                if w.id == updated.id:
                    self._watches[i] = updated
                    break
            self._store.save(self._settings, self._watches)
        return self._settings, self._watches, set_watch

    def _start_worker(self) -> None:
        self.worker = WatcherWorker(self._client, self._get_state)
        self.worker.updated.connect(self._on_worker_update)
        self.worker.start()

    def _on_worker_update(self, watch_id: str, status: str, last_checked: str) -> None:
        self._refresh_table()

    # --- 테이블 ---
    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._watches))
        for row, w in enumerate(self._watches):
            ymd = f"{w.target_ymd[:4]}-{w.target_ymd[4:6]}-{w.target_ymd[6:8]}"
            values = [w.mov_nm, w.site_nm, ymd, w.status, w.last_checked]
            for col, val in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(val))

    # --- 버튼 핸들러 ---
    def on_add(self) -> None:
        try:
            regions = get_regions(self._client)
            movies = get_movies(self._client)
        except Exception as exc:
            QMessageBox.warning(self, "오류", f"CGV 목록을 불러오지 못했습니다:\n{exc}")
            return
        dlg = AddDialog(regions, movies, self)
        if dlg.exec() and dlg.result_watch():
            self._watches.append(dlg.result_watch())
            self._store.save(self._settings, self._watches)
            self._refresh_table()

    def on_delete(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._watches):
            del self._watches[row]
            self._store.save(self._settings, self._watches)
            self._refresh_table()

    def on_check_now(self) -> None:
        _, watches, set_watch = self._get_state()
        for w in list(watches):
            set_watch(check_watch(self._client, w, self._settings))
        self._refresh_table()

    def on_settings(self) -> None:
        dlg = SettingsDialog(self._settings, self)
        if dlg.exec():
            self._settings = dlg.result_settings()
            self._store.save(self._settings, self._watches)

    def closeEvent(self, event) -> None:
        if hasattr(self, "worker"):
            self.worker.stop()
            self.worker.wait(2000)
        super().closeEvent(event)
