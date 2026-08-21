from cgvwatch.core.models import Watch, Status
from cgvwatch.core.detect import evaluate


def _watch(**kw):
    base = dict(id="1", mov_no="30001192", mov_nm="스파이더맨", site_no="0056",
                site_nm="강남", target_ymd="20260729")
    base.update(kw)
    return Watch(**base)


def test_evaluate_true_on_first_open():
    w = _watch(was_open=False)
    assert evaluate(w, {"20260729", "20260730"}) is True


def test_evaluate_false_when_target_not_open_yet():
    w = _watch(was_open=False)
    assert evaluate(w, {"20260801"}) is False


def test_evaluate_false_when_already_open_no_duplicate():
    w = _watch(was_open=True)
    assert evaluate(w, {"20260729"}) is False


def test_default_status_is_waiting():
    assert _watch().status == Status.WAITING
