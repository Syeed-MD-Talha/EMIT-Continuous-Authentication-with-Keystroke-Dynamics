import os
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from desktop import auth
from desktop.enrollment import EnrollmentService
from desktop.storage import Database


class Clock:
    def __init__(self):
        self.current = datetime(2026, 1, 1, 9, 0, 0)

    def __call__(self):
        return self.current

    def advance(self, **kwargs):
        self.current += timedelta(**kwargs)


class FakeAuth:
    def __init__(self):
        self.saved = []

    def save_continuous_profile(self, email, rows, window_size=200):
        self.saved.append((email, rows, window_size))


class FakeCapture(QObject):
    keyCaptured = Signal(int, float, float)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def type_keys(capture, count, start=0.0):
    t = start
    for _ in range(count):
        capture.keyCaptured.emit(30, t, t + 75.0)
        t += 145.0
    return t


def make_service(db, auth_service, capture, clock):
    return EnrollmentService(db, auth_service, capture, now_fn=clock)


def test_start_validates_and_resumes(app, tmp_path):
    db = Database(tmp_path / "e.db")
    auth_service = FakeAuth()
    clock = Clock()
    service = make_service(db, auth_service, FakeCapture(), clock)

    ok, error = service.start("not-an-email", 1)
    assert ok is False
    assert error

    ok, error = service.start("u@e.com", 1)
    assert ok is True
    assert error is None
    assert service.active is True
    period_id = service.period["id"]

    resumed_capture = FakeCapture()
    resumed = make_service(db, auth_service, resumed_capture, clock)
    assert resumed.resume() is True
    assert resumed.active is True
    assert resumed.period["id"] == period_id
    db.close()


def test_deadline_extends_without_minimum(app, tmp_path):
    db = Database(tmp_path / "e.db")
    auth_service = FakeAuth()
    clock = Clock()
    capture = FakeCapture()
    service = make_service(db, auth_service, capture, clock)

    service.start("u@e.com", 1)
    type_keys(capture, 300)
    clock.advance(days=1, minutes=1)
    service.tick()

    assert service.active is True
    assert service.progress()["extended"] is True
    assert auth_service.saved == []
    assert db.list_users() == []
    db.close()


def test_trains_at_deadline_and_deletes_samples(app, tmp_path):
    db = Database(tmp_path / "e.db")
    auth_service = FakeAuth()
    clock = Clock()
    capture = FakeCapture()
    service = make_service(db, auth_service, capture, clock)

    service.start("u@e.com", 1)
    period_id = service.period["id"]
    type_keys(capture, auth.campaign_requirements(1)["min_keys"])
    assert db.load_enrollment_samples(period_id)

    clock.advance(days=1, minutes=1)
    service.tick()

    assert service.active is False
    assert len(auth_service.saved) == 1
    email, rows, window_size = auth_service.saved[0]
    assert email == "u@e.com"
    assert window_size == auth.WINDOW_SIZE
    assert len(rows) >= auth.campaign_requirements(1)["min_windows"]
    assert db.get_enrollment_period(period_id)["status"] == "completed"
    assert db.load_enrollment_samples(period_id) == []
    db.close()


def test_three_day_campaign_needs_two_days(app, tmp_path):
    db = Database(tmp_path / "e.db")
    auth_service = FakeAuth()
    clock = Clock()
    capture = FakeCapture()
    service = make_service(db, auth_service, capture, clock)

    service.start("u@e.com", 3)
    half = auth.campaign_requirements(3)["min_keys"] // 2
    type_keys(capture, half)
    clock.advance(days=1)
    type_keys(capture, half, start=half * 160.0)

    clock.advance(days=2, minutes=1)
    service.tick()

    assert service.active is False
    assert len(auth_service.saved) == 1
    assert len(auth_service.saved[0][1]) >= auth.campaign_requirements(3)["min_windows"]
    db.close()


def test_resume_finishes_expired_campaign(app, tmp_path):
    db = Database(tmp_path / "e.db")
    auth_service = FakeAuth()
    clock = Clock()
    first = make_service(db, auth_service, FakeCapture(), clock)
    first.start("u@e.com", 1)
    type_keys(first.capture, auth.campaign_requirements(1)["min_keys"])

    clock.advance(days=2)
    resumed = make_service(db, auth_service, FakeCapture(), clock)
    assert resumed.resume() is False
    assert resumed.active is False
    assert len(auth_service.saved) == 1
    db.close()


def test_cancel_deletes_samples(app, tmp_path):
    db = Database(tmp_path / "e.db")
    auth_service = FakeAuth()
    clock = Clock()
    capture = FakeCapture()
    service = make_service(db, auth_service, capture, clock)

    service.start("u@e.com", 1)
    period_id = service.period["id"]
    type_keys(capture, 400)
    assert db.load_enrollment_samples(period_id)

    service.cancel()
    assert service.active is False
    assert db.get_enrollment_period(period_id)["status"] == "cancelled"
    assert db.load_enrollment_samples(period_id) == []
    assert auth_service.saved == []
    db.close()


class FailingAuth(FakeAuth):
    def save_continuous_profile(self, email, rows, window_size=200):
        raise RuntimeError("model failed")


def test_training_failure_keeps_campaign_active(app, tmp_path):
    db = Database(tmp_path / "e.db")
    auth_service = FailingAuth()
    clock = Clock()
    capture = FakeCapture()
    service = make_service(db, auth_service, capture, clock)

    service.start("u@e.com", 1)
    type_keys(capture, auth.campaign_requirements(1)["min_keys"])
    failures = []
    service.periodFailed.connect(failures.append)

    clock.advance(days=1, minutes=1)
    service.tick()

    assert service.active is True
    assert failures and "model failed" in failures[0]
    assert db.get_active_enrollment_period() is not None
    db.close()
