import pytest

from desktop import response


def test_actions_cover_all_values():
    values = [value for value, _ in response.ACTIONS]
    assert values == [
        response.ACTION_LOCK,
        response.ACTION_NOTIFY,
        response.ACTION_LOGOFF,
        response.ACTION_SHUTDOWN,
        response.ACTION_RESTART,
    ]


def test_lock_is_the_default_action():
    assert response.DEFAULT_ACTION == response.ACTION_LOCK
    assert response.ACTIONS[0][0] == response.ACTION_LOCK


def test_apply_notify_does_nothing():
    assert response.apply(response.ACTION_NOTIFY) is False
    assert response.apply(response.ACTION_NONE) is False
    assert response.apply("bogus") is False


def test_shutdown_uses_grace_period(monkeypatch):
    calls = []
    monkeypatch.setattr(response, "_run", lambda args: calls.append(args) or True)
    assert response.shutdown() is True
    assert calls[0][:4] == ["shutdown", "/s", "/t", str(response.GRACE_SECONDS)]


def test_restart_uses_grace_period(monkeypatch):
    calls = []
    monkeypatch.setattr(response, "_run", lambda args: calls.append(args) or True)
    assert response.restart() is True
    assert calls[0][:4] == ["shutdown", "/r", "/t", str(response.GRACE_SECONDS)]


def test_logoff_and_cancel(monkeypatch):
    calls = []
    monkeypatch.setattr(response, "_run", lambda args: calls.append(args) or True)
    response.logoff()
    response.cancel_pending()
    assert calls == [["shutdown", "/l"], ["shutdown", "/a"]]


def test_apply_dispatches(monkeypatch):
    calls = []
    monkeypatch.setattr(response, "_run", lambda args: calls.append(args) or True)
    assert response.apply(response.ACTION_SHUTDOWN) is True
    assert calls[0][1] == "/s"
