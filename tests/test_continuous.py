import numpy as np

from desktop.continuous import ContinuousSession


class FakeDB:
    def __init__(self):
        self.rows = []

    def log_attempt(self, *values):
        self.rows.append(values)


class _IdentityScaler:
    def transform(self, X):
        return X


class _FixedModel:
    """Returns a constant decision score so tier logic is deterministic."""

    def __init__(self, value: float):
        self.value = value

    def decision_function(self, X):
        return np.full(len(X), self.value)


def make_profile(value: float) -> dict:
    return {
        "scaler": _IdentityScaler(),
        "model": _FixedModel(value),
        "t_susp": -0.5,
        "t_lock": -2.0,
        "n_features": 30,
        "n_train": 40,
    }


SUSPICIOUS_SCORE = -1.0
NORMAL_SCORE = 0.5
FEATURES = np.zeros(30)


def test_locks_after_consecutive_anomalies():
    db = FakeDB()
    session = ContinuousSession(
        db, "u@e.com", make_profile(SUSPICIOUS_SCORE), lock_after=3, alpha=1.0
    )
    tiers = [session.feed_features(FEATURES)["tier"] for _ in range(3)]
    assert tiers == ["SUSPICIOUS", "SUSPICIOUS", "LOCKED"]
    assert session.locked
    assert len(db.rows) == 3
    assert db.rows[-1][6] == "LOCKED"


def test_normal_window_resets_run():
    session = ContinuousSession(
        FakeDB(), "u@e.com", make_profile(SUSPICIOUS_SCORE), lock_after=3, alpha=1.0
    )
    session.feed_features(FEATURES)
    session.feed_features(FEATURES)
    assert session.suspicious_run == 2

    session.profile = make_profile(NORMAL_SCORE)
    session.feed_features(FEATURES)
    assert session.suspicious_run == 0
    assert not session.locked


def test_locked_session_ignores_further_windows():
    session = ContinuousSession(
        FakeDB(), "u@e.com", make_profile(SUSPICIOUS_SCORE), lock_after=1, alpha=1.0
    )
    session.feed_features(FEATURES)
    assert session.locked
    assert session.feed_features(FEATURES) is None


def test_ewma_smooths_scores():
    session = ContinuousSession(
        FakeDB(), "u@e.com", make_profile(NORMAL_SCORE), lock_after=99, alpha=0.5
    )
    first = session.feed_features(FEATURES)
    assert first["score"] == NORMAL_SCORE

    session.profile = make_profile(SUSPICIOUS_SCORE)
    second = session.feed_features(FEATURES)
    assert second["score"] == 0.5 * SUSPICIOUS_SCORE + 0.5 * NORMAL_SCORE


def test_reset_clears_state():
    session = ContinuousSession(
        FakeDB(), "u@e.com", make_profile(SUSPICIOUS_SCORE), lock_after=1, alpha=1.0
    )
    session.feed_features(FEATURES)
    assert session.locked
    session.reset()
    assert session.ewma is None
    assert session.suspicious_run == 0
    assert not session.locked
    assert session.history == []
