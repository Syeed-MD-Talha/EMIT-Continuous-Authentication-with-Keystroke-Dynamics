import getpass
import re
from datetime import datetime

import numpy as np

from desktop import storage
from features import events_to_features
from model import fit_profile, score, tier

MIN_ATTEMPTS = 5
MAX_ATTEMPTS = 15
MIN_PASSWORD_LEN = 6
MAX_PASSWORD_LEN = 12
MAX_SUSPICIOUS_IN_ROW = 3
MAX_EMAIL_LEN = 100

# Continuous (free-typing) mode
WINDOW_SIZE = 200          # keystrokes per decision = one notification
ENROLL_STRIDE = 100        # overlapping windows give more training samples
MONITOR_STRIDE = 200       # non-overlapping: exactly one decision per 200 keys
IDLE_GAP = 2.0
FEATURE_VERSION = 3

# Multi-day enrollment campaign (continuous free typing only)
TRAINING_PERIOD_CHOICES = {1: "1 day", 3: "3 days"}
DEFAULT_TRAINING_DAYS = 1
CAMPAIGN_REQUIREMENTS = {
    1: {"min_keys": 2000, "min_windows": 10, "min_days": 1},
    3: {"min_keys": 6000, "min_windows": 30, "min_days": 2},
}
MAX_WINDOWS_PER_DAY = 100
CAMPAIGN_TICK_SECONDS = 60


def campaign_requirements(days: int) -> dict:
    if days not in CAMPAIGN_REQUIREMENTS:
        raise ValueError(f"unsupported training period: {days} days")
    return dict(CAMPAIGN_REQUIREMENTS[days])

EMAIL_RE = re.compile(r"[a-z0-9_%+-]+(\.[a-z0-9_%+-]+)*@([a-z0-9]+(-+[a-z0-9]+)*\.)+[a-z]{2,}")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def valid_email(value: str) -> bool:
    return len(value) <= MAX_EMAIL_LEN and EMAIL_RE.fullmatch(value) is not None


def default_email() -> str:
    """Profile name used when the user leaves the email field blank."""
    name = re.sub(r"[^a-z0-9_%+-]", "", getpass.getuser().lower()) or "user"
    return f"{name}@local.host"


def validate_attempt(events, bad: bool, expected_len: int | None = None):
    if bad:
        return None, "Backspace, Delete, or paste was used. Retype from the start."
    count = len(events)
    if count < MIN_PASSWORD_LEN:
        return None, f"Password too short: use at least {MIN_PASSWORD_LEN} characters."
    if count > MAX_PASSWORD_LEN:
        return None, f"Password too long: use at most {MAX_PASSWORD_LEN} characters."
    if expected_len is not None and count != expected_len:
        return None, f"Expected {expected_len} keys, got {count}. Attempt ignored."
    return events_to_features(events), None


class EnrollmentSession:
    def __init__(self, email: str):
        self.email = email
        self.rows: list[list[float]] = []
        self.password_len: int | None = None

    def add_attempt(self, events, bad: bool) -> tuple[bool, str | None]:
        if len(self.rows) >= MAX_ATTEMPTS:
            return False, f"Enrollment is full ({MAX_ATTEMPTS} attempts). Train or reset."
        features, error = validate_attempt(events, bad, self.password_len)
        if error is not None:
            return False, error
        if self.password_len is None:
            self.password_len = len(events)
        self.rows.append(features)
        return True, None

    def can_train(self) -> bool:
        return len(self.rows) >= MIN_ATTEMPTS and self.password_len is not None

    def reset(self) -> None:
        self.rows = []
        self.password_len = None


class AuthService:
    def __init__(self, db: storage.Database):
        self.db = db
        self._cache: dict[str, dict] = {}

    def save_profile(self, email: str, rows, password_len: int) -> None:
        self.db.save_profile(email, rows, password_len, mode="password")
        self._cache.pop(email, None)

    def save_continuous_profile(
        self, email: str, rows, window_size: int = WINDOW_SIZE
    ) -> None:
        self.db.save_profile(
            email,
            rows,
            0,
            mode="continuous",
            window_size=window_size,
            feature_version=FEATURE_VERSION,
        )
        self._cache.pop(email, None)

    def get_profile(self, email: str) -> dict:
        if email not in self._cache:
            record = self.db.load_profile_record(email)
            profile = fit_profile(np.asarray(record["features"], dtype=float))
            profile["password_len"] = record["password_len"]
            profile["mode"] = record["mode"]
            profile["window_size"] = record["window_size"]
            self._cache[email] = profile
        return self._cache[email]

    def evaluate(self, email: str, events, bad: bool):
        profile = self.get_profile(email)
        if profile.get("mode") == "continuous":
            return None, "This profile uses continuous mode. Start monitoring instead."
        features, error = validate_attempt(events, bad, profile["password_len"])
        if error is not None:
            return None, error
        value = score(profile, features)
        result = {
            "score": value,
            "tier": tier(value, profile),
            "t_susp": profile["t_susp"],
            "t_lock": profile["t_lock"],
        }
        return result, None


class LiveSession:
    def __init__(self, db: storage.Database, email: str):
        self.db = db
        self.email = email
        self.typist = "Genuine"
        self.tester = getpass.getuser()
        self.history: list[dict] = []
        self.suspicious_run = 0
        self.locked = False

    def record(self, result: dict) -> str:
        if self.locked:
            return "LOCKED"
        final_tier = result["tier"]
        if final_tier == "SUSPICIOUS":
            self.suspicious_run += 1
        else:
            self.suspicious_run = 0
        if final_tier == "SUSPICIOUS" and self.suspicious_run >= MAX_SUSPICIOUS_IN_ROW:
            final_tier = "LOCKED"
        if final_tier == "LOCKED":
            self.locked = True
        entry = {
            "score": result["score"],
            "tier": final_tier,
            "t_susp": result["t_susp"],
            "t_lock": result["t_lock"],
        }
        self.history.append(entry)
        self.db.log_attempt(
            datetime.now().isoformat(timespec="seconds"),
            self.email,
            self.typist,
            self.tester,
            len(self.history),
            round(result["score"], 4),
            final_tier,
            round(result["t_susp"], 4),
            round(result["t_lock"], 4),
        )
        return final_tier

    def reset(self) -> None:
        self.history = []
        self.suspicious_run = 0
        self.locked = False
