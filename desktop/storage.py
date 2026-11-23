import json
import sqlite3
from pathlib import Path

from desktop import paths

LOG_COLUMNS = ["time", "user", "typist", "tester", "attempt", "score", "tier", "t_susp", "t_lock"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    email TEXT PRIMARY KEY,
    password_len INTEGER NOT NULL,
    features TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT, user TEXT, typist TEXT, tester TEXT, attempt INTEGER,
    score REAL, tier TEXT, t_susp REAL, t_lock REAL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollment_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'continuous',
    started_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    days INTEGER NOT NULL,
    keys_collected INTEGER NOT NULL DEFAULT 0,
    windows_collected INTEGER NOT NULL DEFAULT 0,
    min_keys INTEGER NOT NULL,
    min_windows INTEGER NOT NULL,
    min_days INTEGER NOT NULL DEFAULT 1,
    extended INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_enrollment_periods_status
    ON enrollment_periods(status, email);
CREATE TABLE IF NOT EXISTS enrollment_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    day TEXT NOT NULL,
    features TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_enrollment_samples_period
    ON enrollment_samples(period_id, id);
"""

PROFILE_MIGRATIONS = {
    "mode": "ALTER TABLE profiles ADD COLUMN mode TEXT NOT NULL DEFAULT 'password'",
    "window_size": "ALTER TABLE profiles ADD COLUMN window_size INTEGER",
    "feature_version": "ALTER TABLE profiles ADD COLUMN feature_version INTEGER",
}


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else paths.db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self.init_schema()

    def init_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(profiles)")}
        for name, statement in PROFILE_MIGRATIONS.items():
            if name not in columns:
                self._conn.execute(statement)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def save_profile(
        self,
        email: str,
        rows,
        password_len: int = 0,
        mode: str = "password",
        window_size: int | None = None,
        feature_version: int | None = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO profiles "
                "(email, password_len, features, mode, window_size, feature_version) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    email,
                    int(password_len or 0),
                    json.dumps(rows),
                    mode,
                    window_size,
                    feature_version,
                ),
            )

    def profile_exists(self, email: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM profiles WHERE email = ?", (email,)
        ).fetchone()
        return row is not None

    def list_users(self) -> list[str]:
        rows = self._conn.execute("SELECT email FROM profiles ORDER BY email").fetchall()
        return [row["email"] for row in rows]

    def load_profile_record(self, email: str) -> dict:
        row = self._conn.execute(
            "SELECT features, password_len, mode, window_size, feature_version "
            "FROM profiles WHERE email = ?",
            (email,),
        ).fetchone()
        if row is None:
            raise KeyError(email)
        return {
            "features": json.loads(row["features"]),
            "password_len": int(row["password_len"] or 0),
            "mode": row["mode"] or "password",
            "window_size": row["window_size"],
            "feature_version": row["feature_version"],
        }

    def load_enrollment(self, email: str) -> tuple[list, int]:
        record = self.load_profile_record(email)
        return record["features"], record["password_len"]

    def start_enrollment_period(
        self,
        email: str,
        days: int,
        started_at: str,
        ends_at: str,
        min_keys: int,
        min_windows: int,
        min_days: int = 1,
    ) -> int:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO enrollment_periods "
                "(email, mode, started_at, ends_at, status, days, "
                " min_keys, min_windows, min_days) "
                "VALUES (?, 'continuous', ?, ?, 'active', ?, ?, ?, ?)",
                (email, started_at, ends_at, days, min_keys, min_windows, min_days),
            )
        return int(cursor.lastrowid)

    def get_enrollment_period(self, period_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM enrollment_periods WHERE id = ?", (period_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def get_active_enrollment_period(self) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM enrollment_periods WHERE status = 'active' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row is not None else None

    def add_enrollment_samples(self, period_id: int, email: str, samples) -> int:
        """samples: iterable of (collected_at, day, features)."""
        rows = [
            (period_id, email, collected_at, day, json.dumps(features))
            for collected_at, day, features in samples
        ]
        if not rows:
            return 0
        with self._conn:
            self._conn.executemany(
                "INSERT INTO enrollment_samples "
                "(period_id, email, collected_at, day, features) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.execute(
                "UPDATE enrollment_periods "
                "SET windows_collected = windows_collected + ? WHERE id = ?",
                (len(rows), period_id),
            )
        return len(rows)

    def update_enrollment_keys(self, period_id: int, keys: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE enrollment_periods SET keys_collected = ? WHERE id = ?",
                (int(keys), period_id),
            )

    def load_enrollment_samples(self, period_id: int) -> list[list[float]]:
        rows = self._conn.execute(
            "SELECT features FROM enrollment_samples WHERE period_id = ? ORDER BY id",
            (period_id,),
        ).fetchall()
        return [json.loads(row["features"]) for row in rows]

    def enrollment_daily_counts(self, period_id: int) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT day, COUNT(*) AS count FROM enrollment_samples "
            "WHERE period_id = ? GROUP BY day ORDER BY day",
            (period_id,),
        ).fetchall()
        return {row["day"]: int(row["count"]) for row in rows}

    def enrollment_distinct_days(self, period_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT day) AS count FROM enrollment_samples "
            "WHERE period_id = ?",
            (period_id,),
        ).fetchone()
        return int(row["count"]) if row is not None else 0

    def finish_enrollment_period(self, period_id: int, completed_at: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE enrollment_periods SET status = 'completed', completed_at = ? "
                "WHERE id = ?",
                (completed_at, period_id),
            )

    def mark_enrollment_extended(self, period_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE enrollment_periods SET extended = 1 WHERE id = ?",
                (period_id,),
            )

    def cancel_enrollment_period(self, period_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM enrollment_samples WHERE period_id = ?", (period_id,)
            )
            self._conn.execute(
                "UPDATE enrollment_periods SET status = 'cancelled' WHERE id = ?",
                (period_id,),
            )

    def delete_enrollment_samples(self, period_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM enrollment_samples WHERE period_id = ?", (period_id,)
            )

    def log_attempt(self, *values) -> None:
        if len(values) != len(LOG_COLUMNS):
            raise ValueError(f"expected {len(LOG_COLUMNS)} values, got {len(values)}")
        placeholders = ", ".join("?" for _ in LOG_COLUMNS)
        with self._conn:
            self._conn.execute(
                f"INSERT INTO attempts ({', '.join(LOG_COLUMNS)}) VALUES ({placeholders})",
                values,
            )

    def fetch_attempts(self) -> list[dict]:
        rows = self._conn.execute(
            f"SELECT {', '.join(LOG_COLUMNS)} FROM attempts ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row is not None else default

    def set_setting(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
