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
