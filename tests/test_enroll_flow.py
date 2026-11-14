import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from desktop import auth, storage
from desktop.capture import CaptureService
from desktop.monitor import BackgroundMonitor
from desktop.ui import enroll_page as ep_mod
from desktop.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path):
    db = storage.Database(tmp_path / "s.db")
    svc = auth.AuthService(db)
    cap = CaptureService(window=auth.WINDOW_SIZE, stride=auth.MONITOR_STRIDE)
    mon = BackgroundMonitor(db, svc, cap)
    window = MainWindow(db, svc, cap, mon)
    window._select(0)
    yield window.enroll_page, cap, db, mon
    db.close()


def type_keys(cap, count, start=0.0, rng=None):
    rng = rng or np.random.default_rng(0)
    t = start
    for _ in range(count):
        cap.keyCaptured.emit(30, t, t + 70 + rng.normal(0, 8))
        t += 140 + rng.normal(0, 15)
    return t


def wait(ms=700):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_starts_idle(page):
    enroll, cap, db, mon = page
    assert enroll._state == ep_mod.STATE_IDLE
    assert enroll.train_button.text() == "Start training"


def test_click_enters_collecting(page):
    enroll, cap, db, mon = page
    enroll._train()
    assert enroll._state == ep_mod.STATE_COLLECTING
    assert enroll.train_button.text() == "Stop training"
    assert "Collecting data" in enroll.continuous_status.text()


def test_collecting_survives_page_hidden(page):
    enroll, cap, db, mon = page
    enroll._train()
    enroll.on_hidden()
    assert enroll._collecting is True


def test_threshold_shows_training_then_ready(page):
    enroll, cap, db, mon = page
    enroll._train()
    type_keys(cap, auth.MIN_CONTINUOUS_KEYS)

    assert enroll._state == ep_mod.STATE_TRAINING
    assert enroll.train_button.text() == "Training..."
    assert "Training the model" in enroll.continuous_status.text()

    wait()
    assert enroll._state == ep_mod.STATE_READY
    assert "Training finished" in enroll.continuous_status.text()
    assert db.list_users()
    assert mon.active is True


def test_detection_runs_after_training(page):
    enroll, cap, db, mon = page
    enroll._train()
    t = type_keys(cap, auth.MIN_CONTINUOUS_KEYS)
    wait()

    decisions = []
    mon.decision.connect(decisions.append)
    type_keys(cap, auth.WINDOW_SIZE, start=t + 5000)
    assert len(decisions) == 1
    assert decisions[0]["tier"] in {"NORMAL", "SUSPICIOUS", "LOCKED"}


def test_stop_training_cancels(page):
    enroll, cap, db, mon = page
    enroll._train()
    type_keys(cap, 50)
    enroll._train()
    assert enroll._state == ep_mod.STATE_IDLE
    assert enroll._collecting is False
    assert db.list_users() == []
