from unittest.mock import MagicMock

from cgvwatch.notify.desktop import notify_desktop


def test_notify_desktop_runs_powershell():
    runner = MagicMock()
    notify_desktop("좌석 확보", "H12 잡았습니다", runner=runner)
    args = runner.call_args[0][0]
    assert args[0] == "powershell"
    joined = " ".join(args)
    assert "좌석 확보" in joined
    assert "H12" in joined


def test_notify_desktop_swallows_errors():
    runner = MagicMock(side_effect=OSError("powershell 없음"))
    notify_desktop("제목", "내용", runner=runner)  # 예외가 나면 안 된다


def test_notify_desktop_swallows_bad_arguments():
    """제목·내용이 문자열이 아니어도 예외가 밖으로 나가면 안 된다."""
    runner = MagicMock()
    notify_desktop(None, None, runner=runner)  # 예외가 나면 실패
    runner.assert_not_called()
