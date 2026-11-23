from desktop.storage import Database


def test_profile_roundtrip(tmp_path):
    db = Database(tmp_path / "test.db")
    rows = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    db.save_profile("user@example.com", rows, 6)

    assert db.profile_exists("user@example.com")
    assert db.list_users() == ["user@example.com"]
    loaded, password_len = db.load_enrollment("user@example.com")
    assert loaded == rows
    assert password_len == 6
    db.close()


def test_attempt_log_roundtrip(tmp_path):
    db = Database(tmp_path / "test.db")
    db.log_attempt(
        "2026-01-01T00:00:00",
        "user@example.com",
        "Genuine",
        "tester",
        1,
        -0.5,
        "NORMAL",
        -1.0,
        -2.0,
    )
    rows = db.fetch_attempts()
    assert len(rows) == 1
    assert rows[0]["user"] == "user@example.com"
    assert rows[0]["score"] == -0.5
    assert rows[0]["tier"] == "NORMAL"
    db.close()


def test_settings_roundtrip(tmp_path):
    db = Database(tmp_path / "test.db")
    assert db.get_setting("autostart_enabled", "1") == "1"
    db.set_setting("autostart_enabled", "0")
    assert db.get_setting("autostart_enabled") == "0"
    db.set_setting("autostart_enabled", "1")
    assert db.get_setting("autostart_enabled") == "1"
    db.close()


def test_continuous_profile_roundtrip(tmp_path):
    db = Database(tmp_path / "test.db")
    db.save_profile(
        "c@example.com",
        [[0.1] * 30],
        0,
        mode="continuous",
        window_size=100,
        feature_version=2,
    )
    record = db.load_profile_record("c@example.com")
    assert record["mode"] == "continuous"
    assert record["window_size"] == 100
    assert record["feature_version"] == 2
    assert record["password_len"] == 0
    db.close()


def test_password_profile_defaults_to_password_mode(tmp_path):
    db = Database(tmp_path / "test.db")
    db.save_profile("p@example.com", [[1.0, 2.0]], 6)
    record = db.load_profile_record("p@example.com")
    assert record["mode"] == "password"
    assert record["password_len"] == 6
    db.close()


def test_enrollment_period_roundtrip(tmp_path):
    db = Database(tmp_path / "test.db")
    period_id = db.start_enrollment_period(
        "c@example.com",
        3,
        "2026-01-01T09:00:00",
        "2026-01-04T09:00:00",
        6000,
        30,
        min_days=2,
    )
    period = db.get_active_enrollment_period()
    assert period["id"] == period_id
    assert period["days"] == 3
    assert period["status"] == "active"

    db.update_enrollment_keys(period_id, 700)
    db.add_enrollment_samples(
        period_id,
        "c@example.com",
        [
            ("2026-01-01T10:00:00", "2026-01-01", [0.1] * 30),
            ("2026-01-01T11:00:00", "2026-01-01", [0.2] * 30),
            ("2026-01-02T10:00:00", "2026-01-02", [0.3] * 30),
        ],
    )

    period = db.get_enrollment_period(period_id)
    assert period["keys_collected"] == 700
    assert period["windows_collected"] == 3
    assert db.enrollment_daily_counts(period_id) == {
        "2026-01-01": 2,
        "2026-01-02": 1,
    }
    assert db.enrollment_distinct_days(period_id) == 2
    assert len(db.load_enrollment_samples(period_id)) == 3

    db.finish_enrollment_period(period_id, "2026-01-04T09:00:00")
    assert db.get_active_enrollment_period() is None
    assert db.get_enrollment_period(period_id)["status"] == "completed"

    db.delete_enrollment_samples(period_id)
    assert db.load_enrollment_samples(period_id) == []
    db.close()


def test_cancel_enrollment_period_deletes_samples(tmp_path):
    db = Database(tmp_path / "test.db")
    period_id = db.start_enrollment_period(
        "c@example.com", 1, "2026-01-01T09:00:00", "2026-01-02T09:00:00", 2000, 10
    )
    db.add_enrollment_samples(
        period_id,
        "c@example.com",
        [("2026-01-01T10:00:00", "2026-01-01", [0.1] * 30)],
    )

    db.cancel_enrollment_period(period_id)
    assert db.get_active_enrollment_period() is None
    assert db.get_enrollment_period(period_id)["status"] == "cancelled"
    assert db.load_enrollment_samples(period_id) == []
    db.close()
