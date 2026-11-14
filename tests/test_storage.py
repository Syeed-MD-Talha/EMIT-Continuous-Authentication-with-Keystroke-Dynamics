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
