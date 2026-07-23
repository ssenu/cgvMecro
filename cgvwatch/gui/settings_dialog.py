"""Gmail·알림 설정 다이얼로그."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDialogButtonBox, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QMessageBox,
)

from cgvwatch.core.models import Settings
from cgvwatch.notify.mailer import save_app_password, get_app_password, send_test_mail

APP_PW_HELP = (
    "Gmail 2단계 인증을 켠 뒤 https://myaccount.google.com/apppasswords 에서 "
    "'앱 비밀번호'(공백 없는 16자리)를 발급해 입력하세요."
)


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

        help_label = QLabel(APP_PW_HELP)
        help_label.setWordWrap(True)

        self.test_btn = QPushButton("테스트 메일 보내기")
        self.test_btn.clicked.connect(self._on_test_mail)
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_btn)
        test_row.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("저장")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addLayout(form)
        layout.addLayout(test_row)
        layout.addWidget(buttons)

    def _current_password(self) -> str | None:
        """입력칸에 새로 적었으면 그 값, 아니면 keyring에 저장된 값."""
        typed = self.pw_edit.text().strip()
        if typed:
            return typed
        user = self.gmail_edit.text().strip()
        return get_app_password(user) if user else None

    def _on_test_mail(self) -> None:
        user = self.gmail_edit.text().strip()
        recipient = self.recipient_edit.text().strip()
        password = self._current_password()
        if not user or not password:
            QMessageBox.warning(self, "설정 필요", "Gmail 주소와 앱 비밀번호를 입력하세요.")
            return
        try:
            send_test_mail(user, password, recipient)
        except Exception as exc:
            QMessageBox.critical(self, "발송 실패", f"테스트 메일 발송에 실패했습니다:\n{exc}")
            return
        QMessageBox.information(
            self, "발송 성공", f"테스트 메일을 보냈습니다.\n{recipient or user} 받은편지함을 확인하세요."
        )

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
