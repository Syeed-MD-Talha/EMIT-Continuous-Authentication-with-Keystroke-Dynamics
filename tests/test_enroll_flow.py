import os
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from desktop import auth, storage
from desktop.capture import CaptureService
from desktop.enrollment import EnrollmentService
from desktop.monitor import BackgroundMonitor
from desktop.ui import enroll_page as ep_mod
from desktop.ui.main_window import MainWindow


class Clock:
    def __init__(self):
        self.current = datetime(2026, 1, 1, 9, 0, 0)

    def __call__(self):
        return self.current

    def advance(self, **kwargs):
        self.current += timedelta(**kwargs)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path):
    db = storage.Database(tmp_path / "s.db")
    svc = auth.AuthService(db)
    cap = CaptureService(window=auth.WINDOW_SIZE, stride=auth.MONITOR_STRIDE)
    clock = Clock()
    enrollment = EnrollmentService(db, svc, cap, now_fn=clock)
    mon = BackgroundMonitor(db, svc, cap)
    window = MainWindow(db, svc, cap, mon, enrollment)
    window._select(0)
    yield window.enroll_page, cap, db, mon, enrollment, clock
    db.close()


def type_keys(cap, count, start=0.0, rng=None):
    rng = rng or np.random.default_rng(0)
    t = start
    for _ in range(count):
        cap.keyCaptured.emit(30, t, t + 70 + rng.normal(0, 8))
        t += 140 + rng.normal(0, 15)
    return t


def test_starts_idle(page):
    enroll, cap, db, mon, enrollment, clock = page
    assert enroll._state == ep_mod.STATE_IDLE
    assert enroll.train_button.text() == "Start training"


def test_click_enters_collecting(page):
    enroll, cap, db, mon, enrollment, clock = page
    enroll._train()
    assert enrollment.active is True
    assert enroll._state == ep_mod.STATE_COLLECTING
    assert enroll.train_button.text() == "Stop training"
    assert "Day 1" in enroll.continuous_status.text()


def test_collecting_survives_page_hidden(page):
    enroll, cap, db, mon, enrollment, clock = page
    enroll._train()
    enroll.on_hidden()
    assert enrollment.active is True


def test_trains_at_deadline(page):
    enroll, cap, db, mon, enrollment, clock = page
    enroll._train()
    requirements = auth.campaign_requirements(1)
    type_keys(cap, requirements["min_keys"])

    assert enrollment.active is True
    assert db.list_users() == []
    assert enroll._state == ep_mod.STATE_COLLECTING

    clock.advance(days=1, minutes=1)
    enrollment.tick()

    assert enrollment.active is False
    assert db.list_users()
    assert enroll._state == ep_mod.STATE_READY
    assert "Training finished" in enroll.continuous_status.text()
    assert mon.active is True


def test_detection_runs_after_training(page):
    enroll, cap, db, mon, enrollment, clock = page
    enroll._train()
    t = type_keys(cap, auth.campaign_requirements(1)["min_keys"])
    clock.advance(days=1, minutes=1)
    enrollment.tick()

    decisions = []
    mon.decision.connect(decisions.append)
    type_keys(cap, auth.WINDOW_SIZE, start=t + 5000)
    assert len(decisions) == 1
    assert decisions[0]["tier"] in {"NORMAL", "SUSPICIOUS", "LOCKED"}


def test_three_day_campaign_waits_for_two_days_and_deadline(page):
    enroll, cap, db, mon, enrollment, clock = page
    index = enroll.period_combo.findData(3)
    enroll.period_combo.setCurrentIndex(index)
    enroll._train()
    requirements = auth.campaign_requirements(3)

    half = requirements["min_keys"] // 2
    type_keys(cap, half)
    clock.advance(days=1)
    type_keys(cap, half, start=half * 150.0)

    assert enrollment.active is True
    assert db.list_users() == []

    clock.advance(days=2, minutes=1)
    enrollment.tick()

    assert enrollment.active is False
    assert db.list_users()
    assert enroll._state == ep_mod.STATE_READY


def test_deadline_with_low_data_extends_then_trains(page):
    enroll, cap, db, mon, enrollment, clock = page
    enroll._train()
    type_keys(cap, 300)
    clock.advance(days=1, minutes=1)
    enrollment.tick()

    assert enrollment.active is True
    progress = enrollment.progress()
    assert progress["extended"] is True
    assert db.list_users() == []

    type_keys(cap, auth.campaign_requirements(1)["min_keys"], start=100000.0)
    enrollment.tick()
    assert enrollment.active is False
    assert db.list_users()


def test_stop_training_cancels(page):
    enroll, cap, db, mon, enrollment, clock = page
    enroll._train()
    type_keys(cap, 50)
    enroll._train()
    assert enrollment.active is False
    assert enroll._state == ep_mod.STATE_IDLE
    assert db.list_users() == []
