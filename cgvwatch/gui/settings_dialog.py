"""Gmail·알림 설정 다이얼로그."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox, QVBoxLayout, QLabel,
)

from cgvwatch.core.models import Settings
from cgvwatch.notify.mailer import save_app_password, get_app_password


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("설정")
        self._settings = settings

        self.gmail_edit = QLineEdit(settings.gmail_user)
        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_edit.setPlaceholderText("변경 시에만 입력 (Google 앱 비밀번호 16자리)")
        if settings.gmail_user and get_app_password(settings.gmail_user):
            self.pw_edit.setPlaceholderText("저장됨 — 변경 시에만 입력")
        self.recipient_edit = QLineEdit(settings.recipient)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 180)
        self.interval_spin.setValue(settings.interval_min)
        self.interval_spin.setSuffix(" 분")

        form = QFormLayout()
        form.addRow("Gmail 주소", self.gmail_edit)
        form.addRow("앱 비밀번호", self.pw_edit)
        form.addRow("수신 메일", self.recipient_edit)
        form.addRow("확인 간격", self.interval_spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Gmail 2단계 인증 후 '앱 비밀번호'를 발급해 입력하세요."))
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        user = self.gmail_edit.text().strip()
        pw = self.pw_edit.text().strip()
        if user and pw:
            save_app_password(user, pw)
        self._settings = Settings(
            gmail_user=user,
            recipient=self.recipient_edit.text().strip(),
            interval_min=self.interval_spin.value(),
        )
        self.accept()

    def result_settings(self) -> Settings:
        return self._settings
