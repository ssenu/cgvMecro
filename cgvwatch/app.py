"""CGV 예매 오픈 알리미 진입점."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from cgvwatch.cgv.client import CGVClient
from cgvwatch.core.store import Store
from cgvwatch.gui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow(Store(), CGVClient())
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
