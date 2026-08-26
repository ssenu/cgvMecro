"""윈도우 알림 1회. 추가 설치 없이 PowerShell 내장 기능만 쓴다."""
from __future__ import annotations

import logging
import subprocess
from typing import Callable

logger = logging.getLogger(__name__)

_PS_TEMPLATE = (
    "[reflection.assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
    "$n = New-Object System.Windows.Forms.NotifyIcon; "
    "$n.Icon = [System.Drawing.SystemIcons]::Information; "
    "$n.BalloonTipTitle = '{title}'; "
    "$n.BalloonTipText = '{message}'; "
    "$n.Visible = $true; "
    "$n.ShowBalloonTip(10000); "
    "Start-Sleep -Seconds 10; "
    "$n.Dispose()"
)


def _escape(text: str) -> str:
    return text.replace("'", "''").replace("\n", " ")


def notify_desktop(title: str, message: str, runner: Callable = subprocess.run) -> None:
    """알림을 한 번 띄운다. 실패해도 예외를 밖으로 내보내지 않는다."""
    script = _PS_TEMPLATE.format(title=_escape(title), message=_escape(message))
    try:
        runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            timeout=15,
        )
    except Exception:
        logger.warning("윈도우 알림 실패 (무시하고 계속합니다)", exc_info=True)
