"""BrowserManager의 생존 확인 로직을 검증한다.

실제 Playwright/브라우저는 전혀 띄우지 않는다. 대신 컨텍스트를 흉내 내는
간단한 스텁 클래스를 만들어 BrowserManager의 내부 속성(_context, _pw)에
직접 주입한다.
"""
from cgvwatch.hunt.browser import BrowserManager


class FakePage:
    def __init__(self):
        self.url = "about:blank"


class FakeContext:
    """실제 playwright.sync_api.BrowserContext를 흉내 내는 최소 스텁."""

    def __init__(self, pages=None):
        self.pages = pages if pages is not None else [FakePage()]
        self._close_handlers = []
        self.closed = False

    def on(self, event, handler):
        if event == "close":
            self._close_handlers.append(handler)

    def simulate_external_close(self):
        """사용자가 크롬 창을 직접 닫는 상황을 흉내 낸다."""
        self.closed = True
        self.pages = []
        for handler in self._close_handlers:
            handler(self)


class FakePlaywright:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def _manager(tmp_path) -> BrowserManager:
    return BrowserManager(tmp_path / "profile")


def test_is_running_true_when_context_has_pages(tmp_path):
    m = _manager(tmp_path)
    m._context = FakeContext(pages=[FakePage()])
    m._pw = FakePlaywright()

    assert m.is_running() is True


def test_is_running_false_when_context_closed_externally(tmp_path):
    """사용자가 크롬 창을 직접 닫으면 컨텍스트 객체는 남아 있어도 is_running()은 False."""
    m = _manager(tmp_path)
    context = FakeContext(pages=[FakePage()])
    pw = FakePlaywright()
    m._context = context
    m._pw = pw

    context.simulate_external_close()

    assert m.is_running() is False


def test_is_running_false_when_no_pages_open(tmp_path):
    """지속 컨텍스트에 열린 탭이 하나도 없으면 죽은 것으로 취급한다."""
    m = _manager(tmp_path)
    m._context = FakeContext(pages=[])
    m._pw = FakePlaywright()

    assert m.is_running() is False


def test_is_running_clears_internal_state_when_dead(tmp_path):
    """죽었다고 판정되면 다음 start()가 새로 띄울 수 있도록 내부 상태를 비운다."""
    m = _manager(tmp_path)
    context = FakeContext(pages=[])
    pw = FakePlaywright()
    m._context = context
    m._pw = pw

    assert m.is_running() is False
    assert m._context is None
    assert m._pw is None
    assert pw.stopped is True


def test_is_running_false_when_context_probe_raises(tmp_path):
    """pages 접근 자체가 예외를 던지는 경우(연결이 끊긴 경우)도 방어적으로 False를 돌려준다."""

    class ExplodingContext:
        @property
        def pages(self):
            raise RuntimeError("연결이 끊겼습니다")

    m = _manager(tmp_path)
    m._context = ExplodingContext()
    m._pw = FakePlaywright()

    assert m.is_running() is False
    assert m._context is None


def test_is_running_false_when_no_context(tmp_path):
    m = _manager(tmp_path)
    assert m.is_running() is False
