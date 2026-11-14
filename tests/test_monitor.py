import numpy as np

from desktop import auth
from desktop.monitor import BackgroundMonitor


class FakeDB:
    def __init__(self, settings=None):
        self.rows = []
        self.settings = settings or {}

    def log_attempt(self, *values):
        self.rows.append(values)

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)


class FakeCapture:
    def __init__(self):
        self._slots = []

    class _Signal:
        def __init__(self):
            self._slots = []

        def connect(self, slot):
            self._slots.append(slot)

        def emit(self, *args):
            for slot in list(self._slots):
                slot(*args)

    @property
    def keyCaptured(self):
        if not hasattr(self, "_sig"):
            self._sig = self._Signal()
        return self._sig


class FakeAuth:
    def __init__(self, profile):
        self.profile = profile

    def get_profile(self, email):
        if email != "u@e.com":
            raise KeyError(email)
        return self.profile


class _IdentityScaler:
    def transform(self, X):
        return X


class _FixedModel:
    def __init__(self, value):
        self.value = value

    def decision_function(self, X):
        return np.full(len(X), self.value)


def make_profile(value, mode="continuous"):
    return {
        "scaler": _IdentityScaler(),
        "model": _FixedModel(value),
        "t_susp": -0.5,
        "t_lock": -2.0,
        "n_features": 30,
        "n_train": 40,
        "mode": mode,
        "password_len": 0,
        "window_size": auth.WINDOW_SIZE,
    }


def type_keys(capture, count, start=0.0, hold=80.0, gap=150.0):
    t = start
    for _ in range(count):
        capture.keyCaptured.emit(30, t, t + hold)
        t += gap
    return t


def test_one_decision_per_window():
    capture = FakeCapture()
    monitor = BackgroundMonitor(FakeDB(), FakeAuth(make_profile(0.5)), capture)
    assert monitor.set_profile("u@e.com")
    assert monitor.start()

    decisions = []
    monitor.decision.connect(decisions.append)

    type_keys(capture, auth.WINDOW_SIZE - 1)
    assert decisions == []

    type_keys(capture, 1, start=auth.WINDOW_SIZE * 150.0)
    assert len(decisions) == 1
    assert decisions[0]["tier"] == "NORMAL"

    type_keys(capture, auth.WINDOW_SIZE, start=auth.WINDOW_SIZE * 300.0)
    assert len(decisions) == 2


def test_rejects_password_profile():
    capture = FakeCapture()
    monitor = BackgroundMonitor(
        FakeDB(), FakeAuth(make_profile(0.5, mode="password")), capture
    )
    assert monitor.set_profile("u@e.com") is False
    assert monitor.session is None


def test_unknown_profile_returns_false():
    monitor = BackgroundMonitor(FakeDB(), FakeAuth(make_profile(0.5)), FakeCapture())
    assert monitor.set_profile("other@e.com") is False


def test_locks_and_stops_monitoring():
    capture = FakeCapture()
    monitor = BackgroundMonitor(FakeDB(), FakeAuth(make_profile(-1.0)), capture)
    monitor.set_profile("u@e.com")
    monitor.start()

    locked = []
    monitor.locked.connect(locked.append)

    type_keys(capture, auth.WINDOW_SIZE * 3)
    assert len(locked) == 1
    assert monitor.active is False


def test_does_not_score_when_stopped():
    capture = FakeCapture()
    monitor = BackgroundMonitor(FakeDB(), FakeAuth(make_profile(0.5)), capture)
    monitor.set_profile("u@e.com")

    decisions = []
    monitor.decision.connect(decisions.append)
    type_keys(capture, auth.WINDOW_SIZE * 2)
    assert decisions == []

def test_response_action_defaults_to_lock():
    capture = FakeCapture()
    db = FakeDB()
    monitor = BackgroundMonitor(db, FakeAuth(make_profile(-1.0)), capture)
    monitor.set_profile("u@e.com")
    monitor.start()

    import desktop.monitor as monitor_module

    calls = []
    original = monitor_module.response.apply
    monitor_module.response.apply = lambda action: calls.append(action) or False
    try:
        type_keys(capture, auth.WINDOW_SIZE * 3)
        assert calls == ["lock"]
    finally:
        monitor_module.response.apply = original


def test_response_action_uses_setting():
    capture = FakeCapture()
    db = FakeDB({"response_action": "shutdown"})
    monitor = BackgroundMonitor(db, FakeAuth(make_profile(-1.0)), capture)
    monitor.set_profile("u@e.com")
    monitor.start()

    import desktop.monitor as monitor_module

    calls = []
    original = monitor_module.response.apply
    monitor_module.response.apply = lambda action: calls.append(action) or False
    try:
        type_keys(capture, auth.WINDOW_SIZE * 3)
        assert calls == ["shutdown"]
    finally:
        monitor_module.response.apply = original
