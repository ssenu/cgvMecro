"""메인 윈도우: 감시 목록 관리 + 워커 구동."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMainWindow, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout,
    QVBoxLayout, QWidget, QMessageBox, QHeaderView, QLabel, QFrame, QAbstractItemView,
)

from cgvwatch.cgv.theaters import get_regions
from cgvwatch.cgv.movies import get_movies
from cgvwatch.core.models import Status, Watch
from cgvwatch.core.store import Store
from cgvwatch.core.watcher import WatcherWorker, check_watch
from cgvwatch.gui.add_dialog import AddDialog
from cgvwatch.gui.settings_dialog import SettingsDialog
from cgvwatch.gui.theme import StatusDelegate

HEADERS = ["영화", "상영관", "날짜", "상태", "마지막 확인"]
STATUS_COL = 3


class MainWindow(QMainWindow):
    def __init__(self, store: Store, client) -> None:
        super().__init__()
        self.setWindowTitle("CGV 예매 오픈 알리미")
        self.resize(820, 520)
        self.setMinimumSize(680, 420)
        self._store = store
        self._client = client
        self._settings, self._watches = store.load()

        self._build_menu_bar()

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 22, 28, 16)
        layout.setSpacing(18)

        layout.addWidget(self._build_header())
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self._build_table(), 1)

        self.setCentralWidget(central)
        self.statusBar()  # 하단 상태 표시줄

        self._refresh_table()
        self._start_worker()

    # --- 헤더 ---
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("header")
        v = QVBoxLayout(header)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        title = QLabel("🎬  CGV 예매 오픈 알리미")
        title.setObjectName("appTitle")
        subtitle = QLabel("예매가 열리는 순간, 메일로 알려드립니다")
        subtitle.setObjectName("appSubtitle")

        rule = QFrame()
        rule.setObjectName("accentRule")
        rule.setFixedWidth(56)

        v.addWidget(title)
        v.addWidget(subtitle)
        v.addSpacing(4)
        v.addWidget(rule)
        return header

    # --- 툴바 ---
    def _build_toolbar(self) -> QHBoxLayout:
        add_btn = QPushButton("＋  감시 추가")
        add_btn.setObjectName("primaryButton")
        del_btn = QPushButton("삭제")
        check_btn = QPushButton("지금 확인")
        settings_btn = QPushButton("설정")
        for b in (add_btn, del_btn, check_btn, settings_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self.on_add)
        del_btn.clicked.connect(self.on_delete)
        check_btn.clicked.connect(self.on_check_now)
        settings_btn.clicked.connect(self.on_settings)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(add_btn)
        row.addStretch()
        row.addWidget(del_btn)
        row.addWidget(check_btn)
        row.addWidget(settings_btn)
        return row

    # --- 테이블 ---
    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setItemDelegateForColumn(STATUS_COL, StatusDelegate(self.table))
        return self.table

    # --- 메뉴 바 ---
    def _build_menu_bar(self) -> None:
        menubar = self.menuBar()
        settings_menu = menubar.addMenu("설정")

        open_settings = QAction("메일 설정 열기...", self)
        open_settings.triggered.connect(self.on_settings)
        settings_menu.addAction(open_settings)

        settings_menu.addSeparator()
        quit_action = QAction("종료", self)
        quit_action.triggered.connect(self.close)
        settings_menu.addAction(quit_action)

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

    # --- 테이블 갱신 ---
    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self._watches))
        for row, w in enumerate(self._watches):
            ymd = f"{w.target_ymd[:4]}-{w.target_ymd[4:6]}-{w.target_ymd[6:8]}"
            values = [w.mov_nm, w.site_nm, ymd, w.status, w.last_checked or "—"]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col in (1, 2, STATUS_COL, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 0:
                    f = item.font()
                    f.setWeight(f.Weight.DemiBold)
                    item.setFont(f)
                    item.setToolTip(w.mov_nm)  # 잘린 제목 전체 표시
                self.table.setItem(row, col, item)
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        total = len(self._watches)
        opened = sum(1 for w in self._watches if w.status == Status.OPEN)
        if total == 0:
            self.statusBar().showMessage("감시 항목이 없습니다 — [＋ 감시 추가]로 시작하세요")
        else:
            self.statusBar().showMessage(f"{total}개 감시 중 · 열림 {opened}개 · {self._settings.interval_min}분마다 확인")

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
            self._update_status_bar()

    def closeEvent(self, event) -> None:
        if hasattr(self, "worker"):
            self.worker.stop()
            self.worker.wait(2000)
        super().closeEvent(event)
