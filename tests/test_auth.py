import pytest

from desktop.auth import (
    AuthService,
    EnrollmentSession,
    LiveSession,
    MAX_ATTEMPTS,
    validate_attempt,
)
from desktop.storage import Database


def make_events(offset: float = 0.0, count: int = 6):
    base = 1000.0 + offset
    return [
        {
            "d": base + index * 130.0,
            "u": base + index * 130.0 + 75.0 + (index % 3) * 4.0,
        }
        for index in range(count)
    ]


class FakeDB:
    def __init__(self):
        self.rows = []

    def log_attempt(self, *values):
        self.rows.append(values)


def test_validate_attempt_rejects_bad_input():
    features, error = validate_attempt(make_events(), True)
    assert features is None
    assert error is not None

    features, error = validate_attempt(make_events(count=3), False)
    assert features is None
    assert "too short" in error

    features, error = validate_attempt(make_events(count=13), False)
    assert features is None
    assert "too long" in error

    features, error = validate_attempt(make_events(count=7), False, expected_len=6)
    assert features is None
    assert "Expected 6" in error


def test_enrollment_session_tracks_length_and_cap():
    session = EnrollmentSession("user@example.com")
    assert session.add_attempt(make_events(), False) == (True, None)
    assert session.password_len == 6

    ok, error = session.add_attempt(make_events(count=7), False)
    assert not ok
    assert "Expected 6" in error

    for _ in range(MAX_ATTEMPTS - 1):
        ok, error = session.add_attempt(make_events(), False)
        assert ok
        assert error is None

    ok, error = session.add_attempt(make_events(), False)
    assert not ok
    assert "full" in error
    assert session.can_train()


def test_live_session_locks_after_three_suspicious():
    db = FakeDB()
    session = LiveSession(db, "user@example.com")
    suspicious = {"score": -1.0, "tier": "SUSPICIOUS", "t_susp": -0.5, "t_lock": -2.0}

    assert session.record(suspicious) == "SUSPICIOUS"
    assert session.record(suspicious) == "SUSPICIOUS"
    assert session.record(suspicious) == "LOCKED"
    assert session.locked
    assert len(db.rows) == 3
    assert db.rows[-1][6] == "LOCKED"


def test_live_session_normal_resets_suspicious_run():
    db = FakeDB()
    session = LiveSession(db, "user@example.com")
    suspicious = {"score": -1.0, "tier": "SUSPICIOUS", "t_susp": -0.5, "t_lock": -2.0}
    normal = {"score": 0.5, "tier": "NORMAL", "t_susp": -0.5, "t_lock": -2.0}

    session.record(suspicious)
    session.record(suspicious)
    session.record(normal)
    session.record(suspicious)
    assert not session.locked

    session.reset()
    assert session.history == []
    assert session.suspicious_run == 0
    assert not session.locked


def test_auth_service_integration(tmp_path):
    db = Database(tmp_path / "test.db")
    rows = []
    for index in range(5):
        features, error = validate_attempt(make_events(offset=index * 3.0), False)
        assert error is None
        rows.append(features)
    db.save_profile("user@example.com", rows, 6)

    service = AuthService(db)
    profile = service.get_profile("user@example.com")
    assert profile["password_len"] == 6
    assert profile["n_features"] == len(rows[0])

    result, error = service.evaluate("user@example.com", make_events(offset=4.0), False)
    assert error is None
    assert result["tier"] in {"NORMAL", "SUSPICIOUS", "LOCKED"}
    assert isinstance(result["score"], float)

    result, error = service.evaluate("user@example.com", make_events(count=7), False)
    assert result is None
    assert "Expected 6" in error
    db.close()
